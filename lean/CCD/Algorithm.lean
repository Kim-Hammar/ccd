import CCD.Containment
import CCD.Functionality

/-!
A formalization of Prop. 5 in the paper, i.e., the correctness of CCD
-/

/- Everything below this will be in the namespace "CCD"-/
namespace CCD

/-
Defines α and  V as implicit type variables from some universe and where the equality of
different instances of the type α is decidable. We need decidability to be able to modify
sets of α, i.e., insert or remove elements etc.
-/
variable {α : Type*} {V : Type*} [DecidableEq α]

/--
**Correctness of CCD.** If, for the degraded mode `𝓜_u = M` with attacker-controlled
variables `Y`:
* the unattained privileges are disjoint from `de_{𝒢_u}(Y)` (containment criterion),
* the functionality variables `J` are disjoint from `de_{𝒢_u}(Y)` (functionality criterion), and
* the mode's functionality `Φ(𝓜_u)` meets the critical level `α₀`,

then the mode contains the attack and preserves functionality for all attacker
interventions (i.e. it satisfies the containment and critical-functionality constraints of
the controlled degradation problem).

Formally, the theorem takes an SCM `M` (the degraded mode), the attacker-controlled set `Y`, the
privilege set `P`, the functionality set `J`, the predicate `holds`, an aggregation functional `Φagg`,
and a threshold `α₀`. It takes three hypotheses: `hC`, the containment criterion (unattained privileges
disjoint from the descendants of `Y`); `hF`, the functionality criterion (functionality variables
disjoint from the descendants of `Y`); and `hα`, that the functionality of the mode under the no-op
intervention meets the critical level. It concludes the conjunction `Contains M Y P holds ∧
PreservesΦ M Y J Φagg α₀`, i.e. the mode satisfies both constraints of the controlled degradation problem.

This is the capstone result: it composes the two graphical criteria (Prop. 1 and Prop. 3) into the
correctness statement for CCD, namely that any mode passing both checks and meeting the functionality level
is a feasible solution to the degradation problem.

The proof builds the conjunction with `refine ⟨_, ?_⟩`. The first component is discharged directly by
`containment_of_disjoint M Y P holds hC`, i.e. Prop. 1 applied to the containment criterion `hC`, which
yields `Contains M Y P holds`. The second component, `PreservesΦ M Y J Φagg α₀`, remains as a goal.

To prove it, `intro a ha` fixes an attacker intervention `a` with proof `ha : Attacker Y a`; the goal is
then `Phi M J Φagg a ≥ α₀`. By Prop. 3 (`functionality_invariant_of_disjoint`, applied to the functionality
criterion `hF`), the functionality is invariant under attacker interventions, so `Phi M J Φagg a =
Phi M J Φagg noI`; rewriting with this equality turns the goal into `Phi M J Φagg noI ≥ α₀`, which is exactly
the hypothesis `hα`. Thus the mode preserves functionality against every attacker, completing the proof.

Together the two components establish that the mode contains the attack and keeps functionality at or above
`α₀` for all attacker interventions, which is the machine-checked correctness guarantee for the degraded modes
selected by CCD.
-/
theorem ccd_correct (M : SCM α V) (Y P J : Finset α) (holds : V → Prop)
    (Φagg : ((α → V) → {x // x ∈ J} → V) → ℝ) (α₀ : ℝ)
    (hC : ((↑P : Set α) \ Ptilde M P holds noI) ∩ descendants M Y = ∅)
    (hF : (↑J : Set α) ∩ descendants M Y = ∅)
    (hα : Phi M J Φagg noI ≥ α₀) :
    Contains M Y P holds ∧ PreservesΦ M Y J Φagg α₀ := by
  refine ⟨containment_of_disjoint M Y P holds hC, ?_⟩
  intro a ha
  rw [functionality_invariant_of_disjoint M Y J Φagg hF a ha]
  exact hα

end CCD
