"""
Pure (docker-free) library for the 5G cloud-RAN testbed: address plan, nominal closure
probability, the operator-intervention -> enactment mapping (``ranctl``), the byte-counter
plan and window-row assembly of the collection engine, and the dataset schema. This is
the 5G analogue of ``testbeds/it_system/scripts/testbed_lib.py``.

Everything here is deterministic and unit-tested without docker
(``testbeds/5g_ran/tests/test_ran_lib.py``); the scripts that touch docker
(``ranctl.py``, ``testbed.py``, ``collection.py``) build on these primitives.

Topology (fixed 4 DUs / 4 CUs, mirroring ``FiveGSystem``):
  - DU_i (i=1..4): an ``srsdu`` container with a ZMQ virtual radio, paired with UE_i.
  - CU_j (j=1..4): an ``srscu`` container (F1 server to its DUs; N2/N3 to the core).
  - core: the Open5GS deployment; UE_i: an ``srsue`` container per DU.
  - DU_i attaches to CU_{AT_i} over F1 (nominal AT_i = i); reattachment restarts srsdu_i
    against the target CU's F1 address.
  - sink: the data-network endpoint behind the UPF terminating the per-class UDP flows
    (UL receiver / DL sender); xn / ric-nearrt / ric-nonrt: stub containers that make the
    Xn / E2 / A1 interface closures physically meaningful (as the IT testbed's mgmt_net
    does for A_i) until a real RIC lands.

Traffic plan: 5QI class-k traffic of DU_i rides UDP port ``flow_port(i, k)`` end to end
(UE_i <-> sink), so byte counters attribute load per (DU, class) by destination port
alone -- independent of the UPF's NAT and of the runtime-assigned PDU addresses.

The operator variables (X) map to concrete enactments (see ``enactments_for``):
  - ``QI_i`` (5QI admission threshold): iptables REJECT of the sub-threshold class ports
    before they enter the RAN -- at UE_i's egress for uplink and at the sink's egress for
    downlink; classes k < QI_i are dropped pre-radio in both directions.
  - ``Uu``   (radio): block every DU's ZMQ radio port pair.
  - ``NG_j`` (CU_j midhaul): block CU_j's N3 GTP-U (both directions, REJECT) and its N2
    NGAP (DROP). N2 uses DROP, not REJECT: an ICMP error aborts the SCTP association and
    tears down every UE context behind it, which a nominal-operations window could not
    reverse; DROP is a physical block that short closures survive.
  - ``N6``: block the UPF's data-network forwarding through ogstun (both directions).
  - ``Xn``/``E2``/``A1``: sever the corresponding stub endpoint (inter-CU / near-RT RIC /
    non-RT RIC).
  - ``AT_i`` (CU attachment): not an iptables rule -- a control-plane reattach of DU_i.
"""

from __future__ import annotations
import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Tuple

# --- topology constants -------------------------------------------------------
NUM_DU = 4
NUM_CU = 4
NUM_CLASSES = 10
ATTACKER_CLASSES = (1, 2, 3)

# --- address plan (bridge 10.53.1.0/24; matches compose-smoke.yml) ------------
RAN_SUBNET = "10.53.1.0/24"
AMF_IP = "10.53.1.2"
UPF_IP = "10.53.1.3"
SINK_IP = "10.53.1.250"
XN_IP = "10.53.1.251"
RIC_NEARRT_IP = "10.53.1.252"
RIC_NONRT_IP = "10.53.1.253"
PDU_SUBNET = "10.45.0.0/16"     # UE PDU addresses, assigned by the SMF in attach order
CORE_NGAP_PORT = 38412          # N2 (SCTP): CU -> AMF
CORE_GTPU_PORT = 2152           # N3 (UDP):  CU -> UPF
# F1-U (GTP-U DU<->CU): moved off 2152 so it does not collide with the CU's N3 GTP-U
# (also 2152) inside the same container.
F1U_PORT = 2153
ZMQ_TX_BASE = 2000              # DU_i radio ports: tx = 2000 + 10*i, rx = 2001 + 10*i
CLASS_PORT_BASE = 5000          # class-k traffic of DU_i on UDP port 5000 + 100*i + k

DU_IP_BASE = 20                 # DU_i / UE_i pair at 10.53.1.{20 + i} / {40 + i}
UE_IP_BASE = 40
CU_IP_BASE = 30                 # CU_j at 10.53.1.{30 + j}

# radio / cell parameters (the srsUE-compatible ZMQ settings proven by the smoke gate)
BASE_SRATE = "23.04e6"
DL_ARFCN = 368500               # band n3, 20 MHz, 15 kHz SCS
NR_BAND = 3
CHANNEL_BW_MHZ = 20
COMMON_SCS = 15
PLMN = "00101"
TAC = 7
IMSI_BASE = 1                   # UE_i IMSI = 00101_00000000{IMSI_BASE + i - 1}
UE_K = "00112233445566778899aabbccddeeff"
UE_OPC = "63BFA50EE6523365FF14C1F45F88737D"

UPF_CONTAINER = "ccd5g-upf"
SINK_CONTAINER = "ccd5g-sink"
XN_CONTAINER = "ccd5g-xn"
RIC_NEARRT_CONTAINER = "ccd5g-ric-nearrt"
RIC_NONRT_CONTAINER = "ccd5g-ric-nonrt"

_INTERFACE_VARS = ("Uu", "N6", "Xn", "E2", "A1")
_LINK_RE = re.compile(r"^(NG|QI|AT)(\d+)$")


def du_container(i: int) -> str:
    return f"ccd5g-du{i}"


def cu_container(j: int) -> str:
    return f"ccd5g-cu{j}"


def ue_container(i: int) -> str:
    return f"ccd5g-ue{i}"


def du_ip(i: int) -> str:
    return f"10.53.1.{DU_IP_BASE + i}"


def ue_ip(i: int) -> str:
    return f"10.53.1.{UE_IP_BASE + i}"


def cu_ip(j: int) -> str:
    return f"10.53.1.{CU_IP_BASE + j}"


def zmq_ports(i: int) -> Dict[str, int]:
    """The (gNB-side) tx/rx ZMQ ports of DU_i's virtual radio."""
    return {"tx": ZMQ_TX_BASE + 10 * i, "rx": ZMQ_TX_BASE + 1 + 10 * i}


def flow_port(i: int, k: int) -> int:
    """UDP port carrying DU_i's 5QI class-``k`` traffic (``L^{ik}``), UE_i <-> sink.

    Encoding both the DU and the class in the destination port lets every byte counter
    attribute traffic per (DU, class) without knowing the UEs' NAT-ed or runtime PDU
    addresses.
    """
    if not 1 <= i <= NUM_DU:
        raise ValueError(f"DU index out of range: {i}")
    if not 1 <= k <= NUM_CLASSES:
        raise ValueError(f"class k must be in [1, {NUM_CLASSES}], got {k}")
    return CLASS_PORT_BASE + 100 * i + k


# --- nominal-mode closure probability (the confounder) ------------------------
_PCLOSE_HI, _PCLOSE_LO = 0.30, 0.05


def p_close(demand_frac: float) -> float:
    """Probability an interface/NG link is closed in a nominal window at relative demand
    ``demand_frac`` in [0, 1].

    Mirrors ``FiveGSystem.generate_dataset``: operator degradations are more likely at
    low demand (0.30 at frac=0 down to 0.05 at frac=1), which confounds a closed link
    with low load and is what biases the naive baseline, motivating causal inference.
    """
    frac = min(1.0, max(0.0, demand_frac))
    return float(_PCLOSE_HI - (_PCLOSE_HI - _PCLOSE_LO) * frac)


# --- operator intervention -> enactment mapping (ranctl) ----------------------
@dataclass(frozen=True)
class Enactment:
    """How to realize one operator assignment ``var = value`` on the live RAN.

    ``kind`` is ``"iptables"`` (install rules in the container's ``CCD`` chain) or
    ``"reattach"`` (restart DU_i against a new CU -- a control-plane action, no chain
    rules). ``container`` is where the action applies; ``rule_args`` is the list of
    iptables argument strings (one per rule), empty for a reattach.
    """

    var: str
    value: int
    kind: str
    container: str
    rule_args: List[str]
    target_cu: int = 0            # for reattach: the CU DU_i attaches to


def enactments_for(var: str, value: int) -> List[Enactment]:
    """The enactments realizing ``do(var = value)`` for one operator variable.

    ``value`` is the *degraded* configuration ``D(var)`` from ``FiveGSystem``: 0 for
    interfaces/NG (close the link), 4 for ``QI_i`` (reject attacker classes 1-3), and the
    target CU index for ``AT_i``. A variable may map to several enactments (e.g. ``QI_i``
    filters uplink at UE_i and downlink at the sink; ``Uu`` blocks every DU's radio).
    """
    if var in _INTERFACE_VARS:
        if value != 0:
            raise ValueError(f"interface {var!r} only has degraded value 0, got {value}")
        return _interface_enactments(var)

    match = _LINK_RE.match(var)
    if match is None:
        raise ValueError(f"unknown operator variable: {var!r}")
    kind, idx = match.group(1), int(match.group(2))

    if kind == "NG":
        if not 1 <= idx <= NUM_CU:
            raise ValueError(f"NG index out of range: {var!r}")
        if value != 0:
            raise ValueError(f"NG{idx} only has degraded value 0, got {value}")
        # sever CU_j's midhaul: N3 GTP-U both directions (REJECT) + N2 NGAP (DROP -- see
        # the module docstring for why N2 must not REJECT).
        return [Enactment(
            var=var, value=value, kind="iptables", container=cu_container(idx),
            rule_args=[
                f"-p udp -d {UPF_IP} --dport {CORE_GTPU_PORT} -j REJECT",
                f"-p udp -s {UPF_IP} --dport {CORE_GTPU_PORT} -j REJECT",
                f"-p sctp -d {AMF_IP} --dport {CORE_NGAP_PORT} -j DROP",
                f"-p sctp -s {AMF_IP} -j DROP",
            ],
        )]
    if kind == "QI":
        if not 1 <= idx <= NUM_DU:
            raise ValueError(f"QI index out of range: {var!r}")
        # admission threshold: drop class-k flows with k < value before they enter the
        # RAN -- uplink at UE_i's egress, downlink at the sink's egress (the sink rule is
        # scoped to the PDU subnet so it never matches arriving uplink).
        ports = [flow_port(idx, k) for k in range(1, NUM_CLASSES + 1) if k < value]
        return [
            Enactment(
                var=var, value=value, kind="iptables", container=ue_container(idx),
                rule_args=[f"-p udp --dport {port} -j REJECT" for port in ports],
            ),
            Enactment(
                var=var, value=value, kind="iptables", container=SINK_CONTAINER,
                rule_args=[f"-p udp -d {PDU_SUBNET} --dport {port} -j REJECT" for port in ports],
            ),
        ]
    # kind == "AT": reattach DU_idx to CU_value
    if not 1 <= idx <= NUM_DU:
        raise ValueError(f"AT index out of range: {var!r}")
    if not 1 <= value <= NUM_CU:
        raise ValueError(f"AT{idx} target CU out of range: {value}")
    return [Enactment(
        var=var, value=value, kind="reattach", container=du_container(idx),
        rule_args=[], target_cu=value,
    )]


def _interface_enactments(var: str) -> List[Enactment]:
    """The rules that close one global interface link."""
    if var == "Uu":
        # block every DU's ZMQ radio port pair (the whole air interface). NOTE: never
        # toggled during nominal collection -- severing a ZMQ REQ/REP stream deadlocks
        # the radio until the DU+UE pair is recreated (see README).
        out = []
        for i in range(1, NUM_DU + 1):
            ports = zmq_ports(i)
            out.append(Enactment("Uu", 0, "iptables", du_container(i), [
                f"-p tcp -d {du_ip(i)} --dport {ports['tx']} -j REJECT",
                f"-p tcp -d {ue_ip(i)} --dport {ports['rx']} -j REJECT",
            ]))
        return out
    if var == "N6":
        # UPF data-network forwarding, both directions (rules live in the FORWARD hook)
        return [Enactment("N6", 0, "iptables", UPF_CONTAINER,
                          ["-i ogstun -j REJECT", "-o ogstun -j REJECT"])]
    if var == "Xn":
        return [Enactment("Xn", 0, "iptables", XN_CONTAINER, ["-j REJECT"])]
    if var == "E2":
        return [Enactment("E2", 0, "iptables", RIC_NEARRT_CONTAINER, ["-j REJECT"])]
    if var == "A1":
        return [Enactment("A1", 0, "iptables", RIC_NONRT_CONTAINER, ["-j REJECT"])]
    raise ValueError(f"unknown interface variable: {var!r}")


def controlled_containers() -> List[str]:
    """Every container that can carry ``CCD``-chain rules (all are flushed on sync)."""
    return (
        [cu_container(j) for j in range(1, NUM_CU + 1)]
        + [du_container(i) for i in range(1, NUM_DU + 1)]
        + [ue_container(i) for i in range(1, NUM_DU + 1)]
        + [UPF_CONTAINER, SINK_CONTAINER, XN_CONTAINER, RIC_NEARRT_CONTAINER, RIC_NONRT_CONTAINER]
    )


_CHAIN_HOOKS = ("INPUT", "OUTPUT", "FORWARD")


def _ensure_chain(chain: str, insert_first: bool) -> List[str]:
    """Shell fragments that idempotently create ``chain`` and hook it into the built-in
    chains. The ``CCD`` (filter) chain is inserted at position 1 so its REJECTs always
    precede the ``CCDC`` (counter) chain, which is appended."""
    parts = [f"iptables -N {chain} 2>/dev/null || true"]
    for hook in _CHAIN_HOOKS:
        add = f"iptables -I {hook} 1 -j {chain}" if insert_first else f"iptables -A {hook} -j {chain}"
        parts.append(f"iptables -C {hook} -j {chain} 2>/dev/null || {add}")
    return parts


def sync_commands(mode: Mapping[str, int]) -> List[List[str]]:
    """The ``docker exec`` commands that enact ``mode`` (an operator intervention D(X')).

    Only the iptables-kind variables produce chain commands here; ``AT_i`` reattachments
    are control-plane actions handled by ``ranctl.py``/``enact_mode.py`` (they restart a
    DU) and are returned separately by :func:`reattachments`. As in the IT testbed,
    synchronization is idempotent and complete: *every* controlled container's ``CCD``
    chain is created if missing, flushed, and re-added in one ``docker exec`` -- so
    reopening a link removes its rules without bookkeeping.
    """
    rules_by_container: Dict[str, List[str]] = {c: [] for c in controlled_containers()}
    for var in sorted(mode):
        if mode[var] == _nominal_value(var):
            continue                                   # unchanged from nominal: no rule
        for enact in enactments_for(var, mode[var]):
            if enact.kind != "iptables":
                continue
            rules_by_container[enact.container].extend(enact.rule_args)
    commands = []
    for container in sorted(rules_by_container):
        script = "; ".join(_ensure_chain("CCD", insert_first=True)
                           + ["iptables -F CCD"]
                           + [f"iptables -A CCD {args}" for args in rules_by_container[container]])
        commands.append(["docker", "exec", container, "sh", "-c", script])
    return commands


def reattachments(mode: Mapping[str, int]) -> List[Enactment]:
    """The DU reattachments in ``mode`` (``AT_i`` set to a non-nominal CU)."""
    out = []
    for var in sorted(mode):
        match = _LINK_RE.match(var)
        if match is not None and match.group(1) == "AT" and mode[var] != _nominal_value(var):
            out.extend(enactments_for(var, mode[var]))
    return out


def _nominal_value(var: str) -> int:
    """The nominal (non-degraded) value of an operator variable: interfaces/NG open = 1,
    QI_i admit-all = 1, AT_i attached to CU_i."""
    match = _LINK_RE.match(var)
    if match is not None and match.group(1) == "AT":
        return int(match.group(2))
    return 1


# --- byte-counter plan (the CCDC chain) ----------------------------------------
# Counters live in a per-container CCDC chain of RETURN rules (count-only). The chain is
# hooked after CCD, so rejected traffic is never counted. Keys are (destination, dport):
#   DU_i:  (cu_ip(j), F1U_PORT)          uplink F1-U bytes DU_i -> CU_j  (= Chat^{ij}_U)
#   UE_i:  (PDU_SUBNET, flow_port(i,k))  downlink class-k bytes delivered at UE_i (-> T^i_D)
#   sink:  (SINK_IP, flow_port(i,k))     uplink class-k bytes delivered at the sink (-> T^i_U)
#          (PDU_SUBNET, flow_port(i,k))  downlink class-k bytes admitted at the sink's
#                                        egress, post-QI filter (-> Cbar^i_D)
COUNT_CHAIN = "CCDC"
CounterKey = Tuple[str, int]


def count_rules(container: str) -> List[str]:
    """The CCDC counting rules (iptables argument strings) for ``container``."""
    for i in range(1, NUM_DU + 1):
        if container == du_container(i):
            return [f"-p udp -d {cu_ip(j)} --dport {F1U_PORT} -j RETURN"
                    for j in range(1, NUM_CU + 1)]
        if container == ue_container(i):
            return [f"-p udp -d {PDU_SUBNET} --dport {flow_port(i, k)} -j RETURN"
                    for k in range(1, NUM_CLASSES + 1)]
    if container == SINK_CONTAINER:
        rules = []
        for i in range(1, NUM_DU + 1):
            for k in range(1, NUM_CLASSES + 1):
                rules.append(f"-p udp -d {SINK_IP} --dport {flow_port(i, k)} -j RETURN")
                rules.append(f"-p udp -d {PDU_SUBNET} --dport {flow_port(i, k)} -j RETURN")
        return rules
    return []


def counter_containers() -> List[str]:
    """The containers that carry CCDC byte counters (snapshot targets)."""
    return ([du_container(i) for i in range(1, NUM_DU + 1)]
            + [ue_container(i) for i in range(1, NUM_DU + 1)]
            + [SINK_CONTAINER])


def count_setup_commands() -> List[List[str]]:
    """``docker exec`` commands installing the CCDC counting chains (idempotent; resets
    the counters, so run at setup time -- windows only ever use counter deltas)."""
    commands = []
    for container in counter_containers():
        script = "; ".join(_ensure_chain(COUNT_CHAIN, insert_first=False)
                           + [f"iptables -F {COUNT_CHAIN}"]
                           + [f"iptables -A {COUNT_CHAIN} {args}" for args in count_rules(container)])
        commands.append(["docker", "exec", container, "sh", "-c", script])
    return commands


def counter_read_command(container: str) -> List[str]:
    """The command whose output :func:`parse_counters` understands."""
    return ["docker", "exec", container, "iptables", "-nvx", "-L", COUNT_CHAIN]


def parse_counters(text: str) -> Dict[CounterKey, int]:
    """Parse ``iptables -nvx -L CCDC`` output into ``{(destination, dport): bytes}``."""
    out: Dict[CounterKey, int] = {}
    for line in text.splitlines():
        cols = line.split()
        if len(cols) < 9 or cols[2] != "RETURN":
            continue
        dport = None
        for token in cols[9:]:
            if token.startswith("dpt:"):
                dport = int(token[4:])
        if dport is None:
            continue
        key = (cols[8], dport)
        out[key] = out.get(key, 0) + int(cols[1])
    return out


# --- nominal window sampling (the collection DGP) ------------------------------
# Mirrors FiveGSystem.generate_dataset where physically possible: 5QI thresholds vary as
# regular ops, NG closures are confounded with demand via p_close, and the N6/Xn/E2/A1
# interfaces suffer rare outages. Two deliberate deviations from the simulator, both
# forced by the real radio: Uu stays open (blocking the ZMQ stream mid-run deadlocks the
# radio until the pair is recreated), and AT_i varies per collection *phase* rather than
# per window (a reattach is a DU+UE restart, ~30 s, not a per-window toggle).
P_QI_VARY = 0.5
P_IFACE_DOWN = 0.03
UL_MBPS_RANGE = (1.0, 3.0)      # per-DU total offered uplink, well under the ~5 Mbit/s radio
DL_MBPS_RANGE = (1.5, 6.0)      # per-DU total offered downlink
LOAD_JITTER = 0.2               # +/- multiplicative per-class jitter
PAYLOAD_BYTES = 1200            # UDP payload per datagram (fits every MTU incl. GTP-U)
DIRECTIONS = ("U", "D")


@dataclass
class WindowState:
    """The sampled nominal-operations configuration of one measurement window."""

    demand_frac: float
    qi: Dict[int, int]
    at: Dict[int, int]
    ng: Dict[int, int]
    ifaces: Dict[str, int]
    offered_mbps: Dict[str, Dict[Tuple[int, int], float]] = field(default_factory=dict)

    def mode(self) -> Dict[str, int]:
        """The full operator configuration as a variable -> value mapping."""
        out: Dict[str, int] = dict(self.ifaces)
        out.update({f"QI{i}": v for i, v in self.qi.items()})
        out.update({f"AT{i}": v for i, v in self.at.items()})
        out.update({f"NG{j}": v for j, v in self.ng.items()})
        return out


def sample_window_state(
    rng: random.Random,
    at_map: Mapping[int, int],
    pinned: Optional[Mapping[str, int]] = None,
) -> WindowState:
    """Sample one window's demand + nominal operator configuration.

    ``pinned`` (an enacted degraded mode) overrides the sampled values of the named
    variables -- used by Phi validation, where the mode is held fixed while demand and
    the other variables keep toggling nominally.
    """
    frac = rng.uniform(0.0, 1.0)
    p = p_close(frac)
    qi = {i: rng.randint(2, NUM_CLASSES) if rng.random() < P_QI_VARY else 1
          for i in range(1, NUM_DU + 1)}
    ng = {j: int(rng.random() >= p) for j in range(1, NUM_CU + 1)}
    ifaces = {"Uu": 1}      # pinned open: not physically togglable per window (see above)
    for var in ("N6", "Xn", "E2", "A1"):
        ifaces[var] = int(rng.random() >= P_IFACE_DOWN)
    offered: Dict[str, Dict[Tuple[int, int], float]] = {}
    for d, (lo, hi) in zip(DIRECTIONS, (UL_MBPS_RANGE, DL_MBPS_RANGE)):
        total = lo + frac * (hi - lo)
        offered[d] = {
            (i, k): total / NUM_CLASSES * rng.uniform(1.0 - LOAD_JITTER, 1.0 + LOAD_JITTER)
            for i in range(1, NUM_DU + 1) for k in range(1, NUM_CLASSES + 1)
        }
    state = WindowState(demand_frac=frac, qi=qi, at=dict(at_map), ng=ng, ifaces=ifaces,
                        offered_mbps=offered)
    for var, value in (pinned or {}).items():
        match = _LINK_RE.match(var)
        if var in _INTERFACE_VARS:
            state.ifaces[var] = int(value)
        elif match and match.group(1) == "QI":
            state.qi[int(match.group(2))] = int(value)
        elif match and match.group(1) == "AT":
            state.at[int(match.group(2))] = int(value)
        elif match and match.group(1) == "NG":
            state.ng[int(match.group(2))] = int(value)
        else:
            raise ValueError(f"cannot pin unknown operator variable: {var!r}")
    return state


# --- load-generator specs (consumed by udp_load.py inside the containers) ------
def ul_load_spec(i: int, state: WindowState, duration: float) -> Dict[str, object]:
    """The udp_load.py spec for UE_i's uplink flows (one per 5QI class, to the sink)."""
    flows = [{"id": f"{i}:{k}", "dst": SINK_IP, "port": flow_port(i, k),
              "mbps": state.offered_mbps["U"][(i, k)]}
             for k in range(1, NUM_CLASSES + 1)]
    return {"duration": duration, "payload_bytes": PAYLOAD_BYTES, "flows": flows}


def dl_load_spec(pdu_ips: Mapping[int, str], state: WindowState, duration: float) -> Dict[str, object]:
    """The udp_load.py spec for the sink's downlink flows (all DUs x classes)."""
    flows = []
    for i in range(1, NUM_DU + 1):
        for k in range(1, NUM_CLASSES + 1):
            flows.append({"id": f"{i}:{k}", "dst": pdu_ips[i], "port": flow_port(i, k),
                          "mbps": state.offered_mbps["D"][(i, k)]})
    return {"duration": duration, "payload_bytes": PAYLOAD_BYTES, "flows": flows}


# --- window-row assembly --------------------------------------------------------
# Measurement mapping (documented in README.md): L is measured at the load generators,
# T^i_U / T^i_D and the post-admission downlink load at the endpoint byte counters, and
# Chat^{ij}_U at DU_i's F1-U counters. Ladm applies the exact admission filter to the
# measured L; the downlink attachment split and both directions' midhaul products use
# the *known* F-tilde functions (per-DU attribution inside a CU's N3 tunnel would need
# GTP TEID inspection), which is also exactly what fit_scm assumes for them.
Snapshot = Mapping[str, Mapping[CounterKey, int]]      # container -> parsed CCDC counters


def _mbps(nbytes: float, duration: float) -> float:
    return float(nbytes) * 8.0 / duration / 1e6


def assemble_row(
    *,
    window: int,
    t_start: float,
    duration: float,
    state: WindowState,
    sent_bytes: Mapping[str, Mapping[str, float]],     # direction -> {"i:k": payload bytes}
    before: Snapshot,
    after: Snapshot,
) -> Optional[Dict[str, float]]:
    """Turn one window's loadgen reports + counter snapshots into a dataset row.

    Returns ``None`` if any counter went backwards (container restarted mid-window).
    All load/throughput columns are in Mbit/s.
    """
    deltas: Dict[str, Dict[CounterKey, int]] = {}
    for container in counter_containers():
        b, a = before.get(container, {}), after.get(container, {})
        delta: Dict[CounterKey, int] = {}
        for key, end in a.items():
            diff = end - b.get(key, 0)
            if diff < 0:
                return None
            delta[key] = diff
        deltas[container] = delta

    row: Dict[str, float] = {}
    uu = state.ifaces["Uu"]
    for i in range(1, NUM_DU + 1):
        for d in DIRECTIONS:
            loads = {}
            for k in range(1, NUM_CLASSES + 1):
                loads[k] = _mbps(float(sent_bytes[d].get(f"{i}:{k}", 0.0)), duration)
                row[f"L_{i}_{k}_{d}"] = loads[k]
            row[f"Ladm_{i}_{d}"] = uu * sum(v for k, v in loads.items() if k >= state.qi[i])

        # uplink: Chat measured at DU_i's F1-U counters; Cbar = their sum
        chat_u = {j: _mbps(deltas[du_container(i)].get((cu_ip(j), F1U_PORT), 0), duration)
                  for j in range(1, NUM_CU + 1)}
        row[f"Cbar_{i}_U"] = sum(chat_u.values())
        # downlink: post-admission carried load measured at the sink's egress counters
        row[f"Cbar_{i}_D"] = sum(
            _mbps(deltas[SINK_CONTAINER].get((PDU_SUBNET, flow_port(i, k)), 0), duration)
            for k in range(1, NUM_CLASSES + 1))

        for d in DIRECTIONS:
            c_total = 0.0
            for j in range(1, NUM_CU + 1):
                chat = chat_u[j] if d == "U" else \
                    (row[f"Cbar_{i}_D"] if state.at[i] == j else 0.0)
                row[f"Chat_{i}_{j}_{d}"] = chat
                ctil = state.ng[j] * chat                       # known midhaul product
                row[f"Ctil_{i}_{j}_{d}"] = ctil
                c_total += ctil
            row[f"C_{i}_{d}"] = c_total

        row[f"T_{i}_U"] = sum(
            _mbps(deltas[SINK_CONTAINER].get((SINK_IP, flow_port(i, k)), 0), duration)
            for k in range(1, NUM_CLASSES + 1))
        row[f"T_{i}_D"] = sum(
            _mbps(deltas[ue_container(i)].get((PDU_SUBNET, flow_port(i, k)), 0), duration)
            for k in range(1, NUM_CLASSES + 1))

    for var, value in state.mode().items():
        row[var] = float(value)
    row["window"] = float(window)
    row["t_start"] = t_start
    row["duration"] = duration
    row["demand"] = state.demand_frac
    return row


# --- dataset schema -----------------------------------------------------------
METADATA_COLUMNS = ["window", "t_start", "duration", "demand"]


def dataset_columns() -> List[str]:
    """Column order of the collected dataset D: the observed causal variables (sorted,
    matching ``FiveGTestbedSystem().throughput_nodes``) followed by metadata.

    Kept import-light (no ccd dependency) by reconstructing the throughput-node names
    from the same topology constants the model uses; a unit test asserts the set equals
    ``FiveGTestbedSystem().throughput_nodes``.
    """
    dus = range(1, NUM_DU + 1)
    cus = range(1, NUM_CU + 1)
    classes = range(1, NUM_CLASSES + 1)
    dirs = ("U", "D")
    nodes = set()
    for i in dus:
        for d in dirs:
            nodes.add(f"Ladm_{i}_{d}")
            nodes.add(f"Cbar_{i}_{d}")
            nodes.add(f"C_{i}_{d}")
            nodes.add(f"T_{i}_{d}")
            for k in classes:
                nodes.add(f"L_{i}_{k}_{d}")
            for j in cus:
                nodes.add(f"Chat_{i}_{j}_{d}")
                nodes.add(f"Ctil_{i}_{j}_{d}")
    operator = (
        set(_INTERFACE_VARS)
        | {f"QI{i}" for i in dus}
        | {f"AT{i}" for i in dus}
        | {f"NG{j}" for j in cus}
    )
    return sorted(nodes | operator) + METADATA_COLUMNS


# --- config + compose generation for the 4-DU/4-CU topology -------------------
def imsi(i: int) -> str:
    """IMSI of UE_i (one subscriber per DU)."""
    return f"{PLMN}{IMSI_BASE + i - 1:010d}"


def attachment_map(reattach: Mapping[int, int] | None = None) -> Dict[int, int]:
    """DU_i -> CU_j attachment. Nominal is the identity (DU_i on CU_i); ``reattach``
    overrides individual DUs (e.g. ``{3: 1}`` for D_1's ``AT3=1``)."""
    amap = {i: i for i in range(1, NUM_DU + 1)}
    if reattach:
        for i, j in reattach.items():
            if not (1 <= i <= NUM_DU and 1 <= j <= NUM_CU):
                raise ValueError(f"invalid reattach {i}->{j}")
            amap[i] = j
    return amap


_CU_ADDR_RE = re.compile(r"^\s*cu_cp_addr:\s*(\S+)", re.MULTILINE)


def parse_du_target_cu(du_config_text: str) -> int:
    """The CU index a rendered DU config attaches to (from its ``cu_cp_addr``)."""
    match = _CU_ADDR_RE.search(du_config_text)
    if match is None:
        raise ValueError("no cu_cp_addr in DU config")
    addr = match.group(1)
    for j in range(1, NUM_CU + 1):
        if cu_ip(j) == addr:
            return j
    raise ValueError(f"cu_cp_addr {addr!r} is not a CU address")


def render_cu_config(j: int) -> str:
    """srscu YAML for CU_j: NGAP to the AMF, F1AP server for its DUs (unique gnb_id)."""
    if not 1 <= j <= NUM_CU:
        raise ValueError(f"CU index out of range: {j}")
    ip = cu_ip(j)
    return "\n".join([
        "# GENERATED by generate_compose.py -- do not edit.",
        f"gnb_id: {j}",                           # top-level; unique per CU so the AMF distinguishes them
        "cu_cp:",
        "  amf:",
        f"    addr: {AMF_IP}",
        f"    bind_addr: {ip}",
        "    supported_tracking_areas:",
        f"      - tac: {TAC}",
        "        plmn_list:",
        f'          - plmn: "{PLMN}"',
        "            tai_slice_support_list:",
        "              - sst: 1",
        "  f1ap:",
        f"    bind_addr: {ip}",
        "cu_up:",
        "  ngu:",
        "    socket:",
        f"      - bind_addr: {ip}",               # N3 GTP-U to the UPF: pin to this CU's IP
        "  f1u:",
        f"    bind_port: {F1U_PORT}",             # off 2152 to avoid the N3 GTP-U clash
        f"    peer_port: {F1U_PORT}",
        "    socket:",
        f"      - bind_addr: {ip}",
        "log:",
        f"  filename: /tmp/cu{j}.log",
        "  all_level: info",
        "pcap:",
        "  ngap_enable: false",
        "",
    ])


def render_du_config(i: int, cu_j: int) -> str:
    """srsdu YAML for DU_i attached to CU_j: F1 to the CU, a ZMQ radio paired with UE_i,
    and the srsUE-compatible cell settings proven by the smoke gate."""
    if not 1 <= i <= NUM_DU:
        raise ValueError(f"DU index out of range: {i}")
    if not 1 <= cu_j <= NUM_CU:
        raise ValueError(f"CU index out of range: {cu_j}")
    ports = zmq_ports(i)
    device_args = (f"tx_port=tcp://{du_ip(i)}:{ports['tx']},"
                   f"rx_port=tcp://{ue_ip(i)}:{ports['rx']},base_srate={BASE_SRATE}")
    return "\n".join([
        "# GENERATED by generate_compose.py -- do not edit.",
        f"gnb_id: {cu_j}",                         # must equal the CU's gnb_id: a split gNB
        # (CU + its DUs) shares one gNB-ID, and the served cell's NR-CGI is checked against
        # it at F1 setup. On reattach DU_i's gnb_id follows its new CU.
        f"gnb_du_id: {i}",                        # unique per DU (a CU may serve several)
        "f1ap:",
        f"  cu_cp_addr: {cu_ip(cu_j)}",           # attach to CU_{AT_i}
        f"  bind_addr: {du_ip(i)}",
        "f1u:",
        f"  bind_port: {F1U_PORT}",               # match the CU's F1-U port
        f"  peer_port: {F1U_PORT}",
        "  socket:",
        f"    - bind_addr: {du_ip(i)}",
        "ru_sdr:",
        "  device_driver: zmq",
        f"  device_args: {device_args}",
        "  srate: 23.04",
        "  tx_gain: 75",
        "  rx_gain: 75",
        "cell_cfg:",
        f"  dl_arfcn: {DL_ARFCN}",
        f"  band: {NR_BAND}",
        f"  channel_bandwidth_MHz: {CHANNEL_BW_MHZ}",
        f"  common_scs: {COMMON_SCS}",
        f'  plmn: "{PLMN}"',
        f"  tac: {TAC}",
        f"  pci: {i}",                            # unique physical cell id per DU
        f"  sector_id: {i}",                      # unique NCI per DU: the NR-CGI is
        # (gnb_id, sector_id), and sector_id defaults to 0 for every single-cell DU --
        # without this, a CU rejects its second DU's F1 setup (Duplicate served cell CGI)
        "  pdcch:",
        "    common:",
        "      ss0_index: 0",
        "      coreset0_index: 12",
        "    dedicated:",
        "      ss2_type: common",
        "      dci_format_0_1_and_1_1: false",
        "  pdsch:",
        "    mcs_table: qam64",                   # 256QAM invalid with fallback DCI / common SS#2
        "  pusch:",
        "    mcs_table: qam64",
        "  prach:",
        "    prach_config_index: 1",
        "log:",
        f"  filename: /tmp/du{i}.log",
        "  all_level: info",
        "pcap:",
        "  mac_enable: false",
        "",
    ])


def render_ran_compose(at_map: Mapping[int, int]) -> str:
    """Render the RAN half of the compose (4 CU + 4 DU + 4 UE + sink + Xn/RIC stubs) on
    the shared ``ran`` network, mounting the generated per-node configs from ``./gen/``.
    Combined with ``compose-core.yml`` (same project ``ccd5g``, same network) via ``-f``.

    ``at_map`` is the DU->CU attachment (see :func:`attachment_map`); it only changes the
    ``depends_on`` wiring (each DU waits on its CU) -- the F1 target lives in the DU config.
    """
    lines = [
        "# GENERATED by generate_compose.py -- do not edit.",
        "name: ccd5g",
        "services:",
    ]
    for j in range(1, NUM_CU + 1):
        lines += [
            f"  cu{j}:",
            "    image: ccd-5g-gnb",
            f"    container_name: {cu_container(j)}",
            "    command: srscu -c /cu.yml",
            "    cap_add: [NET_ADMIN]",
            "    depends_on: [amf]",
            "    networks:",
            "      ran:",
            f"        ipv4_address: {cu_ip(j)}",
            "    volumes:",
            f"      - ./gen/cu{j}.yml:/cu.yml:ro",
        ]
    for i in range(1, NUM_DU + 1):
        lines += [
            f"  du{i}:",
            "    image: ccd-5g-gnb",
            f"    container_name: {du_container(i)}",
            "    command: srsdu -c /du.yml",
            "    cap_add: [NET_ADMIN]",
            f"    depends_on: [cu{at_map[i]}]",
            "    networks:",
            "      ran:",
            f"        ipv4_address: {du_ip(i)}",
            "    volumes:",
            f"      - ./gen/du{i}.yml:/du.yml:ro",
        ]
    for i in range(1, NUM_DU + 1):
        lines += [
            f"  ue{i}:",
            "    image: ccd-5g-srsue",
            f"    container_name: {ue_container(i)}",
            "    command: srsue /ue.conf",
            "    cap_add: [NET_ADMIN]",
            "    devices:",
            "      - /dev/net/tun",
            f"    depends_on: [du{i}]",
            "    networks:",
            "      ran:",
            f"        ipv4_address: {ue_ip(i)}",
            "    volumes:",
            f"      - ./gen/ue{i}.conf:/ue.conf:ro",
            "      - ../scripts/udp_load.py:/udp_load.py:ro",
        ]
    # the data-network sink + the Xn / RIC stub endpoints (see the module docstring)
    aux: List[Tuple[str, str, str, List[str]]] = [
        ("sink", SINK_CONTAINER, SINK_IP, ["      - ../scripts/udp_load.py:/udp_load.py:ro"]),
        ("xn", XN_CONTAINER, XN_IP, []),
        ("ric-nearrt", RIC_NEARRT_CONTAINER, RIC_NEARRT_IP, []),
        ("ric-nonrt", RIC_NONRT_CONTAINER, RIC_NONRT_IP, []),
    ]
    for name, container, ip, extra in aux:
        lines += [
            f"  {name}:",
            "    image: ccd-5g-sink",
            f"    container_name: {container}",
            "    command: sleep infinity",
            "    cap_add: [NET_ADMIN]",
            "    networks:",
            "      ran:",
            f"        ipv4_address: {ip}",
        ]
        if extra:
            lines += ["    volumes:"] + extra
    lines.append("")
    return "\n".join(lines)


def render_ue_config(i: int) -> str:
    """srsUE .conf for UE_i: ZMQ paired with DU_i, unique soft-SIM (IMSI per DU)."""
    if not 1 <= i <= NUM_DU:
        raise ValueError(f"UE index out of range: {i}")
    ports = zmq_ports(i)
    device_args = (f"tx_port=tcp://{ue_ip(i)}:{ports['rx']},"
                   f"rx_port=tcp://{du_ip(i)}:{ports['tx']},base_srate={BASE_SRATE}")
    return "\n".join([
        "# GENERATED by generate_compose.py -- do not edit.",
        "[rf]",
        "freq_offset = 0",
        "tx_gain = 75",
        "rx_gain = 40",
        f"srate = {BASE_SRATE}",
        "nof_antennas = 1",
        "device_name = zmq",
        f"device_args = {device_args}",
        "",
        "[rat.eutra]",
        "dl_earfcn = 2850",
        "nof_carriers = 0",
        "",
        "[rat.nr]",
        f"bands = {NR_BAND}",
        "nof_carriers = 1",
        "max_nof_prb = 106",
        "nof_prb = 106",
        "",
        "[pcap]",
        "enable = none",
        "",
        "[log]",
        "all_level = info",
        f"filename = /tmp/ue{i}.log",
        "file_max_size = -1",
        "",
        "[usim]",
        "mode = soft",
        "algo = milenage",
        f"opc  = {UE_OPC}",
        f"k    = {UE_K}",
        f"imsi = {imsi(i)}",
        "imei = 353490069873319",
        "",
        "[rrc]",
        "release = 15",
        "ue_category = 4",
        "",
        "[nas]",
        "apn = internet",
        "apn_protocol = ipv4",
        "",
        "[gw]",
        "netns =",
        "",
        "[gui]",
        "enable = false",
        "",
    ])
