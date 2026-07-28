"""
Synthetic random (Erdos-Renyi) two-layer system models for scalability benchmarking.

``random_system(n)`` builds a valid two-layer model ``<Gamma, G, L>`` of size ~n with an
ER-random causal DAG and a random bipartite attack graph. It is sized so CCD mode
selection (``select_intervention``) does representative work: every exploit is blockable
(so containment is satisfiable), and the attacker-controlled variables ``Y`` are
operator-controllable ancestors of the functionality ``J`` (so the functionality
criterion forces a non-trivial minimal cover and the minimality drop-loop runs).

For the inference-scalability benchmark ``RandomSystem`` also provides a simple
linear-Gaussian data-generating process (``generate_dataset``) and ``functionality_weights``
over the ``J`` nodes -- the values are arbitrary (only the graph structure and row count
drive the DoWhy fit cost), so the causal estimate itself is meaningless; the point is the
timing.
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
        """Unit weight on each functionality node J (Phi = sum_{j in J} E{j | do})."""
        return {j: 1.0 for j in self.functionality}

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """A synthetic linear-Gaussian dataset over the causal nodes: each root is
        standard normal, each non-root the mean of its parents plus noise. Only the
        column count and row count matter (they drive the GCM fit cost)."""
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
    """ER causal DAG on nodes V0..V_{n-1}: an undirected G(n, p) oriented low->high index
    (the index order is a topological order, so the result is acyclic)."""
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

    # roles: ~15% operator-controlled; a few upper-half nodes are functionality (J)
    operator = set(rng.sample(nodes, max(1, n // 7)))
    upper = nodes[n // 2:]
    functionality = set(rng.sample(upper, min(max(1, n // 50), len(upper))))

    # attack graph Gamma: ~n/2 privileges + ~n/2 exploits, random bipartite (each exploit
    # 1-2 preconditions -> 1 postcondition); P-tilde ~ 40% of privileges
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

    # Y: operator-controllable ancestors of J (so the full candidate X' contains Y and the
    # functionality criterion holds, while the minimality loop cannot drop the Y cover)
    ancestors_of_j: Set[str] = set()
    for j in functionality:
        ancestors_of_j |= nx.ancestors(g, j)
    y_pool = sorted(operator & ancestors_of_j)
    attacker_vars = set(rng.sample(y_pool, min(len(y_pool), max(1, n // 40)))) if y_pool else set()

    # capability edges (P' -> Y) with P' <= P-tilde, so Y is derived as attacker_controlled
    attained_list = sorted(attained)
    capability = {
        (frozenset(rng.sample(attained_list, min(len(attained_list), rng.randint(1, 2)))), y)
        for y in attacker_vars
    }
    # blocking edges (X'' -> E): every exploit is blockable, so containment is satisfiable
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
