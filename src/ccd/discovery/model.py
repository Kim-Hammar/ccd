"""
``ConstructedModel``: the output of automatic two-layer-model construction.

It mirrors the public attributes of ``ccd.system.SystemModel`` (the causal graph G, the
attack graph Gamma, the cross-layer edges C and B, the role/privilege sets, the product
functions F-tilde) so the acceptance harness can diff a constructed model against a
hand-authored ``SystemModel`` field by field. It deliberately does **not** subclass
``SystemModel`` -- construction stays in the ``discovery`` package, which never imports
``ccd.system`` -- but exposes the same derived quantities (``unattained``,
``attacker_controlled``, ``throughput_graph``) computed identically.
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
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)                 # G
    attack_graph: nx.DiGraph = field(default_factory=nx.DiGraph)         # Gamma
    operator_controlled: Set[str] = field(default_factory=set)
    functionality: Set[str] = field(default_factory=set)
    privileges: Set[str] = field(default_factory=set)
    exploits: Set[str] = field(default_factory=set)
    attained: Set[str] = field(default_factory=set)                     # P-tilde
    throughput_nodes: Set[str] = field(default_factory=set)
    capability_edges: FrozenSet[Tuple[FrozenSet[str], str]] = field(default_factory=frozenset)   # C
    blocking_edges: FrozenSet[Tuple[FrozenSet[str], str]] = field(default_factory=frozenset)     # B
    product_functions: Dict[str, FrozenSet[str]] = field(default_factory=dict)                    # F-tilde
    # per-exploit provenance kept for L derivation / debugging (link_var, reach edge, class)
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
