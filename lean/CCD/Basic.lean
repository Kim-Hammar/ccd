import Mathlib

/-!
# CCD formalization — basic scaffolding

Shared module overview / table of contents for the Lean formalization of the results in
the paper.

* `CCD.AttackGraph`   — the attack graph `Γ = ⟨P, E, 𝒱⟩`.
* `CCD.CausalModel`   — the structural causal model, `do`-interventions, and `de_{G}(Y)`.
* `CCD.Degradation`   — degraded modes, containment, functionality `Φ`, the problem.
* `CCD.Containment`   — graphical criterion for containment (+ complexity).
* `CCD.Functionality` — graphical criterion for essential functionality (+ complexity).
* `CCD.Algorithm`     — correctness and complexity of CCD (Algorithm 1).
* `CCD.Checkable`     — decidable/checkable form of the criteria (+ complexity notes).
-/
