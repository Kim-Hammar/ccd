"""
Pure (docker-free) library for the 5G cloud-RAN testbed: address plan, nominal closure
probability, the operator-intervention -> enactment mapping (``ranctl``), and the dataset
schema. This is the 5G analogue of ``testbeds/it_system/scripts/testbed_lib.py``.

Everything here is deterministic and unit-tested without docker
(``testbeds/5g_ran/tests/test_ran_lib.py``); the scripts that touch docker
(``ranctl.py``, ``testbed.py``, ``collection.py``) build on these primitives.

Topology (fixed 4 DUs / 4 CUs, mirroring ``FiveGSystem``):
  - DU_i (i=1..4): an ``srsdu`` container with a ZMQ virtual radio, paired with UE_i.
  - CU_j (j=1..4): an ``srscu`` container (F1 server to its DUs; N2/N3 to the core).
  - core: the Open5GS deployment; UE_i: an ``srsue`` container per DU.
  - DU_i attaches to CU_{AT_i} over F1 (nominal AT_i = i); reattachment restarts srsdu_i
    against the target CU's F1 address.

The operator variables (X) map to concrete enactments (see ``enactment_for``):
  - ``QI_i`` (5QI admission threshold): iptables REJECT of the sub-threshold class ports
    at UE_i's tunnel ingress -- classes k < QI_i are dropped before the radio.
  - ``Uu``   (radio): block every DU's ZMQ radio port pair.
  - ``NG_j`` (CU_j midhaul): block CU_j's N2 (SCTP 38412) + N3 (UDP 2152) to the core.
  - ``N6``/``Xn``/``E2``/``A1``: block the corresponding interface link (UPF egress /
    inter-CU / near-RT RIC / non-RT RIC).
  - ``AT_i`` (CU attachment): not an iptables rule -- a control-plane reattach of DU_i.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Dict, List, Mapping

# --- topology constants -------------------------------------------------------
NUM_DU = 4
NUM_CU = 4
NUM_CLASSES = 10
ATTACKER_CLASSES = (1, 2, 3)

# --- address plan (bridge 10.53.1.0/24; matches compose-smoke.yml) ------------
RAN_SUBNET = "10.53.1.0/24"
AMF_IP = "10.53.1.2"
UPF_IP = "10.53.1.3"
CORE_NGAP_PORT = 38412          # N2 (SCTP): CU -> AMF
CORE_GTPU_PORT = 2152           # N3 (UDP):  CU -> UPF
# F1-U (GTP-U DU<->CU): moved off 2152 so it does not collide with the CU's N3 GTP-U
# (also 2152) inside the same container.
F1U_PORT = 2153
ZMQ_TX_BASE = 2000              # DU_i radio ports: tx = 2000 + 10*i, rx = 2001 + 10*i
CLASS_PORT_BASE = 5000          # 5QI class k traffic on UDP port 5000 + k

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


def class_port(k: int) -> int:
    """UDP port carrying 5QI class-``k`` traffic (L^{ik})."""
    if not 1 <= k <= NUM_CLASSES:
        raise ValueError(f"class k must be in [1, {NUM_CLASSES}], got {k}")
    return CLASS_PORT_BASE + k


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

    ``kind`` is ``"iptables"`` (install REJECT rules in the container's ``CCD`` chain) or
    ``"reattach"`` (restart DU_i against a new CU -- a control-plane action, no chain
    rules). ``container`` is where the action applies; ``rule_args`` is the list of
    iptables argument strings (one per REJECT rule), empty for a reattach.
    """

    var: str
    value: int
    kind: str
    container: str
    rule_args: List[str]
    target_cu: int = 0            # for reattach: the CU DU_i attaches to


def enactment_for(var: str, value: int) -> Enactment:
    """The enactment realizing ``do(var = value)`` for one operator variable.

    ``value`` is the *degraded* configuration ``D(var)`` from ``FiveGSystem``: 0 for
    interfaces/NG (close the link), 4 for ``QI_i`` (reject attacker classes 1-3), and the
    target CU index for ``AT_i``.
    """
    if var in _INTERFACE_VARS:
        if value != 0:
            raise ValueError(f"interface {var!r} only has degraded value 0, got {value}")
        return _interface_enactment(var)

    match = _LINK_RE.match(var)
    if match is None:
        raise ValueError(f"unknown operator variable: {var!r}")
    kind, idx = match.group(1), int(match.group(2))

    if kind == "NG":
        if not 1 <= idx <= NUM_CU:
            raise ValueError(f"NG index out of range: {var!r}")
        if value != 0:
            raise ValueError(f"NG{idx} only has degraded value 0, got {value}")
        # sever CU_j's midhaul: block its N2 (NGAP/SCTP) and N3 (GTP-U) to the core
        return Enactment(
            var=var, value=value, kind="iptables", container=cu_container(idx),
            rule_args=[
                f"-p sctp -d {AMF_IP} --dport {CORE_NGAP_PORT} -j REJECT",
                f"-p udp -d {UPF_IP} --dport {CORE_GTPU_PORT} -j REJECT",
            ],
        )
    if kind == "QI":
        if not 1 <= idx <= NUM_DU:
            raise ValueError(f"QI index out of range: {var!r}")
        # admission threshold: drop the class-k UDP ports with k < value at UE_i ingress
        ports = [class_port(k) for k in range(1, NUM_CLASSES + 1) if k < value]
        rules = [f"-p udp --dport {port} -j REJECT" for port in ports]
        return Enactment(
            var=var, value=value, kind="iptables", container=ue_container(idx),
            rule_args=rules,
        )
    # kind == "AT": reattach DU_idx to CU_value
    if not 1 <= idx <= NUM_DU:
        raise ValueError(f"AT index out of range: {var!r}")
    if not 1 <= value <= NUM_CU:
        raise ValueError(f"AT{idx} target CU out of range: {value}")
    return Enactment(
        var=var, value=value, kind="reattach", container=du_container(idx),
        rule_args=[], target_cu=value,
    )


def _interface_enactment(var: str) -> Enactment:
    """REJECT rules that close one global interface link."""
    if var == "Uu":
        # block every DU's ZMQ radio port pair (the whole air interface)
        rules = []
        for i in range(1, NUM_DU + 1):
            ports = zmq_ports(i)
            rules.append(f"-p tcp --dport {ports['tx']} -j REJECT")
            rules.append(f"-p tcp --dport {ports['rx']} -j REJECT")
        return Enactment("Uu", 0, "iptables", "ccd5g-radio", rules)
    if var == "N6":
        # UPF data-network egress
        return Enactment("N6", 0, "iptables", UPF_CONTAINER,
                         ["-o ogstun -j REJECT"])
    if var == "Xn":
        return Enactment("Xn", 0, "iptables", "ccd5g-xn", ["-j REJECT"])
    if var == "E2":
        return Enactment("E2", 0, "iptables", "ccd5g-ric-nearrt", ["-j REJECT"])
    if var == "A1":
        return Enactment("A1", 0, "iptables", "ccd5g-ric-nonrt", ["-j REJECT"])
    raise ValueError(f"unknown interface variable: {var!r}")


UPF_CONTAINER = "ccd5g-upf"


def sync_commands(mode: Mapping[str, int]) -> List[List[str]]:
    """The ``docker exec`` commands that enact ``mode`` (an operator intervention D(X')).

    Only the iptables-kind variables produce chain commands here; ``AT_i`` reattachments
    are control-plane actions handled by ``ranctl.py``/``enact_mode.py`` (they restart a
    DU) and are returned separately by :func:`reattachments`. As in the IT testbed, every
    touched container's ``CCD`` chain is flushed and re-added in one ``docker exec`` so
    synchronization is idempotent.
    """
    rules_by_container: Dict[str, List[str]] = {}
    for var in sorted(mode):
        if mode[var] == _nominal_value(var):
            continue                                   # unchanged from nominal: no rule
        enact = enactment_for(var, mode[var])
        if enact.kind != "iptables":
            continue
        rules_by_container.setdefault(enact.container, []).extend(enact.rule_args)
    commands = []
    for container in sorted(rules_by_container):
        script = "; ".join(["iptables -F CCD"]
                           + [f"iptables -A CCD {args}" for args in rules_by_container[container]])
        commands.append(["docker", "exec", container, "sh", "-c", script])
    return commands


def reattachments(mode: Mapping[str, int]) -> List[Enactment]:
    """The DU reattachments in ``mode`` (``AT_i`` set to a non-nominal CU)."""
    out = []
    for var in sorted(mode):
        match = _LINK_RE.match(var)
        if match is not None and match.group(1) == "AT" and mode[var] != _nominal_value(var):
            out.append(enactment_for(var, mode[var]))
    return out


def _nominal_value(var: str) -> int:
    """The nominal (non-degraded) value of an operator variable: interfaces/NG open = 1,
    QI_i admit-all = 1, AT_i attached to CU_i."""
    match = _LINK_RE.match(var)
    if match is not None and match.group(1) == "AT":
        return int(match.group(2))
    return 1


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
    """Render the RAN half of the compose (4 CU + 4 DU + 4 UE) on the shared ``ran``
    network, mounting the generated per-node configs from ``./gen/``. Combined with
    ``compose-core.yml`` (same project ``ccd5g``, same network) via ``-f``.

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
        ]
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
