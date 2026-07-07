import Mathlib
import CCD.Degradation

/-!
# Graphical criterion for essential functionality

Formalizes the functionality results:
* **Prop. "Graphical criterion for essential functionality"** — if
  `J ∩ de_{𝒢_u}(Y) = ∅` then `Φ(𝓜_{u,a}) = Φ(𝓜_u)` for all attacker interventions `a`.
* **Prop. "Complexity of checking functionality"** — the criterion is checkable in
  `O(|V| + |U| + |𝓔|)` time.

Both criteria share the descendant set `de_{𝒢_u}(Y)`, so they can be checked in a single
graph traversal (cf. `CCD.Containment`).

TODO: theorem statements and proofs to be added once the proof details are provided.
-/

namespace CCD

-- TODO: `theorem functionality_invariant_of_disjoint ...` and the complexity bound.

end CCD
