[//]: # (# Lean 4 Formalization)

A Lean 4 formalization of the theoretical results of the CCD method.

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
| `CCD/AttackGraph.lean`    | The attack graph `Γ`, the intervened graph `Γ_u`, and the containment definition.               |
| `CCD/CausalModel.lean`    | A structural causal model (SCM), `do`-interventions, and descendants.                           |
| `CCD/Degradation.lean`    | The degraded mode, attacker interventions, and functionality `Φ`.                               |
| `CCD/Containment.lean`    | The containment criterion on `Γ_u`.                                                              |
| `CCD/Functionality.lean`  | The functionality criterion.                                                                     |
| `CCD/Algorithm.lean`      | Correctness of CCD in the two-layer model.                                                       |
| `CCD/Checkable.lean`      | Decidable/checkable form of the criteria (runtime bounds in prose).                             |


