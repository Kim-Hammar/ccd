import Mathlib

/-!
# Attack graph

Formalizes the attack graph `Γ = ⟨P, E, 𝒱⟩`: privileges `P` (OR-nodes),
vulnerability exploits `E` (AND-nodes), and the bipartite edge set `𝒱`
encoding exploit pre- and post-conditions.

The edge set `𝒱 ⊆ (P × E) ∪ (E × P)` is represented by its two directions:
`pre p e` encodes an edge `p → e` (privilege `p` is a precondition of
exploit `e`) and `post e p` encodes an edge `e → p` (exploit `e` grants
privilege `p`).
-/

/- Everything below this will be in the namespace "CCD"-/
namespace CCD

/- Implicit type variables from some arbitrary universe -/
variable {P E : Type*}

/--
Defining the attack graph as a struct abstract data type.
The data type is parameterized by the privilege set `P` and the exploit set `E`.
The abstract data type has two functions that must be defined when instantiating
the type: the precondition function and the postcondition function.
The precondition function takes a privilege and exploit as input and outputs
a proposition, i.e., some statement that could evaluate to True.
Similarly, the postcondition function takes anb exploit and a privilege as input and
outputs a proposition, i.e., some statement that could evaluate to True.
-/
structure AttackGraph (P E : Type*) where
  /-- Defines the type signature of a function pre,
  `pre p e` : privilege `p` is a precondition of exploit `e`.
  -/
  pre : P → E → Prop
  /--
  Defines the type signature of a function post,
  `post e p` : exploit `e` grants privilege `p`.
  -/
  post : E → P → Prop

/- Everything below this will be in the namespace "AttackGraph"-/
namespace AttackGraph

/- Declare Γ as a variable of type AttackGraph -/
variable (Γ : AttackGraph P E)

/-
Defines a function called preSet that takes an exploit e of type E as input and outputst a set P.
This set is defined as the set of privileges such that the precondition relation pre p e holds, i.e., the set of
privileges that has an edge to the exploit e.
-/
def preSet (e : E) : Set P := {p | Γ.pre p e}

/-
Defines a function called postSet that takes an exploit e of type E as input and outputs a set P.
This set is defined as the set of privileges such that the postcondition relation post e p holds, i.e., the set of
privileges that has an incoming edge from the exploit e.
-/
def postSet (e : E) : Set P := {p | Γ.post e p}

/-
Defines a function called Enabled that takes two inputs: a set of privileges S and an exploit e.
The function then returns a proposition that is true if the preset (set of preconditions) of the exploit e
is a subset of the set S. Hence, it encodes the logic that an exploit e is enabled given a set of attained
privileges S iff all of its preconditions are in the attained set.
-/
def Enabled (S : Set P) (e : E) : Prop := Γ.preSet e ⊆ S

/-
Defines a function called possibleExploits that takes a set of privileges as input and returns
the set of exploits that are enabled given those privileges.
-/
def possibleExploits (S : Set P) : Set E := {e | Γ.Enabled S e}

/-
Here we define a new type inductively called Reach which is a family of propositions (P -> Prop) that takes a set S of
privileges as input and maps it to a proposition that is true
if a given privilege is reachable from the set S by repeatedly firing enabled exploits.
The reachability logic is defined through two recursive predicates/rules.
The first predicate says that if a privilege p is already in the set of attained privileges,
then p is reachable. The second predicate says that given an exploit and a privilege that is
a postcondition of that exploit, then if all of the preconditions of the exploit are reachable from the set S, then that implies
that the privilege is also reachable.
-/
inductive Reach (S : Set P) : P → Prop
  | init {p : P} : p ∈ S → Reach S p
  | step {e : E} {p : P} :
      Γ.post e p → (∀ q, Γ.pre q e → Reach S q) → Reach S p

/-
Defines a function that takes a set of privileges as input and returns the set of privileges that are
reachable from that set
-/
def reachSet (S : Set P) : Set P := {p | Γ.Reach S p}

/-
Defines a theorem which states that, for any set of privileges S, S is a subset of the set of privileges
that are reachable from S.
-/
theorem subset_reachSet (S : Set P) : S ⊆ Γ.reachSet S :=
  fun _ hp => .init hp

/-- Reachability is monotone in the attained privileges. -/
/-
Defines a theorem which takes as input two sets of privileges: S and T, a proof that S is a subset of T, and a privilege p.
Given these inputs, the theorem states that, given a proof h that p is reachable from S,
then p is also reachable from T, i.e., reachability is monotone in the attained privileges.
The notation {..} indicates implicit argument (caller does not have to specify it, it can be inferred from the other arguments.

The proof is induction. There are two cases. In the first case, the proof h was that the privilege hp already belong to S. In this case
we can apply the proof hST to the privilege hp, which proves that hp is a member of T as well, which proves that hp is reachable from T by
the .init case of the Reach relation.

In the second. case, the proof h was that the privilege ih was recursively reachable from S through the exploit hpost and .step rule of the
Reachability relation. In this case, by the induction assumption, we can apply the .step rule to ih using the exploit hpost.
-/
theorem Reach.mono {S T : Set P} (hST : S ⊆ T) {p : P}
    (h : Γ.Reach S p) : Γ.Reach T p := by
  induction h with
  | init hp => exact .init (hST hp)
  | step hpost _ ih => exact .step hpost ih

/-
Defines a theorem which takes a set of privileges S and a privilege p as input. The theoprem states that
given a proof h that the privilege p is reachable from the set of privileges that are reachable from S,
then we have that p is also reachable from S.

The proof is by induction. The base case is that the proof h was that the privilege hp already belongs to the set of reachable privileges
from S, in which case it is reachable from S by definition of reachability.

In the inductive case, the proof h was that the privilege ih was reachable from the set of reachable privileges from S
through the exploit hpost (i.e, all preconditions of hpost are reachable from the set of reachable privileges from S). In this case,
by definitions, the set of preconditions of that exploit are also reachable from S by definition, so the same logic applies.
-/
theorem reach_reachSet {S : Set P} {p : P}
    (h : Γ.Reach (Γ.reachSet S) p) : Γ.Reach S p := by
  induction h with
  | init hp => exact hp
  | step hpost _ ih => exact .step hpost ih

/-
Defines a function that takes a set S of privileges as input and returns a proposition that is true if the set of reachable privileges from
S is a subset of S, i.e., the set of privileges is closed, i.e., no exploit sequence grants a new privilege.
-/
def Closed (S : Set P) : Prop := Γ.reachSet S ⊆ S

end AttackGraph
end CCD
