"""Tests for ``evaluate_intervention`` (fixed-mode evaluation of an externally supplied mode)."""

from __future__ import annotations
import math
import pytest
from ccd.ccd import evaluate_intervention
from ccd.system.it_system import ITSystem
from ccd.util.graph_util import check_criteria


def test_evaluate_selected_mode_matches_analytic_and_is_feasible():
    """Evaluating the known D_1 mode reproduces the ccd() estimate: contained,
    functional, and Phi-hat close to the analytic (m-1)/m throughput."""
    m = 5
    system = ITSystem(m)
    data = system.generate_dataset(steps=6000, seed=1)
    phi_nominal = float(data["T"].mean()) + system.KAPPA * (m - 1)
    alpha = 0.5 * phi_nominal
    do = {"N1": 0, "M1": 0} | {f"A{i}": 0 for i in range(2, m + 1)}
    analytic = sum(data[f"Th{i}"].mean() for i in range(2, m + 1))

    result = evaluate_intervention(system, data, do, alpha=alpha, num_samples=6000)

    assert result.criteria.contained and result.criteria.functional
    assert result.feasible, f"Phi-hat={result.phi:.1f} should meet alpha={alpha:.1f}"
    assert result.phi == pytest.approx(analytic, rel=0.05)
    assert dict(result.intervention.variables) == do
    direct = check_criteria(system, do)
    assert (result.criteria.contained, result.criteria.functional) == (direct.contained,
                                                                       direct.functional)


def test_evaluate_uncontained_mode_reports_phi_and_feasible():
    """An uncontained proposal (do(N1=0) blocks no exploit) still gets a finite
    Phi-hat; only the criteria verdicts flag it."""
    system = ITSystem(2)
    data = system.generate_dataset(steps=1000, seed=0)
    phi_nominal = float(data["T"].mean()) + system.KAPPA
    alpha = 0.5 * phi_nominal

    result = evaluate_intervention(system, data, {"N1": 0}, alpha=alpha, num_samples=300)

    assert not result.criteria.contained
    assert math.isfinite(result.phi)
    assert result.feasible == (result.phi >= alpha)
    assert result.criteria.violating_exploits
