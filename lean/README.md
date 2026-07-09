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

## Module map

| Module | Paper | Status |
| --- | --- | --- |
| `CCD/CausalModel.lean` | SCM, intervention `eval`, descendants `de_𝒢(Y)`; **locality lemma** (`eval_eq_off_descendants`) — an attacker intervention changes only descendants of `Y` | ✅ proved |
| `CCD/Degradation.lean` | degraded mode, `Ptilde` (`P̃`), functionality `Phi` (`Φ`), `Contains`, `PreservesΦ` | ✅ defs |
| `CCD/Containment.lean` | Prop. *graphical criterion for containment* (`containment_of_disjoint`) | ✅ proved |
| `CCD/Functionality.lean` | Prop. *graphical criterion for essential functionality* (`functionality_invariant_of_disjoint`) | ✅ proved |
| `CCD/Algorithm.lean` | Prop. *correctness of CCD* (`ccd_correct`) | ✅ proved |
| `CCD/Checkable.lean` | criteria are `Decidable`; `ccd_correct_check`; `O(·)` complexity as doc-comments | ✅ decidable + documented |
| `CCD/AttackGraph.lean` | attack graph `Γ = ⟨P, E, 𝒱⟩` — scaffolding; privileges/exploits live as causal-graph nodes (`P ∪ E ⊆ V ∪ U`) | ✅ defs |

`CCD.lean` is the library root and imports all of the above.

Confirm the axiom footprint with:

```bash
echo 'import CCD.Algorithm
#print axioms CCD.ccd_correct' | lake env lean --stdin
```
