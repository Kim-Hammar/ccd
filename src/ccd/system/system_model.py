"""
Abstract base class for two-layer system models <Gamma, G, L>.

The two layers are the attack graph ``Gamma = <P, E, V>`` (bipartite: privilege ->
exploit edges are preconditions, exploit -> privilege edges are postconditions) and the
causal graph ``G`` over the SCM variables. They are connected by the cross-layer edges
``L = C u B``: capability edges ``C`` (which privileges give the attacker control of
which causal variables) and blocking edges ``B`` (which operator interventions make
which exploits infeasible).
"""

from __future__ import annotations
from abc import ABC
from typing import Dict, FrozenSet, Set, Tuple
import networkx as nx


class SystemModel(ABC):
    """
    Interface and shared derived quantities for a two-layer system model <Gamma, G, L>.

    Concrete subclasses (typically ``@dataclass``es) must populate the attributes below;
    the derived quantities (``unattained``, ``attacker_controlled``, ``throughput_graph``)
    are computed from them and need not be overridden.
    """

    # --- interface: concrete subclasses must populate these ------------------
    graph: nx.DiGraph                              # G, the causal DAG (SCM variables only)
    attack_graph: nx.DiGraph                       # Gamma, bipartite over privileges u exploits
    operator_controlled: Set[str]                  # X
    functionality: Set[str]                        # J
    privileges: Set[str]                           # P (nodes of Gamma)
    exploits: Set[str]                             # E (nodes of Gamma)
    attained: Set[str]                             # P-tilde (possible attacker privileges)
    throughput_nodes: Set[str]                     # nodes observable during nominal operation (dataset D)
    # cross-layer capability edges C: (P', Y) means holding all privileges in P' lets the
    # attacker control the causal variable Y. The attacker-controlled set Y is derived
    # from P-tilde through these edges (see ``attacker_controlled``).
    capability_edges: FrozenSet[Tuple[FrozenSet[str], str]]
    # cross-layer blocking edges B: (X'', E) means intervening on all variables in X''
    # makes the exploit E infeasible (removes it from the intervened attack graph).
    blocking_edges: FrozenSet[Tuple[FrozenSet[str], str]]
    # known causal functions F-tilde: each maps an output node to the factors of a
    # *product* function ``output = prod(factors)``, used for context-specific (AND) edge
    # deactivation when constructing an intervened graph.
    product_functions: Dict[str, FrozenSet[str]]

    # --- degraded-mode configuration D(X) -------------------------------------
    @staticmethod
    def degraded_value(_var: str) -> int:
        """D(x): the degraded-mode configuration of a link variable closes it (=0)."""
        return 0

    # --- shared derived quantities -------------------------------------------
    @property
    def unattained(self) -> Set[str]:
        """Privileges the attacker has not (yet) possibly attained: P \\ P-tilde."""
        return self.privileges - self.attained

    @property
    def attacker_controlled(self) -> Set[str]:
        """Y: the attacker-controlled causal variables, derived from P-tilde via the
        capability edges C -- the attacker may control Y iff it may hold all privileges
        of some capability edge (P', Y) with P' <= P-tilde."""
        return {y for required, y in self.capability_edges if required <= self.attained}

    def throughput_graph(self) -> nx.DiGraph:
        """Subgraph over observable variables, used for DoWhy causal inference."""
        return self.graph.subgraph(self.throughput_nodes).copy()
