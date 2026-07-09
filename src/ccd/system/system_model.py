"""
Abstract base class for two-layer (attack-graph + SCM) system models.
"""

from __future__ import annotations
from abc import ABC
from typing import Dict, FrozenSet, Set
import networkx as nx


class SystemModel(ABC):
    """
    Interface and shared derived quantities for a two-layer system model.

    Concrete subclasses (typically ``@dataclass``es) must populate the attributes below;
    the derived quantities (``unattained``, ``containment_targets``, ``throughput_graph``)
    are computed from them and need not be overridden.
    """

    # --- interface: concrete subclasses must populate these ------------------
    graph: nx.DiGraph                              # G, the causal DAG
    operator_controlled: Set[str]                  # X
    attacker_controlled: Set[str]                  # Y
    functionality: Set[str]                        # J
    privileges: Set[str]                           # P
    exploits: Set[str]                             # E
    attained: Set[str]                             # P-tilde (detected held privileges)
    lateral_targets: Set[str]                      # privileges reachable by a lateral exploit
    throughput_nodes: Set[str]                     # nodes observable during nominal operation (dataset D)
    # known causal functions F-tilde: each maps an output node to the factors of a
    # *product* function ``output = prod(factors)``, used for context-specific (AND) edge
    # deactivation when constructing an intervened graph.
    product_functions: Dict[str, FrozenSet[str]]

    # --- degraded-mode configuration R ---------------------------------------
    @staticmethod
    def degraded_value(_var: str) -> int:
        """R(x): the degraded-mode configuration of a link variable closes it (=0)."""
        return 0

    # --- shared derived quantities -------------------------------------------
    @property
    def unattained(self) -> Set[str]:
        """Privileges the attacker has not (yet) attained: P \\ P-tilde."""
        return self.privileges - self.attained

    @property
    def containment_targets(self) -> Set[str]:
        """Privileges the mode must keep unreachable by the attacker.

        Contains the unattained privileges (prevent escalation) AND all lateral-movement
        targets (prevent lateral movement). Protecting the lateral targets regardless of
        P-tilde means that a believed-compromised server is *isolated* rather than conceded,
        so an over-estimated P-tilde no longer opens an uncontained path to it.
        """
        return self.unattained | self.lateral_targets

    def throughput_graph(self) -> nx.DiGraph:
        """Subgraph over observable variables, used for DoWhy causal inference."""
        return self.graph.subgraph(self.throughput_nodes).copy()
