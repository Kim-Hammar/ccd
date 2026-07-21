import CCD.Containment
import CCD.Functionality

/-!
A formalization of Prop. 3 in the paper, i.e., the correctness of CCD in the two-layer
model `⟨Γ, 𝒢, ℒ⟩`.
-/

/- Everything below this will be in the namespace "CCD"-/
namespace CCD

/-
Defines the privilege/exploit types `P`, `E` (attack layer) and the node/value types
`α`, `V` (causal layer) as implicit type variables from some universe, where equality of
causal nodes is decidable. We need decidability to be able to modify sets of α, i.e.,
insert or remove elements etc.
-/
variable {P E : Type*} {α : Type*} {V : Type*} [DecidableEq α]

/--
**Correctness of CCD (Prop. 3 in the paper).** Consider a degradation intervention
`u = do(𝐗'=D(𝐗'))` in the two-layer model, represented here by:
* `Γ` — the attack graph, and `blocked` — the exploits made infeasible by `u` via the
  blocking edges `ℬ` (so `Γ.intervene blocked` is the intervened attack graph `Γ_u`);
* `Ptil` — the set of possible attacker privileges `P̃` at detection time;
* `M` — the intervened SCM `𝓜_u` (the degraded mode);
* `Yeff` — the effective attacker-controlled variables `𝐘 \ 𝐗'` (operator priority on
  the overlap `𝐗 ∩ 𝐘`);
* `J`, `Φagg`, `α₀` — the functionality variables, the functionality aggregate, and the
  critical functionality level.

If
* `hC`: every unblocked exploit with a precondition in `P̃` grants only privileges in
  `P̃` — the containment criterion `ch_{Γ_u}(ch_{Γ_u}(P̃)) ⊆ P̃` of Prop. 1 (i);
* `hF`: the functionality variables are disjoint from `de_{𝒢_u}(𝐘 \ 𝐗')` — the
  functionality criterion of Prop. 1 (ii); and
* `hα`: the mode's functionality `Φ(𝓜_u)` meets the critical level `α₀`,

then `u` contains the attack in the sense of Def. 2 (`de_{Γ_u}(P̃) ∩ 𝐏 ⊆ P̃`) and
preserves functionality `≥ α₀` for **all** attacker interventions — i.e., it satisfies
both constraints of the controlled degradation problem (Problem 1). This is the
capstone result composing the two graphical criteria of Prop. 1.

The proof builds the conjunction with `refine ⟨_, ?_⟩`. The first component is
discharged by `contained_of_unblocked_child` (Prop. 1 (i)) applied to the containment
criterion `hC`, yielding `(Γ.intervene blocked).GContained Ptil`. For the second
component, `intro a ha` fixes an attacker intervention `a` on `Yeff`; by Prop. 1 (ii)
(`functionality_invariant_of_disjoint`, applied to `hF`) the functionality is invariant
under attacker interventions, so rewriting turns the goal `Phi M J Φagg a ≥ α₀` into
`Phi M J Φagg noI ≥ α₀`, which is exactly `hα`.
-/
theorem ccd_correct (Γ : AttackGraph P E) (blocked : E → Prop) (Ptil : Set P)
    (M : SCM α V) (Yeff J : Finset α)
    (Φagg : ((α → V) → {x // x ∈ J} → V) → ℝ) (α₀ : ℝ)
    (hC : ∀ e, ¬ blocked e → (∃ p ∈ Ptil, Γ.pre p e) → ∀ q, Γ.post e q → q ∈ Ptil)
    (hF : (↑J : Set α) ∩ descendants M Yeff = ∅)
    (hα : Phi M J Φagg noI ≥ α₀) :
    (Γ.intervene blocked).GContained Ptil ∧ PreservesΦ M Yeff J Φagg α₀ := by
  refine ⟨contained_of_unblocked_child Γ blocked Ptil hC, ?_⟩
  intro a ha
  rw [functionality_invariant_of_disjoint M Yeff J Φagg hF a ha]
  exact hα

end CCD
