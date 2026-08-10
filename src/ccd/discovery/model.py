"""
``ConstructedModel``: the output of automatic two-layer-model construction.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional, Set, Tuple
import networkx as nx
from ccd.discovery.causal.validation import FalsificationSummary


@dataclass
class ConstructedModel:
    """A machine-constructed two-layer model <Gamma, G, L>."""

    testbed: str
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    attack_graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    operator_controlled: Set[str] = field(default_factory=set)
    functionality: Set[str] = field(default_factory=set)
    privileges: Set[str] = field(default_factory=set)
    exploits: Set[str] = field(default_factory=set)
    attained: Set[str] = field(default_factory=set)
    throughput_nodes: Set[str] = field(default_factory=set)
    capability_edges: FrozenSet[Tuple[FrozenSet[str], str]] = field(default_factory=frozenset)
    blocking_edges: FrozenSet[Tuple[FrozenSet[str], str]] = field(default_factory=frozenset)
    product_functions: Dict[str, FrozenSet[str]] = field(default_factory=dict)
    exploit_meta: Dict[str, Dict[str, str]] = field(default_factory=dict)
    falsification: Optional[FalsificationSummary] = None

    @property
    def unattained(self) -> Set[str]:
        return self.privileges - self.attained

    @property
    def attacker_controlled(self) -> Set[str]:
        return {y for required, y in self.capability_edges if required <= self.attained}

    def throughput_graph(self) -> nx.DiGraph:
        return self.graph.subgraph(self.throughput_nodes).copy()
