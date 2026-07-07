import CCD.Algorithm

/-!
# Checkable form of the criteria (decidability + complexity)

The two graphical criteria depend on the descendant set `D = de_{𝒢_u}(Y)`, which CCD
computes by a single graph traversal (BFS) in `O(|𝐕| + |𝐔| + |𝓔|)` time
(Props. "Complexity of checking containment/functionality"). Given `D` as a `Finset`, the
criteria reduce to two `Finset` disjointness tests, which are **decidable** (a linear-time
membership test). CCD performs at most `|𝐗| + 1` such checks, giving the overall
`O(|𝐗|(|𝐕| + |𝐔| + |𝓔|) + c)` bound of Prop. "Correctness and complexity of CCD" (the
runtime bounds themselves are documented here, not machine-checked).
-/

namespace CCD

variable {α : Type*} {V : Type*} [DecidableEq α]

/-- The finite check CCD performs once it has computed `D = de_{𝒢_u}(Y)`: the unattained
privileges and the functionality variables are each disjoint from `D`. -/
def CriteriaHold (unattained J D : Finset α) : Prop := Disjoint unattained D ∧ Disjoint J D

/-- The check is decidable (a linear-time disjointness test on finite sets). -/
instance (unattained J D : Finset α) : Decidable (CriteriaHold unattained J D) := by
  unfold CriteriaHold; infer_instance

/-- **Correctness of CCD, checkable form.** If the traversal's descendant set `D` and the
detected unattained-privilege set `unattained` faithfully represent the model
(`↑D = de_{𝒢_u}(Y)` and `↑unattained = 𝐏 ∖ P̃_{𝓜_u}`), the finite check passes, and the
mode's functionality meets the critical level, then CCD's mode contains the attack and
preserves functionality. -/
theorem ccd_correct_check (M : SCM α V) (Y P J : Finset α) (holds : V → Prop)
    (Φagg : ((α → V) → {x // x ∈ J} → V) → ℝ) (α₀ : ℝ) (unattained D : Finset α)
    (hD : (↑D : Set α) = descendants M Y)
    (hU : (↑unattained : Set α) = (↑P : Set α) \ Ptilde M P holds noI)
    (hchk : CriteriaHold unattained J D)
    (hα : Phi M J Φagg noI ≥ α₀) :
    Contains M Y P holds ∧ PreservesΦ M Y J Φagg α₀ := by
  obtain ⟨hc, hf⟩ := hchk
  rw [Finset.disjoint_iff_inter_eq_empty] at hc hf
  refine ccd_correct M Y P J holds Φagg α₀ ?_ ?_ hα
  · rw [← hU, ← hD, ← Finset.coe_inter, hc, Finset.coe_empty]
  · rw [← hD, ← Finset.coe_inter, hf, Finset.coe_empty]

end CCD
