import Mathlib.Data.Real.Basic
import CCD.CausalModel

/-!

This file formalizes interventions on the causal layer, system functionality, and the
degraded mode.

Objects layered on top of an SCM `M` (thought of as the degraded mode `𝓜_u`):

* an **attacker intervention** `a` fixes only the effective attacker-controlled
  variables `Y \ X'` (the operator's degradation intervention takes priority on the
  overlap `X ∩ Y`, so the sets below are instantiated with the effective set); the no-op
  `noI` recovers `𝓜_u` itself;
* `Phi` is the system functionality `Φ(𝓜_I)`, an abstract aggregate that reads only the
  functionality variables `J`;
* `PreservesΦ` is the critical-functionality constraint (eq. functionality_constraint).

Containment is no longer defined on the causal layer: in the two-layer model
`⟨Γ, 𝒢, ℒ⟩` it is a property of the intervened **attack graph** `Γ_u` (Def. 2,
`de_{Γ_u}(P̃) ∩ 𝐏 ⊆ P̃`), formalized as `AttackGraph.GContained` in `CCD.AttackGraph`
with the graphical criterion in `CCD.Containment`.
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

/--
The functionality `Φ(𝓜_I)`. It is an arbitrary aggregate `Φagg` of the sample-indexed
values of the functionality variables `J`, capturing "Φ depends on the model only through
`J`".

Formally, we define Phi as a function that takes an SCM `M`, a set of functionality nodes `J`, an aggregation
functional `Φagg`, and an intervention `I` as input, and returns a real number, the functionality score of the intervened
model `𝓜_I`.

The type of `Φagg` deserves explanation. It is `((α → V) → {x // x ∈ J} → V) → ℝ`, i.e. a function that takes a
"J-valuation" and returns a real number. A J-valuation has type `(α → V) → {x // x ∈ J} → V`: given an exogenous
sample `ω` and a functionality variable `p ∈ J`, it returns that variable's value. Here `{x // x ∈ J}` is the
subtype of nodes that belong to `J` (a node bundled with a proof of its membership), so `Φagg` is only ever handed
the values of the functionality variables, never any other node. This is precisely how we encode the paper's
assumption that "Φ depends on the causal model only through the functionality variables `J`": by construction, the
aggregate has access to nothing but the `J`-values, so it literally cannot depend on anything else.

The body `Φagg (fun ω p => eval M I ω (p : α))` builds the J-valuation and feeds it to `Φagg`. The function
`fun ω p => eval M I ω (p : α)` takes a sample `ω` and a functionality variable `p` (of subtype `{x // x ∈ J}`,
coerced to a plain node by `(p : α)`), and returns its evaluated value in the intervened model. Aggregating these
values with `Φagg` yields the functionality score.

Keeping `Φagg` abstract means our results hold for any functionality measure of this form, e.g. an expectation over
`ω`, a worst case, or a Boolean availability check, as long as it reads only the functionality variables. This is
what lets the functionality criterion (Prop. 3) be proved once and for all: if an attacker cannot change the values
of the variables in `J`, then it cannot change `Φ`, whatever aggregate `Φagg` happens to be.
-/
def Phi (M : SCM α V) (J : Finset α) (Φagg : ((α → V) → {x // x ∈ J} → V) → ℝ)
    (I : α → Option V) : ℝ :=
  Φagg (fun ω p => eval M I ω (p : α))

/--
**Critical functionality** (eq. functionality_constraint): the degraded mode keeps the
functionality at or above `α₀` under every attacker intervention.

Formally, we define PreservesΦ as a predicate that takes an SCM `M`, the attacker-controlled set `Y`, the
functionality set `J`, an aggregation functional `Φagg`, and a threshold `α₀`. It returns a proposition: the
statement that the mode preserves critical functionality.

The body `∀ a, Attacker Y a → Phi M J Φagg a ≥ α₀` reads: for every intervention `a`, if `a` is a valid attacker
intervention for `Y` (i.e. `Attacker Y a`, meaning `a` touches only nodes in `Y`), then the functionality of the
model under `a` is at least `α₀`. In words, no matter what the attacker does within its controlled set `Y`, the
system's functionality stays at or above the critical level `α₀`.

This is the machine-checked counterpart of the paper's functionality constraint `Φ(𝓜_{u,a}) ≥ α` for all attacker
interventions `a`. The universal quantifier over `a` is the worst-case requirement: the guarantee must hold against
every admissible attacker, not just on average or in a nominal case. In the two-layer model the set `Y` is
instantiated with the *effective* attacker-controlled set `Y \ X'` (operator priority on the overlap `X ∩ Y`).
Combined with the functionality criterion (Prop. 1 (ii)), which shows the attacker cannot change `Φ` when `J` lies
outside the descendants of `Y \ X'`, this reduces to checking `Φ` once for the degraded mode rather than over all
attacker interventions.
-/
def PreservesΦ (M : SCM α V) (Y J : Finset α)
    (Φagg : ((α → V) → {x // x ∈ J} → V) → ℝ) (α₀ : ℝ) : Prop :=
  ∀ a, Attacker Y a → Phi M J Φagg a ≥ α₀

end CCD
