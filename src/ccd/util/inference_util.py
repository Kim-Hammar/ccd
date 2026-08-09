"""
Causal inference of a degraded mode's functionality using DoWhy's GCM module.
"""

from __future__ import annotations
from typing import AbstractSet, Dict, FrozenSet, Mapping, Optional, Tuple
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
    """Fit a GCM structural causal model"""
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


def split_policy_weights(
    weights: Mapping[str, float],
    operator_controlled: AbstractSet[str],
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Split the Phi weights into data-estimable terms and deterministic *policy* terms."""
    estimable = {c: w for c, w in weights.items() if c not in operator_controlled}
    policy = {c: w for c, w in weights.items() if c in operator_controlled}
    return estimable, policy


def policy_phi(policy_weights: Mapping[str, float], do: Mapping[str, float]) -> float:
    """The deterministic policy term of Phi: sum_c w_c * (do[c] if intervened else 1)."""
    return sum(w * float(do.get(c, 1)) for c, w in policy_weights.items())


def _interventional_samples(
    scm: gcm.StructuralCausalModel,
    do: Mapping[str, float],
    num_samples: int,
) -> pd.DataFrame:
    """Draw samples under the atomic intervention ``do`` (var -> fixed value)."""
    graph_nodes = set(scm.graph.nodes)
    interventions = {
        v: (lambda _x, value=float(val): value)
        for v, val in do.items()
        if v in graph_nodes
    }
    return gcm.interventional_samples(scm, interventions, num_samples_to_draw=num_samples)


def estimate_phi(
    data: pd.DataFrame,
    graph: nx.DiGraph,
    do: Mapping[str, float],
    weights: Optional[Mapping[str, float]] = None,
    num_samples: Optional[int] = None,
    product_functions: Optional[Mapping[str, FrozenSet[str]]] = None,
) -> float:
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
