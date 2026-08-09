"""
Graph-falsification utilities for validating the causal layer G of a two-layer model against testbed data.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable, List, Mapping, Optional, Set
import networkx as nx
import numpy as np
import pandas as pd
from dowhy.gcm.falsify import FalsifyConst, falsify_graph
from dowhy.gcm.independence_test import regression_based

SIGNIFICANCE_LEVEL = 0.05
SIGNIFICANCE_CI = 0.05


@dataclass
class FalsificationResult:
    """Summary of one ``falsify_graph`` run (plain data, JSON-serializable)."""

    n_nodes: int
    n_edges: int
    n_tests: int
    given_violations: int
    perm_violations: List[int]
    p_lmc: float
    p_tpa: float
    falsifiable: Optional[bool]
    falsified: Optional[bool]
    n_permutations: int

    @property
    def violation_rate(self) -> float:
        return self.given_violations / self.n_tests if self.n_tests else float("nan")


def load_dataset(path: str, rename: Optional[Mapping[str, str]] = None) -> pd.DataFrame:
    data = pd.read_csv(path)
    if rename:
        data = data.rename(columns=dict(rename))
    return data


def observable_columns(data: pd.DataFrame, metadata: Set[str]) -> List[str]:
    return [c for c in data.columns if c not in metadata and data[c].nunique() > 1]


def augment_context(graph: nx.DiGraph, context: str, children: Iterable[str]) -> nx.DiGraph:
    augmented = graph.copy()
    augmented.add_node(context)
    for child in children:
        augmented.add_edge(context, child)
    if not nx.is_directed_acyclic_graph(augmented):
        raise ValueError(f"adding context root {context} produced a cycle")
    return augmented


_JITTER_SCALES = (1e-7, 1e-5, 1e-3)


def _robust_regression_based(n_jobs: Optional[int]) -> Callable[..., float]:
    """``regression_based`` tests with jitter retries"""
    def test(*arrays: np.ndarray) -> float:
        try:
            return float(regression_based(*arrays, n_jobs=n_jobs))
        except np.linalg.LinAlgError:
            pass
        rng = np.random.default_rng(0)
        for i, scale in enumerate(_JITTER_SCALES):
            jittered = tuple(
                a + rng.normal(scale=scale * (np.std(a, axis=0, keepdims=True) + 1e-12), size=a.shape)
                for a in (np.asarray(a, dtype=float) for a in arrays)
            )
            try:
                return float(regression_based(*jittered, n_jobs=n_jobs))
            except np.linalg.LinAlgError:
                if i == len(_JITTER_SCALES) - 1:
                    raise
        raise AssertionError("unreachable")
    return test


def falsify(graph: nx.DiGraph, data: pd.DataFrame, n_permutations: int,
            seed: int = 0, n_jobs: Optional[int] = None) -> FalsificationResult:
    """Falsify ``graph`` against ``data``"""
    np.random.seed(seed)
    ci_test = _robust_regression_based(n_jobs)
    result = falsify_graph(
        graph,
        data[list(graph.nodes)],
        independence_test=ci_test,
        conditional_independence_test=ci_test,
        significance_level=SIGNIFICANCE_LEVEL,
        significance_ci=SIGNIFICANCE_CI,
        n_permutations=n_permutations,
        show_progress_bar=False,
        n_jobs=n_jobs,
    )
    lmc = result.summary[FalsifyConst.VALIDATE_LMC]
    tpa = result.summary[FalsifyConst.VALIDATE_TPA]
    return FalsificationResult(
        n_nodes=graph.number_of_nodes(),
        n_edges=graph.number_of_edges(),
        n_tests=int(lmc[FalsifyConst.N_TESTS]),
        given_violations=int(lmc[FalsifyConst.GIVEN_VIOLATIONS]),
        perm_violations=[int(v) for v in lmc[FalsifyConst.PERM_VIOLATIONS]],
        p_lmc=float(lmc[FalsifyConst.P_VALUE]),
        p_tpa=float(tpa[FalsifyConst.P_VALUE]),
        falsifiable=result.falsifiable,
        falsified=result.falsified,
        n_permutations=n_permutations,
    )
