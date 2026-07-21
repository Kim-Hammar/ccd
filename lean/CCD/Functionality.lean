import Mathlib.Tactic
import CCD.Degradation

/-!
A formalization of statement (ii) of Prop. 1 in the paper, i.e., a graphical criterion
for reducing the checking if a degraded mode satisfies the functionality constraint to a
single evaluation of the functionality function `Φ`. In the two-layer model the theorem
is instantiated with the SCM `M = 𝓜_u` (the intervened/degraded mode) and the
**effective** attacker-controlled set `Y := 𝐘 \ 𝐗'` — the operator's degradation
intervention takes priority on the overlap `𝐗 ∩ 𝐘`, so variables already fixed by `u`
are outside the attacker's reach.
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
**Prop. 1 (ii) (graphical criterion for functionality).** If the functionality variables `J` are
disjoint from the descendants of the effective attacker-controlled set `Y` (in the paper:
`J ∩ de_{𝒢_u}(𝐘 \ 𝐗') = ∅`, hypothesis `h` with `M = 𝓜_u` and `Y = 𝐘 \ 𝐗'`), then the
functionality `Φ` is invariant under every attacker intervention: for all valid attacker
interventions `a`, `Φ(𝓜_a) = Φ(𝓜_noI)`. In other words, an attacker confined to `Y` cannot
change the functionality, so checking the functionality constraint reduces to a single evaluation
of `Φ` in the degraded mode (rather than over all attacker interventions).

Formally, the theorem takes an SCM `M`, the attacker-controlled set `Y`, the functionality set `J`,
an aggregation functional `Φagg`, and a proof `h` that the coercion of `J` to a set intersected with
`descendants M Y` is empty (i.e. no functionality variable is a descendant of `Y`). It concludes that
for every attacker intervention `a`, the functionality under `a` equals the functionality under the
no-op intervention `noI`.

The proof proceeds as follows. `intro a ha` fixes an arbitrary attacker intervention `a` together with
a proof `ha : Attacker Y a`. We first establish `hagree`, that `a` and `noI` agree outside `Y`: for any
node `v ∉ Y`, `a v = none` (since `a` is an attacker intervention, by `ha`) and `noI v = none` by
definition, so the two agree. This is exactly the hypothesis the locality lemma requires.

Next, `unfold Phi` exposes the goal as an equality between two applications of `Φagg`, one built from
evaluations under `a` and one under `noI`. Since the two sides differ only in the intervention used to
build the J-valuation, `congr 1` reduces the goal to showing those two J-valuations are equal, and
`funext ω p` reduces further to a pointwise statement: for every sample `ω` and every functionality
variable `p ∈ J`, `eval M a ω p = eval M noI ω p`.

We close this with the locality lemma `eval_eq_off_descendants M a noI ω Y hagree`, which says the two
evaluations agree on any node that is not a descendant of `Y`. It remains to discharge the lemma's side
condition, that `p` is not a descendant of `Y`. Suppose for contradiction it were (`intro hde`). Then `p`
would lie in both `J` (since `p.2` witnesses `p ∈ J`) and `descendants M Y`, i.e. in their intersection
`hmem`. But hypothesis `h` says that intersection is empty, so rewriting with `h` turns `hmem` into
membership in `∅`, which is `False` (`Set.mem_empty_iff_false`). This contradiction shows `p` is not a
descendant of `Y`, so the locality lemma applies and the evaluations agree, completing the proof.

The disjointness hypothesis `h` is the machine-checked form of the paper's condition
`J ∩ de_{𝒢_u}(𝐘 \ 𝐗') = ∅`, and this theorem is the formal statement and proof of Prop. 1 (ii).
-/
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
