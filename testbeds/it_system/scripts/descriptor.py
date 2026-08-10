"""
IT-system testbed adapter: export the construction ``Descriptor`` for the dockerized IT
system, thin over ``testbed_lib`` (reimplements nothing -- addresses, containers, and the
link->iptables mapping all come from there).

Provenance falls straight out of the collection schema: the gateway/DB links ``N_i``/``M_i``
are operator-controlled roots, the carried loads ``Tt_i`` and offered loads ``L_i`` and workload ``W``
are measured, ``Th_i = N_i * Tt_i`` is a derived F-tilde product and ``T = sum_i Th_i`` a
derived aggregate. The attack layer is the 3-class IT chain: ``E1`` foothold (netexploit)
-> ``E_i`` lateral over the management link ``A_i`` (netexploit) -> ``E_{m+1}`` DB
credential reuse over ``M_1`` (credreuse).
"""

from __future__ import annotations
import argparse
from typing import List
import testbed_lib as tl
from ccd.discovery.descriptor import (
    ColumnProvenance, ContextRoot, Descriptor, ExploitTemplate, Host, Mechanism, Network,
    NodeSpec, ReachEdge, VarEnactment)

ATTACKER_HOST = "attacker"
GATEWAY_HOST = "gateway"


def _server(i: int) -> str:
    return f"server{i}"


def build_descriptor(m: int = 10) -> Descriptor:
    """Build the IT-system construction descriptor for ``m`` application servers."""
    if m < 2:
        raise ValueError("m must be >= 2")
    servers = range(1, m + 1)

    networks = [
        Network("service_net", tl.SERVICE_SUBNET),
        Network("db_net", tl.DB_SUBNET),
        Network("mgmt_net", tl.MGMT_SUBNET),
    ]

    hosts: List[Host] = [
        Host(ATTACKER_HOST, container="", role="attacker", privilege_node="P0"),
        Host(GATEWAY_HOST, container=tl.GATEWAY_CONTAINER, ips=[tl.GATEWAY_SERVICE_IP],
             role="gateway"),
    ]
    for i in servers:
        hosts.append(Host(
            _server(i), container=tl.server_container(i),
            ips=[tl.server_service_ip(i), tl.server_db_ip(i), tl.server_mgmt_ip(i)],
            role="server", privilege_node=f"P{i}", produces_vars=[f"Tt{i}"]))
    hosts.append(Host("db", container=tl.DB_CONTAINER, ips=[tl.DB_IP], role="database",
                      privilege_node=f"P{m + 1}"))

    # reachability: attacker -> server1 (foothold, always on); server1 -> server_i over the
    # management net (gated by A_i); server1 -> db (gated by M_1); plus the gateway -> n_i
    # service links (gated by N_i) that the enactments close.
    reachability: List[ReachEdge] = [
        ReachEdge(ATTACKER_HOST, _server(1), "service_net", "tcp", tl.SERVER_PORT),
    ]
    for i in servers:
        reachability.append(ReachEdge(GATEWAY_HOST, _server(i), "service_net", "tcp",
                                      tl.SERVER_PORT, link_var=f"N{i}"))
    for i in range(2, m + 1):
        reachability.append(ReachEdge(_server(1), _server(i), "mgmt_net", "tcp",
                                      link_var=f"A{i}"))
    reachability.append(ReachEdge(_server(1), "db", "db_net", "tcp", 5432, link_var="M1"))

    # --- causal node set + provenance ----------------------------------------
    node_set: List[NodeSpec] = [NodeSpec("W", tier=0, group="W")]
    columns: List[ColumnProvenance] = [ColumnProvenance("W", "measured", host=GATEWAY_HOST)]
    for i in servers:
        srv = {"srv": str(i)}
        node_set += [
            NodeSpec(f"N{i}", tier=0, group="N", index=srv),
            NodeSpec(f"M{i}", tier=0, group="M", index=srv),
            NodeSpec(f"L{i}", tier=1, group="L", index=srv),
            NodeSpec(f"Tt{i}", tier=2, group="Tt", index=srv),
            NodeSpec(f"Th{i}", tier=3, group="Th", index=srv),
        ]
        columns += [
            ColumnProvenance(f"N{i}", "operator_controlled", host=GATEWAY_HOST, enactment_var=f"N{i}"),
            ColumnProvenance(f"M{i}", "operator_controlled", host=_server(i), enactment_var=f"M{i}"),
            ColumnProvenance(f"L{i}", "measured", host=GATEWAY_HOST),
            ColumnProvenance(f"Tt{i}", "measured", host=_server(i)),
            ColumnProvenance(f"Th{i}", "derived", host=_server(i), mechanism=f"Th{i}"),
        ]
    node_set.append(NodeSpec("T", tier=4, group="T", index=None))
    columns.append(ColumnProvenance("T", "derived", mechanism="T"))

    # --- mechanisms (F-tilde products + the aggregate) -----------------------
    mechanisms: List[Mechanism] = [
        Mechanism(f"Th{i}", [f"N{i}", f"Tt{i}"], kind="product") for i in servers]
    mechanisms.append(Mechanism("T", [f"Th{i}" for i in servers], kind="sum"))

    # --- enactments (mirror rule_for / LinkRule) -----------------------------
    enactments: List[VarEnactment] = []
    for i in servers:
        n_rule = tl.rule_for(f"N{i}")
        enactments.append(VarEnactment(f"N{i}", "iptables", container=n_rule.container,
                                       reach_edge=[GATEWAY_HOST, _server(i)]))
        m_rule = tl.rule_for(f"M{i}")
        enactments.append(VarEnactment(f"M{i}", "iptables", container=m_rule.container,
                                       reach_edge=[_server(i), "db"]))
    for i in range(2, m + 1):
        a_rule = tl.rule_for(f"A{i}")
        enactments.append(VarEnactment(f"A{i}", "iptables", container=a_rule.container,
                                       reach_edge=[_server(1), _server(i)]))

    # --- exploit templates (the 3-class IT chain) ----------------------------
    exploits: List[ExploitTemplate] = [
        ExploitTemplate("E1", "P0", "P1", "netexploit",
                        via_reach_edge=[ATTACKER_HOST, _server(1)], requires_service="http"),
    ]
    for i in range(2, m + 1):
        exploits.append(ExploitTemplate(
            f"E{i}", "P1", f"P{i}", "netexploit",
            via_reach_edge=[_server(1), _server(i)], link_var=f"A{i}",
            requires_service="http"))
    exploits.append(ExploitTemplate(
        f"E{m + 1}", "P1", f"P{m + 1}", "credreuse",
        via_reach_edge=[_server(1), "db"], link_var="M1"))

    return Descriptor(
        testbed="it_system",
        scale={"m": m},
        hosts=hosts,
        networks=networks,
        reachability=reachability,
        node_set=node_set,
        columns=columns,
        enactments=enactments,
        product_mechanisms=mechanisms,
        context_roots=[ContextRoot("W", child_group="L")],   # W fans out to the loads L_i
        exploit_templates=exploits,
        attained=["P0", "P1"],
        attacker_start_hosts=[ATTACKER_HOST],
        metadata_columns=list(tl.METADATA_COLUMNS),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit the IT-system construction descriptor.")
    parser.add_argument("-m", type=int, default=10, help="number of application servers")
    parser.add_argument("--out", default=None, help="write JSON here (default: stdout path)")
    args = parser.parse_args()
    descriptor = build_descriptor(args.m)
    descriptor.validate()
    if args.out:
        descriptor.dump(args.out)
        print(f"Wrote IT descriptor (m={args.m}) to {args.out}")
    else:
        import json
        print(json.dumps(descriptor.to_dict(), indent=2))


if __name__ == "__main__":
    main()
