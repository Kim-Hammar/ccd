import Mathlib.Tactic
import CCD.Degradation

/-!
A formalization of Prop. 1 in the paper, i.e., a graphical criterion for reducing
the checking if a degraded mode contains the attack to a simple graphical criterion.
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
**Prop. 1 (graphical criterion for containment).** If every unattained privilege of the degraded
mode (a node in `P` that is not already possible under the no-op intervention `noI`) is disjoint from
the descendants of the attacker-controlled set `Y` (hypothesis `h`), then the mode contains the attack:
no attacker intervention can let the attacker attain a privilege it could not already attain in the
degraded mode. This reduces containment to the simple graphical check "no unattained privilege is a
descendant of `Y`".

Formally, the theorem takes an SCM `M`, the attacker-controlled set `Y`, the privilege set `P`, the
predicate `holds` (deciding when a value counts as the privilege being held), and a proof `h` that the
set of unattained privileges `(↑P \ Ptilde M P holds noI)` intersected with `descendants M Y` is empty.
It concludes `Contains M Y P holds`, the containment property.

The proof establishes the subset inclusion `Ptilde M P holds a ⊆ Ptilde M P holds noI` for every attacker
intervention. `intro a ha p hp` fixes an attacker intervention `a` (with proof `ha : Attacker Y a`), a
privilege `p`, and a proof `hp` that `p` is possible under `a`. Destructuring `hp` with `obtain` yields
`hpP : p ∈ P` and an exogenous sample `ω` with `hω : holds (eval M a ω p)` (the sample witnessing that `p`
is attained under `a`). We must show `p` is possible under `noI`; `refine ⟨hpP, ?_⟩` supplies the `p ∈ P`
part and leaves the existence of a witnessing sample under `noI`.

We argue by contradiction: `by_contra hcon` assumes `p` is NOT possible under `noI`, and
`simp only [not_exists]` turns this into `hcon : ∀ ω, ¬ holds (eval M noI ω p)`, i.e. no sample makes `p`
hold in the un-intervened mode. The proof then reaches a contradiction in three steps.

First, `hunatt`: `p` is an unattained privilege of the degraded mode, i.e. `p ∈ ↑P \ Ptilde M P holds noI`.
It is in `P` (from `hpP`), and it is not in `Ptilde M P holds noI` because any witness that it were possible
under `noI` would contradict `hcon`.

Second, `hnde`: `p` is not a descendant of `Y`. If it were (`hde`), then `p` would lie in the intersection
`(↑P \ Ptilde M P holds noI) ∩ descendants M Y`, which hypothesis `h` says is empty; rewriting with `h` makes
this membership in `∅`, a contradiction (`Set.mem_empty_iff_false`).

Third, we apply locality. `hagree` states that `a` and `noI` agree outside `Y` (since `a` is an attacker
intervention). The locality lemma `eval_eq_off_descendants` then gives `hev : eval M a ω p = eval M noI ω p`,
because `p` is not a descendant of `Y` (from `hnde`). Rewriting `hω` with `hev` turns the witness "p holds
under `a`" into "p holds under `noI` at sample `ω`", which directly contradicts `hcon ω`. This contradiction
completes the proof, establishing that `p` must have been possible under `noI` after all.

The hypothesis `h` is the machine-checked form of the paper's condition `(P \ P̃_𝓜) ∩ de(Y) = ∅`, and this
theorem is the formal statement and proof of Prop. 1.
-/
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
