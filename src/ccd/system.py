"""The two-layer system model for the illustrative example."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Set
import networkx as nx


# --- node-name helpers -------------------------------------------------------
def W() -> str:
    return "W"


def T() -> str:
    return "T"


def P(i: int) -> str:
    return f"P{i}"


def E(i: int) -> str:
    return f"E{i}"


def eps(i: int) -> str:
    return f"eps{i}"


def gam(i: int) -> str:
    return f"gam{i}"


def N(i: int) -> str:
    return f"N{i}"


def M(i: int) -> str:
    return f"M{i}"


def A(i: int) -> str:
    return f"A{i}"


def L(i: int) -> str:
    return f"L{i}"


def Tt(i: int) -> str:
    return f"Tt{i}"


def Th(i: int) -> str:
    return f"Th{i}"


@dataclass
class SystemModel:
    """The two-layer model instance for a given number of servers ``m``."""

    m: int
    # exploits patched by operators (removed from the attacker's reach). Patching
    # E_i drops it from the attacker-controlled set Y; the graph is otherwise unchanged.
    # This is how the paper's recovery actions shrink what the attacker can do, moving
    # the system to a less restrictive degraded mode.
    patched_exploits: FrozenSet[str] = field(default_factory=frozenset)
    # whether the attacker has been evicted from n_1 (e.g. by re-imaging it). Eviction
    # removes the attacker's code execution, so the attacker-controlled set becomes empty
    # (Y = {}) -- the final recovery step, after which no degradation is needed.
    attacker_evicted: bool = False
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)

    # role sets (subsets of the causal-graph nodes)
    operator_controlled: Set[str] = field(default_factory=set)   # X
    attacker_controlled: Set[str] = field(default_factory=set)   # Y
    functionality: Set[str] = field(default_factory=set)         # J
    privileges: Set[str] = field(default_factory=set)            # P (P0..P_{m+1})
    exploits: Set[str] = field(default_factory=set)              # E (E2..E_{m+1})
    attained: Set[str] = field(default_factory=set)              # P-tilde (detected)
    lateral_targets: Set[str] = field(default_factory=set)       # privileges reachable by a lateral exploit

    # nodes that are observable during nominal operation (recorded in dataset D)
    throughput_nodes: Set[str] = field(default_factory=set)

    # known causal functions F-tilde: each maps an output node to the set of factors
    # of a *product* function ``output = prod(factors)``. Used for the context-specific
    # (AND) edge deactivation when constructing an intervened graph.
    product_functions: Dict[str, FrozenSet[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.m < 2:
            raise ValueError("m must be >= 2 (need at least one server besides n_1)")
        self._build()

    # --- degraded-mode configuration R --------------------------------------
    @staticmethod
    def degraded_value(_var: str) -> int:
        """R(x): the degraded-mode configuration of a link variable closes it (=0)."""
        return 0

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

    # --- construction --------------------------------------------------------
    def _build(self) -> None:
        m = self.m
        g = self.graph

        # throughput subsystem (per server)
        for i in range(1, m + 1):
            g.add_edge(W(), L(i))
            g.add_edge(eps(i), L(i))
            g.add_edge(L(i), Tt(i))
            g.add_edge(gam(i), Tt(i))
            g.add_edge(M(i), Tt(i))
            g.add_edge(N(i), Th(i))
            g.add_edge(Tt(i), Th(i))
            g.add_edge(Th(i), T())

        # attacker code-exec on n_1 can drop requests -> controls carried load Tt1
        g.add_edge(P(1), Tt(1))

        # privilege subsystem (attack-graph logic embedded in the causal graph)
        g.add_edge(P(0), P(1))
        for i in range(2, m + 1):
            g.add_edge(E(i), P(i))   # lateral-movement exploit
            g.add_edge(A(i), P(i))   # management link n_1 -> n_i
            g.add_edge(P(1), P(i))   # requires code exec on n_1
        g.add_edge(E(m + 1), P(m + 1))   # DB-credential exploit
        g.add_edge(M(1), P(m + 1))       # link n_1 -> database
        g.add_edge(P(1), P(m + 1))

        # role sets
        self.operator_controlled = (
            {N(i) for i in range(1, m + 1)}
            | {M(i) for i in range(1, m + 1)}
            | {A(i) for i in range(2, m + 1)}
        )
        if self.attacker_evicted:
            self.attacker_controlled = set()
        else:
            self.attacker_controlled = {Tt(1)} | {
                E(i) for i in range(2, m + 2) if E(i) not in self.patched_exploits
            }
        self.functionality = {T()}
        self.privileges = {P(i) for i in range(0, m + 2)}
        self.exploits = {E(i) for i in range(2, m + 2)}
        self.attained = {P(0), P(1)}
        # privileges that are postconditions of a lateral-movement exploit (P_2..P_{m+1})
        self.lateral_targets = {v for v in self.privileges
                                if any(p in self.exploits for p in g.predecessors(v))}

        self.throughput_nodes = (
            {W(), T()}
            | {eps(i) for i in range(1, m + 1)}
            | {gam(i) for i in range(1, m + 1)}
            | {L(i) for i in range(1, m + 1)}
            | {N(i) for i in range(1, m + 1)}
            | {M(i) for i in range(1, m + 1)}
            | {Tt(i) for i in range(1, m + 1)}
            | {Th(i) for i in range(1, m + 1)}
        )

        # known causal functions F-tilde, encoded as product specs (output -> factors)
        pf: Dict[str, FrozenSet[str]] = {}
        for i in range(1, m + 1):
            pf[Th(i)] = frozenset({N(i), Tt(i)})            # Th_i = N_i * Tt_i
        for i in range(2, m + 1):
            pf[P(i)] = frozenset({E(i), A(i), P(1)})        # P_i = E_i * A_i * P_1
        pf[P(m + 1)] = frozenset({E(m + 1), M(1), P(1)})    # P_{m+1} = E_{m+1} * M_1 * P_1
        # T = sum_i Th_i is additive, not a product, so it needs no deactivation spec.
        self.product_functions = pf
