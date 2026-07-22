"""
Pure (docker-free) library for the industrial control system (ICS) testbed: address plan,
nominal closure probability, the operator-intervention -> enactment mapping (``icsctl``),
the nominal window sampling + row assembly, the dataset schema, and the compose template.
This is the ICS analogue of ``testbeds/it_system/scripts/testbed_lib.py`` and
``testbeds/5g_ran/scripts/ran_lib.py``.

Everything here is deterministic and unit-tested without docker
(``testbeds/ics/tests/test_ics_lib.py``); the scripts that touch docker (``icsctl.py``,
``testbed.py``, ``collection.py``) build on these primitives.

Topology (mirrors ``IcsSystem`` -- see docs/graphs.png panel c):
  - ``web`` (enterprise net): the enterprise web server. Its state ``W`` (up / safe mode)
    is an application setting; it reports web integrity ``I``.
  - ``scada`` (enterprise net): the SCADA command client. It issues supervisory setpoint
    commands ``C`` toward the control server, across the G2 gateway.
  - ``control`` (enterprise + plant nets): the supervisory control server. It receives the
    commands (``Ctil`` = the command that crossed the gateway) and, in remote-control mode,
    forwards the valve setpoint (``V = Chat*Ctil``) to the process.
  - ``process`` (plant net): the Tennessee Eastman process (``tep2py``). It applies the
    valve setpoint and reports the process state ``P`` (reactor pressure) and safety ``S``.

The operator variables (X) map to concrete enactments (see ``enactment_for``):
  - ``G2`` (gateway availability): iptables REJECT of the enterprise subnet at the control
    server -- the command never reaches the supervisory net (``Ctil = 0``), which also
    blocks the web->control lateral movement (attack-graph exploits E2, E3).
  - ``Chat`` (control mode): an application setting on the control server -- ``local`` mode
    withholds remote commands from the valves (``V = 0``); ``remote`` mode forwards them.
  - ``W`` (web-server state): an application setting on the web server -- ``safe`` mode
    serves a reduced read-only app (lower integrity ``I``); ``up`` mode serves the full app.
"""

from __future__ import annotations
import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

# --- operator variables (mirror IcsSystem.operator_controlled) ----------------
OPERATOR_VARS = ("W", "G2", "Chat")

# --- address plan (bridge 172.31.x.0/24) --------------------------------------
ENTERPRISE_SUBNET = "172.31.1.0/24"
PLANT_SUBNET = "172.31.2.0/24"
WEB_IP = "172.31.1.11"
SCADA_IP = "172.31.1.12"
CONTROL_ENTERPRISE_IP = "172.31.1.13"       # control server, enterprise-facing (command ingress)
CONTROL_PLANT_IP = "172.31.2.13"            # control server, plant-facing (to the process)
PROCESS_IP = "172.31.2.14"

WEB_CONTAINER = "ccd-ics-web"
SCADA_CONTAINER = "ccd-ics-scada"
CONTROL_CONTAINER = "ccd-ics-control"
PROCESS_CONTAINER = "ccd-ics-process"

APP_PORT = 8080                             # every service serves /metrics, /admin, ... here
WEB_HOST_PORT = 8091
CONTROL_HOST_PORT = 8092
PROCESS_HOST_PORT = 8093
COMMAND_PATH = "/command"                   # scada -> control setpoint ingress

_LINK_RE = re.compile(r"^(W|G2|Chat)$")


def container_for(var: str) -> str:
    """The container whose state realizes operator variable ``var``."""
    if var == "W":
        return WEB_CONTAINER
    if var in ("G2", "Chat"):
        return CONTROL_CONTAINER
    raise ValueError(f"unknown operator variable: {var!r}")


# --- nominal-mode closure probability (the confounder) ------------------------
_PCLOSE_HI, _PCLOSE_LO = 0.30, 0.05


def p_close(demand_frac: float) -> float:
    """Probability that *some* operator variable is in its degraded state in a nominal
    window at relative demand ``demand_frac`` in [0, 1].

    Mirrors ``IcsSystem.generate_dataset``: operator degradations (web safe-mode, gateway
    closed, local control) are more likely at low demand (0.30 at frac=0 down to 0.05 at
    frac=1), which confounds a degradation with low demand and is what biases the naive
    baseline, motivating causal inference.
    """
    frac = min(1.0, max(0.0, demand_frac))
    return float(_PCLOSE_HI - (_PCLOSE_HI - _PCLOSE_LO) * frac)


# --- operator intervention -> enactment mapping (icsctl) ----------------------
@dataclass(frozen=True)
class Enactment:
    """How to realize one operator assignment ``var = value`` on the live testbed.

    ``kind`` is ``"iptables"`` (install a REJECT rule in the container's ``CCD`` chain,
    for ``G2``) or ``"mode"`` (POST an application mode to a container, for ``Chat``/``W``).
    ``container`` is where the action applies; ``rule_args`` holds the iptables argument
    strings (empty for a mode change); ``mode`` is the application mode name (empty for
    iptables).
    """

    var: str
    value: int
    kind: str
    container: str
    rule_args: List[str] = field(default_factory=list)
    mode: str = ""


def enactment_for(var: str, value: int) -> Enactment:
    """The enactment realizing ``do(var = value)`` for one operator variable.

    ``value`` is the degraded configuration ``D(var)`` from ``IcsSystem`` (0 for every ICS
    operator variable) or the nominal value 1.
    """
    if _LINK_RE.match(var) is None:
        raise ValueError(f"unknown operator variable: {var!r}")
    if value not in (0, 1):
        raise ValueError(f"operator variable {var!r} is binary, got {value}")

    if var == "G2":
        # seal the supervisory net: reject the enterprise subnet at the control server, so
        # commands never arrive (Ctil = 0) and web->control lateral movement is blocked.
        rules = [f"-s {ENTERPRISE_SUBNET} -j REJECT"] if value == 0 else []
        return Enactment(var=var, value=value, kind="iptables",
                         container=CONTROL_CONTAINER, rule_args=rules)
    if var == "Chat":
        # control mode: local (0) withholds remote commands from the valves, remote (1)
        # forwards them.
        return Enactment(var=var, value=value, kind="mode",
                         container=CONTROL_CONTAINER, mode="remote" if value == 1 else "local")
    # var == "W": web-server state -- up (1) full app, safe (0) reduced read-only app.
    return Enactment(var=var, value=value, kind="mode",
                     container=WEB_CONTAINER, mode="up" if value == 1 else "safe")


def _nominal_value(_var: str) -> int:
    """The nominal (non-degraded) value of an operator variable: all are open/up = 1."""
    return 1


def sync_commands(mode: Mapping[str, int]) -> List[List[str]]:
    """The ``docker exec`` commands that enact the iptables-kind assignments of ``mode``.

    Only ``G2`` is iptables-kind; ``Chat``/``W`` are application modes handled separately
    by :func:`mode_settings`. As in the other testbeds, the control server's ``CCD`` chain
    is flushed and re-added in one ``docker exec`` so synchronization is idempotent (a
    reopened gateway simply re-adds an empty chain).
    """
    rules_by_container: Dict[str, List[str]] = {CONTROL_CONTAINER: []}
    for var in sorted(mode):
        enact = enactment_for(var, mode[var])
        if enact.kind == "iptables":
            rules_by_container.setdefault(enact.container, []).extend(enact.rule_args)
    commands = []
    for container in sorted(rules_by_container):
        script = "; ".join(["iptables -F CCD"]
                           + [f"iptables -A CCD {args}" for args in rules_by_container[container]])
        commands.append(["docker", "exec", container, "sh", "-c", script])
    return commands


def mode_settings(mode: Mapping[str, int]) -> List[Enactment]:
    """The application-mode enactments (``Chat``, ``W``) in ``mode``, in a stable order."""
    out = []
    for var in ("W", "Chat"):
        if var in mode:
            enact = enactment_for(var, mode[var])
            if enact.kind == "mode":
                out.append(enact)
    return out


# --- nominal window sampling (the collection DGP) ------------------------------
# Mirrors IcsSystem.generate_dataset: at most one operator variable is degraded per window
# (mutually exclusive maintenance), degradations are more likely at low demand via
# ``p_close`` (the confounder), and the supervisory command magnitude scales with demand.
# The mutual exclusion means the joint degraded config do(W=0,G2=0,Chat=0) never occurs in
# nominal data, so the naive baseline is undefined and causal identification is required.
_CMD_GAIN = 40.0                    # command magnitude per unit demand (matches the simulator)
_CMD_SD = 3.0
_D_LOW, _D_HIGH = 0.5, 1.5


@dataclass
class WindowState:
    """The sampled nominal-operations configuration of one measurement window."""

    demand_frac: float
    command: float                  # supervisory setpoint magnitude C offered this window
    operator: Dict[str, int]        # W, G2, Chat in {0, 1}

    def mode(self) -> Dict[str, int]:
        return dict(self.operator)


def sample_window_state(
    rng: random.Random,
    pinned: Optional[Mapping[str, int]] = None,
) -> WindowState:
    """Sample one window's demand, command magnitude, and (mutually exclusive) operator
    configuration.

    ``pinned`` (an enacted degraded mode) overrides the sampled values of the named
    operator variables -- used by Phi validation, where the mode is held fixed while demand
    and the other variables keep toggling nominally.
    """
    frac = rng.uniform(0.0, 1.0)
    demand = _D_LOW + frac * (_D_HIGH - _D_LOW)
    command = max(0.0, _CMD_GAIN * demand + rng.gauss(0.0, _CMD_SD))

    operator = {var: 1 for var in OPERATOR_VARS}
    if rng.random() < p_close(frac):
        operator[rng.choice(OPERATOR_VARS)] = 0        # one mutually-exclusive maintenance action
    for var, value in (pinned or {}).items():
        if var not in OPERATOR_VARS:
            raise ValueError(f"cannot pin unknown operator variable: {var!r}")
        operator[var] = int(value)
    return WindowState(demand_frac=frac, command=command, operator=operator)


# --- window-row assembly --------------------------------------------------------
# Measurement mapping (documented in README.md):
#   C    = the setpoint magnitude offered by the SCADA client this window (known);
#   G2   = the enacted gateway state (known: firewall rule present or not);
#   W, I = read from the web server's /metrics (web state + integrity);
#   Chat, Ctil, V = read from the control server's /metrics (mode, received command that
#          crossed the gateway, and forwarded valve setpoint);
#   P, S = read from the process's /metrics (reactor pressure + safety margin).
Metrics = Mapping[str, float]      # one service's parsed /metrics JSON


def assemble_row(
    *,
    window: int,
    t_start: float,
    duration: float,
    state: WindowState,
    web_metrics: Metrics,
    control_metrics: Metrics,
    process_metrics: Metrics,
) -> Dict[str, float]:
    """Turn one window's enacted config + service /metrics into a dataset row."""
    row: Dict[str, float] = {
        "W": float(web_metrics["W"]),
        "I": float(web_metrics["I"]),
        "G2": float(state.operator["G2"]),
        "Chat": float(control_metrics["Chat"]),
        "C": float(state.command),
        "Ctil": float(control_metrics["Ctil"]),
        "V": float(control_metrics["V"]),
        "P": float(process_metrics["P"]),
        "S": float(process_metrics["S"]),
        "window": float(window),
        "t_start": t_start,
        "duration": duration,
        "demand": state.demand_frac,
    }
    return row


# --- dataset schema -----------------------------------------------------------
METADATA_COLUMNS = ["window", "t_start", "duration", "demand"]


def dataset_columns() -> List[str]:
    """Column order of the collected dataset D: the observed causal variables (sorted,
    matching ``IcsTestbedSystem().throughput_nodes``) followed by metadata.

    Kept import-light (no ccd dependency); a unit test asserts the set equals
    ``IcsTestbedSystem().throughput_nodes``.
    """
    nodes = ["C", "Chat", "Ctil", "G2", "I", "P", "S", "V", "W"]
    return sorted(nodes) + METADATA_COLUMNS


# --- compose generation for the ICS topology ----------------------------------
def generate_compose() -> str:
    """Render ``docker-compose.yml`` for the ICS testbed (web + scada + control + process
    on an enterprise and a plant network). Deterministic text (not a YAML library), with a
    generated-file banner, mirroring the other testbeds."""
    lines = [
        "# GENERATED by generate_compose.py -- do not edit.",
        "name: ccd-ics",
        "services:",
        "  web:",
        "    build: ./web",
        f"    container_name: {WEB_CONTAINER}",
        "    networks:",
        f"      enterprise: {{ipv4_address: {WEB_IP}}}",
        "    ports:",
        f"      - {WEB_HOST_PORT}:{APP_PORT}",
        "  scada:",
        "    build: ./scada",
        f"    container_name: {SCADA_CONTAINER}",
        "    command: sleep infinity",
        "    networks:",
        f"      enterprise: {{ipv4_address: {SCADA_IP}}}",
        "  control:",
        "    build: ./control",
        f"    container_name: {CONTROL_CONTAINER}",
        "    cap_add: [NET_ADMIN]",
        f"    environment: {{PROCESS_URL: 'http://{PROCESS_IP}:{APP_PORT}'}}",
        "    depends_on: [process]",
        "    networks:",
        f"      enterprise: {{ipv4_address: {CONTROL_ENTERPRISE_IP}}}",
        f"      plant: {{ipv4_address: {CONTROL_PLANT_IP}}}",
        "    ports:",
        f"      - {CONTROL_HOST_PORT}:{APP_PORT}",
        "  process:",
        "    build: ./process",
        f"    container_name: {PROCESS_CONTAINER}",
        "    networks:",
        f"      plant: {{ipv4_address: {PROCESS_IP}}}",
        "    ports:",
        f"      - {PROCESS_HOST_PORT}:{APP_PORT}",
        "networks:",
        "  enterprise:",
        "    ipam:",
        f"      config: [{{subnet: {ENTERPRISE_SUBNET}}}]",
        "  plant:",
        "    ipam:",
        f"      config: [{{subnet: {PLANT_SUBNET}}}]",
        "",
    ]
    return "\n".join(lines)
