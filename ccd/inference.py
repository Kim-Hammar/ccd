"""Causal inference of a degraded mode's functionality using DoWhy's GCM module.

The functionality of a degraded mode is the causal effect
``E[T | do(X' = R(X'))]``. The observational dataset ``D`` reflects nominal operation,
so this interventional quantity is estimated by fitting a structural causal model over
the observable (throughput) variables and drawing interventional samples with the
closed links fixed to 0.

``naive_estimate`` computes the (biased) observational conditional ``E[T | X' = 0]`` for
contrast; it is wrong because closed links are confounded with low workload (see
``simulator.py``).
"""

from __future__ import annotations

from typing import Mapping, Optional

import networkx as nx
import pandas as pd

import dowhy.gcm as gcm
import dowhy.gcm.ml as ml


def fit_scm(data: pd.DataFrame, graph: nx.DiGraph) -> gcm.StructuralCausalModel:
    """Fit a GCM structural causal model for ``graph`` from ``data``.

    Root nodes get an empirical marginal; non-root nodes get an additive-noise model
    with a histogram gradient-boosting regressor. The gradient-boosting model is chosen
    deliberately: the system's mechanisms are *gated products* (e.g. ``Th_i = N_i*Tt_i``,
    ``Tt_i = M_i*min(L_i, gam_i)``) whose binary-times-continuous interactions a linear
    regressor cannot represent -- which biases the interventional estimate low. A tree
    ensemble captures the gates, so ``do(N_1=0)`` correctly zeroes ``n_1``'s throughput.
    """
    cols = list(graph.nodes)
    scm = gcm.StructuralCausalModel(graph)
    for node in graph.nodes:
        if graph.in_degree(node) == 0:
            scm.set_causal_mechanism(node, gcm.EmpiricalDistribution())
        else:
            scm.set_causal_mechanism(
                node, gcm.AdditiveNoiseModel(ml.create_hist_gradient_boost_regressor())
            )
    gcm.fit(scm, data[cols])
    return scm


def interventional_mean(
    scm: gcm.StructuralCausalModel,
    do: Mapping[str, float],
    outcome: str = "T",
    num_samples: int = 10_000,
) -> float:
    """Mean of ``outcome`` under the atomic intervention ``do`` (var -> fixed value).

    Only intervention variables that are nodes of the fitted graph are applied; others
    (e.g. management links ``A_i``) do not affect the throughput SCM.
    """
    graph_nodes = set(scm.graph.nodes)
    interventions = {
        v: (lambda _x, value=float(val): value)   # bind value to avoid late-binding bug
        for v, val in do.items()
        if v in graph_nodes
    }
    samples = gcm.interventional_samples(scm, interventions, num_samples_to_draw=num_samples)
    return float(samples[outcome].mean())


def estimate_phi(
    data: pd.DataFrame,
    graph: nx.DiGraph,
    do: Mapping[str, float],
    outcome: str = "T",
    num_samples: Optional[int] = None,
) -> float:
    """Estimate Phi(M_u) = E[outcome | do] via GCM (fit + interventional sampling)."""
    scm = fit_scm(data, graph)
    n = num_samples if num_samples is not None else len(data)
    return interventional_mean(scm, do, outcome=outcome, num_samples=n)


def naive_estimate(data: pd.DataFrame, do: Mapping[str, float], outcome: str = "T") -> float:
    """Biased observational baseline: E[outcome | X' = R(X')] by conditioning."""
    mask = pd.Series(True, index=data.index)
    for v, val in do.items():
        if v in data.columns:
            mask &= data[v] == val
    if not mask.any():
        return float("nan")
    return float(data.loc[mask, outcome].mean())
