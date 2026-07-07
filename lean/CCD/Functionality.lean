import Mathlib.Tactic
import CCD.Degradation

/-!
# Graphical criterion for essential functionality

**Prop. "Graphical criterion for essential functionality".** If the functionality
variables `J` are disjoint from the descendants `de_{𝒢_u}(Y)`, then no attacker
intervention can change the functionality: `Φ(𝓜_{u,a}) = Φ(𝓜_u)` for all `a`.

Both this criterion and the containment criterion depend on the same descendant set
`de_{𝒢_u}(Y)` (cf. `CCD.Containment`), so they are checkable in a single traversal.
-/

namespace CCD

variable {α : Type*} {V : Type*} [DecidableEq α]

theorem functionality_invariant_of_disjoint (M : SCM α V) (Y J : Finset α)
    (Φagg : ((α → V) → {x // x ∈ J} → V) → ℝ)
    (h : (↑J : Set α) ∩ descendants M Y = ∅) :
    ∀ a, Attacker Y a → Phi M J Φagg a = Phi M J Φagg noI := by
  intro a ha
  have hagree : ∀ v, v ∉ Y → a v = (noI : α → Option V) v := by
    intro v hv; simp only [noI]; exact ha v hv
  unfold Phi
  congr 1
  funext ω p
  apply eval_eq_off_descendants M a noI ω Y hagree
  intro hde
  have hmem : (p : α) ∈ (↑J : Set α) ∩ descendants M Y := ⟨Finset.mem_coe.mpr p.2, hde⟩
  rw [h] at hmem
  exact (Set.mem_empty_iff_false _).mp hmem

end CCD
