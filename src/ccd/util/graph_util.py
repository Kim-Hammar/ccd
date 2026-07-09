"""Graph operations for CCD: ancestors/descendants, the intervened graph, and the
two graphical criteria (containment and essential functionality).
"""

from __future__ import annotations
from typing import Dict, Iterable, Set
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
    the context-specific product deactivation described in the module docstring.
    """
    g = system.graph.copy()

    # standard do(): remove incoming edges of each intervened node
    for v in do:
        if v in g:
            for p in list(g.predecessors(v)):
                g.remove_edge(p, v)

    # AND deactivation: a product output with a zeroed factor becomes constant 0
    zeroed = {v for v, val in do.items() if val == 0}
    for out, factors in system.product_functions.items():
        if factors & zeroed and out in g:
            for p in list(g.predecessors(out)):
                g.remove_edge(p, out)

    return g


def check_criteria(system: SystemModel, do: Dict[str, int]) -> CriteriaResult:
    """Check containment and functionality for intervention ``do`` via one traversal.

    Both criteria depend on the same descendant set de_{G_u}(Y).
    """
    g_u = intervened_graph(system, do)
    reachable = descendants(g_u, system.attacker_controlled)
    contained = system.containment_targets.isdisjoint(reachable)
    functional = system.functionality.isdisjoint(reachable)
    return CriteriaResult(contained=contained, functional=functional, reachable=reachable)
