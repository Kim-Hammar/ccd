"""
The two-layer system model for the industrial control system (ICS) example.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import ClassVar, Dict, FrozenSet, Mapping, Set, Tuple
import networkx as nx
import numpy as np
import pandas as pd
from ccd.system.system_model import SystemModel

# Causal-graph nodes
W = "W"
I = "I"
G2C = "G2c"
G2E = "G2e"
CHAT = "Chat"
C = "C"
CTIL = "Ctil"
V = "V"
P = "P"
S = "S"
A = "A"
U = "U"

# Nominal-operation parameters
_D_LOW, _D_HIGH = 0.5, 1.5
_PCLOSE_HI, _PCLOSE_LO = 0.30, 0.05
_CMD_GAIN = 40.0
_CMD_SD = 3.0
_A_MEAN, _A_SD = 50.0, 4.0
_U_SD = 4.0
_V_GAIN = 0.05
_P_SETPOINT = 50.0
_S_SPREAD = 12.0
_I_HEALTHY, _I_SAFEMODE, _I_SD = 88.0, 48.0, 3.0


@dataclass
class IcsSystem(SystemModel):
    """The industrial control system (Tennessee Eastman) instance."""

    use_known_product_mechanisms: ClassVar[bool] = True

    EPSILON: ClassVar[float] = 0.5
    alpha_fraction: ClassVar[float] = 0.4

    patched_exploits: FrozenSet[str] = field(default_factory=frozenset)
    attacker_evicted: bool = False
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

    @staticmethod
    def Priv(n: int) -> str:
        return f"P{n}"

    @staticmethod
    def EX(n: int) -> str:
        return f"E{n}"

    def __post_init__(self) -> None:
        self._build()

    def _build(self) -> None:
        g = self.graph
        g.add_edge(W, I)
        g.add_edge(G2C, CTIL)
        g.add_edge(C, CTIL)
        g.add_edge(CHAT, V)
        g.add_edge(CTIL, V)
        g.add_edge(V, P)
        g.add_edge(A, P)
        g.add_edge(U, P)
        g.add_edge(P, S)

        patched = self.patched_exploits | ({self.EX(1)} if self.attacker_evicted else frozenset())

        gamma = self.attack_graph
        gamma.add_nodes_from(self.Priv(n) for n in range(0, 5))
        for pre, ex, post in [
            (self.Priv(0), self.EX(1), self.Priv(1)),
            (self.Priv(1), self.EX(2), self.Priv(2)),
            (self.Priv(1), self.EX(3), self.Priv(3)),
            (self.Priv(3), self.EX(4), self.Priv(4)),
        ]:
            if ex not in patched:
                gamma.add_edge(pre, ex)
                gamma.add_edge(ex, post)

        self.operator_controlled = {W, G2E, G2C, CHAT}
        self.functionality = {I, S, G2E, G2C}
        self.privileges = {self.Priv(n) for n in range(0, 5)}
        self.exploits = {self.EX(n) for n in range(1, 5)} - patched
        self.attained = ({self.Priv(0)} if self.attacker_evicted
                         else {self.Priv(0), self.Priv(1), self.Priv(3)})

        self.capability_edges = frozenset({
            (frozenset({self.Priv(1)}), W),
            (frozenset({self.Priv(3)}), C),
        })
        blocking = [
            (frozenset({W}), self.EX(1)),
            (frozenset({G2E}), self.EX(2)),
            (frozenset({G2C}), self.EX(3)),
            (frozenset({CHAT}), self.EX(4)),
        ]
        self.blocking_edges = frozenset((req, ex) for req, ex in blocking if ex not in patched)
        self.throughput_nodes = {W, I, G2C, CHAT, C, CTIL, V, P, S}

        self.product_functions = {
            CTIL: frozenset({G2C, C}),
            V: frozenset({CHAT, CTIL}),
        }

    def attack_value(self, var: str) -> int:
        if var == W:
            return 2
        if var == C:
            return 1
        return super().attack_value(var)

    @property
    def functionality_weights(self) -> Mapping[str, float]:
        return {I: 0.01, S: 0.01, G2E: self.EPSILON, G2C: self.EPSILON}

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """Return ``steps`` rows of nominal ICS operation over the observed variables."""
        rng = np.random.RandomState(seed)

        demand = rng.uniform(_D_LOW, _D_HIGH, steps)
        frac = (demand - _D_LOW) / (_D_HIGH - _D_LOW)
        p_close = _PCLOSE_HI - (_PCLOSE_HI - _PCLOSE_LO) * frac

        maintain = rng.uniform(0.0, 1.0, steps) < p_close
        which = np.where(maintain, rng.randint(0, 3, steps), -1)
        w = (which != 0).astype(int)
        g2c = (which != 1).astype(int)
        chat = (which != 2).astype(int)

        c = np.maximum(0.0, _CMD_GAIN * demand + rng.normal(0.0, _CMD_SD, steps))
        ctil = g2c * c
        v = chat * ctil

        a = rng.normal(_A_MEAN, _A_SD, steps)
        u = rng.normal(0.0, _U_SD, steps)
        p = a + _V_GAIN * v + u
        s = 100.0 * np.exp(-(((p - _P_SETPOINT) / _S_SPREAD) ** 2))
        integ = np.where(w == 1, _I_HEALTHY, _I_SAFEMODE) + rng.normal(0.0, _I_SD, steps)
        integ = np.clip(integ, 0.0, 100.0)

        data = {W: w, I: integ, G2C: g2c, CHAT: chat, C: c, CTIL: ctil, V: v, P: p, S: s}
        columns = sorted(self.throughput_nodes)
        return pd.DataFrame({col: data[col] for col in columns})
