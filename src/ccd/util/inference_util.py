"""Causal inference of a degraded mode's functionality using DoWhy's GCM module."""

from __future__ import annotations

from typing import Mapping, Optional

import networkx as nx
import pandas as pd

import dowhy.gcm as gcm
import dowhy.gcm.ml as ml


def fit_scm(data: pd.DataFrame, graph: nx.DiGraph) -> gcm.StructuralCausalModel:
    """Fit a GCM structural causal model for ``graph`` from ``data``."""
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
    """Mean of ``outcome`` under the atomic intervention ``do`` (var -> fixed value)."""
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
