"""
Tests for the construction of the causal graph
"""

from __future__ import annotations
import os
import networkx as nx
import pandas as pd
import pytest
from ccd.discovery.causal.build_g import build_g
from ccd.discovery.evaluation.graph_diff import diff_graphs
from ccd.system.it_testbed_system import ITTestbedSystem

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IT_DATA = os.path.join(_REPO_ROOT, "testbeds", "it_system", "data", "dataset.csv")

pytestmark = pytest.mark.skipif(not os.path.exists(_IT_DATA),
                                reason="IT testbed dataset not collected")


@pytest.fixture(scope="module")
def it_data() -> pd.DataFrame:
    return pd.read_csv(_IT_DATA)


@pytest.fixture(scope="module")
def it_descriptor(testbed_loader):
    return testbed_loader("it_system", "descriptor").build_descriptor(10)


def test_build_g_reconstructs_it_graph_exactly(it_descriptor, it_data):
    construction = build_g(it_descriptor, it_data)
    target = ITTestbedSystem(10).throughput_graph()
    diff = diff_graphs(construction.graph, target)
    assert diff.exact, f"missing={diff.missing} extra={diff.extra}"
    assert diff.isomorphic
    assert diff.precision == 1.0 and diff.recall == 1.0


def test_build_g_uses_symmetry_reduction(it_descriptor, it_data):
    construction = build_g(it_descriptor, it_data)
    assert construction.representative == {"srv": "1"}
    assert {"L1", "M1", "N1", "Tt1"} <= set(construction.learn_nodes)
    assert "W" not in construction.learn_nodes
    assert not any(n.endswith(("2", "3", "4", "5")) for n in construction.learn_nodes)
    assert ("W", "L1") in construction.context_edges
    assert ("N1", "Th1") in construction.mechanism_edges


def test_build_g_context_root_recovers_load_edges(it_descriptor, it_data):
    construction = build_g(it_descriptor, it_data)
    for i in range(1, 11):
        assert construction.graph.has_edge(f"L{i}", f"Tt{i}")
        assert construction.graph.has_edge(f"N{i}", f"Tt{i}")
        assert construction.graph.has_edge(f"M{i}", f"Tt{i}")


def test_constructed_g_not_falsified(it_descriptor, it_data):
    from ccd.discovery.causal.validation import validate_graph
    construction = build_g(it_descriptor, it_data)
    summary = validate_graph(construction.graph, it_data, n_permutations=20)
    assert summary.falsified is False


def test_build_g_scales_down_to_small_m(testbed_loader, it_data):
    desc = testbed_loader("it_system", "descriptor").build_descriptor(3)
    construction = build_g(desc, it_data)
    target = ITTestbedSystem(3).throughput_graph()
    target_sub: nx.DiGraph = target.subgraph(construction.graph.nodes).copy()
    assert set(construction.graph.edges()) == set(target_sub.edges())
