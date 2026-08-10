"""
ICS (Tennessee Eastman) testbed adapter: export the construction ``Descriptor`` for the
dockerized ICS, thin over ``ics_lib`` (reimplements nothing -- containers, subnets, and the
operator-variable enactment kinds all come from there).

Adds the phase-2 features over the IT adapter: ``mode`` enactments (``W``/``Chat``
application modes) alongside iptables (``G2``), the dual-homed control server (enterprise
+ plant), the ``G2c``/``G2e`` split of the single recorded gateway ``G2`` (via enactment
``name_map``), a conceded privilege (the control server P3, whose exploit ``E3`` keeps its
blocking edge but is seeded compromised), and the two-level products ``Ctil = G2c*C`` and
``V = Chat*Ctil`` whose terminal output ``V`` feeds the measured process node ``P``.
"""

from __future__ import annotations
import argparse
from typing import List
import ics_lib as il
from ccd.discovery.descriptor import (
    ColumnProvenance, Descriptor, ExploitTemplate, Host, Mechanism, Network, NodeSpec,
    ReachEdge, VarEnactment)

ATTACKER_HOST = "attacker"
WEB_HOST = "web"
SCADA_HOST = "scada"
CONTROL_HOST = "control"
PROCESS_HOST = "process"


def build_descriptor() -> Descriptor:
    """Build the ICS construction descriptor for the dockerized Tennessee Eastman testbed."""
    networks = [
        Network("enterprise", il.ENTERPRISE_SUBNET),
        Network("plant", il.PLANT_SUBNET),
    ]

    hosts: List[Host] = [
        Host(ATTACKER_HOST, container="", role="attacker", privilege_node="P0"),
        Host(WEB_HOST, container=il.WEB_CONTAINER, ips=[il.WEB_IP], role="web",
             privilege_node="P1", produces_vars=["W"]),
        Host(SCADA_HOST, container=il.SCADA_CONTAINER, ips=[il.SCADA_IP], role="supervisory",
             privilege_node="P2"),
        Host(CONTROL_HOST, container=il.CONTROL_CONTAINER,
             ips=[il.CONTROL_ENTERPRISE_IP, il.CONTROL_PLANT_IP], role="control",
             privilege_node="P3", produces_vars=["C"], conceded=True),
        Host(PROCESS_HOST, container=il.PROCESS_CONTAINER, ips=[il.PROCESS_IP],
             role="field", privilege_node="P4"),
    ]

    # reachability: the attacker reaches the web app (foothold, gated by the web mode W);
    # the web server reaches scada (gated by the enterprise gateway G2e) and the control
    # server (gated by G2c); the control server reaches the process (gated by Chat).
    reachability = [
        ReachEdge(ATTACKER_HOST, WEB_HOST, "enterprise", "tcp", il.APP_PORT, link_var="W"),
        ReachEdge(WEB_HOST, SCADA_HOST, "enterprise", "tcp", il.APP_PORT, link_var="G2e"),
        ReachEdge(WEB_HOST, CONTROL_HOST, "enterprise", "tcp", il.APP_PORT, link_var="G2c"),
        ReachEdge(CONTROL_HOST, PROCESS_HOST, "plant", "tcp", il.APP_PORT, link_var="Chat"),
    ]

    # --- causal node set + provenance ----------------------------------------
    # operator-controlled roots W/G2c/Chat, measured C/I/P/S, derived products Ctil/V
    node_set = [
        NodeSpec("W", tier=0), NodeSpec("G2c", tier=0), NodeSpec("Chat", tier=0),
        NodeSpec("C", tier=0),
        NodeSpec("I", tier=1), NodeSpec("Ctil", tier=1),
        NodeSpec("V", tier=2),
        NodeSpec("P", tier=3),
        NodeSpec("S", tier=4),
    ]
    columns = [
        ColumnProvenance("W", "operator_controlled", host=WEB_HOST, enactment_var="W"),
        ColumnProvenance("G2c", "operator_controlled", host=CONTROL_HOST, enactment_var="G2c"),
        ColumnProvenance("Chat", "operator_controlled", host=CONTROL_HOST, enactment_var="Chat"),
        ColumnProvenance("C", "measured", host=CONTROL_HOST),
        ColumnProvenance("I", "measured", host=WEB_HOST),
        ColumnProvenance("Ctil", "derived", mechanism="Ctil"),
        ColumnProvenance("V", "derived", mechanism="V"),
        ColumnProvenance("P", "measured", host=PROCESS_HOST),
        ColumnProvenance("S", "measured", host=PROCESS_HOST),
    ]
    mechanisms = [
        Mechanism("Ctil", ["G2c", "C"], kind="product"),
        Mechanism("V", ["Chat", "Ctil"], kind="product"),
    ]

    # --- enactments (mirror ics_lib.enactment_for) ---------------------------
    # the single recorded gateway column G2 (iptables at the control server) is split into
    # the causal G2c (carries Ctil; name_map renames the dataset G2 -> G2c) and G2e (no
    # causal edge, matters only via its blocking edge on E2).
    enactments = [
        VarEnactment("W", "mode", container=il.WEB_CONTAINER, reach_edge=[ATTACKER_HOST, WEB_HOST]),
        VarEnactment("G2c", "iptables", container=il.CONTROL_CONTAINER,
                     reach_edge=[WEB_HOST, CONTROL_HOST], name_map="G2"),
        VarEnactment("G2e", "iptables", container=il.CONTROL_CONTAINER,
                     reach_edge=[WEB_HOST, SCADA_HOST], name_map="G2"),
        VarEnactment("Chat", "mode", container=il.CONTROL_CONTAINER,
                     reach_edge=[CONTROL_HOST, PROCESS_HOST]),
    ]

    # --- exploit templates (the 4-exploit ICS chain) -------------------------
    exploits = [
        ExploitTemplate("E1", "P0", "P1", "netexploit",
                        via_reach_edge=[ATTACKER_HOST, WEB_HOST], link_var="W",
                        requires_service="http"),
        ExploitTemplate("E2", "P1", "P2", "netexploit",
                        via_reach_edge=[WEB_HOST, SCADA_HOST], link_var="G2e",
                        requires_service="http"),
        ExploitTemplate("E3", "P1", "P3", "conceded",
                        via_reach_edge=[WEB_HOST, CONTROL_HOST], link_var="G2c"),
        ExploitTemplate("E4", "P3", "P4", "credreuse",
                        via_reach_edge=[CONTROL_HOST, PROCESS_HOST], link_var="Chat"),
    ]

    return Descriptor(
        testbed="ics",
        hosts=hosts,
        networks=networks,
        reachability=reachability,
        node_set=node_set,
        columns=columns,
        enactments=enactments,
        product_mechanisms=mechanisms,
        exploit_templates=exploits,
        attained=["P0", "P1", "P3"],
        attacker_start_hosts=[ATTACKER_HOST],
        metadata_columns=list(il.METADATA_COLUMNS),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit the ICS construction descriptor.")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    descriptor = build_descriptor()
    descriptor.validate()
    if args.out:
        descriptor.dump(args.out)
        print(f"Wrote ICS descriptor to {args.out}")
    else:
        import json
        print(json.dumps(descriptor.to_dict(), indent=2))


if __name__ == "__main__":
    main()
