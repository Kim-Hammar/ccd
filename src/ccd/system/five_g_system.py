"""
The two-layer system model for the 5G cloud radio access network example.

The network has four gNBs (RU+DU+CU) over two vBBUs, a core, and a near-RT/non-RT RIC.
The attacker has compromised CU_3 (code execution) and controls UEs on DU_1 generating
traffic in 5QI classes 1-3; at detection it has not moved beyond CU_3.

The causal model (per DU i, 5QI class k in 1..Q, CU j, direction d in {U(L), D(L)}):

    UE^{ik} -> L^{ik} -> Ladm^i          admission: Ladm^i_d = Uu * sum_{k>=QI_i} L^{ik}_d
    Ladm^i -> Cbar^i                     carried per-cell load (+ load variation)
    Cbar^i -> Chat^{ij}                  attachment: Chat^{ij}_d = 1{Ccal_i = j} * Cbar^i_d
    Chat^{ij} -> Ctil^{ij}               midhaul:    Ctil^{ij}_d = NG_j * Chat^{ij}_d
    Ctil^{ij} -> C^i -> T^i              throughput (+ interfaces A1, N6, Xn, E2)

Operator controls X = interfaces {Uu, E2, A1, N6, Xn}, per-DU 5QI thresholds QI_i, per-DU
CU attachment Ccal_i (helper ``AT(i)``), and per-CU midhaul enables NG_j. Functionality
J = the eight throughputs T^i_d plus the management interfaces E2, A1 (so E2, A1 lie in
both X and J). Attacker-controlled Y = the DU_1 attacker UEs (classes 1-3) and the CU_3
carried loads Chat^{i3}. Functionality Phi = sum_{i,d} E{T^i_d} + omega*(E2 + A1).

Two operator interventions are *non-binary*: D(QI_i) raises the admission threshold above
the attacker's classes (=4), and D(Ccal_i) re-attaches DU_i to a healthy CU. These, and
the value-aware deactivation of the admission/attachment gates, are why this model uses
the generalized ``degraded_value`` / ``deactivated_edges`` / ``augment_mode`` /
``functionality_weights`` hooks on ``SystemModel``.

NOTE on naming: the attack-graph exploit "E2" of the paper and the causal interface "E2"
would collide, so exploits are named ``EX1..EX5`` here; interfaces keep their literal
names. The two graphs' node sets are disjoint (asserted by a test).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import ClassVar, Dict, FrozenSet, Mapping, Set, Tuple
import networkx as nx
import numpy as np
import pandas as pd
from ccd.system.system_model import SystemModel

# --- structure ---------------------------------------------------------------
_NUM_DU = 4
_NUM_CU = 4
_NUM_CLASSES = 10          # Q: 5QI classes 1..10
_ATTACKER_CLASSES = (1, 2, 3)   # classes the DU_1 attacker controls
_DIRECTIONS = ("U", "D")   # uplink / downlink

# --- nominal-operation parameters for generate_dataset -----------------------
_PER_CLASS_LOAD = 3.0      # mu: mean per-class load (10 classes -> ~30 per DU/direction)
_LOAD_SD = 0.4
_CBAR_SD = 1.0
_C_SD = 1.0
_T_SD = 1.0
_W_LOW, _W_HIGH = 0.5, 1.5
_PCLOSE_HI, _PCLOSE_LO = 0.30, 0.05    # confounded (interfaces/NG) closure prob at low/high demand
_P_IFACE_DOWN = 0.03                   # rare interface outages (N6, Xn, E2, A1)
_P_QI_VARY = 0.5                       # nominal 5QI-threshold reconfig frequency
_P_AT_VARY = 0.5                       # nominal CU-reattach (load-balancing) frequency


@dataclass
class FiveGSystem(SystemModel):
    """The 5G cloud-RAN instance (fixed four DUs / four CUs)."""

    # closing E2 (near-RT RIC) is required to contain the attack but forfeits the omega
    # management term -- the X n J tension. omega is calibrated to ~one throughput stream.
    OMEGA: ClassVar[float] = 30.0
    # the midhaul products Ctil = NG * Chat are gated, so use the known function exactly
    use_known_product_mechanisms: ClassVar[bool] = True

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

    # internal indices populated by _build (not constructor arguments)
    _qi_index: Dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _at_index: Dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _ng_vars: Set[str] = field(default_factory=set, init=False, repr=False)
    _nominal_cu: Dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _degraded_config: Dict[str, int] = field(default_factory=dict, init=False, repr=False)

    # --- node-name helpers ---------------------------------------------------
    @staticmethod
    def QI(i: int) -> str:
        return f"QI{i}"

    @staticmethod
    def AT(i: int) -> str:                 # Ccal_i: CU attached to DU_i (value = target CU)
        return f"AT{i}"

    @staticmethod
    def NG(j: int) -> str:
        return f"NG{j}"

    @staticmethod
    def UE(i: int, k: int) -> str:         # 5QI class-k traffic source of DU_i (drives UL+DL)
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

    def __post_init__(self) -> None:
        self._build()

    # --- construction --------------------------------------------------------
    def _build(self) -> None:
        dus = range(1, _NUM_DU + 1)
        cus = range(1, _NUM_CU + 1)
        classes = range(1, _NUM_CLASSES + 1)
        g = self.graph

        for i in dus:
            for d in _DIRECTIONS:
                for k in classes:
                    g.add_edge(self.UE(i, k), self.L(i, k, d))
                    g.add_edge(self.L(i, k, d), self.Ladm(i, d))
                g.add_edge(self.QI(i), self.Ladm(i, d))
                g.add_edge("Uu", self.Ladm(i, d))
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

        # attack graph Gamma (exploits EX* to avoid the E2 name collision)
        gamma = self.attack_graph
        gamma.add_nodes_from(self.P(n) for n in range(0, 6))
        for pre, ex, post in [
            (self.P(0), self.EX(1), self.P(1)),   # flood RU_1 uplink -> control RU_1 traffic
            (self.P(0), self.EX(2), self.P(2)),   # exploit CU_3 -> code exec on CU_3
            (self.P(2), self.EX(3), self.P(3)),   # access E2 interface -> near-RT RIC
            (self.P(2), self.EX(4), self.P(4)),   # lateral movement -> AMF
            (self.P(3), self.EX(5), self.P(5)),   # lateral through RAN -> all DUs/CUs
        ]:
            gamma.add_edge(pre, ex)
            gamma.add_edge(ex, post)

        # role sets
        self.operator_controlled = (
            {"Uu", "E2", "A1", "N6", "Xn"}
            | {self.QI(i) for i in dus}
            | {self.AT(i) for i in dus}
            | {self.NG(j) for j in cus}
        )
        self.functionality = {self.T(i, d) for i in dus for d in _DIRECTIONS} | {"E2", "A1"}
        self.privileges = {self.P(n) for n in range(0, 6)}
        self.exploits = {self.EX(n) for n in range(1, 6)}
        self.attained = {self.P(0), self.P(1), self.P(2)}

        # cross-layer edges L = C u B
        self.capability_edges = frozenset(
            {(frozenset({self.P(1)}), self.UE(1, k)) for k in _ATTACKER_CLASSES}
            | {(frozenset({self.P(2)}), self.Chat(i, 3, d)) for i in dus for d in _DIRECTIONS}
        )
        self.blocking_edges = frozenset({
            (frozenset({"E2"}), self.EX(3)),
            (frozenset({self.NG(3)}), self.EX(4)),
        })

        # observed variables (dataset D): everything except the UE sources and the noise
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

        # known functions F-tilde: only the pure-product midhaul Ctil = NG_j * Chat
        self.product_functions = {
            self.Ctil(i, j, d): frozenset({self.NG(j), self.Chat(i, j, d)})
            for i in dus for j in cus for d in _DIRECTIONS
        }

        # degraded configurations D(X); indices used by the value-aware hooks
        self._qi_index = {self.QI(i): i for i in dus}
        self._at_index = {self.AT(i): i for i in dus}
        self._ng_vars = {self.NG(j) for j in cus}
        self._nominal_cu = {i: i for i in dus}     # DU_i nominally attached to CU_i
        self._degraded_config: Dict[str, int] = {}
        for var in ("Uu", "E2", "A1", "N6", "Xn"):
            self._degraded_config[var] = 0
        for j in cus:
            self._degraded_config[self.NG(j)] = 0
        for i in dus:
            self._degraded_config[self.QI(i)] = _ATTACKER_CLASSES[-1] + 1   # =4: reject classes 1-3
            self._degraded_config[self.AT(i)] = i                            # nominal (augment overrides)

    # --- intervention hooks --------------------------------------------------
    def degraded_value(self, var: str) -> int:
        return self._degraded_config.get(var, 0)

    def deactivated_edges(self, do: Mapping[str, int]) -> Set[Tuple[str, str]]:
        edges = set(super().deactivated_edges(do))          # midhaul product rule (NG_j = 0)
        for var, val in do.items():
            i = self._qi_index.get(var)
            if i is not None:                               # admission threshold: drop classes k < val
                for k in range(1, _NUM_CLASSES + 1):
                    if k < val:
                        for d in _DIRECTIONS:
                            edges.add((self.L(i, k, d), self.Ladm(i, d)))
            i = self._at_index.get(var)
            if i is not None:                               # attachment: keep only the chosen CU
                for j in range(1, _NUM_CU + 1):
                    if j != val:
                        for d in _DIRECTIONS:
                            edges.add((self.Cbar(i, d), self.Chat(i, j, d)))
        return edges

    def degradation_cost(self, var: str) -> float:
        """Functional damage of intervening on ``var`` (higher is attempted-dropped first),
        so the greedy minimality prefers keeping targeted low-cost interventions over
        global sledgehammers."""
        if var in ("Uu", "N6", "Xn"):     # global gates: kill every DU's admission/throughput
            return 4.0
        if var in self._ng_vars:           # closing a CU's midhaul: kills a whole CU's traffic
            return 3.0
        if var in ("E2", "A1"):            # management interfaces
            return 2.0
        if var in self._qi_index:          # per-DU admission threshold: cheap, local
            return 1.0
        return 0.0                          # AT_i re-attachment (restorative) and the rest

    def augment_mode(self, do: Mapping[str, int]) -> Dict[str, int]:
        mode = dict(do)
        closed_cus = {j for j in range(1, _NUM_CU + 1) if mode.get(self.NG(j), 1) == 0}
        open_cus = [j for j in range(1, _NUM_CU + 1) if j not in closed_cus]
        for i in range(1, _NUM_DU + 1):
            if self._nominal_cu[i] in closed_cus and self.AT(i) not in mode and open_cus:
                mode[self.AT(i)] = open_cus[0]      # re-attach DU_i to the lowest open CU
        return mode

    @property
    def functionality_weights(self) -> Mapping[str, float]:
        weights: Dict[str, float] = {
            self.T(i, d): 1.0 for i in range(1, _NUM_DU + 1) for d in _DIRECTIONS
        }
        weights["E2"] = self.OMEGA
        weights["A1"] = self.OMEGA
        return weights

    # --- nominal data-generating process (reference simulator) ---------------
    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """Return ``steps`` rows of nominal 5G operation over the observed variables.

        Honors the known functions F-tilde plus noise, with operator degradations more
        likely at low demand (the confounder that biases the naive baseline). The 5QI
        thresholds and CU attachments also vary as regular load-balancing operations.
        """
        dus = range(1, _NUM_DU + 1)
        cus = range(1, _NUM_CU + 1)
        classes = range(1, _NUM_CLASSES + 1)
        rng = np.random.RandomState(seed)

        demand = rng.uniform(_W_LOW, _W_HIGH, steps)
        frac = (demand - _W_LOW) / (_W_HIGH - _W_LOW)
        p_close = _PCLOSE_HI - (_PCLOSE_HI - _PCLOSE_LO) * frac       # confounded with demand

        def bernoulli_open(prob: np.ndarray) -> np.ndarray:
            return (rng.uniform(0.0, 1.0, steps) >= prob).astype(int)

        data: Dict[str, np.ndarray] = {}

        # operator variables
        uu = bernoulli_open(p_close)
        data["Uu"] = uu
        for iface in ("N6", "Xn", "E2", "A1"):
            data[iface] = bernoulli_open(np.full(steps, _P_IFACE_DOWN))
        qi = {}
        for i in dus:
            vary = rng.uniform(0.0, 1.0, steps) < _P_QI_VARY
            qi[i] = np.where(vary, rng.randint(2, _NUM_CLASSES + 1, steps), 1)   # nominal admit-all=1
            data[self.QI(i)] = qi[i]
        at = {}
        for i in dus:
            vary = rng.uniform(0.0, 1.0, steps) < _P_AT_VARY
            at[i] = np.where(vary, rng.randint(1, _NUM_CU + 1, steps), i)        # nominal CU_i
            data[self.AT(i)] = at[i]
        ng = {}
        for j in cus:
            ng[j] = bernoulli_open(p_close)
            data[self.NG(j)] = ng[j]

        # radio + transport chain, per DU
        for i in dus:
            for d in _DIRECTIONS:
                loads = {}
                for k in classes:
                    loads[k] = np.maximum(0.0, demand * _PER_CLASS_LOAD
                                          + rng.normal(0.0, _LOAD_SD, steps))
                    data[self.L(i, k, d)] = loads[k]
                admitted = np.zeros(steps)
                for k in classes:
                    admitted += np.where(k >= qi[i], loads[k], 0.0)
                ladm = uu * admitted                                             # admission
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
