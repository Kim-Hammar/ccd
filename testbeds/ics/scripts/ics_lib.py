"""
Pure (docker-free) library for the ICS testbed: address plan, nominal closure
probability, the operator-intervention -> enactment mapping (``icsctl``), window
sampling + row assembly, the dataset schema, and the compose template. The ICS
analogue of ``testbed_lib.py`` / ``ran_lib.py``; deterministic and unit-tested
without docker (``tests/test_ics_lib.py``).

Topology (mirrors ``IcsSystem``): ``web`` (enterprise; state ``W``, reports integrity
``I``), ``scada`` (enterprise; offers commands ``C`` across the G2 gateway),
``control`` (enterprise + plant; receives ``Ctil``, forwards ``V = Chat*Ctil``), and
``process`` (plant; tep2py, reports pressure ``P`` and safety ``S``). Enactments
(``enactment_for``): ``G2`` is an iptables REJECT of the enterprise subnet at the
control server (also blocks the web->control lateral movement E2/E3); ``Chat`` and
``W`` are application modes (local control withholds ``V``; web safe-mode lowers ``I``).
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
    """Probability that some operator variable is degraded in a nominal window at
    relative demand ``demand_frac`` in [0, 1].

    The confounder (mirrors ``IcsSystem.generate_dataset``): degradations are likelier
    at low demand (0.30 at frac=0 down to 0.05 at frac=1), biasing the naive baseline.
    """
    frac = min(1.0, max(0.0, demand_frac))
    return float(_PCLOSE_HI - (_PCLOSE_HI - _PCLOSE_LO) * frac)


# --- operator intervention -> enactment mapping (icsctl) ----------------------
@dataclass(frozen=True)
class Enactment:
    """How to realize one operator assignment ``var = value`` on the live testbed:
    ``kind`` is ``"iptables"`` (G2: rules in the container's ``CCD`` chain) or
    ``"mode"`` (Chat/W: POST an application mode); ``rule_args``/``mode`` hold the
    corresponding payload (the other is empty)."""

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
    """The ``docker exec`` commands that enact the iptables-kind assignments of ``mode``
    (only ``G2``; ``Chat``/``W`` go through :func:`mode_settings`). Idempotent
    flush-and-readd of the control server's ``CCD`` chain, as in the other testbeds.
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
# Mirrors IcsSystem.generate_dataset: at most one operator variable degraded per window
# (mutually exclusive maintenance -> the joint degraded config never occurs nominally,
# so the naive baseline is undefined), degradations likelier at low demand (p_close),
# command magnitude scales with demand.
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
    configuration. ``pinned`` overrides the named variables -- used by Phi validation,
    where the enacted mode is held fixed while the rest keeps toggling nominally."""
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
# Measurement mapping (see README.md): C and G2 are the enacted config; W/I, Chat/Ctil/V,
# and P/S are read from the web, control, and process /metrics respectively.
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
    """Column order of the collected dataset D: observed causal variables, then
    metadata. Import-light (no ccd dependency); a unit test asserts the set equals
    ``IcsTestbedSystem().throughput_nodes``."""
    nodes = ["C", "Chat", "Ctil", "G2", "I", "P", "S", "V", "W"]
    return sorted(nodes) + METADATA_COLUMNS


# --- compose generation for the ICS topology ----------------------------------
def generate_compose() -> str:
    """Render ``docker-compose.yml`` for the ICS testbed (web + scada + control + process
    on an enterprise and a plant network); deterministic text, mirroring the other
    testbeds."""
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
