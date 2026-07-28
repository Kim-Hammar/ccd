"""Unit tests for the synthetic random two-layer model generator (scalability benchmark)."""

import warnings
import networkx as nx
import pytest
warnings.filterwarnings("ignore")
from ccd.ccd import select_intervention
from ccd.util.graph_util import check_criteria
from ccd.util.synthetic import random_system


def test_causal_graph_is_a_dag_of_the_requested_size():
    s = random_system(120, seed=0)
    assert s.graph.number_of_nodes() == 120
    assert nx.is_directed_acyclic_graph(s.graph)


def test_attack_and_causal_node_sets_are_disjoint():
    s = random_system(120, seed=1)
    assert set(s.attack_graph.nodes).isdisjoint(set(s.graph.nodes))
    assert s.privileges and s.exploits
    assert s.attained <= s.privileges


def test_roles_are_populated_and_consistent():
    s = random_system(200, seed=2)
    assert s.operator_controlled <= set(s.graph.nodes)
    assert s.functionality <= set(s.graph.nodes)
    assert s.attacker_controlled <= set(s.graph.nodes)   # derived Y via capability edges


def test_larger_n_gives_a_larger_two_layer_graph():
    small = random_system(80, seed=0)
    large = random_system(320, seed=0)
    small_size = small.graph.number_of_nodes() + small.attack_graph.number_of_nodes()
    large_size = large.graph.number_of_nodes() + large.attack_graph.number_of_nodes()
    assert large_size > small_size


@pytest.mark.parametrize("n", [50, 150, 400])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_select_intervention_runs_and_is_feasible(n: int, seed: int):
    # generation is tuned so a containing mode exists (every exploit blockable, Y an
    # operator-controllable ancestor set of J), so mode selection returns a valid cover
    s = random_system(n, seed=seed)
    u = select_intervention(s)
    assert u is not None
    assert check_criteria(s, u.variables).ok


def test_reproducible_for_a_fixed_seed():
    a = random_system(100, seed=7)
    b = random_system(100, seed=7)
    assert set(a.graph.edges) == set(b.graph.edges)
    assert a.operator_controlled == b.operator_controlled
    assert a.blocking_edges == b.blocking_edges


def test_rejects_too_small_n():
    with pytest.raises(ValueError):
        random_system(3)


def test_dataset_and_weights_support_inference():
    # the synthetic DGP yields a column per causal node and unit weights on J, so the
    # inference benchmark can fit an SCM and estimate Phi (values are arbitrary)
    s = random_system(60, seed=0)
    data = s.generate_dataset(steps=200, seed=0)
    assert set(data.columns) == s.throughput_nodes
    assert len(data) == 200
    assert set(s.functionality_weights) == s.functionality
    assert all(w == 1.0 for w in s.functionality_weights.values())
