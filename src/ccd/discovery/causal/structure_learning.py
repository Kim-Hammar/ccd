"""
Constraint-based structure learning over a fixed node set (causal-learn PC).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import FrozenSet, Iterable, List, Mapping, Sequence, Set, Tuple
import numpy as np
import pandas as pd
from causallearn.graph.GraphNode import GraphNode
from causallearn.search.ConstraintBased.PC import pc
from causallearn.utils.cit import fisherz, kci
from causallearn.utils.PCUtils.BackgroundKnowledge import BackgroundKnowledge

DEFAULT_ALPHA = 0.05


@dataclass
class LearnedEdges:
    """The output of one structure-learning run over ``nodes``."""

    directed: Set[Tuple[str, str]]
    undirected: Set[FrozenSet[str]]
    indep_test: str


def build_background_knowledge(
    node_names: Sequence[str],
    *,
    tier_of: Mapping[str, int],
    required_edges: Iterable[Tuple[str, str]] = (),
    frozen_parents: Mapping[str, FrozenSet[str]] = {},
    parentless: Iterable[str] = (),
) -> BackgroundKnowledge:
    """Assemble a causal-learn ``BackgroundKnowledge`` from descriptor-derived constraints."""
    nodes = {name: GraphNode(name) for name in node_names}
    bk = BackgroundKnowledge()

    tiers = sorted(set(tier_of[n] for n in node_names))
    tier_rank = {t: r for r, t in enumerate(tiers)}
    for name in node_names:
        bk.add_node_to_tier(nodes[name], tier_rank[tier_of[name]])
    for t in tiers:
        bk.forbid_within_tier(tier_rank[t])

    for src, dst in required_edges:
        if src in nodes and dst in nodes:
            bk.add_required_by_node(nodes[src], nodes[dst])

    node_set = set(node_names)
    for child, parents in frozen_parents.items():
        if child not in node_set:
            continue
        for other in node_names:
            if other != child and other not in parents:
                bk.add_forbidden_by_node(nodes[other], nodes[child])

    for child in parentless:
        if child not in node_set:
            continue
        for other in node_names:
            if other != child:
                bk.add_forbidden_by_node(nodes[other], nodes[child])

    return bk


def _read_edges(matrix: np.ndarray, node_names: Sequence[str]) -> LearnedEdges:
    """Decode a causal-learn adjacency matrix into directed/undirected edge sets."""
    directed: Set[Tuple[str, str]] = set()
    undirected: Set[FrozenSet[str]] = set()
    n = len(node_names)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = matrix[i, j], matrix[j, i]
            if a == -1 and b == 1:
                directed.add((node_names[i], node_names[j]))
            elif a == 1 and b == -1:
                directed.add((node_names[j], node_names[i]))
            elif a != 0 or b != 0:
                undirected.add(frozenset({node_names[i], node_names[j]}))
    return LearnedEdges(directed=directed, undirected=undirected, indep_test="")


def learn_edges(
    data: pd.DataFrame,
    node_names: Sequence[str],
    bk: BackgroundKnowledge,
    *,
    alpha: float = DEFAULT_ALPHA,
    indep_test: str = kci,
    allow_fallback: bool = True,
) -> LearnedEdges:
    """Run PC over ``data[node_names]`` with ``bk`` and return the discovered edges."""
    matrix_data = data[list(node_names)].to_numpy(dtype=float)
    tests: List[str] = [indep_test]
    if allow_fallback and indep_test != fisherz:
        tests.append(fisherz)
    last_error: Exception = RuntimeError("no independence test attempted")
    for test in tests:
        try:
            cg = pc(matrix_data, alpha, test, background_knowledge=bk,
                    node_names=list(node_names), show_progress=False)
            edges = _read_edges(cg.G.graph, node_names)
            edges.indep_test = str(test)
            return edges
        except (np.linalg.LinAlgError, ValueError, ZeroDivisionError) as err:
            last_error = err
    raise last_error
