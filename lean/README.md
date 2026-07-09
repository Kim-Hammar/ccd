# CCD — formal proofs (Lean 4 + Mathlib)

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

| Module                    | Formalization                                                                            |
|---------------------------|------------------------------------------------------------------------------------------|
| `CCD/CausalModel.lean`    | Formalization of a structural causal model (SCM).                                        |
| `CCD/Degradation.lean`    | Formalization of the degraded mode and containment (Def. 1 and 2 in the paper)           |
| `CCD/Containment.lean`    | Formalization of Prop. 1 in the paper                                                    |
| `CCD/Functionality.lean`  | Formalization of Prop. 3 in the paper                                                    |
| `CCD/Algorithm.lean`      | Formalization of Prop. 5 in the paper                                                    |
| `CCD/Checkable.lean`      | Formalization of the computational complexity results (Prop. 2 and Prop. 4 in the paper) |
| `CCD/AttackGraph.lean`    | Formalization of the attack graph                                                        |

`CCD.lean` is the library root and imports all of the above.

