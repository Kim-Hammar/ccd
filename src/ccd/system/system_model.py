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
from typing import ClassVar, Dict, FrozenSet, Mapping, Set, Tuple
import networkx as nx
import pandas as pd


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

    # Whether to use the known product functions F-tilde as *exact* GCM mechanisms
    # (rather than fitting a regressor) during causal inference. Needed when a known
    # product is *gated* so its training data degenerates -- e.g. on the testbed the
    # measured carried load satisfies ``Tt_i = 0`` whenever ``N_i = 0``, which makes a
    # boosted regressor place its split at the knife edge (between 0 and the minimum
    # open-load) and misfire under interventional noise. The simulator's carried load is
    # ungated, so a regressor suffices there.
    use_known_product_mechanisms: ClassVar[bool] = False

    # --- degraded-mode configuration D(X) -------------------------------------
    def degraded_value(self, var: str) -> int:
        """D(x): the degraded-mode configuration of an operator variable.

        Base: closing the link (=0). Subclasses override for non-binary configurations
        (e.g. a raised 5QI admission threshold, or a re-attachment target index).
        """
        return 0

    # --- intervention semantics (overridable hooks) --------------------------
    def deactivated_edges(self, do: Mapping[str, int]) -> Set[Tuple[str, str]]:
        """Extra edges ``(parent, out)`` to sever in G_u because a known function
        F-tilde makes ``out`` constant under ``do``, beyond the standard do-operator
        cuts.

        Base rule: a *product* output (registered in ``product_functions``) with any
        zeroed factor becomes constant 0, so all of its in-edges are cut. Subclasses
        override to add *value-aware* rules (e.g. a threshold that drops only the
        sub-threshold input edges, or an attachment indicator that keeps only the
        selected branch); they typically call ``super().deactivated_edges(do)`` first.
        """
        zeroed = {v for v, val in do.items() if val == 0}
        edges: Set[Tuple[str, str]] = set()
        for out, factors in self.product_functions.items():
            if factors & zeroed and out in self.graph:
                for p in self.graph.predecessors(out):
                    edges.add((p, out))
        return edges

    def degradation_cost(self, _var: str) -> float:
        """Relative functionality cost of intervening on ``var``, used only to order the
        minimality drop-loop when several minimal covers exist (higher cost is dropped
        first). Base: 0 -- order by name only, so behaviour is unchanged."""
        return 0.0

    def augment_mode(self, do: Mapping[str, int]) -> Dict[str, int]:
        """Add functionality-restoring, *criteria-neutral* value-changes to a selected
        mode (e.g. re-route legitimate traffic off a link the containment mode closed).

        These do not change containment or the attacker's reachable set, so they are
        applied after minimality rather than searched over. Base: no augmentation.
        """
        return dict(do)

    @property
    def functionality_weights(self) -> Mapping[str, float]:
        """Weighted outcome columns w_c defining Phi = sum_c w_c * E[c | do]. Base:
        ``{"T": 1.0}`` -- a single throughput column, as in the illustrative example."""
        return {"T": 1.0}

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

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """Nominal-operation dataset D. Overridden by systems with a reference simulator;
        testbed-backed systems collect D externally and leave this raising."""
        raise NotImplementedError("this system has no reference simulator")
