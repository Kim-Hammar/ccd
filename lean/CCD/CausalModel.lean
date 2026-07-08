import Mathlib.Logic.Relation
import Mathlib.Data.Finset.Basic
import Mathlib.Data.Set.Basic

/-!
# Structural causal model

A deterministic model of the SCM `𝓜 = ⟨U, V, F, P(U)⟩`, i.e., the P(U) is the degenerate distribution.
Defining a deterministic SCM is without loss of generality for the proofs in the paper and significantly
reduces the amount of formalization necessary.

* The causal graph is a DAG, encoded by a topological `rank` and a `parents` map with
  `edge_rank : p ∈ parents v → rank p < rank v` (acyclicity).
* Causal functions `f v` read only the parents of `v` (`f_parents`).
* Roots (`parents v = ∅`, the exogenous variables `U`) read their value from a sample
  `ω : α → V`; the "positive probability" in `P̃` is abstracted as "for some `ω`".
* `eval M I ω` evaluates every node under an intervention `I` (a partial assignment).

The key result is `eval_eq_off_descendants`: an intervention that changes only a set `Y`
leaves every non-descendant of `Y` unchanged.
-/

/- Everything below this will be in the namespace "CCD"-/
namespace CCD

/-
Defines the SCM as a struct data type that is parameterized by two types: `α` and `V`, where
`α` is the type of nodes in the causal graph and `V` is the type of the values that nodes in the causal graph can take on.
The struct datatype has five fields that must be defined when instantiating the type:
1. The rank field, which is a function that maps an input of type `α` to the natural numbers, i.e., it assigns a number to each node.
2. The parents field, which is a function that maps every node to a finite set (Finset) of nodes that represent its parents.
3. The edge_rank field, which is a proof that for all nodes v and parents p of v, the rank of p must be less than the rank of v.
4. The f field, which is a function that maps every node to a function that maps the values of its parents to its value
5. The f_parents field which is a proof that, for every node v and. any two node-valuations g,h, if g and h have the same assignments (valuations)
to the parents of v, then it implies that the value of v given the valuation (assignment g) must be equal to the value of v given the. assignment h.
-/
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

/-
Defines α and  V as implicit type variables from some universe and where the equality of
different instances of the type α is decidable. We need decidability to be able to modify
sets of α, i.e., insert or remove elements etc.
-/
variable {α : Type*} {V : Type*} [DecidableEq α]

/-
Defines a function that evaluates every node under the intervention `I` (a partial assignment) and exogenous sample
`ω`. Intervened nodes take their assigned value; roots take `ω`; other nodes apply their causal function to the (recursively evaluated) parents.

Formally the function takes as input an SCM, an intervention and an exogenous sampe. The intervention is a function that maps
the nodes either to a value or to nothing/null (i.e., Option V). The exogenous sample is a function that maps each node to an assignment/value.

The output of the eval function is another function that maps each node to a value. This function is defined recursively.
First, to evaluate a node v, we start by checking if it is assigned a value by the intervention, if it is, then we give it that value.
Otherwise, if the parents of v in the SCM is not empty, then we assign the value of v given by its causal function based on the values of the parents.
If the parents is empty, then we give the value to v as assigned by the exogenous assignment omega.

The final two lines are to define that the function is well-defined in the sense that it will terminate.

-/
def eval (M : SCM α V) (I : α → Option V) (ω : α → V) : α → V
  | v =>
    match I v with
    | some x => x
    | none =>
        if (M.parents v).Nonempty then
          M.f v (fun p => if _hp : p ∈ M.parents v then eval M I ω p else ω p)
        else ω v
termination_by v => M.rank v /- Define the property of the input on which termination will be judged-/
/-
A proof that every recursive call decreases the rank.
The proof is based on invoking the edge_rank proof of the SCM, which proves that the rank of a parent is less than
that of its child. The first _ refers to v in the proof and the second _ refers to p in the proof.
The third argument is the proof that p is a parent of v, i.e., p ∈ parents v. This proof already exists in the
local context: it was bound by the dependent `if hp : p ∈ M.parents v` guard, since the recursive call only
happens in the `then` branch where p is a parent. So `by assumption` does not assume anything; it just tells
Lean to locate that existing proof in the context and pass it as the third argument.
-/
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
