"""
5G cloud-RAN testbed adapter: export the construction ``Descriptor`` for the dockerized
srsRAN/Open5GS RAN, thin over ``ran_lib`` (topology constants, container names, attacker
classes).

The hardest of the three (phase 3): ~196 causal columns with four index dimensions
(DU, CU, 5QI class, direction) exploited by symmetry reduction; per-(DU,CU,dir) midhaul
products ``Ctil = NG_j * Chat``; the ``AT_i`` reattachment as an operator variable; and an
attack chain whose footholds are invisible to a network scan -- ``EX1`` is a UE radio
injection (``radioinject``) and ``EX4``/``EX5`` are control-plane moves (``credreuse``),
none scan-grounded. The attacker holds DU_1's UEs in the high-5QI classes (P1) and CU_3
(P2); capability edges give P1 the attacker UE sources and P2 the CU_3 carried loads.
"""

from __future__ import annotations
import argparse
from typing import List
import ran_lib as rl
from ccd.discovery.descriptor import (
    ColumnProvenance, Descriptor, ExploitTemplate, Host, Mechanism, Network, NodeSpec,
    ReachEdge, VarEnactment)

ATTACKER_HOST = "attacker"
DU1_HOST = "du1"
CU3_HOST = "cu3"
RIC_HOST = "ric_nearrt"
CORE_HOST = "core"
RAN_HOST = "ran"
_INTERFACES = ("E2", "A1", "N6", "Xn")


def _dus() -> range:
    return range(1, rl.NUM_DU + 1)


def _cus() -> range:
    return range(1, rl.NUM_CU + 1)


def _classes() -> range:
    return range(1, rl.NUM_CLASSES + 1)


def build_descriptor() -> Descriptor:
    """Build the 5G cloud-RAN construction descriptor (4 DUs / 4 CUs / 10 classes)."""
    dirs = rl.DIRECTIONS

    networks = [Network("ran", "10.53.1.0/24")]      # the RAN bridge (compose-core.yml)
    hosts: List[Host] = [
        Host(ATTACKER_HOST, container="", role="attacker", privilege_node="P0"),
        Host(DU1_HOST, container=rl.du_container(1), ips=[rl.du_ip(1)], role="du",
             privilege_node="P1",
             produces_vars=[f"UE_1_{k}" for k in rl.ATTACKER_CLASSES]),
        Host(CU3_HOST, container=rl.cu_container(3), ips=[rl.cu_ip(3)], role="cu",
             privilege_node="P2",
             produces_vars=[f"Chat_{i}_3_{d}" for i in _dus() for d in dirs]),
        Host(RIC_HOST, container=rl.RIC_NEARRT_CONTAINER, ips=[rl.RIC_NEARRT_IP],
             role="near-rt-ric", privilege_node="P3"),
        Host(CORE_HOST, container=rl.UPF_CONTAINER, ips=[rl.UPF_IP], role="core",
             privilege_node="P4"),
        Host(RAN_HOST, container="", role="ran", privilege_node="P5"),
    ]

    # reachability: the two footholds (radio to DU_1, network to CU_3) plus the CU_3
    # escalations gated by E2 (near-RT RIC) and NG3 (CU_3 midhaul), then the wider RAN.
    reachability = [
        ReachEdge(ATTACKER_HOST, DU1_HOST, "ran", "radio"),
        ReachEdge(ATTACKER_HOST, CU3_HOST, "ran", "tcp"),
        ReachEdge(CU3_HOST, RIC_HOST, "ran", "sctp", link_var="E2"),
        ReachEdge(CU3_HOST, CORE_HOST, "ran", "udp", rl.CORE_GTPU_PORT, link_var="NG3"),
        ReachEdge(RIC_HOST, RAN_HOST, "ran", "tcp"),
    ]

    node_set, columns = _causal_layer()
    mechanisms = _mechanisms()
    enactments = _enactments()
    exploits = [
        ExploitTemplate("EX1", "P0", "P1", "radioinject",
                        via_reach_edge=[ATTACKER_HOST, DU1_HOST]),
        ExploitTemplate("EX2", "P0", "P2", "netexploit",
                        via_reach_edge=[ATTACKER_HOST, CU3_HOST], requires_service="http"),
        ExploitTemplate("EX3", "P2", "P3", "netexploit",
                        via_reach_edge=[CU3_HOST, RIC_HOST], link_var="E2",
                        requires_service="e2"),
        ExploitTemplate("EX4", "P2", "P4", "credreuse",
                        via_reach_edge=[CU3_HOST, CORE_HOST], link_var="NG3"),
        ExploitTemplate("EX5", "P3", "P5", "credreuse",
                        via_reach_edge=[RIC_HOST, RAN_HOST]),
    ]

    return Descriptor(
        testbed="5g_ran",
        scale={"num_du": rl.NUM_DU, "num_cu": rl.NUM_CU, "num_classes": rl.NUM_CLASSES},
        hosts=hosts,
        networks=networks,
        reachability=reachability,
        node_set=node_set,
        columns=columns,
        enactments=enactments,
        product_mechanisms=mechanisms,
        confounders=["demand"],          # condition out the load confounder (NG/T both fall at low demand)
        exploit_templates=exploits,
        attained=["P0", "P1", "P2"],
        attacker_start_hosts=[ATTACKER_HOST],
        metadata_columns=list(rl.METADATA_COLUMNS),
    )


def _causal_layer() -> tuple[List[NodeSpec], List[ColumnProvenance]]:
    """The 196 causal nodes with named-dimension indices, tiers, and provenance."""
    dirs = rl.DIRECTIONS
    nodes: List[NodeSpec] = []
    cols: List[ColumnProvenance] = []

    def add(name: str, tier: int, group: str, index: dict, source: str, **prov: str) -> None:
        nodes.append(NodeSpec(name, tier=tier, group=group, index=index))
        cols.append(ColumnProvenance(name, source, **prov))

    for i in _dus():
        du = str(i)
        add(f"QI{i}", 0, "QI", {"du": du}, "enacted", enactment_var=f"QI{i}")
        add(f"Uu{i}", 0, "Uu", {"du": du}, "enacted", enactment_var=f"Uu{i}")
        add(f"AT{i}", 0, "AT", {"du": du}, "enacted", enactment_var=f"AT{i}")
    for j in _cus():
        add(f"NG{j}", 0, "NG", {"cu": str(j)}, "enacted", enactment_var=f"NG{j}")
    for iface in _INTERFACES:
        nodes.append(NodeSpec(iface, tier=0, group=None))
        cols.append(ColumnProvenance(iface, "enacted", enactment_var=iface))

    # Ladm/Chat/C have KNOWN parents (admission sums the admitted classes gated by QI/Uu;
    # attachment gates the carried load onto the chosen CU; C sums the midhaul over CUs), so
    # they are declared derived (their incoming edges come from mechanisms). Cbar and T keep
    # measured parents (Ladm->Cbar and C/interface->T are what discovery genuinely learns).
    for i in _dus():
        du = str(i)
        for d in dirs:
            idx_id = {"du": du, "dir": d}
            for k in _classes():
                add(f"L_{i}_{k}_{d}", 0, "L", {"du": du, "cls": str(k), "dir": d}, "measured")
            add(f"Ladm_{i}_{d}", 1, "Ladm", dict(idx_id), "derived", mechanism=f"Ladm_{i}_{d}")
            add(f"Cbar_{i}_{d}", 2, "Cbar", dict(idx_id), "measured")
            for j in _cus():
                idx_ijd = {"du": du, "cu": str(j), "dir": d}
                add(f"Chat_{i}_{j}_{d}", 3, "Chat", dict(idx_ijd), "derived",
                    mechanism=f"Chat_{i}_{j}_{d}")
                add(f"Ctil_{i}_{j}_{d}", 4, "Ctil", dict(idx_ijd), "derived",
                    mechanism=f"Ctil_{i}_{j}_{d}")
            add(f"C_{i}_{d}", 5, "C", dict(idx_id), "derived", mechanism=f"C_{i}_{d}")
            add(f"T_{i}_{d}", 6, "T", dict(idx_id), "measured")
    return nodes, cols


def _mechanisms() -> List[Mechanism]:
    """Known-parent mechanisms: the admission sum, attachment gate, midhaul product, and
    the CU aggregation. Only the midhaul is a gated product (carries to product_functions)."""
    dirs = rl.DIRECTIONS
    out: List[Mechanism] = []
    for i in _dus():
        for d in dirs:
            # Ladm_i_d = Uu_i * sum_{k<=QI_i} L_i_k_d  (admission: classes summed, gated)
            factors = [f"L_{i}_{k}_{d}" for k in _classes()] + [f"QI{i}", f"Uu{i}"]
            out.append(Mechanism(f"Ladm_{i}_{d}", factors, kind="sum"))
            for j in _cus():
                # Chat_i_j_d = [AT_i == j] * Cbar_i_d   (attachment selection)
                out.append(Mechanism(f"Chat_{i}_{j}_{d}", [f"Cbar_{i}_{d}", f"AT{i}"], kind="gate"))
                # Ctil_i_j_d = NG_j * Chat_i_j_d        (midhaul, the gated product F-tilde)
                out.append(Mechanism(f"Ctil_{i}_{j}_{d}", [f"NG{j}", f"Chat_{i}_{j}_{d}"],
                                     kind="product"))
            # C_i_d = sum_j Ctil_i_j_d               (carried load aggregated over CUs)
            out.append(Mechanism(f"C_{i}_{d}", [f"Ctil_{i}_{j}_{d}" for j in _cus()], kind="sum"))
    return out


def _enactments() -> List[VarEnactment]:
    """Operator-variable enactments (kinds mirror ran_lib.enactments_for)."""
    out: List[VarEnactment] = []
    for iface in _INTERFACES:
        out.append(VarEnactment(iface, "iptables"))
    for i in _dus():
        out.append(VarEnactment(f"Uu{i}", "iptables", container=rl.du_container(i)))
        out.append(VarEnactment(f"QI{i}", "iptables", container=rl.ue_container(i)))
        out.append(VarEnactment(f"AT{i}", "reattach", container=rl.du_container(i)))
    for j in _cus():
        out.append(VarEnactment(f"NG{j}", "iptables", container=rl.cu_container(j)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit the 5G cloud-RAN construction descriptor.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    descriptor = build_descriptor()
    descriptor.validate()
    if args.out:
        descriptor.dump(args.out)
        print(f"Wrote 5G descriptor to {args.out}")
    else:
        print(f"5G descriptor: {len(descriptor.node_set)} nodes, "
              f"{len(descriptor.product_mechanisms)} mechanisms, "
              f"{len(descriptor.exploit_templates)} exploits")


if __name__ == "__main__":
    main()
