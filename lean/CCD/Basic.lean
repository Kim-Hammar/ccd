import Mathlib

/-!
# CCD formalization — basic scaffolding

Shared definitions and notation for the Lean formalization of the results in
*"Cyber Resilience through Controlled Degradation"* (Hammar, Lupu, Alpcan).

The formalization is organized to mirror the paper:
* `CCD.AttackGraph`   — the attack graph `Γ = ⟨P, E, 𝒱⟩`.
* `CCD.CausalModel`   — the structural causal model, `do`-interventions, and `de_{G}(Y)`.
* `CCD.Degradation`   — degraded modes, containment, functionality `Φ`, the problem.
* `CCD.Containment`   — graphical criterion for containment (+ complexity).
* `CCD.Functionality` — graphical criterion for essential functionality (+ complexity).
* `CCD.Algorithm`     — correctness and complexity of CCD (Algorithm 1).

Proof statements and bodies are filled in incrementally.
-/

namespace CCD

-- TODO: shared notation / conventions used across the formalization.

end CCD
