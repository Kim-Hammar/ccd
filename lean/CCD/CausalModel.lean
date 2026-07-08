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

/--
Unfolding equation for `eval`.

`eval` is defined by well-founded recursion (it recurses on parents, using the rank as a
termination measure). Unlike an ordinary definition, such a function does NOT reduce to its
body automatically: writing `eval M I ω v` in a goal will not simplify to the `match` on `I v`
on its own, because internally `eval` is compiled through Lean's well-founded recursion
machinery rather than as a plain equation. This theorem restores that convenience by stating,
as an explicit equation, that `eval M I ω v` equals its own body. We can then unfold `eval` in
later proofs to expose the `match`/`if` structure for case analysis.

The proof uses `rw` (short for "rewrite"), a tactic that takes an equation `a = b` and replaces
occurrences of the left-hand side `a` with the right-hand side `b` in the current goal. Here we
rewrite with `eval.eq_def`, the raw equation lemma that Lean auto-generates for every definition;
it equates `eval M I ω v` with its internal compiled body. After this rewrite the two sides of
our goal are identical, so the goal closes by reflexivity (which `rw` checks automatically).

Formally, reading left to right: `theorem eval_def` names the result; the arguments
`(M : SCM α V) (I : α → Option V) (ω : α → V) (v : α)` are the inputs it is quantified over,
i.e., an SCM `M`, an intervention `I`, an exogenous sample `ω`, and a node `v`. Everything after
the final `:` is the statement being proved, namely the equation `eval M I ω v = ...`, whose
right-hand side is literally the body of `eval` (the `match` on `I v`, and within the `none` case
the `if` on whether `v` has parents). The `:= by` introduces the proof in tactic mode, and the
single tactic `rw [eval.eq_def]` discharges it as described above.
-/
theorem eval_def (M : SCM α V) (I : α → Option V) (ω : α → V) (v : α) :
    eval M I ω v =
      match I v with
      | some x => x
      | none =>
          if (M.parents v).Nonempty then
            M.f v (fun p => if _hp : p ∈ M.parents v then eval M I ω p else ω p)
          else ω v := by
  rw [eval.eq_def]

/--
The edge relation `p → v` of the causal graph.

Formally, it defines a function that takes an SCM and two nodes p and v as input and it returns a proposition
that is true when p is a parent of v in the SCM.
-/
def Child (M : SCM α V) (p v : α) : Prop := p ∈ M.parents v

/--
Reachability (reflexive-transitive closure of `Child`).

Formally, it defines a function that takes an SCM as input and returns a function, which in itself returns a
function, which returns a proposition. Hence, you can think of it as returning a relation Reaches M v p means that
p is reachable from v in the SCM M. Here we use Relation.ReflTransGen from Mathlib as a shorthand to construct this
relation.
-/
def Reaches (M : SCM α V) : α → α → Prop := Relation.ReflTransGen (Child M)

/--
Descendants of a set `Y`: nodes reachable from some `y ∈ Y`.

Formally, it defines a function that takes as input an SCM and a finite set of nodes and then
it returns the set of nodes that are reachable from any node in the set Y.
-/
def descendants (M : SCM α V) (Y : Finset α) : Set α := {w | ∃ y ∈ Y, Reaches M y w}

/-
Here we remove the assumption that equality between nodes is decidable simply because the following theorem does not
need this assumption.
-/
omit [DecidableEq α] in

/--
A node of `Y` is a descendant of `Y`.

Formally, we define a theorem that takes an SCM, a finite set of nodes, a single node y, and a proof that y belongs to Y.
The theorem then states that y is a descendant of Y in the SCM.

The proof works by unfolding what "descendant" means.
By definition, `descendants M Y` is the set of nodes `w` for which there exists some `y' ∈ Y` that reaches `w`, i.e.,
`y ∈ descendants M Y` unfolds to the proposition `∃ y', y' ∈ Y ∧ Reaches M y' y`. To prove such a statement, we must
supply three things: a witness node `y'`, a proof that `y' ∈ Y`, and a proof that `y'` reaches `y`. These three pieces
are exactly the three entries in the angle brackets `⟨y, hy, Relation.ReflTransGen.refl⟩`, which is Lean's syntax for
building a value by listing its components (Lean infers from the goal type which constructor to use). Here the witness
is `y` itself; `hy` is the given proof that `y ∈ Y`; and `Relation.ReflTransGen.refl` proves that `y` reaches itself in
zero steps, since reachability is the reflexive-transitive closure of the edge relation and `refl` is its reflexive base
case. In words, every node of `Y` reaches itself trivially and therefore is a descendant of `Y`.
-/
theorem mem_descendants_self (M : SCM α V) {Y : Finset α} {y : α} (hy : y ∈ Y) :
    y ∈ descendants M Y := ⟨y, hy, Relation.ReflTransGen.refl⟩

/-
Here we remove the assumption that equality between nodes is decidable simply because the following theorem does not
need this assumption.
-/
omit [DecidableEq α] in

/--
Descendant sets are closed under edges: a parent of a non-descendant is a non-descendant.

Formally, we define a theorem that takes an SCM, a finite set of nodes, two nodes w and p, a proof that w is not a descendant of Y,
and a proof that p is a parent of w.

The theorem then states that p is not a descendant of Y.

The proof is by contradiction. The goal `p ∉ descendants M Y` is by definition `p ∈ descendants M Y → False`, i.e., "assuming
p is a descendant of Y leads to a contradiction." The `intro` tactic introduces (assumes) the antecedent of this implication,
moving it into our hypotheses so that we are left to prove `False`. Because a descendant proof is an existential-conjunction
`∃ y, y ∈ Y ∧ Reaches M y p`, we destructure it in place with the angle-bracket pattern `⟨y, hyY, hyp⟩`: `y` is the witness node,
`hyY : y ∈ Y`, and `hyp : Reaches M y p` (y reaches p).

We now derive the contradiction. The `exact` tactic closes the goal by supplying a term of exactly the goal's type (here `False`).
We produce `False` by feeding `hw` (the proof that w is NOT a descendant of Y, i.e., `w ∈ descendants M Y → False`) a proof that
w IS a descendant of Y, which is the contradiction. That proof is the anonymous constructor `⟨y, hyY, hyp.tail hp⟩`: the same
witness `y`, the same membership `hyY`, and a proof that y reaches w. The last piece uses `hyp.tail hp`: `hyp` says y reaches p,
and `hp` says p is a parent of w (an edge p → w), so `ReflTransGen.tail` extends the path by that one edge to conclude y reaches w.
Thus w is a descendant of Y, contradicting `hw`, which gives `False` and completes the proof.
-/
theorem not_descendant_parent (M : SCM α V) {Y : Finset α} {w p : α}
    (hw : w ∉ descendants M Y) (hp : p ∈ M.parents w) : p ∉ descendants M Y := by
  intro ⟨y, hyY, hyp⟩
  exact hw ⟨y, hyY, hyp.tail hp⟩

/--
**Locality lemma.** If two interventions agree outside `Y`, then their evaluations agree
on every node that is not a descendant of `Y`. (Attacker interventions, which fix only
variables in `Y`, cannot change non-descendants of `Y`.)

Formally, the theorem takes an SCM `M`, two interventions `I₁` and `I₂`, an exogenous sample `ω`,
a finite set of nodes `Y`, and a proof `hagree` that `I₁` and `I₂` assign the same thing to every
node outside `Y`. It states that for every node `w` that is not a descendant of `Y`, evaluating `w`
under `I₁` gives the same value as under `I₂`. This is the structural heart of the paper's criteria:
an attacker intervention only touches variables in `Y`, so anything not downstream of `Y` is
unaffected, which is exactly what makes containment and functionality checkable from the graph alone.

The proof is by strong induction on the rank of `w` (the topological depth of the node). We cannot
induct on `w` directly, so we first generalize over the rank via an auxiliary claim `key`: "for every
number `n`, for every node `w` of rank `n` that is not a descendant of `Y`, the two evaluations agree."
The tactic `have key : ... := by ...` proves this auxiliary statement and adds it as a hypothesis; the
final two lines then apply it to close the actual goal.

Inside `key`, `intro n` fixes an arbitrary rank `n`, and `induction n using Nat.strong_induction_on`
performs strong induction: in the single case, we get an induction hypothesis `ih` stating the claim
holds for ALL nodes of rank strictly less than `n`. We then `intro w hrank hw` to assume a node `w`,
a proof `hrank : M.rank w = n`, and a proof `hw : w ∉ descendants M Y`.

The first step establishes `hwY : w ∉ Y`. This follows because if `w` were in `Y` it would be a
descendant of `Y` (by `mem_descendants_self`), contradicting `hw`. The term `fun h => hw (mem_descendants_self M h)`
is this reasoning as a function: given a proof `h : w ∈ Y`, it produces a contradiction, which is exactly
a proof of `w ∉ Y`.

Next, `rw [eval_def, eval_def, hagree w hwY]` rewrites the goal. The two `eval_def`s unfold both `eval M I₁ ω w`
and `eval M I₂ ω w` into their bodies (the `match` on the intervention), and `hagree w hwY` rewrites `I₁ w` to
`I₂ w`, using that the two interventions agree at `w` (since `w ∉ Y`). Now both sides are the same `match` on
`I₂ w`, so we `cases I₂ w` to split on whether `w` is intervened:

* `some x => rfl`: if `w` is intervened to value `x`, both sides evaluate to `x`, so they are equal by
  reflexivity (`rfl`).

* `none`: `w` is not intervened, so we split further with `by_cases hne : (M.parents w).Nonempty` on whether
  `w` has parents.
  - If it has parents (`·` first bullet): `simp only [hne, if_true]` selects the "has parents" branch on both
    sides, leaving us to show the two causal-function applications `M.f w (...)` are equal. Since a causal
    function reads only its parents' values (`M.f_parents`), `apply M.f_parents` reduces the goal to showing
    the two parent-valuations agree at every parent. We `intro p hp` to take a parent `p` with proof
    `hp : p ∈ M.parents w`, then build the facts needed to invoke the induction hypothesis: `hpne` says `p` is
    not a descendant of `Y` (a parent of a non-descendant is a non-descendant, by `not_descendant_parent`), and
    `hplt : M.rank p < n` says `p` has smaller rank (from `edge_rank`, transported along `hrank` with the
    rewrite operator `▸`). After `simp only [hp, dif_pos]` resolves the dependent `if` guarding the parent value,
    `exact ih (M.rank p) hplt p rfl hpne` closes the goal: the induction hypothesis, applied to `p` (which has
    smaller rank and is not a descendant), gives exactly that the two evaluations agree at `p`.
  - If it has no parents (`·` second bullet): `simp only [hne, if_false]` selects the "no parents" branch on both
    sides, where each evaluates to `ω w`, so the goal closes automatically.

Finally, outside `key`, `intro w hw` takes the node `w` and the proof it is not a descendant, and
`exact key (M.rank w) w rfl hw` instantiates the auxiliary claim at `n := M.rank w` (with `rfl` proving
`M.rank w = M.rank w`), yielding the desired equality.
-/
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
