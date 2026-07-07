import CCD.Containment
import CCD.Functionality

/-!
# Causal Controlled Degradation (Algorithm 1)

**Prop. "Correctness of CCD".** An intervention that satisfies both graphical criteria
(containment and essential functionality) and whose degraded-mode functionality meets the
critical level `α₀` is a solution to the controlled degradation problem — i.e. it contains
the attack *and* preserves functionality under every attacker intervention. This is exactly
what CCD returns, so any intervention it returns solves the problem.

Since CCD checks the two criteria against the same descendant set, the guarantees follow by
combining `containment_of_disjoint` (Prop. containment) and
`functionality_invariant_of_disjoint` (Prop. functionality). The `O(|X|(|V|+|U|+|𝓔|)+c)`
complexity bound is documented rather than machine-checked (see `CCD.CausalModel` /
`Decidable` instances for checkability).
-/

namespace CCD

variable {α : Type*} {V : Type*} [DecidableEq α]

/-- **Correctness of CCD.** If, for the degraded mode `𝓜_u = M` with attacker-controlled
variables `Y`:
* the unattained privileges are disjoint from `de_{𝒢_u}(Y)` (containment criterion),
* the functionality variables `J` are disjoint from `de_{𝒢_u}(Y)` (functionality criterion), and
* the mode's functionality `Φ(𝓜_u)` meets the critical level `α₀`,

then the mode contains the attack and preserves functionality for all attacker
interventions (i.e. it satisfies the containment and critical-functionality constraints of
the controlled degradation problem). -/
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
