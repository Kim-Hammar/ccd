"""
Abstract base class for two-layer system models <Gamma, G, L>
"""

from __future__ import annotations
from abc import ABC
from typing import ClassVar, Dict, FrozenSet, Mapping, Set, Tuple
import networkx as nx
import pandas as pd


class SystemModel(ABC):
    """
    Interface and shared derived quantities for a two-layer system model <Gamma, G, L>.
    """

    graph: nx.DiGraph
    attack_graph: nx.DiGraph
    operator_controlled: Set[str]
    functionality: Set[str]
    privileges: Set[str]
    exploits: Set[str]
    attained: Set[str]
    throughput_nodes: Set[str]
    capability_edges: FrozenSet[Tuple[FrozenSet[str], str]]
    blocking_edges: FrozenSet[Tuple[FrozenSet[str], str]]
    product_functions: Dict[str, FrozenSet[str]]
    use_known_product_mechanisms: ClassVar[bool] = False
    alpha_fraction: ClassVar[float] = 0.5

    def degraded_value(self, var: str) -> int:
        return 0

    def attack_value(self, var: str) -> int:
        return 0

    def deactivated_edges(self, do: Mapping[str, int]) -> Set[Tuple[str, str]]:
        zeroed = {v for v, val in do.items() if val == 0}
        edges: Set[Tuple[str, str]] = set()
        for out, factors in self.product_functions.items():
            if factors & zeroed and out in self.graph:
                for p in self.graph.predecessors(out):
                    edges.add((p, out))
        return edges

    def degradation_cost(self, _var: str) -> float:
        return 0.0

    def augment_mode(self, do: Mapping[str, int]) -> Dict[str, int]:
        return dict(do)

    @property
    def functionality_weights(self) -> Mapping[str, float]:
        return {"T": 1.0}

    @property
    def unattained(self) -> Set[str]:
        return self.privileges - self.attained

    @property
    def attacker_controlled(self) -> Set[str]:
        return {y for required, y in self.capability_edges if required <= self.attained}

    def throughput_graph(self) -> nx.DiGraph:
        return self.graph.subgraph(self.throughput_nodes).copy()

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        raise NotImplementedError("this system has no reference simulator")
