"""
Unit tests for ``ccd.util.validation_util``: graph falsification of a causal graph G
against observational data (LMC violations vs node-permuted DAGs) and the dataset /
graph helpers used by ``examples/model_validation.py``.
"""

from __future__ import annotations
import dataclasses
import pathlib
import networkx as nx
import numpy as np
import pandas as pd
import pytest
from ccd.util.validation_util import FalsificationResult, augment_context, falsify, load_dataset, observable_columns


def _linear_gaussian_dataset(steps: int = 300, seed: int = 1) -> tuple[nx.DiGraph, pd.DataFrame]:
    """A 7-node linear-Gaussian DAG (asymmetric, no isolated nodes, so node-permuted
    DAGs violate LMC conditions the true graph satisfies) and data from its DGP."""
    rng = np.random.RandomState(seed)
    w = rng.normal(size=steps)
    l1 = w + rng.normal(scale=0.5, size=steps)
    l2 = w + rng.normal(scale=0.5, size=steps)
    m1 = rng.normal(size=steps)
    t1 = 0.7 * l1 + 0.5 * m1 + rng.normal(scale=0.5, size=steps)
    t2 = 0.7 * l2 + rng.normal(scale=0.5, size=steps)
    s = 0.6 * t1 + 0.6 * t2 + rng.normal(scale=0.5, size=steps)
    data = pd.DataFrame({"W": w, "L1": l1, "L2": l2, "M1": m1, "T1": t1, "T2": t2, "S": s})
    graph = nx.DiGraph([("W", "L1"), ("W", "L2"), ("M1", "T1"), ("L1", "T1"), ("L2", "T2"),
                        ("T1", "S"), ("T2", "S")])
    return graph, data


def test_falsify_true_graph_beats_permuted_baseline() -> None:
    # falsify_graph is not reproducible across processes (joblib + set-iteration
    # order), so the assertions bound the statistics instead of pinning exact values
    graph, data = _linear_gaussian_dataset()
    result = falsify(graph, data, n_permutations=5, seed=0, n_jobs=1)
    assert result.n_nodes == 7 and result.n_edges == 7
    assert result.n_tests == 22   # determined by the graph structure alone
    assert len(result.perm_violations) == 5 and result.n_permutations == 5
    assert 0.0 <= result.p_lmc <= 1.0 and 0.0 <= result.p_tpa <= 1.0
    # the true graph passes most LMC tests (CI false positives aside), and the worst
    # node-permuted DAG violates at least as many conditions
    assert result.given_violations <= 0.5 * result.n_tests
    assert max(result.perm_violations) >= result.given_violations
    assert result.falsifiable is not None
    assert result.violation_rate == pytest.approx(result.given_violations / result.n_tests)


def test_observable_columns_drops_metadata_and_constants() -> None:
    data = pd.DataFrame({"W": [1.0, 2.0, 3.0], "T": [4.0, 5.0, 6.0],
                         "NG3": [0.0, 0.0, 0.0], "window": [0, 1, 2]})
    assert observable_columns(data, {"window"}) == ["W", "T"]


def test_load_dataset_renames(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "dataset.csv"
    pd.DataFrame({"G2": [1, 0, 1], "S": [50, 60, 70]}).to_csv(path, index=False)
    data = load_dataset(str(path), rename={"G2": "G2c"})
    assert list(data.columns) == ["G2c", "S"]
    assert load_dataset(str(path)).columns.tolist() == ["G2", "S"]


def test_augment_context_adds_root_and_preserves_dag() -> None:
    graph = nx.DiGraph([("L1", "T"), ("L2", "T")])
    augmented = augment_context(graph, "demand", ["L1", "L2"])
    assert set(augmented.edges()) == {("demand", "L1"), ("demand", "L2"), ("L1", "T"), ("L2", "T")}
    assert nx.is_directed_acyclic_graph(augmented)
    assert "demand" not in graph   # the input graph is unmodified


def test_augment_context_rejects_cycles() -> None:
    graph = nx.DiGraph([("L1", "demand")])
    with pytest.raises(ValueError):
        augment_context(graph, "demand", ["L1"])


def test_falsification_result_roundtrips_via_dict() -> None:
    result = FalsificationResult(n_nodes=3, n_edges=2, n_tests=4, given_violations=1,
                                 perm_violations=[2, 3], p_lmc=0.0, p_tpa=0.0,
                                 falsifiable=True, falsified=False, n_permutations=2)
    assert FalsificationResult(**dataclasses.asdict(result)) == result
