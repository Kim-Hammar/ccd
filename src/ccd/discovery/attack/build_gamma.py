"""
Assemble the attack graph Gamma from the MulVAL derivation.

Gamma is the bipartite privilege/exploit graph of ``SystemModel``: privilege OR-nodes
``P_i`` and exploit AND-nodes ``E`` with edges ``P_pre -> E -> P_post``. Each fired
template becomes an exploit node; every privilege a host can hold becomes a privilege node
(so isolated, not-yet-reached privileges still appear, matching the hand-built Gamma). The
per-exploit provenance (``link_var``, reach edge, class) is kept in ``exploit_meta`` for
the cross-layer B join.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Set
import networkx as nx
from ccd.discovery.attack.datalog_rules import derive
from ccd.discovery.attack.scanner import ScannerInterface
from ccd.discovery.descriptor import Descriptor


@dataclass
class GammaConstruction:
    """The constructed Gamma plus the sets and per-exploit provenance the model needs."""

    graph: nx.DiGraph
    privileges: Set[str] = field(default_factory=set)
    exploits: Set[str] = field(default_factory=set)
    exploit_meta: Dict[str, Dict[str, str]] = field(default_factory=dict)


def build_gamma(desc: Descriptor, scanner: ScannerInterface) -> GammaConstruction:
    """Construct Gamma for ``desc``, grounding host exploitability with ``scanner``."""
    scan_hosts = [h.id for h in desc.hosts if h.container]
    vuln_facts = scanner.scan(scan_hosts)
    derivation = derive(desc, vuln_facts)

    graph = nx.DiGraph()
    privileges: Set[str] = {"P0"} if "P0" in desc.attained else set()
    for host in desc.hosts:
        if host.privilege_node is not None:
            privileges.add(host.privilege_node)
    privileges |= set(desc.attained)
    graph.add_nodes_from(sorted(privileges))

    exploits: Set[str] = set()
    exploit_meta: Dict[str, Dict[str, str]] = {}
    for tmpl in desc.exploit_templates:
        if tmpl.id not in derivation.fired:
            continue
        exploits.add(tmpl.id)
        graph.add_node(tmpl.id)
        graph.add_edge(tmpl.pre_privilege, tmpl.id)
        graph.add_edge(tmpl.id, tmpl.post_privilege)
        meta: Dict[str, str] = {"class": tmpl.exploit_class}
        if tmpl.link_var is not None:
            meta["link_var"] = tmpl.link_var
        if tmpl.via_reach_edge is not None:
            meta["reach_src"], meta["reach_dst"] = tmpl.via_reach_edge[0], tmpl.via_reach_edge[1]
        exploit_meta[tmpl.id] = meta

    return GammaConstruction(graph=graph, privileges=privileges, exploits=exploits,
                             exploit_meta=exploit_meta)
