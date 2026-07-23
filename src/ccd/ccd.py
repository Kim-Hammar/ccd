"""Implementation of Causal Controlled Degradation (CCD)"""

from __future__ import annotations
from typing import Optional
import pandas as pd
from ccd.dto.ccd_result import CCDResult
from ccd.dto.intervention import Intervention
from ccd.system.system_model import SystemModel
from ccd.util.graph_util import ancestors, check_criteria
from ccd.util.inference_util import estimate_phi
from ccd.util.sort_util import sort_key


def select_intervention(system: SystemModel) -> Optional[Intervention]:
    """Graph-only mode selection (lines 1-9 of the CCD algorithm). Returns None (bottom)
    if the full candidate intervention already violates a criterion."""
    # candidate set X' = (X n an_G(J)) u U{X'' | (X'', E) in B, ch_Gamma(E) not<= P-tilde}
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

    # minimality: drop any variable whose removal keeps both criteria satisfied,
    # attempting the costliest (degradation_cost) first when several minimal covers exist
    for var in sorted(candidate_vars, key=lambda v: (-system.degradation_cost(v), sort_key(v))):
        if var not in active:
            continue
        reduced = active - {var}
        if check_criteria(system, do_of(reduced)).ok:
            active = reduced

    # apply criteria-neutral, functionality-restoring augmentations before the Phi check
    mode = system.augment_mode({v: system.degraded_value(v) for v in sorted(active, key=sort_key)})
    return Intervention(mode)


def ccd(
    system: SystemModel,
    data: pd.DataFrame,
    alpha: float,
    num_samples: Optional[int] = None,
    **inference_kwargs,
) -> CCDResult:
    """Run CCD end-to-end: select the degraded mode, then estimate and check its
    functionality via causal inference (DoWhy GCM)."""
    u = select_intervention(system)
    if u is None:
        return CCDResult(intervention=None, phi=float("nan"), alpha=alpha, feasible=False)

    phi = estimate_phi(
        data,
        system.throughput_graph(),
        u.variables,
        weights=system.functionality_weights,
        num_samples=num_samples,
        product_functions=system.product_functions if system.use_known_product_mechanisms else None,
        **inference_kwargs,
    )
    return CCDResult(intervention=u, phi=phi, alpha=alpha, feasible=phi >= alpha)
