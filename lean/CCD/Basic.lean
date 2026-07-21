import Mathlib

/-!
# CCD formalization — basic scaffolding

Shared module overview / table of contents for the Lean formalization of the results in
the paper.

* `CCD.AttackGraph`   — the attack graph `Γ = ⟨P, E, 𝒱⟩`, the intervened graph `Γ_u`
  (blocked exploits removed), and containment (Def. 2, `de_{Γ_u}(P̃) ∩ 𝐏 ⊆ P̃`).
* `CCD.CausalModel`   — the structural causal model, `do`-interventions, and `de_{𝒢}(Y)`.
* `CCD.Degradation`   — degraded modes, attacker interventions, functionality `Φ`.
* `CCD.Containment`   — graphical criterion for containment on `Γ_u` (Prop. 1 (i)).
* `CCD.Functionality` — graphical criterion for essential functionality (Prop. 1 (ii)).
* `CCD.Algorithm`     — correctness of CCD in the two-layer model (Prop. 3, Algorithm 1).
* `CCD.Checkable`     — decidable/checkable form of the criteria (Prop. 1 (iii) notes).
-/
