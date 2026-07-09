"""Implementation of Causal Controlled Degradation (CCD)"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from ccd.graph_ops import ancestors, check_criteria
from ccd.inference import estimate_phi
from ccd.base_system import SystemModel


def _sort_key(var: str):
    """Order link variables by letter then numeric index (N1, M1, A2, A3, ...)."""
    match = re.match(r"([A-Za-z]+)(\d+)", var)
    if match:
        return (match.group(1), int(match.group(2)))
    return (var, 0)


@dataclass(frozen=True)
class Intervention:
    """A degraded-mode intervention do(X' = R(X')); here R closes each link (value 0)."""

    variables: Dict[str, int]

    def __str__(self) -> str:
        assigns = ", ".join(f"{v}={self.variables[v]}" for v in sorted(self.variables, key=_sort_key))
        return f"do({assigns})"


@dataclass
class CCDResult:
    """Result of running CCD: the selected degraded mode and its estimated functionality."""

    intervention: Optional[Intervention]   # candidate mode (None if no mode satisfies the criteria)
    phi: float                             # estimated functionality Phi-hat(M_u) (nan if no candidate)
    alpha: float                           # critical functionality level
    feasible: bool                         # True iff a mode was found AND phi >= alpha


def select_intervention(system: SystemModel) -> Optional[Intervention]:
    """Graph-only mode selection (Algorithm 1, lines 1-8). Returns None (bottom) if the
    full candidate intervention already violates a criterion."""
    # line 1: restrict to links that can affect the criteria
    targets = system.containment_targets | system.functionality
    candidate_vars = system.operator_controlled & ancestors(system.graph, targets)

    # lines 2-4: close all candidate links; bail out if criteria are violated
    active = set(candidate_vars)
    if not check_criteria(system, {v: 0 for v in active}).ok:
        return None

    # lines 5-8: drop any link whose removal keeps both criteria satisfied (minimality:
    # intervening on fewer links never reduces functionality)
    for var in sorted(candidate_vars, key=_sort_key):
        if var not in active:
            continue
        reduced = active - {var}
        if check_criteria(system, {v: 0 for v in reduced}).ok:
            active = reduced

    return Intervention({v: 0 for v in sorted(active, key=_sort_key)})


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
