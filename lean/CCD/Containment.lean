import Mathlib.Tactic
import CCD.Degradation

/-!
# Graphical criterion for containment

**Prop. "Graphical criterion for containment".** If the unattained privileges
`P ∖ P̃_{𝓜_u}` are disjoint from the descendants `de_{𝒢_u}(Y)` of the attacker-controlled
variables, then the intervention contains the attack (no attacker intervention can make an
unattained privilege attained).
-/

namespace CCD

variable {α : Type*} {V : Type*} [DecidableEq α]

theorem containment_of_disjoint (M : SCM α V) (Y P : Finset α) (holds : V → Prop)
    (h : ((↑P : Set α) \ Ptilde M P holds noI) ∩ descendants M Y = ∅) :
    Contains M Y P holds := by
  intro a ha p hp
  obtain ⟨hpP, ω, hω⟩ := hp
  refine ⟨hpP, ?_⟩
  by_contra hcon
  simp only [not_exists] at hcon
  -- p is an unattained privilege of the degraded mode
  have hunatt : p ∈ ((↑P : Set α) \ Ptilde M P holds noI) := by
    refine ⟨Finset.mem_coe.mpr hpP, ?_⟩
    rintro ⟨-, ω', hω'⟩
    exact hcon ω' hω'
  -- hence, by the criterion, p is not a descendant of Y
  have hnde : p ∉ descendants M Y := by
    intro hde
    have hmem : p ∈ ((↑P : Set α) \ Ptilde M P holds noI) ∩ descendants M Y := ⟨hunatt, hde⟩
    rw [h] at hmem
    exact (Set.mem_empty_iff_false p).mp hmem
  -- the attacker intervention agrees with the no-op off Y, so it cannot change p
  have hagree : ∀ v, v ∉ Y → a v = (noI : α → Option V) v := by
    intro v hv; simp only [noI]; exact ha v hv
  have hev : eval M a ω p = eval M noI ω p :=
    eval_eq_off_descendants M a noI ω Y hagree p hnde
  rw [hev] at hω
  exact hcon ω hω

end CCD
