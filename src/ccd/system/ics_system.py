"""
The two-layer system model for the industrial control system (ICS) example.

The system runs the Tennessee Eastman process across an enterprise network (web server
behind an Internet gateway), a supervisory network (control server + engineering
station), and a field network of valve controllers. The attacker has code execution on
the web server and can move laterally into the supervisory network to inject unsafe
process commands; at detection the IDS localizes it to the web server and the control
server (not the engineering station).

The causal model (matching docs/graphs.png panel c):

    W  -> I                              web integrity depends on the web-server state
    G2, C -> Ctil                        supervisory control state:  Ctil = G2 * C
    Chat, Ctil -> V                      valve state (remote-driven): V   = Chat * Ctil
    V, A, U -> P                         physical process state (+ actuation A, disturbance U)
    P  -> S                              process safety depends on the process state

Supervisory commands C reach the field controllers only if the G2 gateway is open
(Ctil = G2 * C), and the valves follow those commands only in remote-control mode
(V = Chat * Ctil); these two functions are the known F-tilde. The remaining functions
(I, P, S) are unknown.

Roles: operator controls X = {W, G2, Chat} (web-server safe mode, gateway availability,
control mode); attacker controls Y = {W, C} (web-server state via P1, supervisory commands
via P3); functionality J = {I, S} (web integrity + process safety), so W lies in both X
and Y. Functionality Phi(M) = E{I} + E{S}.

The selected mode D_1 = do(W=0, G2=0, Chat=0) blocks E1-E4 and severs the attacker's
commands C from the process. Only ``functionality_weights`` is overridden; every other
generalization hook keeps its base default, so the ICS exercises the generalized CCD
core with no core changes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import ClassVar, Dict, FrozenSet, Mapping, Set, Tuple
import networkx as nx
import numpy as np
import pandas as pd
from ccd.system.system_model import SystemModel

# --- causal-graph node names (Chat = C-hat control mode, Ctil = C-tilde control state) ---
W = "W"          # web-server state          (operator- and attacker-controlled)
I = "I"          # web-service integrity      (functionality)
G2 = "G2"        # G2 gateway availability    (operator-controlled)
CHAT = "Chat"    # control mode (remote?)     (operator-controlled)
C = "C"          # supervisory commands       (attacker-controlled)
CTIL = "Ctil"    # supervisory control state  (endogenous;  Ctil = G2 * C)
V = "V"          # valve state                (endogenous;  V = Chat * Ctil)
P = "P"          # physical process state     (endogenous)
S = "S"          # process safety             (functionality)
A = "A"          # valve actuation            (exogenous, unobserved)
U = "U"          # random disturbance         (exogenous, unobserved)

# --- nominal-operation parameters for generate_dataset -----------------------
_D_LOW, _D_HIGH = 0.5, 1.5              # production-demand range
_PCLOSE_HI, _PCLOSE_LO = 0.30, 0.05    # maintenance prob at low/high demand (the confounder)
_CMD_GAIN = 40.0                       # supervisory command magnitude per unit demand
_CMD_SD = 3.0
_A_MEAN, _A_SD = 50.0, 4.0             # local safe-control actuation (holds P at setpoint 50)
_U_SD = 4.0                            # process disturbance
_V_GAIN = 0.05                         # modest remote-command influence on the process point
_P_SETPOINT = 50.0
_S_SPREAD = 12.0                       # safety falls off as P leaves the safe band
_I_HEALTHY, _I_SAFEMODE, _I_SD = 88.0, 48.0, 3.0


@dataclass
class IcsSystem(SystemModel):
    """The industrial control system (Tennessee Eastman) instance."""

    # the known control-state / valve products are gated (Ctil = 0 when G2 = 0, V = 0 when
    # Chat = 0), so use F-tilde as exact mechanisms rather than fitting a regressor.
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

    @staticmethod
    def Priv(n: int) -> str:
        return f"P{n}"

    @staticmethod
    def EX(n: int) -> str:
        return f"E{n}"

    def __post_init__(self) -> None:
        self._build()

    # --- construction --------------------------------------------------------
    def _build(self) -> None:
        g = self.graph
        g.add_edge(W, I)
        g.add_edge(G2, CTIL)
        g.add_edge(C, CTIL)
        g.add_edge(CHAT, V)
        g.add_edge(CTIL, V)
        g.add_edge(V, P)
        g.add_edge(A, P)
        g.add_edge(U, P)
        g.add_edge(P, S)

        # attack graph Gamma: web foothold -> lateral movement -> command injection
        gamma = self.attack_graph
        gamma.add_nodes_from(self.Priv(n) for n in range(0, 5))
        for pre, ex, post in [
            (self.Priv(0), self.EX(1), self.Priv(1)),   # web application exploit -> web server
            (self.Priv(1), self.EX(2), self.Priv(2)),   # lateral movement -> engineering station
            (self.Priv(1), self.EX(3), self.Priv(3)),   # lateral movement -> control server
            (self.Priv(3), self.EX(4), self.Priv(4)),   # command injection -> field controllers
        ]:
            gamma.add_edge(pre, ex)
            gamma.add_edge(ex, post)

        # role sets
        self.operator_controlled = {W, G2, CHAT}
        self.functionality = {I, S}
        self.privileges = {self.Priv(n) for n in range(0, 5)}
        self.exploits = {self.EX(n) for n in range(1, 5)}
        # detected: web server (P1) and control server (P3) compromised, not the
        # engineering station (P2) or the field controllers (P4)
        self.attained = {self.Priv(0), self.Priv(1), self.Priv(3)}

        # cross-layer edges L = C u B
        self.capability_edges = frozenset({
            (frozenset({self.Priv(1)}), W),      # code exec on the web server -> web-server state
            (frozenset({self.Priv(3)}), C),      # control-server access -> supervisory commands
        })
        self.blocking_edges = frozenset({
            (frozenset({W}), self.EX(1)),        # safe web-server state -> no web app to exploit
            (frozenset({G2}), self.EX(2)),       # closed gateway -> no lateral movement into
            (frozenset({G2}), self.EX(3)),       # the supervisory net (blocks both E2 and E3)
            (frozenset({CHAT}), self.EX(4)),     # local control mode -> no remote command injection
        })

        # observed variables (dataset D): all endogenous/operator vars; the exogenous
        # actuation A and disturbance U are unobserved noise folded into P's mechanism
        self.throughput_nodes = {W, I, G2, CHAT, C, CTIL, V, P, S}

        # known functions F-tilde: the gated control-state and valve products
        self.product_functions = {
            CTIL: frozenset({G2, C}),            # Ctil = G2 * C
            V: frozenset({CHAT, CTIL}),          # V = Chat * Ctil
        }

    # --- intervention hooks --------------------------------------------------
    @property
    def functionality_weights(self) -> Mapping[str, float]:
        """Phi(M) = E{I} + E{S}: web-service integrity plus physical-process safety."""
        return {I: 1.0, S: 1.0}

    # --- nominal data-generating process (reference simulator) ---------------
    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """Return ``steps`` rows of nominal ICS operation over the observed variables.

        Honors the known products plus noise. Maintenance (``W=0``/``G2=0``/``Chat=0``)
        is mutually exclusive per window and likelier at low demand -- the confounder:
        the joint degraded config never occurs observationally (Phi must be
        *identified*, not read off) and naive conditioning is biased.
        """
        rng = np.random.RandomState(seed)

        demand = rng.uniform(_D_LOW, _D_HIGH, steps)
        frac = (demand - _D_LOW) / (_D_HIGH - _D_LOW)
        p_close = _PCLOSE_HI - (_PCLOSE_HI - _PCLOSE_LO) * frac        # confounded with demand

        # at most one operator variable is degraded per window (mutually exclusive
        # maintenance), so the three closures never co-occur in nominal data
        maintain = rng.uniform(0.0, 1.0, steps) < p_close
        which = np.where(maintain, rng.randint(0, 3, steps), -1)       # -1 = none; 0/1/2 = W/G2/Chat
        w = (which != 0).astype(int)
        g2 = (which != 1).astype(int)
        chat = (which != 2).astype(int)

        c = np.maximum(0.0, _CMD_GAIN * demand + rng.normal(0.0, _CMD_SD, steps))
        ctil = g2 * c                                                  # known: Ctil = G2 * C
        v = chat * ctil                                               # known: V = Chat * Ctil

        a = rng.normal(_A_MEAN, _A_SD, steps)                         # local safe control (unobserved)
        u = rng.normal(0.0, _U_SD, steps)                            # disturbance (unobserved)
        p = a + _V_GAIN * v + u                                      # process point; local control -> ~setpoint
        s = 100.0 * np.exp(-(((p - _P_SETPOINT) / _S_SPREAD) ** 2))   # safety: peak at the setpoint
        integ = np.where(w == 1, _I_HEALTHY, _I_SAFEMODE) + rng.normal(0.0, _I_SD, steps)
        integ = np.clip(integ, 0.0, 100.0)

        data = {W: w, I: integ, G2: g2, CHAT: chat, C: c, CTIL: ctil, V: v, P: p, S: s}
        columns = sorted(self.throughput_nodes)
        return pd.DataFrame({col: data[col] for col in columns})
