"""
Shared runner for CCD scenarios
"""

from __future__ import annotations
import math
import warnings

warnings.filterwarnings("ignore")

import pandas as pd
from dowhy.gcm.config import disable_progress_bars
from ccd.ccd import ccd
from ccd.dto.ccd_result import CCDResult
from ccd.util.graph_util import blocked_exploits
from ccd.util.inference_util import naive_estimate, policy_phi, split_policy_weights
from ccd.system.system_model import SystemModel

disable_progress_bars()


def _weighted_mean(data: pd.DataFrame, weights) -> float:
    """The nominal functionality Phi(M) = sum_c w_c * E[c] over the weighted columns."""
    return sum(w * float(data[c].mean()) for c, w in weights.items() if c in data.columns)


def nominal_phi(system: SystemModel, data: pd.DataFrame) -> float:
    """Phi(M) nominal = data-estimable terms from ``D`` + policy terms at their nominal value 1."""
    estimable, policy = split_policy_weights(system.functionality_weights, system.operator_controlled)
    return _weighted_mean(data, estimable) + policy_phi(policy, {})


def run_ccd_on_data(
    system: SystemModel,
    data: pd.DataFrame,
    *,
    title: str,
    num_samples: int | None = None,
    unit: str = "req/s",
) -> CCDResult:
    """Run CCD on ``system`` with dataset ``data`` and print a report. Returns the ``CCDResult``."""
    print(title)
    m = getattr(system, "m", None)
    if m is not None:
        print(f"System: gateway + m={m} servers + database\n")

    estimable, policy = split_policy_weights(system.functionality_weights, system.operator_controlled)
    phi_nominal = nominal_phi(system, data)
    frac = system.alpha_fraction
    alpha = frac * phi_nominal

    result = ccd(system, data, alpha=alpha, num_samples=num_samples)

    print(f"Nominal functionality   Phi(M)        = {phi_nominal:8.2f} {unit}")
    print(f"Critical level          alpha={frac:g}Phi = {alpha:8.2f} {unit}\n")

    if result.intervention is None:
        print("CCD: no degraded mode satisfies the containment/functionality criteria.")
        return result

    applied = sorted(result.intervention.variables)
    if applied:
        blocked = sorted(blocked_exploits(system, set(result.intervention.variables)))
        print(f"Selected degraded mode  u = {result.intervention}")
        print(f"  -> intervenes on {len(applied)} variable(s): {', '.join(applied)}")
        print(f"  -> blocks {len(blocked)} exploit(s): {', '.join(blocked) if blocked else '-'}\n")
    else:
        print(f"Selected mode           u = {result.intervention}  (no interventions)")
        print("  -> full functionality restored: no degradation needed.\n")

    naive = naive_estimate(data, result.intervention.variables, weights=estimable)
    if not math.isnan(naive):
        naive += policy_phi(policy, result.intervention.variables)
    print(f"Estimated functionality Phi-hat(M_u) [causal, do-intervention] = {result.phi:8.2f} {unit}"
          f"  ({result.phi / phi_nominal:5.1%} of nominal)")
    if math.isnan(naive):
        print("Naive observational     E[Phi | degraded config]              =      n/a"
              "         (this exact degraded config never occurs in nominal data:")
        print("                                                                          "
              " observational conditioning is undefined, so causal inference is required)\n")
    else:
        print(f"Naive observational     E[Phi | degraded config]              = {naive:8.2f} {unit}"
              f"  (biased: interventions confounded with low load)\n")

    verdict = "FEASIBLE (meets alpha)" if result.feasible else "INFEASIBLE (below alpha)"
    print(f"Result: {verdict}  ->  Phi-hat {'>=' if result.feasible else '<'} alpha")
    return result


def run_scenario(
    system: SystemModel,
    *,
    title: str,
    steps: int = 10_000,
    seed: int = 0,
    num_samples: int | None = None,
    unit: str = "req/s",
) -> CCDResult:
    """Simulate ``D`` for ``system``, run CCD, and print a report. Returns the ``CCDResult``."""
    data = system.generate_dataset(steps=steps, seed=seed)
    return run_ccd_on_data(system, data, title=title, num_samples=num_samples, unit=unit)
