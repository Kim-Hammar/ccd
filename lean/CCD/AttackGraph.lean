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
The abstract data type has two function that must be defined when instantiating
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

/--
Defines a function called preSet that takes an exploit e of type E as input and outputst a set P.
This set is defined as the set of privileges such that the precondition relation pre p e holds, i.e., the set of
privileges that has an edge to the exploit e.
-/
def preSet (e : E) : Set P := {p | Γ.pre p e}

/--
Defines a function called postSet that takes an exploit e of type E as input and outputst a set P.
This set is defined as the set of privileges such that the postcondition relation post e p holds, i.e., the set of
privileges that has an incoming edge from the exploit e.
-/
def postSet (e : E) : Set P := {p | Γ.post e p}

/-- An exploit is enabled given attained privileges `S` if all its
preconditions are attained (AND semantics). -/
def Enabled (S : Set P) (e : E) : Prop := Γ.preSet e ⊆ S

/-- The set of possible exploits given attained privileges `S`;
the formal counterpart of `Ẽ` in the paper. -/
def possibleExploits (S : Set P) : Set E := {e | Γ.Enabled S e}

/-- Privileges reachable from the initial set `S` by repeatedly firing
enabled exploits. `init` embeds the attained privileges (monotone
accumulation: privileges are never lost); `step` fires an exploit whose
preconditions are all reachable (AND) and grants any one of its
postconditions (OR). -/
inductive Reach (S : Set P) : P → Prop
  | init {p : P} : p ∈ S → Reach S p
  | step {e : E} {p : P} :
      Γ.post e p → (∀ q, Γ.pre q e → Reach S q) → Reach S p

/-- The reachable privilege set; the formal counterpart of the forward
closure of `P̃` in the paper. -/
def reachSet (S : Set P) : Set P := {p | Γ.Reach S p}

/-- Attained privileges are reachable. -/
theorem subset_reachSet (S : Set P) : S ⊆ Γ.reachSet S :=
  fun _ hp => .init hp

/-- Reachability is monotone in the attained privileges. -/
theorem Reach.mono {S T : Set P} (hST : S ⊆ T) {p : P}
    (h : Γ.Reach S p) : Γ.Reach T p := by
  induction h with
  | init hp => exact .init (hST hp)
  | step hpost _ ih => exact .step hpost ih

/-- `reachSet` is a closure operator: idempotence. -/
theorem reach_reachSet {S : Set P} {p : P}
    (h : Γ.Reach (Γ.reachSet S) p) : Γ.Reach S p := by
  induction h with
  | init hp => exact hp
  | step hpost _ ih => exact .step hpost ih

/-- The graph-layer notion of containment: the attained set is closed,
i.e., no exploit sequence grants a new privilege. -/
def Closed (S : Set P) : Prop := Γ.reachSet S ⊆ S

end AttackGraph
end CCD
