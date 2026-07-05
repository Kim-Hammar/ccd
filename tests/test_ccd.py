"""Tests for the CCD illustrative example.

Structural tests (mode selection + graphical criteria) are cheap and run for a range of
``m`` including large systems. The numeric feasibility test invokes DoWhy causal
inference and is therefore run only for moderate ``m``.
"""

import time
import warnings
import pytest
warnings.filterwarnings("ignore")
from ccd.ccd import ccd, select_intervention
from ccd.graph_ops import check_criteria, intervened_graph, descendants
from ccd.simulator import generate_dataset
from ccd.system import SystemModel


def expected_mode(m: int) -> set:
    """CCD should isolate the compromised n_1: close N_1, M_1, and all A_i (i>=2)."""
    return {"N1", "M1"} | {f"A{i}" for i in range(2, m + 1)}


# --- structural tests (fast, graph-only) ------------------------------------
@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_selects_isolate_n1_mode(m):
    u = select_intervention(SystemModel(m))
    assert u is not None
    assert set(u.variables) == expected_mode(m)
    assert all(v == 0 for v in u.variables.values())   # every selected link is closed


@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_selected_mode_satisfies_criteria(m):
    system = SystemModel(m)
    u = select_intervention(system)
    res = check_criteria(system, u.variables)
    assert res.contained, "no unattained privilege may be reachable by the attacker"
    assert res.functional, "throughput T must not be reachable by the attacker"


@pytest.mark.parametrize("drop", ["N1", "M1", "A2"])
def test_mode_is_minimal_dropping_any_link_breaks_a_criterion(drop):
    """Removing any single link from the selected mode must violate a criterion,
    which shows the selected mode is minimal (Algorithm 1, lines 5-8)."""
    system = SystemModel(5)
    u = select_intervention(system)
    reduced = {v: 0 for v in u.variables if v != drop}
    assert not check_criteria(system, reduced).ok


def test_no_intervention_is_infeasible():
    """With no links closed, the attacker reaches both unattained privileges and T."""
    system = SystemModel(5)
    res = check_criteria(system, {})
    assert not res.contained
    assert not res.functional


def test_and_deactivation_cuts_attacker_from_throughput():
    """do(N_1=0) must remove the Tt_1 -> Th_1 edge so T leaves the attacker's reach."""
    system = SystemModel(5)
    # before: attacker-controlled Tt_1 reaches T
    assert "T" in descendants(system.graph, {"Tt1"})
    g_u = intervened_graph(system, {"N1": 0})
    assert not g_u.has_edge("Tt1", "Th1")
    assert "T" not in descendants(g_u, {"Tt1"})


def test_runtime_is_polynomial_and_practical():
    """Graph-only CCD is polynomial in m (paper's bound O(|X|(|V|+|U|+|E|)), i.e. ~m^2).
    Assert it stays fast and grows no worse than roughly quadratically."""
    def timed(m):
        system = SystemModel(m)
        best = min(  # take the min of a few runs to reduce timing noise
            (_time_once(system) for _ in range(3)),
        )
        return best

    select_intervention(SystemModel(10))  # warm up
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
    system = SystemModel(m)
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
