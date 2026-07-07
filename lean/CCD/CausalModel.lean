import Mathlib

/-!
# Structural causal model

Formalizes the SCM `𝓜 = ⟨U, V, F, P(U)⟩` (Sec. "Causal Model"): exogenous variables `U`,
endogenous variables `V`, causal functions `F`, and the directed acyclic causal graph `𝒢`.
Includes the `do(Z = z)` intervention operator, the intervened model/graph
`𝓜_{do(Z=z)}` / `𝒢_{do(Z=z)}`, and the descendant set `de_{𝒢}(Y)` used by the graphical
criteria.

TODO: definitions and lemmas to be added once the proof details are provided.
-/

namespace CCD

-- TODO: `structure SCM`, `do`-intervention, intervened graph, `descendants`.

end CCD
