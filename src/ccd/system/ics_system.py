"""
The two-layer system model for the industrial control system (ICS) example.

The system runs the Tennessee Eastman process across an enterprise network (web server
behind an Internet gateway), a supervisory network (control server + engineering
station), and a field network of valve controllers. The attacker has code execution on
the web server and can move laterally into the supervisory network to inject unsafe
process commands; at detection the IDS localizes it to the web server and the control
server (not the engineering station).

The causal model:

    W  -> I                              web integrity depends on the web-server state
    G2c, C -> Ctil                       supervisory control state:  Ctil = G2c * C
    Chat, Ctil -> V                      valve state (remote-driven): V   = Chat * Ctil
    V, A, U -> P                         physical process state (+ actuation A, disturbance U)
    P  -> S                              process safety depends on the process state

The G2 gateway enforces two policies: G2c (enterprise -> control server; carries the
supervisory commands, Ctil = G2c * C) and G2e (enterprise -> engineering station; no
causal edges -- it matters only through its blocking edge, like the IT A_i). The valves
follow commands only in remote-control mode (V = Chat * Ctil); the two products are the
known F-tilde, the remaining functions (I, P, S) are unknown.

Roles: operator controls X = {W, G2e, G2c, Chat}; attacker controls Y = {W, C}
(web-server state via P1, supervisory commands via P3); functionality
J = {I, S, G2e, G2c} (web integrity + process safety + the gateway policies), so W lies
in both X and Y, and the gateways lie in both X and J.
Phi(M) = E{I} + E{S} + epsilon * E{G2_1 + G2_2} with epsilon = EPSILON = 0.5, where the
gateway terms are deterministic policy terms (exact per mode). The essential level is
alpha = 0.4 * Phi(M) (``alpha_fraction``).

The web-server state W has domain {0, 1, 2}: 0 = unavailable (safe mode),
1 = available, 2 = service responses tampered with. The attack (impact) configurations
are A(W) = 2 and A(C) = 1 (malicious supervisory commands); the attacker software is
not implemented, so these appear only in the model-derived evaluation baselines, and
the nominal DGP emits W in {0, 1}.

The selected mode D_1 = do(W=0, G2e=0, Chat=0) blocks E1/E2/E4 and severs the attacker's
commands from the process (V = 0); the control-server path G2c stays open because E3 only
re-grants the conceded P3 -- this is what separates D_1 from naive block-every-vulnerability
containment, which closes G2c as well. Only ``functionality_weights`` is overridden; every
other generalization hook keeps its base default, so the ICS exercises the generalized CCD
core with no core changes.

Recovery: ``patched_exploits`` removes exploits from Gamma (patching the supervisory-net
vulnerabilities E2/E3 yields D_2 = do(W=0, Chat=0) -- the engineering path reopens; W stays
closed while the attacker holds the web server, Chat while E4 is feasible);
``attacker_evicted`` re-images the compromised hosts (P-tilde shrinks to {P0}, E1 patched),
yielding D_3 = do().
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import ClassVar, Dict, FrozenSet, Mapping, Set, Tuple
import networkx as nx
import numpy as np
import pandas as pd
from ccd.system.system_model import SystemModel

# --- causal-graph node names (Chat = C-hat control mode, Ctil = C-tilde control state) ---
W = "W"          # web-server state {0,1,2}: 0 unavailable / 1 available / 2 tampered
#                  (operator- and attacker-controlled; A(W) = 2, D(W) = 0)
I = "I"          # web-service integrity      (functionality)
G2C = "G2c"      # gateway: enterprise -> control server (operator-controlled; carries Ctil)
G2E = "G2e"      # gateway: enterprise -> engineering station (operator-controlled; no causal
#                  edges -- it matters only through its blocking edge, like the IT A_i)
CHAT = "Chat"    # control mode (remote?)     (operator-controlled)
C = "C"          # supervisory commands       (attacker-controlled; A(C) = 1 malicious)
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

    # value of each open G2 gateway policy in Phi (epsilon)
    EPSILON: ClassVar[float] = 0.5
    # essential functionality level alpha = 0.4 * Phi(M)
    alpha_fraction: ClassVar[float] = 0.4

    # operator-patched exploits: removed from Gamma (recovery actions remove edges)
    patched_exploits: FrozenSet[str] = field(default_factory=frozenset)
    # attacker evicted (web + control server re-imaged, patching E1): P-tilde -> {P0}
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

    # --- construction --------------------------------------------------------
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

        # attack graph Gamma: web foothold -> lateral movement -> command injection
        gamma = self.attack_graph
        gamma.add_nodes_from(self.Priv(n) for n in range(0, 5))
        for pre, ex, post in [
            (self.Priv(0), self.EX(1), self.Priv(1)),   # web application exploit -> web server
            (self.Priv(1), self.EX(2), self.Priv(2)),   # lateral movement -> engineering station
            (self.Priv(1), self.EX(3), self.Priv(3)),   # lateral movement -> control server
            (self.Priv(3), self.EX(4), self.Priv(4)),   # command injection -> field controllers
        ]:
            if ex not in patched:
                gamma.add_edge(pre, ex)
                gamma.add_edge(ex, post)

        # role sets
        self.operator_controlled = {W, G2E, G2C, CHAT}
        self.functionality = {I, S, G2E, G2C}
        self.privileges = {self.Priv(n) for n in range(0, 5)}
        self.exploits = {self.EX(n) for n in range(1, 5)} - patched
        # detected: web server (P1) and control server (P3) compromised, not the
        # engineering station (P2) or the field controllers (P4); eviction re-images both
        self.attained = ({self.Priv(0)} if self.attacker_evicted
                         else {self.Priv(0), self.Priv(1), self.Priv(3)})

        # cross-layer edges L = C u B
        self.capability_edges = frozenset({
            (frozenset({self.Priv(1)}), W),      # code exec on the web server -> web-server state
            (frozenset({self.Priv(3)}), C),      # control-server access -> supervisory commands
        })
        blocking = [
            (frozenset({W}), self.EX(1)),        # safe web-server state -> no web app to exploit
            (frozenset({G2E}), self.EX(2)),      # closed engineering-station path -> no lateral
            #                                      movement to the engineering station
            (frozenset({G2C}), self.EX(3)),      # closed control-server path -> no lateral
            #                                      movement to the control server (conceded: P3 in P~)
            (frozenset({CHAT}), self.EX(4)),     # local control mode -> no remote command injection
        ]
        self.blocking_edges = frozenset((req, ex) for req, ex in blocking if ex not in patched)

        # observed variables (dataset D): all endogenous/operator vars with causal edges;
        # the exogenous A and U are unobserved noise folded into P's mechanism, and G2e
        # is unobserved (no causal edges -- it enters Phi only through its policy state)
        self.throughput_nodes = {W, I, G2C, CHAT, C, CTIL, V, P, S}

        # known functions F-tilde: the gated control-state and valve products
        self.product_functions = {
            CTIL: frozenset({G2C, C}),           # Ctil = G2c * C
            V: frozenset({CHAT, CTIL}),          # V = Chat * Ctil
        }

    # --- intervention hooks --------------------------------------------------
    def attack_value(self, var: str) -> int:
        """A(W) = 2 (service responses tampered with) and A(C) = 1 (malicious
        supervisory commands); the ICS impact is tampering, not denial."""
        if var == W:
            return 2
        if var == C:
            return 1
        return super().attack_value(var)

    @property
    def functionality_weights(self) -> Mapping[str, float]:
        """Phi(M) = E{I} + E{S} + epsilon * E{G2_1 + G2_2}. The I and S columns are
        recorded as 0-100 scores (simulator and testbed alike), so their weight 0.01
        rescales them to [0, 1] indicators and puts epsilon = 0.5 on the same
        scale; the gateway terms are deterministic policy terms."""
        return {I: 0.01, S: 0.01, G2E: self.EPSILON, G2C: self.EPSILON}

    # --- nominal data-generating process (reference simulator) ---------------
    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """Return ``steps`` rows of nominal ICS operation over the observed variables.

        Honors the known products plus noise. Maintenance (``W=0``/``G2c=0``/``Chat=0``)
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
        which = np.where(maintain, rng.randint(0, 3, steps), -1)       # -1 = none; 0/1/2 = W/G2c/Chat
        w = (which != 0).astype(int)
        g2c = (which != 1).astype(int)
        chat = (which != 2).astype(int)

        c = np.maximum(0.0, _CMD_GAIN * demand + rng.normal(0.0, _CMD_SD, steps))
        ctil = g2c * c                                                 # known: Ctil = G2c * C
        v = chat * ctil                                               # known: V = Chat * Ctil

        a = rng.normal(_A_MEAN, _A_SD, steps)                         # local safe control (unobserved)
        u = rng.normal(0.0, _U_SD, steps)                            # disturbance (unobserved)
        p = a + _V_GAIN * v + u                                      # process point; local control -> ~setpoint
        s = 100.0 * np.exp(-(((p - _P_SETPOINT) / _S_SPREAD) ** 2))   # safety: peak at the setpoint
        integ = np.where(w == 1, _I_HEALTHY, _I_SAFEMODE) + rng.normal(0.0, _I_SD, steps)
        integ = np.clip(integ, 0.0, 100.0)

        data = {W: w, I: integ, G2C: g2c, CHAT: chat, C: c, CTIL: ctil, V: v, P: p, S: s}
        columns = sorted(self.throughput_nodes)
        return pd.DataFrame({col: data[col] for col in columns})
