"""Unit tests for the 5G cloud-RAN system model and the generalized core hooks."""

import warnings
import networkx as nx
warnings.filterwarnings("ignore")
from ccd.ccd import ccd, select_intervention
from ccd.system.illustrative_example_system import IllustrativeExampleSystem
from ccd.system.five_g_system import FiveGSystem
from ccd.util.graph_util import check_criteria, blocked_exploits, descendants, intervened_graph
from ccd.util.scenario_util import _weighted_mean

S = FiveGSystem


def _core_mode() -> dict:
    return {"E2": 0, "NG3": 0, "QI1": 4}


def _d1_mode() -> dict:
    return {"AT3": 1, "E2": 0, "NG3": 0, "QI1": 4}


# --- graph structure ---------------------------------------------------------
def test_causal_graph_is_a_dag_with_the_full_chain():
    s = S()
    assert nx.is_directed_acyclic_graph(s.graph)
    for i in (1, 4):
        for d in ("U", "D"):
            assert s.graph.has_edge(s.UE(i, 2), s.L(i, 2, d))
            assert s.graph.has_edge(s.L(i, 2, d), s.Ladm(i, d))
            assert s.graph.has_edge("Uu", s.Ladm(i, d)) and s.graph.has_edge(s.QI(i), s.Ladm(i, d))
            assert s.graph.has_edge(s.Ladm(i, d), s.Cbar(i, d))
            assert s.graph.has_edge(s.Cbar(i, d), s.Chat(i, 3, d))
            assert s.graph.has_edge(s.AT(i), s.Chat(i, 3, d))
            assert s.graph.has_edge(s.Chat(i, 3, d), s.Ctil(i, 3, d))
            assert s.graph.has_edge(s.NG(3), s.Ctil(i, 3, d))
            assert s.graph.has_edge(s.Ctil(i, 3, d), s.C(i, d))
            assert s.graph.has_edge(s.C(i, d), s.T(i, d))
            for iface in ("A1", "N6", "Xn", "E2"):
                assert s.graph.has_edge(iface, s.T(i, d))


def test_roles_match_spec():
    s = S()
    assert s.operator_controlled == (
        {"Uu", "E2", "A1", "N6", "Xn"}
        | {s.QI(i) for i in range(1, 5)} | {s.AT(i) for i in range(1, 5)}
        | {s.NG(j) for j in range(1, 5)}
    )
    assert s.functionality == {s.T(i, d) for i in range(1, 5) for d in ("U", "D")} | {"E2", "A1"}
    assert {"E2", "A1"} <= (s.operator_controlled & s.functionality)   # X n J overlap
    assert s.attained == {"P0", "P1", "P2"}
    assert s.unattained == {"P3", "P4", "P5"}


def test_capability_edges_derive_Y():
    s = S()
    expected = {s.UE(1, k) for k in (1, 2, 3)} | {s.Chat(i, 3, d) for i in range(1, 5) for d in ("U", "D")}
    assert s.attacker_controlled == expected


def test_blocking_edges():
    s = S()
    assert blocked_exploits(s, {"E2"}) == {"EX3"}
    assert blocked_exploits(s, {"NG3"}) == {"EX4"}
    assert blocked_exploits(s, {"NG1", "NG2"}) == set()


def test_attack_and_causal_node_sets_are_disjoint():
    """The exploit 'EX2' must not collide with the causal interface 'E2'."""
    s = S()
    assert set(s.attack_graph.nodes).isdisjoint(set(s.graph.nodes))
    assert "EX2" in s.attack_graph and "E2" in s.graph
    assert "E2" not in s.attack_graph and "EX2" not in s.graph


def test_throughput_nodes_exclude_ue_and_noise():
    s = S()
    assert not any(n.startswith(("UE_", "eps_", "epsbar_", "gam_")) for n in s.throughput_nodes)
    assert s.T(1, "U") in s.throughput_nodes and s.QI(1) in s.throughput_nodes
    # in the fit subgraph L becomes a root (its UE parent is unobserved)
    assert s.throughput_graph().in_degree(s.L(1, 1, "U")) == 0


# --- value-aware deactivation ------------------------------------------------
def test_qi_threshold_deactivation_is_value_aware():
    s = S()
    g4 = intervened_graph(s, {"QI1": 4})
    assert [k for k in range(1, 11) if not g4.has_edge(s.L(1, k, "U"), s.Ladm(1, "U"))] == [1, 2, 3]
    assert [k for k in range(1, 11) if g4.has_edge(s.L(1, k, "U"), s.Ladm(1, "U"))] == [4, 5, 6, 7, 8, 9, 10]
    g2 = intervened_graph(s, {"QI1": 2})
    assert [k for k in range(1, 11) if not g2.has_edge(s.L(1, k, "U"), s.Ladm(1, "U"))] == [1]


def test_attachment_deactivation_keeps_only_chosen_cu():
    s = S()
    g = intervened_graph(s, {"AT3": 1})
    for d in ("U", "D"):
        assert g.has_edge(s.Cbar(3, d), s.Chat(3, 1, d))
        assert not g.has_edge(s.Cbar(3, d), s.Chat(3, 2, d))
        assert not g.has_edge(s.Cbar(3, d), s.Chat(3, 3, d))


def test_midhaul_product_deactivation():
    s = S()
    g = intervened_graph(s, {"NG3": 0})
    for i in range(1, 5):
        for d in ("U", "D"):
            assert not g.has_edge(s.Chat(i, 3, d), s.Ctil(i, 3, d))


# --- mode selection ----------------------------------------------------------
def test_selects_expected_d1_mode():
    s = S()
    u = select_intervention(s)
    assert u is not None
    assert u.variables == _d1_mode()          # core {QI1,E2,NG3} + augmented AT3


def test_d1_satisfies_criteria():
    assert check_criteria(S(), _d1_mode()).ok


def test_core_mode_is_minimal():
    s = S()
    for drop in _core_mode():
        reduced = {k: v for k, v in _core_mode().items() if k != drop}
        assert not check_criteria(s, reduced).ok


def test_augment_mode_is_criteria_neutral():
    s = S()
    core = check_criteria(s, _core_mode())
    aug = check_criteria(s, _d1_mode())
    assert core.ok and aug.ok
    assert core.reachable == aug.reachable


def test_cost_ordering_keeps_targeted_qi_over_global_uu():
    """Without the degradation-cost tie-break the greedy would keep the global Uu (killing
    all admission -> infeasible); the cost order keeps the targeted QI1 instead."""
    u = select_intervention(S())
    assert "QI1" in u.variables and "Uu" not in u.variables and "N6" not in u.variables


# --- numeric round-trip (invokes DoWhy) --------------------------------------
def test_reference_sim_roundtrip_is_feasible_and_accurate():
    s = S()
    data = s.generate_dataset(steps=3000, seed=1)
    weights = s.functionality_weights
    phi_nominal = _weighted_mean(data, weights)
    alpha = 0.5 * phi_nominal

    result = ccd(s, data, alpha=alpha, num_samples=3000)

    assert result.intervention is not None
    assert result.intervention.variables == _d1_mode()
    assert result.feasible
    # partial degradation: below nominal but comfortably above the critical level
    assert alpha < result.phi < phi_nominal


# --- base-class hook identity (regression guard for the core generalization) --
def test_base_degraded_value_is_zero():
    assert IllustrativeExampleSystem(3).degraded_value("N1") == 0


def test_base_augment_mode_is_identity():
    s = IllustrativeExampleSystem(3)
    do = {"N1": 0, "M1": 0}
    assert s.augment_mode(do) == do


def test_base_deactivated_edges_still_cuts_product_output():
    s = IllustrativeExampleSystem(3)
    g = intervened_graph(s, {"N1": 0})
    assert not g.has_edge("Tt1", "Th1")     # AND deactivation via product_functions
    assert "T" not in descendants(g, {"Tt1"})


def test_base_functionality_weights_is_single_throughput():
    assert dict(IllustrativeExampleSystem(3).functionality_weights) == {"T": 1.0}
