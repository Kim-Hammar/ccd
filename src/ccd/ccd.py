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
    """Graph-only mode selection. Returns None (bottom) if the full candidate intervention
    already violates a criterion."""
    # restrict to links that can affect the criteria
    targets = system.containment_targets | system.functionality
    candidate_vars = system.operator_controlled & ancestors(system.graph, targets)

    # close all candidate links; bail out if criteria are violated
    active = set(candidate_vars)
    if not check_criteria(system, {v: 0 for v in active}).ok:
        return None

    # drop any link whose removal keeps both criteria satisfied (minimality:
    # intervening on fewer links never reduces functionality)
    for var in sorted(candidate_vars, key=sort_key):
        if var not in active:
            continue
        reduced = active - {var}
        if check_criteria(system, {v: 0 for v in reduced}).ok:
            active = reduced

    return Intervention({v: 0 for v in sorted(active, key=sort_key)})


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
        num_samples=num_samples,
        **inference_kwargs,
    )
    return CCDResult(intervention=u, phi=phi, alpha=alpha, feasible=phi >= alpha)
