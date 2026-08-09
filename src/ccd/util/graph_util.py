"""
Graph operations for CCD
"""

from __future__ import annotations
from typing import AbstractSet, Dict, Iterable, Mapping, Set
import networkx as nx
from ccd.dto.criteria_result import CriteriaResult
from ccd.system.system_model import SystemModel
from ccd.util.sort_util import sort_key


def ancestors(graph: nx.DiGraph, nodes: Iterable[str]) -> Set[str]:
    """an(S): all ancestors of ``nodes`` in ``graph``, including ``nodes`` themselves."""
    result: Set[str] = set()
    for n in nodes:
        if n in graph:
            result.add(n)
            result |= nx.ancestors(graph, n)
    return result


def descendants(graph: nx.DiGraph, nodes: Iterable[str]) -> Set[str]:
    """de(S): the (proper) descendants of ``nodes`` in ``graph``."""
    result: Set[str] = set()
    for n in nodes:
        if n in graph:
            result |= nx.descendants(graph, n)
    return result


def intervened_graph(system: SystemModel, do: Dict[str, int]) -> nx.DiGraph:
    """Build G_u for the intervention ``do``"""
    g = system.graph.copy()

    for v in do:
        if v in g:
            for p in list(g.predecessors(v)):
                g.remove_edge(p, v)

    for p, out in system.deactivated_edges(do):
        if g.has_edge(p, out):
            g.remove_edge(p, out)

    return g


def blocked_exploits(system: SystemModel, do_vars: AbstractSet[str]) -> Set[str]:
    return {e for required, e in system.blocking_edges if required <= do_vars}


def intervened_attack_graph(system: SystemModel, do_vars: AbstractSet[str]) -> nx.DiGraph:
    gamma = system.attack_graph.copy()
    gamma.remove_nodes_from(blocked_exploits(system, do_vars))
    return gamma


def check_criteria(system: SystemModel, do: Dict[str, int]) -> CriteriaResult:
    """Check the two graphical criteria for the intervention"""
    do_vars = set(do)
    blocked = blocked_exploits(system, do_vars)
    gamma = system.attack_graph
    violating = {
        e for e in system.exploits
        if e in gamma and e not in blocked
        and any(p in system.attained for p in gamma.predecessors(e))
        and not set(gamma.successors(e)) <= system.attained
    }
    contained = not violating

    g_u = intervened_graph(system, do)
    seeds = system.attacker_controlled - do_vars
    reachable = seeds | descendants(g_u, seeds)
    functional = system.functionality.isdisjoint(reachable)
    return CriteriaResult(
        contained=contained,
        functional=functional,
        reachable=reachable,
        blocked=blocked,
        violating_exploits=violating,
    )


def attainable_privileges(system: SystemModel, do_vars: AbstractSet[str]) -> Set[str]:
    """The privileges the attacker can attain"""
    gamma_u = intervened_attack_graph(system, do_vars)
    seeds = system.attained & set(gamma_u.nodes)
    return system.attained | (descendants(gamma_u, seeds) & system.privileges)


def worst_case_attack(system: SystemModel, do: Mapping[str, int]) -> Dict[str, int]:
    """The attacker intervention ``a`` of the worst case for the mode ``do``."""
    attainable = attainable_privileges(system, set(do))
    controlled = {y for required, y in system.capability_edges if required <= attainable}
    return {y: system.attack_value(y) for y in sorted(controlled - set(do), key=sort_key)}
