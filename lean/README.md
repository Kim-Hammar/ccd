[//]: # (# Lean 4 Formalization)

A Lean 4 formalization of the theoretical results in the paper.

## Toolchain

- Lean `v4.31.0`, Mathlib `v4.31.0`.
- Install [`elan`](https://github.com/leanprover/elan): `brew install elan-init`
  (or `curl -sSf https://elan.lean-lang.org/elan-init.sh | sh`).

## Build

```bash
lake exe cache get   # download the prebuilt Mathlib cache (avoids compiling Mathlib)
lake build           # build the CCD library
```

## Formalizations

| Module                    | Formalization                                                                                   |
|---------------------------|-------------------------------------------------------------------------------------------------|
| `CCD/AttackGraph.lean`    | The attack graph `Γ`, the intervened graph `Γ_u`, and containment (Def. 2 in the paper).        |
| `CCD/CausalModel.lean`    | A structural causal model (SCM), `do`-interventions, and descendants.                           |
| `CCD/Degradation.lean`    | The degraded mode (Def. 1), attacker interventions, and functionality `Φ`.                      |
| `CCD/Containment.lean`    | The containment criterion on `Γ_u` (Prop. 1 (i) in the paper).                                  |
| `CCD/Functionality.lean`  | The functionality criterion (Prop. 1 (ii) in the paper).                                        |
| `CCD/Algorithm.lean`      | Correctness of CCD in the two-layer model (Prop. 3 in the paper).                               |
| `CCD/Checkable.lean`      | Decidable/checkable form of the criteria (Prop. 1 (iii) in the paper; runtime bounds in prose). |


