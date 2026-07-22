"""
Causal inference of a degraded mode's functionality using DoWhy's GCM module.

Mechanism assignment uses the known causal functions F-tilde where available: a node
whose ``product_functions`` factors coincide with its parents in the fit graph gets a
deterministic product mechanism (``output = prod(parents)``) instead of a fitted
regressor. This matters beyond fidelity to the method (F-tilde *is* known): gated
mechanisms like ``Th_i = N_i * Tt_i`` produce training data with a gap (the output is
exactly 0 or >= the minimum open-load), and a boosted regressor can place its split
threshold at the knife edge, so that interventional samples of ``Tt_i`` jittering
around 0 (additive noise) fall on the wrong side and inflate ``Phi-hat``. The known
product is exact at the gap.
"""

from __future__ import annotations
from typing import FrozenSet, Mapping, Optional
import networkx as nx
import numpy as np
import pandas as pd
import dowhy.gcm as gcm
import dowhy.gcm.ml as ml
from dowhy.gcm.ml import PredictionModel


class ProductModel(PredictionModel):
    """A known (F-tilde) mechanism: the output is the product of its inputs."""

    def fit(self, X: np.ndarray, Y: np.ndarray) -> None:
        """Nothing to fit: the function is known."""

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.prod(np.asarray(X, dtype=float), axis=1).reshape(-1, 1)

    def clone(self) -> "ProductModel":
        return ProductModel()


def fit_scm(
    data: pd.DataFrame,
    graph: nx.DiGraph,
    product_functions: Optional[Mapping[str, FrozenSet[str]]] = None,
) -> gcm.StructuralCausalModel:
    """Fit a GCM structural causal model for ``graph`` from ``data``.

    ``product_functions`` are the known causal functions F-tilde (output -> factors);
    a node whose factors equal its parents in ``graph`` gets the exact ``ProductModel``
    mechanism, all other non-roots get a gradient-boosting regressor.
    """
    products = product_functions or {}
    cols = list(graph.nodes)
    scm = gcm.StructuralCausalModel(graph)
    for node in graph.nodes:
        if graph.in_degree(node) == 0:
            scm.set_causal_mechanism(node, gcm.EmpiricalDistribution())
        elif node in products and products[node] == set(graph.predecessors(node)):
            scm.set_causal_mechanism(node, gcm.AdditiveNoiseModel(ProductModel()))
        else:
            scm.set_causal_mechanism(
                node, gcm.AdditiveNoiseModel(ml.create_hist_gradient_boost_regressor())
            )
    gcm.fit(scm, data[cols])
    return scm


_DEFAULT_WEIGHTS: Mapping[str, float] = {"T": 1.0}


def _interventional_samples(
    scm: gcm.StructuralCausalModel,
    do: Mapping[str, float],
    num_samples: int,
) -> pd.DataFrame:
    """Draw samples under the atomic intervention ``do`` (var -> fixed value)."""
    graph_nodes = set(scm.graph.nodes)
    interventions = {
        v: (lambda _x, value=float(val): value)   # bind value to avoid late-binding bug
        for v, val in do.items()
        if v in graph_nodes
    }
    return gcm.interventional_samples(scm, interventions, num_samples_to_draw=num_samples)


def interventional_mean(
    scm: gcm.StructuralCausalModel,
    do: Mapping[str, float],
    outcome: str = "T",
    num_samples: int = 10_000,
) -> float:
    """Mean of ``outcome`` under the atomic intervention ``do`` (var -> fixed value)."""
    return float(_interventional_samples(scm, do, num_samples)[outcome].mean())


def estimate_phi(
    data: pd.DataFrame,
    graph: nx.DiGraph,
    do: Mapping[str, float],
    weights: Optional[Mapping[str, float]] = None,
    num_samples: Optional[int] = None,
    product_functions: Optional[Mapping[str, FrozenSet[str]]] = None,
) -> float:
    """Estimate Phi(M_u) = sum_c w_c * E[c | do] via GCM (fit + interventional sampling).

    ``weights`` maps outcome columns to their functionality weights w_c (default a single
    unit-weighted throughput column ``T``). The SCM is fit once and sampled once; the
    weighted sum over the requested columns is returned.
    """
    weights = weights if weights is not None else _DEFAULT_WEIGHTS
    scm = fit_scm(data, graph, product_functions=product_functions)
    n = num_samples if num_samples is not None else len(data)
    samples = _interventional_samples(scm, do, n)
    return sum(w * float(samples[c].mean()) for c, w in weights.items() if c in samples.columns)


def naive_estimate(
    data: pd.DataFrame,
    do: Mapping[str, float],
    weights: Optional[Mapping[str, float]] = None,
) -> float:
    """Biased observational baseline: sum_c w_c * E[c | X' = R(X')] by conditioning."""
    weights = weights if weights is not None else _DEFAULT_WEIGHTS
    mask = pd.Series(True, index=data.index)
    for v, val in do.items():
        if v in data.columns:
            mask &= data[v] == val
    if not mask.any():
        return float("nan")
    subset = data.loc[mask]
    return sum(w * float(subset[c].mean()) for c, w in weights.items() if c in subset.columns)
