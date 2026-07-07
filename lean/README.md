# CCD — formal proofs (Lean 4 + Mathlib)

A Lean 4 formalization of the theoretical results in *"Cyber Resilience through Controlled
Degradation"* (Hammar, Lupu, Alpcan). Work in progress: the module skeleton mirrors the
paper; proof statements and bodies are filled in incrementally.

## Toolchain

- Lean `v4.31.0`, Mathlib `v4.31.0` (pinned in `lean-toolchain` / `lakefile.toml`).
- Install [`elan`](https://github.com/leanprover/elan): `brew install elan-init`
  (or `curl -sSf https://elan.lean-lang.org/elan-init.sh | sh`).

## Build

```bash
lake exe cache get   # download the prebuilt Mathlib cache (avoids compiling Mathlib)
lake build           # build the CCD library
```

## Module map (→ paper)

| Module | Paper |
| --- | --- |
| `CCD/AttackGraph.lean` | attack graph `Γ = ⟨P, E, 𝒱⟩` (Sec. "Attacker Model") |
| `CCD/CausalModel.lean` | SCM, `do`-intervention, intervened graph, `de_𝒢(Y)` (Sec. "Causal Model") |
| `CCD/Degradation.lean` | degraded mode, containment, functionality `Φ`, the problem |
| `CCD/Containment.lean` | graphical criterion for containment (+ complexity) |
| `CCD/Functionality.lean` | graphical criterion for essential functionality (+ complexity) |
| `CCD/Algorithm.lean` | correctness and complexity of CCD (Algorithm 1) |

`CCD.lean` is the library root and imports all of the above.
