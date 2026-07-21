import CCD.Algorithm

/-!
A formalization of statement (iii) of Prop. 1 in the paper, i.e., that the two graphical
criteria are effectively checkable, together with the executable form of the CCD
correctness theorem.

The containment criterion `ch_{Γ_u}(ch_{Γ_u}(P̃)) ⊆ P̃` is one pass over the exploits:
compute the blocked set from the blocking edges `ℬ` (`O(|𝐄| + |ℬ|)`), then verify that
every unblocked exploit with a precondition in `P̃` grants only privileges in `P̃`
(`O(|𝐏| + |𝒱|)`), for `O(|𝐏| + |𝐄| + |𝒱| + |ℬ|)` elementary operations in total. The
functionality criterion depends on the descendant set `D = de_{𝒢_u}(𝐘 \ 𝐗')`, which CCD
computes by a single graph traversal (BFS) in `O(|𝐕| + |𝐔| + |𝓔|)` time; given `D` as a
`Finset`, the criterion reduces to a `Finset` disjointness test. CCD performs at most
`|𝐗| + 1` such checks, giving the overall
`O(|𝐗|(|𝐕| + |𝐔| + |𝓔| + |𝐏| + |𝐄| + |𝒱| + |ℬ|))` bound of Prop. 3 (the runtime
bounds themselves are documented here, not machine-checked; what is machine-checked is
**decidability**, i.e., that both criteria are finite computable checks).
-/

/- Everything below this will be in the namespace "CCD"-/
namespace CCD

/-
Defines the privilege/exploit types `P`, `E` (attack layer) and the node/value types
`α`, `V` (causal layer) as implicit type variables from some universe, where equality of
causal nodes and privileges is decidable. We need decidability to be able to test
membership in finite sets of α and P.
-/
variable {P E : Type*} {α : Type*} {V : Type*} [DecidableEq α]

/--
The finite containment check CCD performs (Prop. 1 (i) as a computation): given the
attack graph `Γ`, the blocked-exploit predicate `blocked` (computed from the blocking
edges `ℬ` and the intervention set `𝐗'`), and the detected privileges `Ptil = P̃` as a
`Finset`, every unblocked exploit with a precondition in `P̃` must grant only privileges
already in `P̃` — i.e., `ch_{Γ_u}(ch_{Γ_u}(P̃)) ⊆ P̃`.
-/
def ContainmentHolds (Γ : AttackGraph P E) (blocked : E → Prop) (Ptil : Finset P) : Prop :=
  ∀ e : E, ¬ blocked e → (∃ p ∈ Ptil, Γ.pre p e) → ∀ q : P, Γ.post e q → q ∈ Ptil

/--
The containment check is decidable, i.e. there is an algorithm that decides whether
`ContainmentHolds` holds. We register this as a typeclass `instance` so that Lean
supplies the decision procedure automatically wherever the criterion must be evaluated
(e.g. in an `if` or via `decide`).

The proof does not construct the procedure by hand. `unfold ContainmentHolds` exposes
the definition and `infer_instance` assembles a `Decidable` instance from existing ones:
the outer `∀ e : E` is a finite conjunction (`Fintype E`), `¬ blocked e` is decidable by
the `DecidablePred blocked` argument, the bounded existential over the `Finset` `Ptil`
is decidable given decidable `Γ.pre`, the inner `∀ q : P` is again a finite conjunction
(`Fintype P`), and membership `q ∈ Ptil` is decidable by `DecidableEq P`. Composing
these yields the one-pass check over the exploits underlying the complexity claim of
Prop. 1 (iii).
-/
instance (Γ : AttackGraph P E) (blocked : E → Prop) (Ptil : Finset P)
    [Fintype P] [Fintype E] [DecidableEq P]
    [∀ p e, Decidable (Γ.pre p e)] [∀ e p, Decidable (Γ.post e p)]
    [DecidablePred blocked] :
    Decidable (ContainmentHolds Γ blocked Ptil) := by
  unfold ContainmentHolds; infer_instance

/--
The finite check CCD performs for a candidate intervention (lines 3–4 and 7–8 of
Algorithm 1): the containment criterion on the intervened attack graph, and the
disjointness of the functionality variables `J` from the computed descendant set
`D = de_{𝒢_u}(𝐘 \ 𝐗')`.
-/
def CriteriaHold (Γ : AttackGraph P E) (blocked : E → Prop) (Ptil : Finset P)
    (J D : Finset α) : Prop :=
  ContainmentHolds Γ blocked Ptil ∧ Disjoint J D

/--
The combined criteria check is decidable: the containment half by the instance above,
the functionality half because `Finset` disjointness is a finite membership test
(decidable equality on `α`), and a conjunction of decidable propositions is decidable.
-/
instance (Γ : AttackGraph P E) (blocked : E → Prop) (Ptil : Finset P) (J D : Finset α)
    [Fintype P] [Fintype E] [DecidableEq P]
    [∀ p e, Decidable (Γ.pre p e)] [∀ e p, Decidable (Γ.post e p)]
    [DecidablePred blocked] :
    Decidable (CriteriaHold Γ blocked Ptil J D) := by
  unfold CriteriaHold; infer_instance

/--
**Correctness of CCD, checkable form.** If the traversal's descendant set `D`
faithfully represents the model (`↑D = de_{𝒢_u}(𝐘 \ 𝐗')`, hypothesis `hD`), the finite
check `CriteriaHold` passes, and the mode's functionality meets the critical level, then
CCD's mode contains the attack (Def. 2 on the intervened attack graph) and preserves
functionality against every attacker intervention.

This is the executable counterpart of `ccd_correct`. Whereas `ccd_correct` states the
criteria abstractly (the containment hypothesis over a `Set` of privileges, the
functionality criterion as set-theoretic disjointness), this version states them as the
finite, decidable check `CriteriaHold Γ blocked Ptil J D` that CCD actually runs after
computing the blocked exploits and the descendant set `D` by graph traversals. Unlike
the causal-layer containment of the previous formalization, `P̃` is an *input* here
(the detection output), so no faithfulness hypothesis for it is needed — only `hD`
links the computed `D` to the true descendant set.

The proof bridges the finite check to the abstract criteria. `obtain ⟨hc, hf⟩ := hchk`
splits the check into the containment fact `hc : ContainmentHolds Γ blocked Ptil` and
the disjointness fact `hf : Disjoint J D`, and
`rw [Finset.disjoint_iff_inter_eq_empty] at hf` turns the latter into an empty `Finset`
intersection. We then invoke `ccd_correct` with `Ptil` coerced to a `Set`, leaving the
two abstract criteria as goals. The containment goal is `hc` transported through the
`Finset`/`Set` coercion: `rintro` destructures the existential precondition witness, and
`Finset.mem_coe` converts membership in `↑Ptil` to membership in `Ptil` (and back for
the conclusion). The functionality goal is closed by rewriting the abstract intersection
backwards through the faithfulness equation `hD` into the coercion of the `Finset`
intersection (`Finset.coe_inter`), replacing it by `∅` via `hf`, and finishing with
`Finset.coe_empty`.
-/
theorem ccd_correct_check (Γ : AttackGraph P E) (blocked : E → Prop) (Ptil : Finset P)
    (M : SCM α V) (Yeff J : Finset α)
    (Φagg : ((α → V) → {x // x ∈ J} → V) → ℝ) (α₀ : ℝ) (D : Finset α)
    (hD : (↑D : Set α) = descendants M Yeff)
    (hchk : CriteriaHold Γ blocked Ptil J D)
    (hα : Phi M J Φagg noI ≥ α₀) :
    (Γ.intervene blocked).GContained (↑Ptil : Set P) ∧ PreservesΦ M Yeff J Φagg α₀ := by
  obtain ⟨hc, hf⟩ := hchk
  rw [Finset.disjoint_iff_inter_eq_empty] at hf
  refine ccd_correct Γ blocked (↑Ptil : Set P) M Yeff J Φagg α₀ ?_ ?_ hα
  · rintro e hnb ⟨p, hpS, hpre⟩ q hpost
    exact Finset.mem_coe.mpr (hc e hnb ⟨p, Finset.mem_coe.mp hpS, hpre⟩ q hpost)
  · rw [← hD, ← Finset.coe_inter, hf, Finset.coe_empty]

end CCD
