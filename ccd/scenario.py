"""Shared runner for CCD scenarios.

``run_scenario`` builds an observational dataset for a given ``SystemModel``, runs CCD,
and prints a mode-agnostic report: the nominal functionality, the critical level, the
selected degraded mode (the set of closed links), the causally-estimated functionality
``Phi-hat`` and a biased naive baseline, and the feasibility verdict. The per-scenario
entry points (``run_scenario_1.py``, ``run_scenario_2.py``) are thin wrappers that build
the appropriate ``SystemModel`` and call this.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from dowhy.gcm.config import disable_progress_bars

from ccd.ccd import CCDResult, ccd
from ccd.inference import naive_estimate
from ccd.simulator import generate_dataset
from ccd.system import SystemModel

disable_progress_bars()


def run_scenario(
    system: SystemModel,
    *,
    title: str,
    steps: int = 10_000,
    seed: int = 0,
    num_samples: int | None = None,
) -> CCDResult:
    """Run CCD on ``system`` and print a report. Returns the ``CCDResult``."""
    m = system.m
    print(title)
    print(f"System: gateway + m={m} servers + database\n")

    data = generate_dataset(system, steps=steps, seed=seed)
    phi_nominal = float(data["T"].mean())
    alpha = 0.5 * phi_nominal

    result = ccd(system, data, alpha=alpha, num_samples=num_samples)

    print(f"Nominal functionality   Phi(M)       = {phi_nominal:8.2f} req/s")
    print(f"Critical level          alpha=0.5Phi = {alpha:8.2f} req/s\n")

    if result.intervention is None:
        print("CCD: no degraded mode satisfies the containment/functionality criteria.")
        return result

    closed = sorted(result.intervention.variables)
    print(f"Selected degraded mode  u = {result.intervention}")
    print(f"  -> closes {len(closed)} link(s): {', '.join(closed)}\n")

    naive = naive_estimate(data, result.intervention.variables)
    print(f"Estimated functionality Phi-hat(M_u) [causal, do-intervention] = {result.phi:8.2f} req/s"
          f"  ({result.phi / phi_nominal:5.1%} of nominal)")
    print(f"Naive observational     E[T | links closed]                   = {naive:8.2f} req/s"
          f"  (biased: closures confounded with low workload)\n")

    verdict = "FEASIBLE (meets alpha)" if result.feasible else "INFEASIBLE (below alpha)"
    print(f"Result: {verdict}  ->  Phi-hat {'>=' if result.feasible else '<'} alpha")
    return result
