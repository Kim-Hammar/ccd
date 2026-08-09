"""
Synthetic random (Erdos-Renyi) two-layer system models for scalability benchmarking.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import random
from typing import Dict, FrozenSet, Mapping, Set, Tuple
import networkx as nx
import numpy as np
import pandas as pd
from ccd.system.system_model import SystemModel


@dataclass
class RandomSystem(SystemModel):
    """A synthetic two-layer model with random ER graphs (scalability benchmarking only)."""

    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    attack_graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    operator_controlled: Set[str] = field(default_factory=set)
    functionality: Set[str] = field(default_factory=set)
    privileges: Set[str] = field(default_factory=set)
    exploits: Set[str] = field(default_factory=set)
    attained: Set[str] = field(default_factory=set)
    capability_edges: FrozenSet[Tuple[FrozenSet[str], str]] = field(default_factory=frozenset)
    blocking_edges: FrozenSet[Tuple[FrozenSet[str], str]] = field(default_factory=frozenset)
    throughput_nodes: Set[str] = field(default_factory=set)
    product_functions: Dict[str, FrozenSet[str]] = field(default_factory=dict)

    @property
    def functionality_weights(self) -> Mapping[str, float]:
        return {j: 1.0 for j in self.functionality}

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """A synthetic linear-Gaussian dataset over the causal nodes"""
        rng = np.random.RandomState(seed)
        values: Dict[str, np.ndarray] = {}
        for node in nx.topological_sort(self.graph):
            parents = list(self.graph.predecessors(node))
            if not parents:
                values[node] = rng.normal(0.0, 1.0, steps)
            else:
                parent_mean = np.mean([values[p] for p in parents], axis=0)
                values[node] = parent_mean + rng.normal(0.0, 0.5, steps)
        return pd.DataFrame({node: values[node] for node in self.throughput_nodes})


def _random_dag(n: int, avg_degree: float, seed: int) -> nx.DiGraph:
    p = min(1.0, avg_degree / max(1, n - 1))
    undirected = nx.fast_gnp_random_graph(n, p, seed=seed, directed=False)
    g = nx.DiGraph()
    g.add_nodes_from(f"V{i}" for i in range(n))
    for u, v in undirected.edges():
        lo, hi = (u, v) if u < v else (v, u)
        g.add_edge(f"V{lo}", f"V{hi}")
    return g


def random_system(n: int, avg_degree: float = 4.0, seed: int = 0) -> RandomSystem:
    """A random two-layer model of ~n causal nodes (+ ~n/2 privileges/exploits)."""
    if n < 4:
        raise ValueError(f"n must be >= 4, got {n}")
    rng = random.Random(seed)
    g = _random_dag(n, avg_degree, seed)
    nodes = [f"V{i}" for i in range(n)]

    operator = set(rng.sample(nodes, max(1, n // 7)))
    upper = nodes[n // 2:]
    functionality = set(rng.sample(upper, min(max(1, n // 50), len(upper))))

    num_priv, num_expl = max(2, n // 2), max(1, n // 2)
    privileges = [f"P{i}" for i in range(num_priv)]
    exploits = [f"E{i}" for i in range(num_expl)]
    gamma = nx.DiGraph()
    gamma.add_nodes_from(privileges)
    gamma.add_nodes_from(exploits)
    for e in exploits:
        for pre in rng.sample(privileges, rng.randint(1, 2)):
            gamma.add_edge(pre, e)
        gamma.add_edge(e, rng.choice(privileges))
    attained = set(rng.sample(privileges, max(1, int(0.4 * num_priv))))

    ancestors_of_j: Set[str] = set()
    for j in functionality:
        ancestors_of_j |= nx.ancestors(g, j)
    y_pool = sorted(operator & ancestors_of_j)
    attacker_vars = set(rng.sample(y_pool, min(len(y_pool), max(1, n // 40)))) if y_pool else set()

    attained_list = sorted(attained)
    capability = {
        (frozenset(rng.sample(attained_list, min(len(attained_list), rng.randint(1, 2)))), y)
        for y in attacker_vars
    }
    operator_list = sorted(operator)
    blocking = {
        (frozenset(rng.sample(operator_list, rng.randint(1, min(2, len(operator_list))))), e)
        for e in exploits
    }

    return RandomSystem(
        graph=g, attack_graph=gamma, operator_controlled=operator,
        functionality=functionality, privileges=set(privileges), exploits=set(exploits),
        attained=attained, capability_edges=frozenset(capability),
        blocking_edges=frozenset(blocking), throughput_nodes=set(nodes),
    )
