"""
Graph operations for CCD: ancestors/descendants, the intervened causal and attack
graphs, and the two graphical criteria (containment and essential functionality).

Containment is checked on the intervened attack graph Gamma_u (blocked exploits
removed): every unblocked exploit with a precondition in P-tilde must grant only
privileges already in P-tilde, i.e. ch_{Gamma_u}(ch_{Gamma_u}(P-tilde)) <= P-tilde.
Functionality is checked on the intervened causal graph G_u: no functionality variable
may be a descendant of the effective attacker-controlled set Y \\ X'.
"""

from __future__ import annotations
from typing import AbstractSet, Dict, Iterable, Set
import networkx as nx
from ccd.dto.criteria_result import CriteriaResult
from ccd.system.system_model import SystemModel


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
    """Build G_u for the intervention ``do`` (var -> fixed value).

    Applies the standard do-operator (sever each intervened node from its causes) and
    the context-specific known-function deactivation supplied by
    ``system.deactivated_edges`` (product/threshold/attachment gates).
    """
    g = system.graph.copy()

    # standard do(): remove incoming edges of each intervened node
    for v in do:
        if v in g:
            for p in list(g.predecessors(v)):
                g.remove_edge(p, v)

    # known-function deactivation (product, threshold, attachment, ...)
    for p, out in system.deactivated_edges(do):
        if g.has_edge(p, out):
            g.remove_edge(p, out)

    return g


def blocked_exploits(system: SystemModel, do_vars: AbstractSet[str]) -> Set[str]:
    """{E | (X'', E) in B, X'' <= X'}: the exploits made infeasible by intervening on
    ``do_vars``, via the blocking edges B of the two-layer graph."""
    return {e for required, e in system.blocking_edges if required <= do_vars}


def intervened_attack_graph(system: SystemModel, do_vars: AbstractSet[str]) -> nx.DiGraph:
    """Build Gamma_u for the intervention on ``do_vars``: the attack graph with the
    blocked exploits (and their pre-/postcondition edges) removed."""
    gamma = system.attack_graph.copy()
    gamma.remove_nodes_from(blocked_exploits(system, do_vars))
    return gamma


def check_criteria(system: SystemModel, do: Dict[str, int]) -> CriteriaResult:
    """Check the two graphical criteria (Prop. 1) for the intervention ``do``.

    Containment (i): every unblocked exploit with a precondition in P-tilde grants only
    privileges already in P-tilde (ch_{Gamma_u}(ch_{Gamma_u}(P-tilde)) <= P-tilde),
    checked in one pass over the exploits. Functionality (ii): J is disjoint from
    de_{G_u}(Y \\ X') -- the operator intervention takes priority on X n Y, so intervened
    variables are removed from the attacker's seed set.
    """
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
    reachable = descendants(g_u, system.attacker_controlled - do_vars)
    functional = system.functionality.isdisjoint(reachable)
    return CriteriaResult(
        contained=contained,
        functional=functional,
        reachable=reachable,
        blocked=blocked,
        violating_exploits=violating,
    )
