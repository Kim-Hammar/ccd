import Mathlib.Data.Real.Basic
import CCD.CausalModel

/-!
# Degraded modes and the controlled degradation problem

Objects layered on top of an SCM `M` (thought of as the degraded mode `𝓜_u`):

* an **attacker intervention** `a` fixes only the attacker-controlled variables `Y`;
  the no-op `noI` recovers `𝓜_u` itself;
* `Ptilde` is the set of *possible* privileges `P̃_{𝓜_I}` (attainable for some exogenous
  sample), abstracting Pearl's `P(P'=1) > 0`;
* `Phi` is the functionality `Φ(𝓜_I)`, an abstract aggregate that reads only the
  functionality variables `J`;
* `Contains` is the containment property (Def. "Containment"), and `PreservesΦ` is the
  critical-functionality constraint (eq. functionality_constraint).
-/

namespace CCD

variable {α : Type*} {V : Type*} [DecidableEq α]

/-- The empty (no-op) intervention; applied to the model it gives the degraded mode `𝓜_u`. -/
def noI : α → Option V := fun _ => none

/-- An attacker intervention fixes only variables in the attacker-controlled set `Y`. -/
def Attacker (Y : Finset α) (a : α → Option V) : Prop := ∀ v, v ∉ Y → a v = none

omit [DecidableEq α] in
/-- The no-op intervention is (trivially) an attacker intervention. -/
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
