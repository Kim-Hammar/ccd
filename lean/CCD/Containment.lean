import Mathlib.Tactic
import CCD.AttackGraph

/-!
A formalization of statement (i) of Prop. 1 in the paper: a graphical criterion on the
intervened attack graph `Γ_u` that reduces checking whether a degraded mode contains the
attack (Def. 2, `de_{Γ_u}(P̃) ∩ 𝐏 ⊆ P̃`) to a one-pass check over the exploits, namely
`ch_{Γ_u}(ch_{Γ_u}(P̃)) ⊆ P̃`: every unblocked exploit with a precondition in `P̃` must
have all of its postconditions already in `P̃`.
-/

/- Everything below this will be in the namespace "CCD"-/
namespace CCD

/- Implicit type variables (privileges and exploits) from some arbitrary universe -/
variable {P E : Type*}

/--
**Prop. 1 (i), core form.** If every exploit that has some precondition in `S` grants only
privileges already in `S` (hypothesis `h`, the paper's `ch_Γ(ch_Γ(P̃)) ⊆ P̃` with `S = P̃`),
then the attack graph is contained for `S` in the sense of Def. 2: every privilege-layer
descendant of `S` lies in `S`.

Formally, the theorem takes an attack graph `Γ`, a privilege set `S`, and the hypothesis
`h : ∀ e, (∃ p ∈ S, Γ.pre p e) → ∀ q, Γ.post e q → q ∈ S`, which reads: for every exploit
`e`, if some privilege `p ∈ S` is a precondition of `e` (i.e., `e ∈ ch_Γ(S)`), then every
privilege `q` granted by `e` (i.e., `q ∈ ch_Γ(e)`) is in `S`. It concludes `Γ.GContained S`.

The proof is by induction on the derivation of `GDescend S p` (i.e., on the length of the
privilege-layer path from `S` to `p`). In the `init` case, `p ∈ S` by assumption. In the
`step` case, the path reaches `p` through an edge pair `p' → e → p` where `p'` is a
descendant of `S`; the induction hypothesis `ih` gives `p' ∈ S`, so `e` has the
precondition `p' ∈ S`, and `h` applied to the witness `⟨p', ih, hpre⟩` and the
postcondition edge `hpost` yields `p ∈ S`.
-/
theorem contained_of_child_child (Γ : AttackGraph P E) (S : Set P)
    (h : ∀ e, (∃ p ∈ S, Γ.pre p e) → ∀ q, Γ.post e q → q ∈ S) :
    Γ.GContained S := by
  intro p hp
  induction hp with
  | init hp => exact hp
  | step _ hpre hpost ih => exact h _ ⟨_, ih, hpre⟩ _ hpost

/--
**Prop. 1 (i), stated on the intervened attack graph `Γ_u`.** Consider a degradation
intervention `u = do(X'=D(X'))` whose blocked exploits are given by the predicate
`blocked` (via the blocking edges `ℬ`: `blocked e` iff some `(X'', e) ∈ ℬ` has
`X'' ⊆ X'`). If every **unblocked** exploit with a precondition in `S = P̃` grants only
privileges already in `P̃` (hypothesis `h` — this is exactly the criterion
`ch_{Γ_u}(ch_{Γ_u}(P̃)) ⊆ P̃` of eq. (containment_condition), since blocked exploits have
no edges in `Γ_u`), then the intervened graph `Γ_u = Γ.intervene blocked` is contained
for `P̃`, i.e., `u` satisfies the containment constraint of Def. 2.

The proof applies the core form `contained_of_child_child` to `Γ.intervene blocked`. In
the intervened graph an edge `Γ_u.pre p e` (resp. `Γ_u.post e q`) is by definition the
conjunction of the original edge with `¬ blocked e`; destructuring these conjunctions
(via `rintro`) recovers precisely the hypotheses of `h`: the exploit is unblocked, has a
precondition in `S`, and grants `q` — so `h` closes the goal.
-/
theorem contained_of_unblocked_child (Γ : AttackGraph P E) (blocked : E → Prop) (S : Set P)
    (h : ∀ e, ¬ blocked e → (∃ p ∈ S, Γ.pre p e) → ∀ q, Γ.post e q → q ∈ S) :
    (Γ.intervene blocked).GContained S := by
  apply contained_of_child_child
  rintro e ⟨p, hpS, hpre, hnb⟩ q ⟨hpost, -⟩
  exact h e hnb ⟨p, hpS, hpre⟩ q hpost

end CCD
