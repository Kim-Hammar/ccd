"""Model-misspecification perturbations for the CCD sensitivity analysis.

Given the *true* ``IllustrativeExampleSystem``, these helpers build a *misspecified* copy that CCD is
run on, so we can then evaluate CCD's selected mode against the true model. Three kinds of
misspecification are supported:

* ``underspecify``  -- the operator's causal graph is missing edges,
* ``overspecify``   -- the operator's causal graph has spurious edges,
* ``perturb_detection`` -- the detected privilege set P-tilde is wrong.

Only the misspecified *copy* is mutated; the true model is left untouched.
"""

from __future__ import annotations

import copy
from typing import FrozenSet, Set

import networkx as nx
import numpy as np

from ccd.ccd import select_intervention
from ccd.dto.outcome import Outcome
from ccd.util.graph_util import check_criteria
from ccd.system.illustrative_example_system import IllustrativeExampleSystem

# Bind the illustrative system's node-name helpers (static methods) for brevity.
E = IllustrativeExampleSystem.E
P = IllustrativeExampleSystem.P
Tt = IllustrativeExampleSystem.Tt


def attacker_capabilities(m: int, held: Set[str], patched: FrozenSet[str] = frozenset()) -> Set[str]:
    """The attacker-controlled variables Y implied by the set of ``held`` privileges.

    Code execution on n_i (privilege P_i) lets the attacker drop requests on n_i, i.e.
    control its carried load Tt_i; holding P_1 additionally enables the (unpatched)
    exploits E_2..E_{m+1}. For ``held = {P0, P1}`` this returns exactly the model's
    default Y = {Tt1, E2..E_{m+1}}.
    """
    y: Set[str] = {Tt(i) for i in range(1, m + 1) if P(i) in held}
    if P(1) in held:
        y |= {E(i) for i in range(2, m + 2) if E(i) not in patched}
    return y


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
    """Return a copy of ``graph`` with ``round(rho*|E|)`` spurious, DAG-preserving edges added.

    Candidate edges go forward in a topological order, so the graph stays acyclic.
    """
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
    system: IllustrativeExampleSystem, rho: float, rng: np.random.RandomState
) -> IllustrativeExampleSystem:
    """Return a copy of ``system`` with a fraction ``rho`` of causal-graph edges removed."""
    mis = copy.deepcopy(system)
    mis.graph = remove_edges(mis.graph, rho, rng)
    # trim each product function to the factors that survive as parents in the graph
    mis.product_functions = {
        out: frozenset(factors & set(mis.graph.predecessors(out)))
        for out, factors in mis.product_functions.items()
        if out in mis.graph
    }
    return mis


def overspecify(system: IllustrativeExampleSystem, rho: float, rng: np.random.RandomState) -> IllustrativeExampleSystem:
    """Return a copy of ``system`` with ``round(rho*|E|)`` spurious (DAG-preserving) edges added.

    Added edges are not registered in ``product_functions`` (their mechanism is unknown).
    """
    mis = copy.deepcopy(system)
    mis.graph = add_dag_edges(mis.graph, rho, rng)
    return mis


def perturb_detection(
    system: IllustrativeExampleSystem, rho: float, rng: np.random.RandomState
) -> IllustrativeExampleSystem:
    """Return a copy of ``system`` with a fraction ``rho`` of privileges P_1..P_{m+1} flipped
    in the detected set P-tilde (under- and over-detection), and Y recomputed accordingly."""
    mis = copy.deepcopy(system)
    flippable = [P(i) for i in range(1, mis.m + 2)]   # P_1..P_{m+1}; P_0 (network access) is a given
    k = round(rho * len(flippable))
    if k > 0:
        attained = set(mis.attained)
        for idx in rng.choice(len(flippable), size=k, replace=False):
            p = flippable[idx]
            attained.discard(p) if p in attained else attained.add(p)
        mis.attained = attained
        mis.attacker_controlled = attacker_capabilities(mis.m, attained, mis.patched_exploits)
    return mis


def underspecify_privileges(
    system: IllustrativeExampleSystem, rho: float, rng: np.random.RandomState
) -> IllustrativeExampleSystem:
    """Return a copy of ``system`` with a fraction of *truly-held* privileges dropped from
    P-tilde (under-detection: the operator underestimates the attacker's foothold).

    ``rho`` is a fraction of the m+1 privileges P_1..P_{m+1}, capped at the number actually
    held; Y is recomputed from the shrunken P-tilde.
    """
    mis = copy.deepcopy(system)
    removable = sorted(set(mis.attained) - {P(0)})   # held privileges, excluding network access
    k = min(round(rho * (mis.m + 1)), len(removable))
    if k > 0:
        attained = set(mis.attained)
        for idx in rng.choice(len(removable), size=k, replace=False):
            attained.discard(removable[idx])
        mis.attained = attained
        mis.attacker_controlled = attacker_capabilities(mis.m, attained, mis.patched_exploits)
    return mis


def overspecify_privileges(
    system: IllustrativeExampleSystem, rho: float, rng: np.random.RandomState
) -> IllustrativeExampleSystem:
    """Return a copy of ``system`` with a fraction of *not-held* privileges added to P-tilde
    (over-detection: the operator believes the attacker holds privileges it does not).

    ``rho`` is a fraction of the m+1 privileges P_1..P_{m+1}, capped at the number not held;
    Y is recomputed from the enlarged P-tilde.
    """
    mis = copy.deepcopy(system)
    addable = sorted(mis.unattained - {P(0)})        # not-held privileges (P_2..P_{m+1})
    k = min(round(rho * (mis.m + 1)), len(addable))
    if k > 0:
        attained = set(mis.attained)
        for idx in rng.choice(len(addable), size=k, replace=False):
            attained.add(addable[idx])
        mis.attained = attained
        mis.attacker_controlled = attacker_capabilities(mis.m, attained, mis.patched_exploits)
    return mis


def evaluate_structural(
    true_system: IllustrativeExampleSystem, misspec_system: IllustrativeExampleSystem
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
