import CCD.Algorithm

/-!
A formalization of Props. 2 and 4 in the paper, i.e., the computational complexity of CCD.

The two graphical criteria depend on the descendant set `D = de_{𝒢_u}(Y)`, which CCD
computes by a single graph traversal (BFS) in `O(|𝐕| + |𝐔| + |𝓔|)` time
(Props. "Complexity of checking containment/functionality"). Given `D` as a `Finset`, the
criteria reduce to two `Finset` disjointness tests, which are **decidable** (a linear-time
membership test). CCD performs at most `|𝐗| + 1` such checks, giving the overall
`O(|𝐗|(|𝐕| + |𝐔| + |𝓔|) + c)` bound of Prop. "Correctness and complexity of CCD" (the
runtime bounds themselves are documented here, not machine-checked).
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
The finite check CCD performs once it has computed `D = de_{𝒢_u}(Y)`: the unattained
privileges and the functionality variables are each disjoint from `D`.

Formally, it is a functionthat takes three finite sets of causal nodes as input: unattained, J, and D.
Given these inputs it returns a proposition which is true if the unattained set is joint from D and
the set J is disjoint from D.
-/
def CriteriaHold (unattained J D : Finset α) : Prop := Disjoint unattained D ∧ Disjoint J D

/--
The criteria check is decidable, i.e. there is an algorithm that decides whether `CriteriaHold`
holds for given finite sets. We register this as a typeclass `instance` so that Lean supplies the
decision procedure automatically wherever the criteria must be evaluated (e.g. in an `if` or via
`decide`), rather than requiring it to be passed explicitly.

The proof does not construct the procedure by hand. `unfold CriteriaHold` exposes the definition as
the conjunction `Disjoint unattained D ∧ Disjoint J D`, and `infer_instance` asks the typeclass system
to assemble a `Decidable` instance for it from existing ones: `Finset` disjointness is decidable (a
finite membership test, available because `α` has decidable equality), and a conjunction of decidable
propositions is decidable. Composing these yields the decision procedure, which is the linear-time
`Finset` disjointness check underlying the complexity claims for CCD.
-/
instance (unattained J D : Finset α) : Decidable (CriteriaHold unattained J D) := by
  unfold CriteriaHold; infer_instance

/--
**Correctness of CCD, checkable form.** If the traversal's descendant set `D` and the
detected unattained-privilege set `unattained` faithfully represent the model
(`↑D = de_{𝒢_u}(Y)` and `↑unattained = 𝐏 ∖ P̃_{𝓜_u}`), the finite check passes, and the
mode's functionality meets the critical level, then CCD's mode contains the attack and
preserves functionality.

This is the executable counterpart of `ccd_correct`. Whereas `ccd_correct` states the criteria as
set-theoretic disjointness conditions on the (possibly infinite) node type, this version states them
as the finite, decidable check `CriteriaHold unattained J D` that CCD actually runs on `Finset`s after
its graph traversal. The two extra hypotheses `hD` and `hU` are the faithfulness assumptions linking the
computed data to the model: `hD` says the traversal's descendant set `D`, coerced to a set, equals the
true descendant set `descendants M Y`, and `hU` says the detected set `unattained` equals the true set of
unattained privileges `↑P \ Ptilde M P holds noI`. Under these, passing the finite check implies the
abstract criteria, so the same correctness guarantee follows.

Formally, the theorem takes the SCM `M`, the sets `Y`, `P`, `J`, the predicate `holds`, the aggregate
`Φagg`, the threshold `α₀`, and additionally the two computed finite sets `unattained` and `D`. Its
hypotheses are the two faithfulness equations `hD`, `hU`, the decidable check `hchk : CriteriaHold
unattained J D`, and the functionality bound `hα`. It concludes the same conjunction as `ccd_correct`,
that the mode contains the attack and preserves functionality.

The proof bridges the finite check to the abstract criteria. `obtain ⟨hc, hf⟩ := hchk` splits the check
into its two disjointness facts: `hc : Disjoint unattained D` (containment) and `hf : Disjoint J D`
(functionality). `rw [Finset.disjoint_iff_inter_eq_empty] at hc hf` rewrites each `Finset` disjointness
into the equivalent statement that the corresponding `Finset` intersection is empty.

We then invoke the abstract correctness theorem: `refine ccd_correct M Y P J holds Φagg α₀ ?_ ?_ hα`
supplies `M`, the sets, and the functionality bound `hα`, and leaves two goals, the abstract containment
criterion and the abstract functionality criterion, to be discharged.

Each goal is closed by transporting the finite-intersection fact through the faithfulness equations. For
containment, `rw [← hU, ← hD, ← Finset.coe_inter, hc, Finset.coe_empty]` rewrites the abstract intersection
`(↑P \ Ptilde M P holds noI) ∩ descendants M Y` backwards through `hU` and `hD` into the coercion of the
`Finset` intersection `↑(unattained ∩ D)` (using `Finset.coe_inter` to pull the coercion outside), then
replaces `unattained ∩ D` by `∅` via `hc`, and finally `Finset.coe_empty` turns `↑∅` into the empty set,
matching the required `= ∅`. The functionality goal is closed the same way with `hD`, `hf`, and the
coercion lemmas. Both goals discharged, the mode satisfies both constraints.

This theorem is what connects the machine-checked correctness to the algorithm as implemented: CCD runs a
graph traversal to obtain `D`, reads off `unattained` from the detection information, and evaluates the
decidable `CriteriaHold` check; the faithfulness hypotheses `hD` and `hU` certify that these computed
objects correctly represent the model, so a passing check yields the feasibility guarantee.
-/
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
