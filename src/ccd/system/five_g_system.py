"""
The two-layer system model for the 5G cloud radio access network example.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import ClassVar, Dict, FrozenSet, Mapping, Set, Tuple
import networkx as nx
import numpy as np
import pandas as pd
from ccd.system.system_model import SystemModel

# Structure
_NUM_DU = 4
_NUM_CU = 4
_NUM_CLASSES = 10
_ATTACKER_CLASSES = (7, 8, 9, 10)
_DIRECTIONS = ("U", "D")   # uplink / downlink

# Nominal-operation
_PER_CLASS_LOAD = 3.0
_LOAD_SD = 0.4
_CBAR_SD = 1.0
_C_SD = 1.0
_T_SD = 1.0
_W_LOW, _W_HIGH = 0.5, 1.5
_PCLOSE_HI, _PCLOSE_LO = 0.30, 0.05
_P_IFACE_DOWN = 0.03
_P_QI_VARY = 0.5
_P_AT_VARY = 0.5


@dataclass
class FiveGSystem(SystemModel):
    """The 5G cloud-RAN instance (fixed four DUs / four CUs)."""

    OMEGA: ClassVar[float] = 5.0
    use_known_product_mechanisms: ClassVar[bool] = True
    alpha_fraction: ClassVar[float] = 0.75

    num_du: int = _NUM_DU
    num_cu: int = _NUM_CU
    num_classes: int = _NUM_CLASSES
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

    _qi_index: Dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _at_index: Dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _ng_vars: Set[str] = field(default_factory=set, init=False, repr=False)
    _uu_vars: Set[str] = field(default_factory=set, init=False, repr=False)
    _nominal_cu: Dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _degraded_config: Dict[str, int] = field(default_factory=dict, init=False, repr=False)

    @staticmethod
    def QI(i: int) -> str:
        return f"QI{i}"

    @staticmethod
    def Uu(i: int) -> str:
        return f"Uu{i}"

    @staticmethod
    def AT(i: int) -> str:
        return f"AT{i}"

    @staticmethod
    def NG(j: int) -> str:
        return f"NG{j}"

    @staticmethod
    def UE(i: int, k: int) -> str:
        return f"UE_{i}_{k}"

    @staticmethod
    def L(i: int, k: int, d: str) -> str:
        return f"L_{i}_{k}_{d}"

    @staticmethod
    def Ladm(i: int, d: str) -> str:
        return f"Ladm_{i}_{d}"

    @staticmethod
    def Cbar(i: int, d: str) -> str:
        return f"Cbar_{i}_{d}"

    @staticmethod
    def Chat(i: int, j: int, d: str) -> str:
        return f"Chat_{i}_{j}_{d}"

    @staticmethod
    def Ctil(i: int, j: int, d: str) -> str:
        return f"Ctil_{i}_{j}_{d}"

    @staticmethod
    def C(i: int, d: str) -> str:
        return f"C_{i}_{d}"

    @staticmethod
    def T(i: int, d: str) -> str:
        return f"T_{i}_{d}"

    @staticmethod
    def eps(i: int, d: str) -> str:
        return f"eps_{i}_{d}"

    @staticmethod
    def epsbar(i: int, d: str) -> str:
        return f"epsbar_{i}_{d}"

    @staticmethod
    def gam(i: int, d: str) -> str:
        return f"gam_{i}_{d}"

    @staticmethod
    def P(n: int) -> str:
        return f"P{n}"

    @staticmethod
    def EX(n: int) -> str:
        return f"EX{n}"

    def _partner_cu(self, i: int) -> int | None:
        """The degraded attachment map"""
        partner = i + 1 if i % 2 == 1 else i - 1
        return partner if 1 <= partner <= self.num_cu else None

    def __post_init__(self) -> None:
        if self.num_cu < 3:
            raise ValueError(f"num_cu must be >= 3 (attacker holds CU_3), got {self.num_cu}")
        if self.num_du < 3:
            raise ValueError(f"num_du must be >= 3 (D_1 reattaches DU_3), got {self.num_du}")
        if self.num_cu < self.num_du:
            raise ValueError(f"num_cu ({self.num_cu}) must be >= num_du ({self.num_du}) "
                             "for the nominal DU_i -> CU_i attachment")
        if self.num_classes < max(_ATTACKER_CLASSES):
            raise ValueError(f"num_classes must be >= {max(_ATTACKER_CLASSES)}, got {self.num_classes}")
        self._build()

    def _build(self) -> None:
        dus = range(1, self.num_du + 1)
        cus = range(1, self.num_cu + 1)
        classes = range(1, self.num_classes + 1)
        g = self.graph

        for i in dus:
            for d in _DIRECTIONS:
                for k in classes:
                    g.add_edge(self.UE(i, k), self.L(i, k, d))
                    g.add_edge(self.L(i, k, d), self.Ladm(i, d))
                g.add_edge(self.QI(i), self.Ladm(i, d))
                g.add_edge(self.Uu(i), self.Ladm(i, d))
                g.add_edge(self.Ladm(i, d), self.Cbar(i, d))
                g.add_edge(self.epsbar(i, d), self.Cbar(i, d))
                for j in cus:
                    g.add_edge(self.Cbar(i, d), self.Chat(i, j, d))
                    g.add_edge(self.AT(i), self.Chat(i, j, d))
                    g.add_edge(self.Chat(i, j, d), self.Ctil(i, j, d))
                    g.add_edge(self.NG(j), self.Ctil(i, j, d))
                    g.add_edge(self.Ctil(i, j, d), self.C(i, d))
                g.add_edge(self.eps(i, d), self.C(i, d))
                g.add_edge(self.C(i, d), self.T(i, d))
                g.add_edge(self.gam(i, d), self.T(i, d))
                for iface in ("A1", "N6", "Xn", "E2"):
                    g.add_edge(iface, self.T(i, d))

        patched = self.patched_exploits | (
            {self.EX(1), self.EX(2)} if self.attacker_evicted else frozenset())

        gamma = self.attack_graph
        gamma.add_nodes_from(self.P(n) for n in range(0, 6))
        for pre, ex, post in [
            (self.P(0), self.EX(1), self.P(1)),
            (self.P(0), self.EX(2), self.P(2)),
            (self.P(2), self.EX(3), self.P(3)),
            (self.P(2), self.EX(4), self.P(4)),
            (self.P(3), self.EX(5), self.P(5)),
        ]:
            if ex not in patched:
                gamma.add_edge(pre, ex)
                gamma.add_edge(ex, post)

        self.operator_controlled = (
            {"E2", "A1", "N6", "Xn"}
            | {self.Uu(i) for i in dus}
            | {self.QI(i) for i in dus}
            | {self.AT(i) for i in dus}
            | {self.NG(j) for j in cus}
        )
        self.functionality = {self.T(i, d) for i in dus for d in _DIRECTIONS} | {"E2", "A1"}
        self.privileges = {self.P(n) for n in range(0, 6)}
        self.exploits = {self.EX(n) for n in range(1, 6)} - patched
        self.attained = {self.P(0)} if self.attacker_evicted else {self.P(0), self.P(1), self.P(2)}

        self.capability_edges = frozenset(
            {(frozenset({self.P(1)}), self.UE(1, k)) for k in _ATTACKER_CLASSES}
            | {(frozenset({self.P(2)}), self.Chat(i, 3, d)) for i in dus for d in _DIRECTIONS}
        )
        blocking = [
            (frozenset({"E2"}), self.EX(3)),
            (frozenset({self.NG(3)}), self.EX(4)),
        ]
        self.blocking_edges = frozenset((req, ex) for req, ex in blocking if ex not in patched)

        self.throughput_nodes = (
            {self.Ladm(i, d) for i in dus for d in _DIRECTIONS}
            | {self.Cbar(i, d) for i in dus for d in _DIRECTIONS}
            | {self.C(i, d) for i in dus for d in _DIRECTIONS}
            | {self.T(i, d) for i in dus for d in _DIRECTIONS}
            | {self.L(i, k, d) for i in dus for k in classes for d in _DIRECTIONS}
            | {self.Chat(i, j, d) for i in dus for j in cus for d in _DIRECTIONS}
            | {self.Ctil(i, j, d) for i in dus for j in cus for d in _DIRECTIONS}
            | self.operator_controlled
        )

        self.product_functions = {
            self.Ctil(i, j, d): frozenset({self.NG(j), self.Chat(i, j, d)})
            for i in dus for j in cus for d in _DIRECTIONS
        }

        self._qi_index = {self.QI(i): i for i in dus}
        self._at_index = {self.AT(i): i for i in dus}
        self._ng_vars = {self.NG(j) for j in cus}
        self._uu_vars = {self.Uu(i) for i in dus}
        self._nominal_cu = {i: i for i in dus}
        self._degraded_config: Dict[str, int] = {}
        for var in ("E2", "A1", "N6", "Xn"):
            self._degraded_config[var] = 0
        for i in dus:
            self._degraded_config[self.Uu(i)] = 0
        for j in cus:
            self._degraded_config[self.NG(j)] = 0
        for i in dus:
            self._degraded_config[self.QI(i)] = min(_ATTACKER_CLASSES) - 1
            partner = self._partner_cu(i)
            self._degraded_config[self.AT(i)] = partner if partner is not None else i

    def degraded_value(self, var: str) -> int:
        return self._degraded_config.get(var, 0)

    def deactivated_edges(self, do: Mapping[str, int]) -> Set[Tuple[str, str]]:
        edges = set(super().deactivated_edges(do))
        for var, val in do.items():
            i = self._qi_index.get(var)
            if i is not None:
                for k in range(1, self.num_classes + 1):
                    if k > val:
                        for d in _DIRECTIONS:
                            edges.add((self.L(i, k, d), self.Ladm(i, d)))
            i = self._at_index.get(var)
            if i is not None:
                for j in range(1, self.num_cu + 1):
                    if j != val:
                        for d in _DIRECTIONS:
                            edges.add((self.Cbar(i, d), self.Chat(i, j, d)))
        return edges

    def degradation_cost(self, var: str) -> float:
        if var in ("N6", "Xn") or var in self._uu_vars:
            return 4.0
        if var in self._ng_vars:
            return 3.0
        if var in ("E2", "A1"):
            return 2.0
        if var in self._qi_index:
            return 1.0
        return 0.0

    def augment_mode(self, do: Mapping[str, int]) -> Dict[str, int]:
        mode = dict(do)
        closed_cus = {j for j in range(1, self.num_cu + 1) if mode.get(self.NG(j), 1) == 0}
        open_cus = [j for j in range(1, self.num_cu + 1) if j not in closed_cus]
        for i in range(1, self.num_du + 1):
            if self._nominal_cu[i] in closed_cus and self.AT(i) not in mode and open_cus:
                partner = self._partner_cu(self._nominal_cu[i])
                mode[self.AT(i)] = partner if partner in open_cus else open_cus[0]
        return mode

    @property
    def functionality_weights(self) -> Mapping[str, float]:
        weights: Dict[str, float] = {
            self.T(i, d): 1.0 for i in range(1, self.num_du + 1) for d in _DIRECTIONS
        }
        weights["E2"] = self.OMEGA
        weights["A1"] = self.OMEGA
        return weights

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """Return ``steps`` rows of nominal 5G operation over the observed variables."""
        dus = range(1, self.num_du + 1)
        cus = range(1, self.num_cu + 1)
        classes = range(1, self.num_classes + 1)
        rng = np.random.RandomState(seed)

        demand = rng.uniform(_W_LOW, _W_HIGH, steps)
        frac = (demand - _W_LOW) / (_W_HIGH - _W_LOW)
        p_close = _PCLOSE_HI - (_PCLOSE_HI - _PCLOSE_LO) * frac       # confounded with demand

        def bernoulli_open(prob: np.ndarray) -> np.ndarray:
            return (rng.uniform(0.0, 1.0, steps) >= prob).astype(int)

        data: Dict[str, np.ndarray] = {}

        uu = {}
        for i in dus:
            uu[i] = bernoulli_open(p_close)
            data[self.Uu(i)] = uu[i]
        for iface in ("N6", "Xn", "E2", "A1"):
            data[iface] = bernoulli_open(np.full(steps, _P_IFACE_DOWN))
        qi = {}
        for i in dus:
            vary = rng.uniform(0.0, 1.0, steps) < _P_QI_VARY
            qi[i] = np.where(vary, rng.randint(1, self.num_classes, steps), self.num_classes)
            data[self.QI(i)] = qi[i]
        at = {}
        for i in dus:
            vary = rng.uniform(0.0, 1.0, steps) < _P_AT_VARY
            at[i] = np.where(vary, rng.randint(1, self.num_cu + 1, steps), i)        # nominal CU_i
            data[self.AT(i)] = at[i]
        ng = {}
        for j in cus:
            ng[j] = bernoulli_open(p_close)
            data[self.NG(j)] = ng[j]

        for i in dus:
            for d in _DIRECTIONS:
                loads = {}
                for k in classes:
                    loads[k] = np.maximum(0.0, demand * _PER_CLASS_LOAD
                                          + rng.normal(0.0, _LOAD_SD, steps))
                    data[self.L(i, k, d)] = loads[k]
                admitted = np.zeros(steps)
                for k in classes:
                    admitted += np.where(k <= qi[i], loads[k], 0.0)
                ladm = uu[i] * admitted                                          # admission
                data[self.Ladm(i, d)] = ladm
                cbar = np.maximum(0.0, ladm + rng.normal(0.0, _CBAR_SD, steps))  # carried (+ eps-bar)
                data[self.Cbar(i, d)] = cbar
                c_total = np.zeros(steps)
                for j in cus:
                    chat = np.where(at[i] == j, cbar, 0.0)                       # attachment
                    data[self.Chat(i, j, d)] = chat
                    ctil = ng[j] * chat                                          # midhaul
                    data[self.Ctil(i, j, d)] = ctil
                    c_total += ctil
                c_val = np.maximum(0.0, c_total + rng.normal(0.0, _C_SD, steps))  # (+ eps)
                data[self.C(i, d)] = c_val
                thr = data["N6"] * data["Xn"] * c_val + rng.normal(0.0, _T_SD, steps)  # (+ gamma)
                data[self.T(i, d)] = np.maximum(0.0, thr)

        columns = sorted(self.throughput_nodes)
        return pd.DataFrame({col: data[col] for col in columns})
