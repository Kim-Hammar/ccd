"""Tests for the worst-case attacker intervention (Problem 1's ``for all a`` clause)."""

from __future__ import annotations
from ccd.ccd import select_intervention
from ccd.system.five_g_system import FiveGSystem
from ccd.system.ics_system import IcsSystem
from ccd.system.illustrative_example_system import IllustrativeExampleSystem
from ccd.util.graph_util import attainable_privileges, check_criteria, worst_case_attack


# --- attainable privileges ---------------------------------------------------
def test_contained_mode_attains_nothing_new():
    """A contained mode leaves the attainable set equal to P-tilde (Def. 2)."""
    for system in (IllustrativeExampleSystem(5), FiveGSystem(), IcsSystem()):
        u = select_intervention(system)
        assert u is not None
        assert check_criteria(system, u.variables).contained
        assert attainable_privileges(system, set(u.variables)) == system.attained


def test_uncontained_mode_attains_more():
    """Without any intervention the IT attacker moves laterally to every server."""
    system = IllustrativeExampleSystem(5)
    attainable = attainable_privileges(system, set())
    assert system.attained < attainable
    assert attainable == system.privileges


# --- worst-case attack -------------------------------------------------------
def test_it_no_degradation_attack_matches_paper():
    """No degradation: the attacker reaches every server and drops all carried load."""
    m = 5
    system = IllustrativeExampleSystem(m)
    attack = worst_case_attack(system, {})
    assert attack == {f"Tt{i}": 0 for i in range(1, m + 1)}


def test_ics_no_degradation_attack_matches_paper():
    """No degradation: do_A(W=2, C=1) -- tampered responses + malicious commands."""
    assert worst_case_attack(IcsSystem(), {}) == {"C": 1, "W": 2}


def test_degradation_takes_priority_on_shared_variables():
    """W is in X n Y: pinned by the operator, it is excluded from the attack."""
    system = IcsSystem()
    attack = worst_case_attack(system, {"W": 0, "G2e": 0, "Chat": 0})
    assert "W" not in attack
    assert attack == {"C": 1}


def test_it_contained_mode_confines_the_attack_to_the_foothold():
    m = 5
    system = IllustrativeExampleSystem(m)
    u = select_intervention(system)
    assert u is not None
    assert worst_case_attack(system, u.variables) == {"Tt1": 0}


def test_five_g_attack_covers_attacker_ues_and_cu3_loads():
    system = FiveGSystem()
    attack = worst_case_attack(system, {})
    assert {f"UE_1_{k}" for k in (7, 8, 9, 10)} <= set(attack)
    assert {system.Chat(i, 3, d) for i in range(1, 5) for d in ("U", "D")} <= set(attack)
    assert all(value == 0 for value in attack.values())   # denial, not tampering
