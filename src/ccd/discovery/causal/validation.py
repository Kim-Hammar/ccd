"""
Data validation of a constructed causal graph G, wrapping the shared falsification
machinery in ``ccd.util.validation_util`` (``observable_columns`` / ``augment_context`` /
``falsify``). The acceptance gate for G is **not** edge isomorphism against the
hand-built graph but whether the constructed G survives falsification on the testbed
dataset, so this is where construction meets the same test the hand-built graphs pass.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Optional
import networkx as nx
import pandas as pd
from ccd.util.validation_util import FalsificationResult, augment_context, falsify


@dataclass
class FalsificationSummary:
    """A JSON-serializable digest of one ``falsify`` run on a constructed graph."""

    n_nodes: int
    n_edges: int
    n_tests: int
    given_violations: int
    violation_rate: float
    p_lmc: float
    p_tpa: float
    falsifiable: Optional[bool]
    falsified: Optional[bool]

    @classmethod
    def from_result(cls, result: FalsificationResult) -> "FalsificationSummary":
        return cls(
            n_nodes=result.n_nodes,
            n_edges=result.n_edges,
            n_tests=result.n_tests,
            given_violations=result.given_violations,
            violation_rate=result.violation_rate,
            p_lmc=result.p_lmc,
            p_tpa=result.p_tpa,
            falsifiable=result.falsifiable,
            falsified=result.falsified,
        )


def validate_graph(
    graph: nx.DiGraph,
    data: pd.DataFrame,
    n_permutations: int,
    *,
    context: Optional[str] = None,
    context_children: Optional[Iterable[str]] = None,
    seed: int = 0,
) -> FalsificationSummary:
    """Falsify ``graph`` against ``data`` over the graph's own node set.

    ``context`` optionally adds an exogenous context root (the workload/demand
    confounder) with edges to ``context_children`` before testing -- the same
    ``augment_context`` step the hand-built-graph validation uses so the two runs are
    comparable.
    """
    tested = graph
    if context is not None:
        children = [c for c in (context_children or []) if c in graph]
        tested = augment_context(graph, context, children)
    columns = list(tested.nodes)
    result = falsify(tested, data[columns], n_permutations, seed=seed)
    return FalsificationSummary.from_result(result)
