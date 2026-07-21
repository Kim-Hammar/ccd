"""Unit Tests for CCD."""

import copy
import time
import warnings
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Set, Tuple
import networkx as nx
import numpy as np
import pytest
warnings.filterwarnings("ignore")
from ccd.ccd import ccd, select_intervention
from ccd.util.graph_util import (
    blocked_exploits,
    check_criteria,
    descendants,
    intervened_attack_graph,
    intervened_graph,
)
from ccd.util.perturb_util import (
    evaluate_structural,
    overspecify,
    overspecify_attack,
    overspecify_privileges,
    perturb_detection,
    underspecify,
    underspecify_attack,
    underspecify_privileges,
)
from ccd.system.illustrative_example_system import IllustrativeExampleSystem
from ccd.system.system_model import SystemModel

E = IllustrativeExampleSystem.E


def expected_mode(m: int) -> set:
    """CCD should isolate the compromised n_1: close N_1, M_1, and all A_i (i>=2)."""
    return {"N1", "M1"} | {f"A{i}" for i in range(2, m + 1)}


def patched_system(m: int) -> IllustrativeExampleSystem:
    """Scenario 2: operators have patched the exploits E_2..E_{m+1}."""
    return IllustrativeExampleSystem(m, patched_exploits=frozenset(E(i) for i in range(2, m + 2)))


def evicted_system(m: int) -> IllustrativeExampleSystem:
    """Scenario 3: E_2..E_{m+1} patched, then the attacker evicted from n_1 (E_1 patched,
    P-tilde = {P0}); the derived attacker-controlled set Y is empty."""
    return IllustrativeExampleSystem(
        m,
        patched_exploits=frozenset(E(i) for i in range(2, m + 2)),
        attacker_evicted=True,
    )


# --- structural tests (fast, graph-only) ------------------------------------
@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_selects_isolate_n1_mode(m):
    u = select_intervention(IllustrativeExampleSystem(m))
    assert u is not None
    assert set(u.variables) == expected_mode(m)
    assert all(v == 0 for v in u.variables.values())   # every selected link is closed


@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_selected_mode_satisfies_criteria(m):
    system = IllustrativeExampleSystem(m)
    u = select_intervention(system)
    res = check_criteria(system, u.variables)
    assert res.contained, "every feasible exploit must be blocked or grant only privileges in P-tilde"
    assert res.functional, "throughput T must not be reachable by the attacker"


@pytest.mark.parametrize("drop", ["N1", "M1", "A2"])
def test_mode_is_minimal_dropping_any_link_breaks_a_criterion(drop):
    """Removing any single link from the selected mode must violate a criterion,
    which shows the selected mode is minimal (Algorithm 1, lines 5-8)."""
    system = IllustrativeExampleSystem(5)
    u = select_intervention(system)
    reduced = {v: 0 for v in u.variables if v != drop}
    assert not check_criteria(system, reduced).ok


def test_no_intervention_is_infeasible():
    """With no links closed, feasible exploits grant unattained privileges and the
    attacker reaches T."""
    system = IllustrativeExampleSystem(5)
    res = check_criteria(system, {})
    assert not res.contained
    assert not res.functional


def test_criteria_result_reports_violating_exploits():
    """With no links closed, exactly the exploits granting unattained privileges violate
    containment (E_1 grants P_1, which is already in P-tilde, so it is conceded)."""
    system = IllustrativeExampleSystem(5)
    res = check_criteria(system, {})
    assert res.violating_exploits == {E(i) for i in range(2, 7)}
    assert res.blocked == set()


def test_blocked_exploits_and_intervened_attack_graph():
    """Blocking edges: do(A2=0) blocks exactly E2; do(M1=0) blocks the credential
    exploit E_{m+1}; a partial blocking set (no blocking edge satisfied) blocks nothing."""
    system = IllustrativeExampleSystem(5)
    assert blocked_exploits(system, {"A2"}) == {"E2"}
    assert blocked_exploits(system, {"M1"}) == {"E6"}
    assert blocked_exploits(system, {"N1", "N2"}) == set()

    gamma_u = intervened_attack_graph(system, {"A2"})
    assert "E2" not in gamma_u
    assert not gamma_u.has_edge("P1", "E2")
    assert "E3" in gamma_u


def test_candidate_set_matches_algorithm_line_1():
    """X' = (X n an_G(J)) u the blocking sets of exploits granting unattained privileges:
    all N_i and M_i (throughput ancestors) plus A_2..A_m (blocking E_2..E_m; M_1 blocks
    E_{m+1} and is already an ancestor of J)."""
    m = 5
    system = IllustrativeExampleSystem(m)
    u = select_intervention(system)
    assert u is not None
    # the *selected* mode is a subset of the candidate set; check the candidate structure
    # indirectly: A_i only enters via its blocking edge, so conceding P_i must drop it
    conceded = copy.deepcopy(system)
    conceded.attained = conceded.attained | {"P2"}
    u_conceded = select_intervention(conceded)
    assert "A2" not in u_conceded.variables
    assert "A3" in u_conceded.variables


def test_patched_exploits_removed_from_attack_graph():
    """Patched exploits are removed from Gamma and from the blocking edges."""
    system = patched_system(5)
    assert all(E(i) not in system.attack_graph for i in range(2, 7))
    assert all(E(i) not in system.exploits for i in range(2, 7))
    assert system.blocking_edges == frozenset()
    assert "E1" in system.attack_graph   # the foothold exploit is not patched in D_2


def test_evicted_removes_e1_and_shrinks_attained():
    """Eviction (scenario 3) patches the foothold exploit E_1 and shrinks P-tilde to {P0}."""
    system = evicted_system(5)
    assert "E1" not in system.attack_graph
    assert system.attained == {"P0"}
    assert system.attacker_controlled == set()


@dataclass
class _OverlapSystem(SystemModel):
    """Minimal synthetic system with X n Y != {} (the illustrative example has no overlap)."""

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


def test_functionality_seeds_exclude_intervened_vars():
    """Operator priority on X n Y: a variable both attacker- and operator-controlled is
    removed from the attacker's seed set once intervened on (Y \\ X' in Prop. 1 (ii))."""
    system = _OverlapSystem()
    system.graph.add_edge("S", "T")                       # service S feeds functionality T
    system.attack_graph.add_node("P1")
    system.operator_controlled = {"S"}                    # the operator can disable S ...
    system.capability_edges = frozenset({(frozenset({"P1"}), "S")})   # ... and so can the attacker
    system.functionality = {"T"}
    system.privileges = {"P1"}
    system.attained = {"P1"}

    assert system.attacker_controlled == {"S"}            # X n Y = {S}
    assert not check_criteria(system, {}).functional      # un-intervened: attacker reaches T
    assert check_criteria(system, {"S": 0}).functional    # do(S=0): seed set Y \ X' is empty


def test_capability_edges_derive_Y():
    """Y is derived from P-tilde via the capability edges: P_1 gives control of Tt_1,
    and believing P_2 held adds Tt_2."""
    m = 5
    system = IllustrativeExampleSystem(m)
    assert system.attacker_controlled == {"Tt1"}
    system.attained = system.attained | {"P2"}
    assert system.attacker_controlled == {"Tt1", "Tt2"}


def test_and_deactivation_cuts_attacker_from_throughput():
    """do(N_1=0) must remove the Tt_1 -> Th_1 edge so T leaves the attacker's reach."""
    system = IllustrativeExampleSystem(5)
    # before: attacker-controlled Tt_1 reaches T
    assert "T" in descendants(system.graph, {"Tt1"})
    g_u = intervened_graph(system, {"N1": 0})
    assert not g_u.has_edge("Tt1", "Th1")
    assert "T" not in descendants(g_u, {"Tt1"})


def test_runtime_is_polynomial_and_practical():
    """Graph-only CCD is polynomial in m (paper's bound O(|X|(|V|+|U|+|E|)), i.e. ~m^2).
    Assert it stays fast and grows no worse than roughly quadratically."""
    def timed(m):
        system = IllustrativeExampleSystem(m)
        best = min(  # take the min of a few runs to reduce timing noise
            (_time_once(system) for _ in range(3)),
        )
        return best

    select_intervention(IllustrativeExampleSystem(10))  # warm up
    t_small = timed(40)
    t_large = timed(160)   # 4x the size -> ~16x under quadratic, ~64x under cubic

    assert t_large < 5.0, "m=160 should still be fast (well under a few seconds)"
    # rule out cubic-or-worse growth (with slack for measurement noise)
    assert t_large < 32 * t_small + 0.1


def _time_once(system):
    t = time.perf_counter()
    select_intervention(system)
    return time.perf_counter() - t


# --- numeric feasibility (invokes DoWhy causal inference) --------------------
@pytest.mark.parametrize("m", [5, 10])
def test_degraded_mode_is_feasible_and_estimate_matches_analytic(m):
    system = IllustrativeExampleSystem(m)
    data = system.generate_dataset(steps=6000, seed=1)

    phi_nominal = float(data["T"].mean())
    alpha = 0.5 * phi_nominal

    # analytic interventional throughput: server 1 off, others nominal
    analytic = sum(data[f"Th{i}"].mean() for i in range(2, m + 1))

    result = ccd(system, data, alpha=alpha, num_samples=6000)

    assert result.intervention is not None
    assert set(result.intervention.variables) == expected_mode(m)
    assert result.feasible, f"Phi-hat={result.phi:.1f} should meet alpha={alpha:.1f}"
    # causal estimate should be close to the analytic (m-1)/m throughput
    assert result.phi == pytest.approx(analytic, rel=0.05)


# --- Scenario 2: exploits E_2..E_{m+1} patched (recovery step D_2) -----------
@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_patched_selects_only_isolate_gateway(m):
    """With lateral movement and DB access patched, CCD only needs to close N_1."""
    u = select_intervention(patched_system(m))
    assert u is not None
    assert set(u.variables) == {"N1"}


@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_patched_mode_satisfies_criteria(m):
    system = patched_system(m)
    res = check_criteria(system, select_intervention(system).variables)
    assert res.contained and res.functional


@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_patched_mode_is_less_restrictive_than_scenario_1(m):
    """The D_2 mode must be a strict subset of the D_1 mode (fewer links closed)."""
    d1 = set(select_intervention(IllustrativeExampleSystem(m)).variables)
    d2 = set(select_intervention(patched_system(m)).variables)
    assert d2 < d1


@pytest.mark.parametrize("m", [5, 10])
def test_patched_mode_is_feasible_and_matches_analytic(m):
    system = patched_system(m)
    data = system.generate_dataset(steps=6000, seed=1)

    alpha = 0.5 * float(data["T"].mean())
    # closing only N_1 zeroes n_1's throughput; servers 2..m are nominal
    analytic = sum(data[f"Th{i}"].mean() for i in range(2, m + 1))

    result = ccd(system, data, alpha=alpha, num_samples=6000)

    assert result.intervention is not None
    assert set(result.intervention.variables) == {"N1"}
    assert result.feasible
    assert result.phi == pytest.approx(analytic, rel=0.05)


# --- Scenario 3: attacker evicted, Y = {} (full restore D_3) -----------------
@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_evicted_has_empty_attacker_set(m):
    assert evicted_system(m).attacker_controlled == set()


@pytest.mark.parametrize("m", [2, 5, 10, 50])
def test_evicted_selects_empty_intervention(m):
    """With no attacker, no degradation is needed: CCD closes no links."""
    u = select_intervention(evicted_system(m))
    assert u is not None
    assert set(u.variables) == set()
    assert check_criteria(evicted_system(m), u.variables).ok


@pytest.mark.parametrize("m", [5, 10])
def test_evicted_restores_full_functionality(m):
    system = evicted_system(m)
    data = system.generate_dataset(steps=6000, seed=1)
    phi_nominal = float(data["T"].mean())
    alpha = 0.5 * phi_nominal

    result = ccd(system, data, alpha=alpha, num_samples=6000)

    assert result.intervention is not None
    assert set(result.intervention.variables) == set()
    assert result.feasible
    # empty intervention (do()) reproduces the full nominal throughput
    assert result.phi == pytest.approx(phi_nominal, rel=0.05)


def test_recovery_progression_is_monotone():
    """D_1 (containment) superset D_2 (patched) superset D_3 (evicted, empty)."""
    m = 10
    d1 = set(select_intervention(IllustrativeExampleSystem(m)).variables)
    d2 = set(select_intervention(patched_system(m)).variables)
    d3 = set(select_intervention(evicted_system(m)).variables)
    assert d1 > d2 > d3
    assert d3 == set()


# --- Sensitivity to misspecification (ccd/util/perturb_util.py) --------------
@pytest.mark.parametrize("perturb", [underspecify, overspecify, perturb_detection,
                                     underspecify_privileges, overspecify_privileges,
                                     underspecify_attack, overspecify_attack])
def test_rho_zero_leaves_mode_valid(perturb):
    """With no perturbation, CCD's mode is valid in the true model."""
    system = IllustrativeExampleSystem(10)
    out = evaluate_structural(system, perturb(system, 0.0, np.random.RandomState(0)))
    assert out.valid


def test_under_detection_is_detected_infeasible():
    """Missing the attacker's foothold (P_1 dropped from P-tilde) makes the foothold
    exploit E_1 look feasible-and-unblockable (no blocking edge exists for it), so the
    containment criterion is unsatisfiable and CCD returns bottom -- a *detected*
    failure, not a silent one."""
    system = IllustrativeExampleSystem(10)
    out = evaluate_structural(system, underspecify_privileges(system, 0.1, np.random.RandomState(0)))
    assert out.infeasible
    assert not out.valid


@pytest.mark.parametrize("seed", range(20))
def test_over_detection_concedes_believed_privileges(seed):
    """Under the two-layer criterion, privileges wrongly believed held are *conceded*:
    exploits into them need no blocking, so the corresponding links stay open and
    containment fails against the true model (a containment risk, symmetric with
    under-detection)."""
    system = IllustrativeExampleSystem(10)
    out = evaluate_structural(system, overspecify_privileges(system, 0.3, np.random.RandomState(seed)))
    assert out.silent_containment_failure


def test_overspecification_never_silently_unsafe():
    """Spurious *causal* edges make CCD conservative, never silently unsafe: containment
    lives entirely on the attack layer, so causal-graph overspecification cannot hide an
    attack path (it can only add candidate links)."""
    system = IllustrativeExampleSystem(10)
    for seed in range(50):
        out = evaluate_structural(system, overspecify(system, 0.3, np.random.RandomState(seed)))
        assert not out.silent_containment_failure


def test_attack_overspecification_never_silently_unsafe():
    """Spurious attack-graph edges can only make more exploits look feasible or grant
    more privileges, so CCD blocks at least as much -- never a silent containment failure."""
    system = IllustrativeExampleSystem(10)
    for seed in range(50):
        out = evaluate_structural(system, overspecify_attack(system, 0.3, np.random.RandomState(seed)))
        assert not out.silent_containment_failure


def test_missing_functionality_edge_causes_silent_functionality_failure():
    """Dropping Tt1->Th1 hides the attacker's path to T, so CCD omits N1 and functionality
    fails in the true model."""
    system = IllustrativeExampleSystem(10)
    mis = copy.deepcopy(system)
    mis.graph.remove_edge("Tt1", "Th1")
    mis.product_functions["Th1"] = mis.product_functions["Th1"] - {"Tt1"}
    assert "N1" not in select_intervention(mis).variables
    assert evaluate_structural(system, mis).silent_functionality_failure


def test_missing_attack_edge_causes_silent_containment_failure():
    """Dropping the postcondition edge E2->P2 from the attack graph makes E2 look
    harmless (it grants nothing), so CCD omits A2 and containment fails in the true
    model."""
    system = IllustrativeExampleSystem(10)
    mis = copy.deepcopy(system)
    mis.attack_graph.remove_edge("E2", "P2")
    assert "A2" not in select_intervention(mis).variables
    assert evaluate_structural(system, mis).silent_containment_failure
