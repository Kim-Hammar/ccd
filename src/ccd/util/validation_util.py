"""
Graph-falsification utilities for validating the causal layer G of a two-layer model
against measured data: test the local Markov conditions (LMC) implied by G -- each
variable independent of its non-descendants given its parents -- on an observational
dataset D, and compare the number of violated conditions against node-permuted random
DAGs (the permutation baseline of Eulig et al. 2023, via DoWhy's ``falsify_graph``).
G is not falsified when it violates significantly fewer conditions than the permuted
DAGs (``p_lmc`` below the significance level).

Only the LMC and TPA (informativeness) metrics are evaluated: the gated products in
F-tilde (e.g. ``Th_i = N_i * Tt_i``) are deterministic given their parents, which
satisfies the local Markov condition but violates faithfulness, so causal-minimality
checks (``validate_cm``/``validate_pd``) are not applicable. The (conditional)
independence test is DoWhy's ``regression_based`` F-test: the default kernel test is
orders of magnitude slower, and a linear partial-correlation test over-rejects on the
gated-product mechanisms.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable, List, Mapping, Optional, Set
import networkx as nx
import numpy as np
import pandas as pd
from dowhy.gcm.falsify import FalsifyConst, falsify_graph
from dowhy.gcm.independence_test import regression_based

# significance level for the permutation test (p_lmc) and for the per-condition CI
# tests; significance_ci is also the expected false-positive rate among the LMC tests,
# so a violation rate near 5% on the true graph is the test's noise floor.
SIGNIFICANCE_LEVEL = 0.05
SIGNIFICANCE_CI = 0.05


@dataclass
class FalsificationResult:
    """Summary of one ``falsify_graph`` run (plain data, JSON-serializable)."""

    n_nodes: int
    n_edges: int
    n_tests: int                     # number of LMC conditions tested on the given G
    given_violations: int            # LMC violations of the given G
    perm_violations: List[int]       # LMC violations of each node-permuted DAG
    p_lmc: float                     # P(permuted DAG violates <= given G)
    p_tpa: float                     # informativeness: P(permuted DAG in the MEC of G)
    falsifiable: Optional[bool]      # None when not evaluable
    falsified: Optional[bool]
    n_permutations: int

    @property
    def violation_rate(self) -> float:
        """Fraction of tested LMC conditions the given G violates."""
        return self.given_violations / self.n_tests if self.n_tests else float("nan")


def load_dataset(path: str, rename: Optional[Mapping[str, str]] = None) -> pd.DataFrame:
    """Load a measured dataset D, applying the model's column renames (the ICS dataset
    records the physical gateway as ``G2``; the causal model names it ``G2c``)."""
    data = pd.read_csv(path)
    if rename:
        data = data.rename(columns=dict(rename))
    return data


def observable_columns(data: pd.DataFrame, metadata: Set[str]) -> List[str]:
    """Columns of D that are observable variables with variation: metadata columns and
    constant columns are dropped (CI tests on constants are degenerate)."""
    return [c for c in data.columns if c not in metadata and data[c].nunique() > 1]


def augment_context(graph: nx.DiGraph, context: str, children: Iterable[str]) -> nx.DiGraph:
    """Return a copy of ``graph`` with an observed context root ``context -> children``
    added (e.g. the 5G ``demand`` driver of the UE load roots, the analog of the IT
    model's workload root ``W``; without it the load roots are confounded)."""
    augmented = graph.copy()
    augmented.add_node(context)
    for child in children:
        augmented.add_edge(context, child)
    if not nx.is_directed_acyclic_graph(augmented):
        raise ValueError(f"adding context root {context} produced a cycle")
    return augmented


# escalating jitter scales (relative to each column's std) for _robust_regression_based
_JITTER_SCALES = (1e-7, 1e-5, 1e-3)


def _robust_regression_based(n_jobs: Optional[int]) -> Callable[..., float]:
    """``regression_based`` with jitter retries: measured columns can be exactly
    collinear (gated products, duplicated chains), and a permuted DAG can place them
    in one conditioning set, making the Nystroem kernel matrix singular ("SVD did not
    converge"); a tiny relative jitter breaks the degeneracy without moving the
    p-value."""
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
    """Falsify ``graph`` against ``data`` (LMC + TPA only, ``regression_based`` CI
    tests, ``n_permutations`` node-permuted DAGs as the baseline). ``falsify_graph``
    draws permutations and test randomness from the global numpy RNG, hence the
    explicit seed; the result is only fully reproducible with ``n_jobs=1`` and a
    fixed ``PYTHONHASHSEED`` (joblib workers and set-iteration order otherwise
    consume RNG state in nondeterministic order)."""
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
