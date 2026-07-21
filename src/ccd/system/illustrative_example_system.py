"""
The two-layer system model for the illustrative example, which
includes a gateway load-balancing across ``m`` application servers plus a database.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Set, Tuple
import networkx as nx
import numpy as np
import pandas as pd
from ccd.system.system_model import SystemModel

# --- nominal-operation parameters for generate_dataset -----------------------
_W_LOW, _W_HIGH = 100.0, 1000.0          # workload W ~ U[100, 1000] (req/s)
_LOAD_NOISE_SD = 2.0                     # SD of load-split noise eps_i
_CAP_MEAN, _CAP_SD = 600.0, 50.0         # processing capacity gamma_i (rarely the bottleneck)
_PCLOSE_LOW_W, _PCLOSE_HIGH_W = 0.30, 0.05   # maintenance-closure prob at low / high workload


@dataclass
class IllustrativeExampleSystem(SystemModel):
    """The illustrative-example instance for a given number of servers ``m``."""

    m: int
    # exploits patched by operators. Patching E_i removes it from the attack graph
    # Gamma (recovery actions remove edges from Gamma), which shrinks the set of
    # feasible attack paths and moves the system to a less restrictive degraded mode.
    patched_exploits: FrozenSet[str] = field(default_factory=frozenset)
    # whether the attacker has been evicted from n_1 (e.g. by re-imaging it after the
    # foothold exploit E_1 was patched). Eviction shrinks P-tilde to {P0}; with E_1
    # patched, no exploit is feasible and the derived attacker-controlled set Y is
    # empty -- the final recovery step, after which no degradation is needed.
    attacker_evicted: bool = False
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)              # G (causal layer)
    attack_graph: nx.DiGraph = field(default_factory=nx.DiGraph)       # Gamma (attack layer)

    # role sets (subsets of the causal-graph / attack-graph nodes)
    operator_controlled: Set[str] = field(default_factory=set)   # X
    functionality: Set[str] = field(default_factory=set)         # J
    privileges: Set[str] = field(default_factory=set)            # P (P0..P_{m+1})
    exploits: Set[str] = field(default_factory=set)              # E (E1..E_{m+1}, unpatched)
    attained: Set[str] = field(default_factory=set)              # P-tilde (detected)

    # cross-layer edges L = C u B
    capability_edges: FrozenSet[Tuple[FrozenSet[str], str]] = field(default_factory=frozenset)   # C
    blocking_edges: FrozenSet[Tuple[FrozenSet[str], str]] = field(default_factory=frozenset)     # B

    # nodes that are observable during nominal operation (recorded in dataset D)
    throughput_nodes: Set[str] = field(default_factory=set)

    # known causal functions F-tilde: each maps an output node to the set of factors
    # of a *product* function ``output = prod(factors)``. Used for the context-specific
    # (AND) edge deactivation when constructing an intervened graph.
    product_functions: Dict[str, FrozenSet[str]] = field(default_factory=dict)

    # --- node-name helpers ---------------------------------------------------
    @staticmethod
    def W() -> str:
        return "W"

    @staticmethod
    def T() -> str:
        return "T"

    @staticmethod
    def P(i: int) -> str:
        return f"P{i}"

    @staticmethod
    def E(i: int) -> str:
        return f"E{i}"

    @staticmethod
    def eps(i: int) -> str:
        return f"eps{i}"

    @staticmethod
    def gam(i: int) -> str:
        return f"gam{i}"

    @staticmethod
    def N(i: int) -> str:
        return f"N{i}"

    @staticmethod
    def M(i: int) -> str:
        return f"M{i}"

    @staticmethod
    def A(i: int) -> str:
        return f"A{i}"

    @staticmethod
    def L(i: int) -> str:
        return f"L{i}"

    @staticmethod
    def Tt(i: int) -> str:
        return f"Tt{i}"

    @staticmethod
    def Th(i: int) -> str:
        return f"Th{i}"

    def __post_init__(self) -> None:
        if self.m < 2:
            raise ValueError("m must be >= 2 (need at least one server besides n_1)")
        self._build()

    # --- construction --------------------------------------------------------
    def _build(self) -> None:
        m = self.m
        g = self.graph

        # causal layer G: the throughput subsystem (per server)
        for i in range(1, m + 1):
            g.add_edge(self.W(), self.L(i))
            g.add_edge(self.eps(i), self.L(i))
            g.add_edge(self.L(i), self.Tt(i))
            g.add_edge(self.gam(i), self.Tt(i))
            g.add_edge(self.M(i), self.Tt(i))
            g.add_edge(self.N(i), self.Th(i))
            g.add_edge(self.Tt(i), self.Th(i))
            g.add_edge(self.Th(i), self.T())

        patched = self.patched_exploits | ({self.E(1)} if self.attacker_evicted else frozenset())

        # attack layer Gamma: P0 -> E1 -> P1; from P1, lateral E_2..E_m and credential E_{m+1}
        gamma = self.attack_graph
        gamma.add_nodes_from(self.P(i) for i in range(0, m + 2))
        exploit_edges = [(self.P(0), self.E(1), self.P(1))]
        for i in range(2, m + 1):
            exploit_edges.append((self.P(1), self.E(i), self.P(i)))       # lateral movement
        exploit_edges.append((self.P(1), self.E(m + 1), self.P(m + 1)))   # DB credentials
        for pre, e, post in exploit_edges:
            if e not in patched:
                gamma.add_edge(pre, e)
                gamma.add_edge(e, post)

        # role sets
        self.operator_controlled = (
            {self.N(i) for i in range(1, m + 1)}
            | {self.M(i) for i in range(1, m + 1)}
            | {self.A(i) for i in range(2, m + 1)}
        )
        self.functionality = {self.T()}
        self.privileges = {self.P(i) for i in range(0, m + 2)}
        self.exploits = {self.E(i) for i in range(1, m + 2)} - patched
        self.attained = {self.P(0)} if self.attacker_evicted else {self.P(0), self.P(1)}

        # cross-layer edges L = C u B.
        # C: code execution on n_i (privilege P_i) lets the attacker drop requests on
        # n_i, i.e. control its carried load Tt_i.
        self.capability_edges = frozenset(
            (frozenset({self.P(i)}), self.Tt(i)) for i in range(1, m + 1)
        )
        # B: closing the management link A_i blocks the lateral exploit E_i; closing the
        # link M_1 (n_1 -> database) blocks the credential exploit E_{m+1}.
        blocking = [(frozenset({self.A(i)}), self.E(i)) for i in range(2, m + 1)]
        blocking.append((frozenset({self.M(1)}), self.E(m + 1)))
        self.blocking_edges = frozenset((req, e) for req, e in blocking if e not in patched)

        self.throughput_nodes = (
            {self.W(), self.T()}
            | {self.eps(i) for i in range(1, m + 1)}
            | {self.gam(i) for i in range(1, m + 1)}
            | {self.L(i) for i in range(1, m + 1)}
            | {self.N(i) for i in range(1, m + 1)}
            | {self.M(i) for i in range(1, m + 1)}
            | {self.Tt(i) for i in range(1, m + 1)}
            | {self.Th(i) for i in range(1, m + 1)}
        )

        # known causal functions F-tilde, encoded as product specs (output -> factors)
        pf: Dict[str, FrozenSet[str]] = {}
        for i in range(1, m + 1):
            pf[self.Th(i)] = frozenset({self.N(i), self.Tt(i)})   # Th_i = N_i * Tt_i
        # T = sum_i Th_i is additive, not a product, so it needs no deactivation spec.
        self.product_functions = pf

    # --- nominal data-generating process -------------------------------------
    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """Return a DataFrame of ``steps`` rows of nominal operation for this system."""
        m = self.m
        rng = np.random.RandomState(seed)

        workload = rng.uniform(_W_LOW, _W_HIGH, steps)
        # closure probability decreases linearly with workload
        frac = (workload - _W_LOW) / (_W_HIGH - _W_LOW)
        p_close = _PCLOSE_LOW_W - (_PCLOSE_LOW_W - _PCLOSE_HIGH_W) * frac

        data: dict[str, np.ndarray] = {self.W(): workload}
        total = np.zeros(steps)

        for i in range(1, m + 1):
            eps = rng.normal(0.0, _LOAD_NOISE_SD, steps)
            cap = rng.normal(_CAP_MEAN, _CAP_SD, steps)
            load = np.maximum(0.0, workload / m + eps)          # L_i ~ W/m, split evenly
            n_open = (rng.uniform(0.0, 1.0, steps) > p_close).astype(int)   # gateway -> n_i
            m_open = (rng.uniform(0.0, 1.0, steps) > p_close).astype(int)   # n_i -> database
            carried = m_open * np.minimum(load, cap)            # Tt_i = M_i * min(L_i, gam_i)
            throughput = n_open * carried                       # Th_i = N_i * Tt_i
            total += throughput

            data[self.eps(i)] = eps
            data[self.gam(i)] = cap
            data[self.L(i)] = load
            data[self.N(i)] = n_open
            data[self.M(i)] = m_open
            data[self.Tt(i)] = carried
            data[self.Th(i)] = throughput

        data[self.T()] = total
        return pd.DataFrame(data)
