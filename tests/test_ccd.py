"""Unit Tests for CCD."""

import copy
import time
import warnings
import numpy as np
import pytest
warnings.filterwarnings("ignore")
from ccd.ccd import ccd, select_intervention
from ccd.graph_ops import check_criteria, intervened_graph, descendants
from ccd.perturb import (
    attacker_capabilities,
    evaluate_structural,
    overspecify,
    overspecify_privileges,
    perturb_detection,
    underspecify,
    underspecify_privileges,
)
from ccd.simulator import generate_dataset
from ccd.illustrative_example_system import E, IllustrativeExampleSystem


def expected_mode(m: int) -> set:
    """CCD should isolate the compromised n_1: close N_1, M_1, and all A_i (i>=2)."""
    return {"N1", "M1"} | {f"A{i}" for i in range(2, m + 1)}


def patched_system(m: int) -> IllustrativeExampleSystem:
    """Scenario 2: operators have patched the exploits E_2..E_{m+1}."""
    return IllustrativeExampleSystem(m, patched_exploits=frozenset(E(i) for i in range(2, m + 2)))


def evicted_system(m: int) -> IllustrativeExampleSystem:
    """Scenario 3: the attacker has been evicted from n_1 (Y = {})."""
    return IllustrativeExampleSystem(m, attacker_evicted=True)


# --- structural tests (fast, graph-only) ------------------------------------
@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_selects_isolate_n1_mode(m):
    u = select_intervention(IllustrativeExampleSystem(m))
    assert u is not None
    assert set(u.variables) == expected_mode(m)
    assert all(v == 0 for v in u.variables.values())   # every selected link is closed


@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_selected_mode_satisfies_criteria(m):
    system = IllustrativeExampleSystem(m)
    u = select_intervention(system)
    res = check_criteria(system, u.variables)
    assert res.contained, "no unattained privilege may be reachable by the attacker"
    assert res.functional, "throughput T must not be reachable by the attacker"


@pytest.mark.parametrize("drop", ["N1", "M1", "A2"])
def test_mode_is_minimal_dropping_any_link_breaks_a_criterion(drop):
    """Removing any single link from the selected mode must violate a criterion,
    which shows the selected mode is minimal (Algorithm 1, lines 5-8)."""
    system = IllustrativeExampleSystem(5)
    u = select_intervention(system)
    reduced = {v: 0 for v in u.variables if v != drop}
    assert not check_criteria(system, reduced).ok


def test_no_intervention_is_infeasible():
    """With no links closed, the attacker reaches both unattained privileges and T."""
    system = IllustrativeExampleSystem(5)
    res = check_criteria(system, {})
    assert not res.contained
    assert not res.functional


def test_and_deactivation_cuts_attacker_from_throughput():
    """do(N_1=0) must remove the Tt_1 -> Th_1 edge so T leaves the attacker's reach."""
    system = IllustrativeExampleSystem(5)
    # before: attacker-controlled Tt_1 reaches T
    assert "T" in descendants(system.graph, {"Tt1"})
    g_u = intervened_graph(system, {"N1": 0})
    assert not g_u.has_edge("Tt1", "Th1")
    assert "T" not in descendants(g_u, {"Tt1"})


def test_runtime_is_polynomial_and_practical():
    """Graph-only CCD is polynomial in m (paper's bound O(|X|(|V|+|U|+|E|)), i.e. ~m^2).
    Assert it stays fast and grows no worse than roughly quadratically."""
    def timed(m):
        system = IllustrativeExampleSystem(m)
        best = min(  # take the min of a few runs to reduce timing noise
            (_time_once(system) for _ in range(3)),
        )
        return best

    select_intervention(IllustrativeExampleSystem(10))  # warm up
    t_small = timed(40)
    t_large = timed(160)   # 4x the size -> ~16x under quadratic, ~64x under cubic

    assert t_large < 5.0, "m=160 should still be fast (well under a few seconds)"
    # rule out cubic-or-worse growth (with slack for measurement noise)
    assert t_large < 32 * t_small + 0.1


def _time_once(system):
    t = time.perf_counter()
    select_intervention(system)
    return time.perf_counter() - t


# --- numeric feasibility (invokes DoWhy causal inference) --------------------
@pytest.mark.parametrize("m", [5, 10])
def test_degraded_mode_is_feasible_and_estimate_matches_analytic(m):
    system = IllustrativeExampleSystem(m)
    data = generate_dataset(system, steps=6000, seed=1)

    phi_nominal = float(data["T"].mean())
    alpha = 0.5 * phi_nominal

    # analytic interventional throughput: server 1 off, others nominal
    analytic = sum(data[f"Th{i}"].mean() for i in range(2, m + 1))

    result = ccd(system, data, alpha=alpha, num_samples=6000)

    assert result.intervention is not None
    assert set(result.intervention.variables) == expected_mode(m)
    assert result.feasible, f"Phi-hat={result.phi:.1f} should meet alpha={alpha:.1f}"
    # causal estimate should be close to the analytic (m-1)/m throughput
    assert result.phi == pytest.approx(analytic, rel=0.05)


# --- Scenario 2: exploits E_2..E_{m+1} patched (recovery step D_2) -----------
@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_patched_selects_only_isolate_gateway(m):
    """With lateral movement and DB access patched, CCD only needs to close N_1."""
    u = select_intervention(patched_system(m))
    assert u is not None
    assert set(u.variables) == {"N1"}


@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_patched_mode_satisfies_criteria(m):
    system = patched_system(m)
    res = check_criteria(system, select_intervention(system).variables)
    assert res.contained and res.functional


@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_patched_mode_is_less_restrictive_than_scenario_1(m):
    """The D_2 mode must be a strict subset of the D_1 mode (fewer links closed)."""
    d1 = set(select_intervention(IllustrativeExampleSystem(m)).variables)
    d2 = set(select_intervention(patched_system(m)).variables)
    assert d2 < d1


@pytest.mark.parametrize("m", [5, 10])
def test_patched_mode_is_feasible_and_matches_analytic(m):
    system = patched_system(m)
    data = generate_dataset(system, steps=6000, seed=1)

    alpha = 0.5 * float(data["T"].mean())
    # closing only N_1 zeroes n_1's throughput; servers 2..m are nominal
    analytic = sum(data[f"Th{i}"].mean() for i in range(2, m + 1))

    result = ccd(system, data, alpha=alpha, num_samples=6000)

    assert result.intervention is not None
    assert set(result.intervention.variables) == {"N1"}
    assert result.feasible
    assert result.phi == pytest.approx(analytic, rel=0.05)


# --- Scenario 3: attacker evicted, Y = {} (full restore D_3) -----------------
@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_evicted_has_empty_attacker_set(m):
    assert evicted_system(m).attacker_controlled == set()


@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_evicted_selects_empty_intervention(m):
    """With no attacker, no degradation is needed: CCD closes no links."""
    u = select_intervention(evicted_system(m))
    assert u is not None
    assert set(u.variables) == set()
    assert check_criteria(evicted_system(m), u.variables).ok


@pytest.mark.parametrize("m", [5, 10])
def test_evicted_restores_full_functionality(m):
    system = evicted_system(m)
    data = generate_dataset(system, steps=6000, seed=1)
    phi_nominal = float(data["T"].mean())
    alpha = 0.5 * phi_nominal

    result = ccd(system, data, alpha=alpha, num_samples=6000)

    assert result.intervention is not None
    assert set(result.intervention.variables) == set()
    assert result.feasible
    # empty intervention (do()) reproduces the full nominal throughput
    assert result.phi == pytest.approx(phi_nominal, rel=0.05)


def test_recovery_progression_is_monotone():
    """D_1 (containment) superset D_2 (patched) superset D_3 (evicted, empty)."""
    m = 10
    d1 = set(select_intervention(IllustrativeExampleSystem(m)).variables)
    d2 = set(select_intervention(patched_system(m)).variables)
    d3 = set(select_intervention(evicted_system(m)).variables)
    assert d1 > d2 > d3
    assert d3 == set()


# --- Sensitivity to misspecification (ccd/perturb.py) ------------------------
@pytest.mark.parametrize("m", [2, 5, 10])
def test_attacker_capabilities_matches_true_Y(m):
    assert attacker_capabilities(m, {"P0", "P1"}) == IllustrativeExampleSystem(m).attacker_controlled


@pytest.mark.parametrize("perturb", [underspecify, overspecify, perturb_detection,
                                     underspecify_privileges, overspecify_privileges])
def test_rho_zero_leaves_mode_valid(perturb):
    """With no perturbation, CCD's mode is valid in the true model."""
    system = IllustrativeExampleSystem(10)
    out = evaluate_structural(system, perturb(system, 0.0, np.random.RandomState(0)))
    assert out.valid


def test_under_detection_breaks_containment():
    """Missing the attacker's foothold leaves CCD blind; the mode is invalid in truth."""
    system = IllustrativeExampleSystem(10)
    out = evaluate_structural(system, underspecify_privileges(system, 0.1, np.random.RandomState(0)))
    assert not out.valid


@pytest.mark.parametrize("seed", range(20))
def test_over_detection_stays_safe(seed):
    """Because containment protects all lateral targets, believing extra servers are
    compromised makes CCD isolate them (conservative) rather than concede -- still valid."""
    system = IllustrativeExampleSystem(10)
    out = evaluate_structural(system, overspecify_privileges(system, 0.3, np.random.RandomState(seed)))
    assert out.valid


def test_containment_targets_are_lateral_privileges():
    """Lateral targets (P_2..P_{m+1}) are protected regardless of P-tilde."""
    system = IllustrativeExampleSystem(6)
    assert system.lateral_targets == {f"P{i}" for i in range(2, 8)}
    assert system.lateral_targets <= system.containment_targets


def test_overspecification_never_silently_unsafe():
    """Spurious edges make CCD conservative, never silently unsafe (no containment failure)."""
    system = IllustrativeExampleSystem(10)
    for seed in range(50):
        out = evaluate_structural(system, overspecify(system, 0.3, np.random.RandomState(seed)))
        assert not out.silent_containment_failure


def test_missing_functionality_edge_causes_silent_functionality_failure():
    """Dropping Tt1->Th1 hides the attacker's path to T, so CCD omits N1 and functionality
    fails in the true model."""
    system = IllustrativeExampleSystem(10)
    mis = copy.deepcopy(system)
    mis.graph.remove_edge("Tt1", "Th1")
    mis.product_functions["Th1"] = mis.product_functions["Th1"] - {"Tt1"}
    assert "N1" not in select_intervention(mis).variables
    assert evaluate_structural(system, mis).silent_functionality_failure


def test_missing_attack_edge_causes_silent_containment_failure():
    """Dropping E2->P2 hides the lateral-movement path, so CCD omits A2 and containment
    fails in the true model."""
    system = IllustrativeExampleSystem(10)
    mis = copy.deepcopy(system)
    mis.graph.remove_edge("E2", "P2")
    mis.product_functions["P2"] = mis.product_functions["P2"] - {"E2"}
    assert "A2" not in select_intervention(mis).variables
    assert evaluate_structural(system, mis).silent_containment_failure
