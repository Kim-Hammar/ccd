import Mathlib.Data.Real.Basic
import CCD.CausalModel

/-!

This file formalizes intervention, containment, system functionality, and degraded mode.

Objects layered on top of an SCM `M` (thought of as the degraded mode `𝓜_u`):

* an **attacker intervention** `a` fixes only the attacker-controlled variables `Y`;
  the no-op `noI` recovers `𝓜_u` itself;
* `Ptilde` is the set of *possible* privileges `P̃_{𝓜_I}` (attainable for some exogenous
  sample);
* `Phi` is the system functionality `Φ(𝓜_I)`, an abstract aggregate that reads only the
  functionality variables `J`;
* `Contains` is the containment property (Def. "Containment"), and `PreservesΦ` is the
  critical-functionality constraint (eq. functionality_constraint).
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
The empty (no-op) intervention; applied to the model it gives the degraded mode `𝓜_u`.

Formally, it defines a function of type: α → Option V, i.e., it returns another function
takes a node as input and returns either an assignment V or null, which then is defined as
fun _ => none, which means it returns none for all possible input nodes, i.e., no node is intervened on.
-/
def noI : α → Option V := fun _ => none

/--
An attacker intervention fixes only variables in the attacker-controlled set `Y`.

Formally, it defines a function that takes a finite set of nodes Y as input, as well as a function a of the form α → Option V,
i.e., a function that assigns values to nodes. Given these inputs, the function then returns a proposition
which is true if for all nodes v ∈ Y, if v¬∈ Y, then the function a assigns the value none to v.

I.e., the proposition is true if a is a valid attacker intervention on Y.
-/
def Attacker (Y : Finset α) (a : α → Option V) : Prop := ∀ v, v ∉ Y → a v = none

/-
Here we remove the assumption that equality between nodes is decidable simply because the following theorem does not
need this assumption.
-/
omit [DecidableEq α] in


/--
The no-op intervention is (trivially) an attacker intervention.

Formally, we define a theorem that takes a finite set of nodes Y as input and states that
the no-op intervention `noI` is a valid attacker intervention for `Y`, i.e., `Attacker Y noI` holds.

Recall that `Attacker Y a` unfolds to `∀ v, v ∉ Y → a v = none`. So proving `Attacker Y noI` means
showing that for every node `v` outside `Y`, `noI v = none`. This is immediate, because `noI` is
defined to return `none` for every node, so it certainly returns `none` outside `Y`.

The proof term `fun _ _ => rfl` captures exactly this. Since the statement is a `∀` followed by an
implication (`∀ v, v ∉ Y → noI v = none`), a proof is a function taking two arguments: the node `v`
and a proof that `v ∉ Y`. Both are ignored here (the two `_`), because the conclusion does not depend
on them: `noI v = none` holds for any `v` regardless of whether it is in `Y`. The body `rfl` proves
`noI v = none` by reflexivity, since `noI v` reduces to `none` by definition, so both sides of the
equation are definitionally the same.

This lemma matters because it lets us treat the nominal (un-intervened) system as a special case of an
attacker intervention, which is convenient when comparing an attacked evaluation against the nominal one.
-/
theorem attacker_noI (Y : Finset α) : Attacker Y (noI : α → Option V) := fun _ _ => rfl

/-- The set of possible privileges `P̃_{𝓜_I}`: privileges in `P` attainable (value satisfies
`holds`, i.e. `= 1`) for some exogenous sample. -/
def Ptilde (M : SCM α V) (P : Finset α) (holds : V → Prop) (I : α → Option V) : Set α :=
  {p | p ∈ P ∧ ∃ ω, holds (eval M I ω p)}

/-- The functionality `Φ(𝓜_I)`. It is an arbitrary aggregate `Φagg` of the sample-indexed
values of the functionality variables `J`, capturing "Φ depends on the model only through
`J`". -/
def Phi (M : SCM α V) (J : Finset α) (Φagg : ((α → V) → {x // x ∈ J} → V) → ℝ)
    (I : α → Option V) : ℝ :=
  Φagg (fun ω p => eval M I ω (p : α))

/-- **Containment** (Def. "Containment"): the degraded mode prevents the attacker from
acquiring any privilege that is not already possible in the mode — i.e. no attacker
intervention enlarges the set of possible privileges. -/
def Contains (M : SCM α V) (Y P : Finset α) (holds : V → Prop) : Prop :=
  ∀ a, Attacker Y a → Ptilde M P holds a ⊆ Ptilde M P holds noI

/-- **Critical functionality** (eq. functionality_constraint): the degraded mode keeps the
functionality at or above `α₀` under every attacker intervention. -/
def PreservesΦ (M : SCM α V) (Y J : Finset α)
    (Φagg : ((α → V) → {x // x ∈ J} → V) → ℝ) (α₀ : ℝ) : Prop :=
  ∀ a, Attacker Y a → Phi M J Φagg a ≥ α₀

end CCD
