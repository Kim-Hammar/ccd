"""Implementation of Causal Controlled Degradation (CCD)"""

from __future__ import annotations
from typing import Mapping, Optional
import pandas as pd
from ccd.dto.ccd_result import CCDResult
from ccd.dto.evaluation_result import EvaluationResult
from ccd.dto.intervention import Intervention
from ccd.system.system_model import SystemModel
from ccd.util.graph_util import ancestors, check_criteria
from ccd.util.inference_util import estimate_phi, policy_phi, split_policy_weights
from ccd.util.sort_util import sort_key


def select_intervention(system: SystemModel) -> Optional[Intervention]:
    """Graph-only mode selection (lines 1-9 of the CCD algorithm)."""
    gamma = system.attack_graph
    unconceded = {
        e for e in system.exploits
        if e in gamma and not set(gamma.successors(e)) <= system.attained
    }
    candidate_vars = system.operator_controlled & ancestors(system.graph, system.functionality)
    for required, e in system.blocking_edges:
        if e in unconceded:
            candidate_vars |= required

    def do_of(vars_: set) -> dict:
        return {v: system.degraded_value(v) for v in vars_}

    active = set(candidate_vars)
    if not check_criteria(system, do_of(active)).ok:
        return None

    for var in sorted(candidate_vars, key=lambda v: (-system.degradation_cost(v), sort_key(v))):
        if var not in active:
            continue
        reduced = active - {var}
        if check_criteria(system, do_of(reduced)).ok:
            active = reduced

    mode = system.augment_mode({v: system.degraded_value(v) for v in sorted(active, key=sort_key)})
    return Intervention(mode)


def evaluate_intervention(
    system: SystemModel,
    data: pd.DataFrame,
    do: Mapping[str, int],
    *,
    alpha: float,
    num_samples: Optional[int] = None,
    **inference_kwargs,
) -> EvaluationResult:
    """Evaluate a fixed intervention"""
    criteria = check_criteria(system, dict(do))

    estimable, policy = split_policy_weights(system.functionality_weights, system.operator_controlled)
    phi = estimate_phi(
        data,
        system.throughput_graph(),
        do,
        weights=estimable,
        num_samples=num_samples,
        product_functions=system.product_functions if system.use_known_product_mechanisms else None,
        **inference_kwargs,
    ) + policy_phi(policy, do)
    return EvaluationResult(intervention=Intervention(dict(do)), phi=phi, alpha=alpha,
                            feasible=phi >= alpha, criteria=criteria)


def ccd(
    system: SystemModel,
    data: pd.DataFrame,
    alpha: float,
    num_samples: Optional[int] = None,
    **inference_kwargs,
) -> CCDResult:
    """Run CCD"""
    u = select_intervention(system)
    if u is None:
        return CCDResult(intervention=None, phi=float("nan"), alpha=alpha, feasible=False)

    ev = evaluate_intervention(system, data, u.variables, alpha=alpha,
                               num_samples=num_samples, **inference_kwargs)
    return CCDResult(intervention=u, phi=ev.phi, alpha=alpha, feasible=ev.feasible)
