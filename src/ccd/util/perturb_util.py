"""
Model-misspecification perturbations for the CCD sensitivity analysis
"""

from __future__ import annotations
import copy
import networkx as nx
import numpy as np
from ccd.ccd import select_intervention
from ccd.dto.outcome import Outcome
from ccd.util.graph_util import check_criteria
from ccd.system.it_system import ITSystem


def remove_edges(graph: nx.DiGraph, rho: float, rng: np.random.RandomState) -> nx.DiGraph:
    """Return a copy of ``graph`` with a fraction ``rho`` of its edges removed at random."""
    g = graph.copy()
    edges = list(g.edges())
    k = round(rho * len(edges))
    if k > 0:
        for j in rng.choice(len(edges), size=k, replace=False):
            g.remove_edge(*edges[j])
    return g


def add_dag_edges(graph: nx.DiGraph, rho: float, rng: np.random.RandomState) -> nx.DiGraph:
    """Return a copy of ``graph`` with ``round(rho*|E|)`` spurious edges added, forward
    in a topological order so the graph stays acyclic."""
    g = graph.copy()
    topo = list(nx.topological_sort(g))
    existing = set(g.edges())
    candidates = [
        (topo[i], topo[j])
        for i in range(len(topo))
        for j in range(i + 1, len(topo))
        if (topo[i], topo[j]) not in existing
    ]
    k = min(round(rho * g.number_of_edges()), len(candidates))
    if k > 0:
        for idx in rng.choice(len(candidates), size=k, replace=False):
            g.add_edge(*candidates[idx])
    return g


def underspecify(
    system: ITSystem, rho: float, rng: np.random.RandomState
) -> ITSystem:
    """Return a copy of ``system`` with a fraction ``rho`` of causal-graph edges removed."""
    mis = copy.deepcopy(system)
    mis.graph = remove_edges(mis.graph, rho, rng)
    mis.product_functions = {
        out: frozenset(factors & set(mis.graph.predecessors(out)))
        for out, factors in mis.product_functions.items()
        if out in mis.graph
    }
    return mis


def overspecify(system: ITSystem, rho: float, rng: np.random.RandomState) -> ITSystem:
    """Return a copy of ``system`` with ``round(rho*|E|)`` spurious (DAG-preserving) edges added."""
    mis = copy.deepcopy(system)
    mis.graph = add_dag_edges(mis.graph, rho, rng)
    return mis


def underspecify_attack(
    system: ITSystem, rho: float, rng: np.random.RandomState
) -> ITSystem:
    """Return a copy of ``system`` with a fraction ``rho`` of attack-graph edges removed"""
    mis = copy.deepcopy(system)
    mis.attack_graph = remove_edges(mis.attack_graph, rho, rng)
    return mis


def overspecify_attack(
    system: ITSystem, rho: float, rng: np.random.RandomState
) -> ITSystem:
    """Return a copy of ``system`` with ``round(rho*|V|)`` spurious attack-graph edges added."""
    mis = copy.deepcopy(system)
    gamma = mis.attack_graph
    existing = set(gamma.edges())
    exploits_in_gamma = sorted(e for e in mis.exploits if e in gamma)
    candidates = [
        (p, e) for p in sorted(mis.privileges) for e in exploits_in_gamma if (p, e) not in existing
    ] + [
        (e, p) for e in exploits_in_gamma for p in sorted(mis.privileges) if (e, p) not in existing
    ]
    k = min(round(rho * gamma.number_of_edges()), len(candidates))
    if k > 0:
        for idx in rng.choice(len(candidates), size=k, replace=False):
            gamma.add_edge(*candidates[idx])
    return mis


def evaluate_structural(
    true_system: ITSystem, misspec_system: ITSystem
) -> Outcome:
    """Run CCD on the misspecified model and check the selected mode on the true model."""
    u = select_intervention(misspec_system)
    if u is None:
        return Outcome(infeasible=True, contained=False, functional=False, mode_size=None)
    res = check_criteria(true_system, u.variables)
    return Outcome(
        infeasible=False,
        contained=res.contained,
        functional=res.functional,
        mode_size=len(u.variables),
    )
