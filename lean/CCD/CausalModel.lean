import Mathlib.Logic.Relation
import Mathlib.Data.Finset.Basic
import Mathlib.Data.Set.Basic

/-!
# Structural causal model

An abstract, deterministic model of the SCM `𝓜 = ⟨U, V, F, P(U)⟩` (Sec. "Causal Model"),
rich enough to state and prove the paper's graphical criteria.

* The causal graph is a DAG, encoded by a topological `rank` and a `parents` map with
  `edge_rank : p ∈ parents v → rank p < rank v` (acyclicity).
* Causal functions `f v` read only the parents of `v` (`f_parents`).
* Roots (`parents v = ∅`, the exogenous variables `U`) read their value from a sample
  `ω : α → V`; the "positive probability" in `P̃` is abstracted as "for some `ω`".
* `eval M I ω` evaluates every node under an intervention `I` (a partial assignment).

The key result is `eval_eq_off_descendants`: an intervention that changes only a set `Y`
leaves every non-descendant of `Y` unchanged.
-/

namespace CCD

/-- A structural causal model over nodes `α` with values in `V`, as a ranked DAG whose
causal functions depend only on their parents. -/
structure SCM (α : Type*) (V : Type*) where
  /-- A topological rank; edges strictly increase it (encodes acyclicity). -/
  rank : α → ℕ
  /-- Parents (direct causes) of each node in the causal graph. -/
  parents : α → Finset α
  /-- Edges go from lower to higher rank. -/
  edge_rank : ∀ v, ∀ p ∈ parents v, rank p < rank v
  /-- The causal function of each node (as a function of a full valuation). -/
  f : α → (α → V) → V
  /-- Each causal function reads only the values of the node's parents. -/
  f_parents : ∀ v (g h : α → V), (∀ p ∈ parents v, g p = h p) → f v g = f v h

variable {α : Type*} {V : Type*} [DecidableEq α]

/-- Evaluate every node under intervention `I` (a partial assignment) and exogenous sample
`ω`. Intervened nodes take their assigned value; roots take `ω`; other nodes apply their
causal function to the (recursively evaluated) parents. -/
def eval (M : SCM α V) (I : α → Option V) (ω : α → V) : α → V
  | v =>
    match I v with
    | some x => x
    | none =>
        if (M.parents v).Nonempty then
          M.f v (fun p => if _hp : p ∈ M.parents v then eval M I ω p else ω p)
        else ω v
termination_by v => M.rank v
decreasing_by exact M.edge_rank _ _ (by assumption)

/-- Unfolding equation for `eval`. -/
theorem eval_def (M : SCM α V) (I : α → Option V) (ω : α → V) (v : α) :
    eval M I ω v =
      match I v with
      | some x => x
      | none =>
          if (M.parents v).Nonempty then
            M.f v (fun p => if _hp : p ∈ M.parents v then eval M I ω p else ω p)
          else ω v := by
  rw [eval.eq_def]

/-- The edge relation `p → v` of the causal graph. -/
def Child (M : SCM α V) (p v : α) : Prop := p ∈ M.parents v

/-- Reachability (reflexive-transitive closure of `Child`). -/
def Reaches (M : SCM α V) : α → α → Prop := Relation.ReflTransGen (Child M)

/-- Descendants of a set `Y`: nodes reachable from some `y ∈ Y`. -/
def descendants (M : SCM α V) (Y : Finset α) : Set α := {w | ∃ y ∈ Y, Reaches M y w}

omit [DecidableEq α] in
/-- A node of `Y` is a descendant of `Y`. -/
theorem mem_descendants_self (M : SCM α V) {Y : Finset α} {y : α} (hy : y ∈ Y) :
    y ∈ descendants M Y := ⟨y, hy, Relation.ReflTransGen.refl⟩

omit [DecidableEq α] in
/-- Descendant sets are closed under edges: a parent of a non-descendant is a non-descendant. -/
theorem not_descendant_parent (M : SCM α V) {Y : Finset α} {w p : α}
    (hw : w ∉ descendants M Y) (hp : p ∈ M.parents w) : p ∉ descendants M Y := by
  intro ⟨y, hyY, hyp⟩
  exact hw ⟨y, hyY, hyp.tail hp⟩

/-- **Locality lemma.** If two interventions agree outside `Y`, then their evaluations agree
on every node that is not a descendant of `Y`. (Attacker interventions, which fix only
variables in `Y`, cannot change non-descendants of `Y`.) -/
theorem eval_eq_off_descendants (M : SCM α V) (I₁ I₂ : α → Option V) (ω : α → V)
    (Y : Finset α) (hagree : ∀ v, v ∉ Y → I₁ v = I₂ v) :
    ∀ w, w ∉ descendants M Y → eval M I₁ ω w = eval M I₂ ω w := by
  have key : ∀ n, ∀ w, M.rank w = n → w ∉ descendants M Y →
      eval M I₁ ω w = eval M I₂ ω w := by
    intro n
    induction n using Nat.strong_induction_on with
    | _ n ih =>
      intro w hrank hw
      have hwY : w ∉ Y := fun h => hw (mem_descendants_self M h)
      rw [eval_def, eval_def, hagree w hwY]
      cases I₂ w with
      | some x => rfl
      | none =>
          by_cases hne : (M.parents w).Nonempty
          · simp only [hne, if_true]
            apply M.f_parents
            intro p hp
            have hpne : p ∉ descendants M Y := not_descendant_parent M hw hp
            have hplt : M.rank p < n := hrank ▸ M.edge_rank w p hp
            simp only [hp, dif_pos]
            exact ih (M.rank p) hplt p rfl hpne
          · simp only [hne, if_false]
  intro w hw
  exact key (M.rank w) w rfl hw

end CCD
