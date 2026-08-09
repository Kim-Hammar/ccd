import Mathlib

/-!
# CCD formalization — basic scaffolding

Shared module overview / table of contents for the Lean formalization of the CCD
results.

* `CCD.AttackGraph`   — the attack graph `Γ = ⟨P, E, 𝒱⟩`, the intervened graph `Γ_u`
  (blocked exploits removed), and containment (`de_{Γ_u}(P̃) ∩ 𝐏 ⊆ P̃`).
* `CCD.CausalModel`   — the structural causal model, `do`-interventions, and `de_{𝒢}(Y)`.
* `CCD.Degradation`   — degraded modes, attacker interventions, functionality `Φ`.
* `CCD.Containment`   — graphical criterion for containment on `Γ_u`.
* `CCD.Functionality` — graphical criterion for essential functionality.
* `CCD.Algorithm`     — correctness of CCD in the two-layer model.
* `CCD.Checkable`     — decidable/checkable form of the criteria.
-/
