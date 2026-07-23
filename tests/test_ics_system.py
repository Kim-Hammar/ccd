"""Unit tests for the industrial control system (Tennessee Eastman) model."""

import warnings
import networkx as nx
warnings.filterwarnings("ignore")
from ccd.ccd import ccd, select_intervention
from ccd.system.ics_system import IcsSystem
from ccd.util.graph_util import check_criteria, blocked_exploits, intervened_graph, descendants
from ccd.util.scenario_util import _weighted_mean

S = IcsSystem


def _d1_mode() -> dict:
    return {"W": 0, "G2": 0, "Chat": 0}


# --- graph structure ---------------------------------------------------------
def test_causal_graph_is_a_dag_with_the_known_products():
    s = S()
    assert nx.is_directed_acyclic_graph(s.graph)
    assert s.graph.has_edge("W", "I")
    assert s.graph.has_edge("G2", "Ctil") and s.graph.has_edge("C", "Ctil")
    assert s.graph.has_edge("Chat", "V") and s.graph.has_edge("Ctil", "V")
    for parent in ("V", "A", "U"):
        assert s.graph.has_edge(parent, "P")
    assert s.graph.has_edge("P", "S")


def test_roles_match_spec():
    s = S()
    assert s.operator_controlled == {"W", "G2", "Chat"}
    assert s.functionality == {"I", "S"}
    assert "W" in (s.operator_controlled & s.attacker_controlled)   # X n Y overlap
    assert s.attained == {"P0", "P1", "P3"}
    assert s.unattained == {"P2", "P4"}


def test_capability_edges_derive_Y():
    s = S()
    assert s.attacker_controlled == {"W", "C"}       # W via P1, C via P3


def test_blocking_edges_gateway_blocks_both_lateral_movements():
    s = S()
    assert blocked_exploits(s, {"W"}) == {"E1"}
    assert blocked_exploits(s, {"G2"}) == {"E2", "E3"}   # closed gateway blocks both
    assert blocked_exploits(s, {"Chat"}) == {"E4"}


def test_attack_and_causal_node_sets_are_disjoint():
    s = S()
    assert set(s.attack_graph.nodes).isdisjoint(set(s.graph.nodes))


def test_throughput_nodes_are_the_observed_variables():
    s = S()
    assert s.throughput_nodes == {"W", "I", "G2", "Chat", "C", "Ctil", "V", "P", "S"}
    # the exogenous actuation/disturbance are unobserved -> P is a root in the fit subgraph
    assert "A" not in s.throughput_nodes and "U" not in s.throughput_nodes
    assert s.throughput_graph().in_degree("P") == 1     # only V observed among P's parents


# --- known-product deactivation (base hook, no override) ---------------------
def test_gateway_closure_deactivates_the_control_state_product():
    s = S()
    g = intervened_graph(s, {"G2": 0})
    assert not g.has_edge("C", "Ctil")               # Ctil = G2*C constant 0 -> loses parents
    assert "S" not in descendants(g, {"C"})          # attacker command severed from safety


def test_local_control_deactivates_the_valve_product():
    s = S()
    g = intervened_graph(s, {"Chat": 0})
    assert not g.has_edge("Ctil", "V")               # V = Chat*Ctil constant 0 -> loses parents


# --- mode selection ----------------------------------------------------------
def test_selects_expected_d1_mode():
    s = S()
    u = select_intervention(s)
    assert u is not None
    assert u.variables == _d1_mode()


def test_d1_satisfies_criteria():
    assert check_criteria(S(), _d1_mode()).ok


def test_d1_is_minimal():
    s = S()
    for drop in _d1_mode():
        reduced = {k: v for k, v in _d1_mode().items() if k != drop}
        assert not check_criteria(s, reduced).ok      # every intervention is required


def test_no_overridden_hooks_beyond_functionality_weights():
    """Regression guard: the ICS uses the base core hooks unchanged (only Phi differs)."""
    s = S()
    assert s.degraded_value("G2") == 0                # base binary closure
    assert s.augment_mode(_d1_mode()) == _d1_mode()   # base identity
    assert s.degradation_cost("W") == 0.0             # base
    assert dict(s.functionality_weights) == {"I": 1.0, "S": 1.0}


# --- numeric round-trip (invokes DoWhy) --------------------------------------
def test_reference_sim_roundtrip_is_feasible_and_partial():
    s = S()
    data = s.generate_dataset(steps=3000, seed=1)
    # the joint degraded config never occurs in nominal data -> naive is undefined,
    # causal identification is required
    assert int(((data["W"] == 0) & (data["G2"] == 0) & (data["Chat"] == 0)).sum()) == 0

    weights = s.functionality_weights
    phi_nominal = _weighted_mean(data, weights)
    alpha = 0.5 * phi_nominal

    result = ccd(s, data, alpha=alpha, num_samples=3000)

    assert result.intervention is not None
    assert result.intervention.variables == _d1_mode()
    assert result.feasible
    assert alpha < result.phi < phi_nominal          # partial degradation, above critical
