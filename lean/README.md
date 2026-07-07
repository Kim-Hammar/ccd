# CCD — formal proofs (Lean 4 + Mathlib)

A Lean 4 formalization of the theoretical results in *"Cyber Resilience through Controlled
Degradation"* (Hammar, Lupu, Alpcan). The paper's correctness results are proved; the whole
library builds with **no `sorry`** (confirmed via `#print axioms`: only
`propext / Classical.choice / Quot.sound`).

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

| Module | Paper | Status |
| --- | --- | --- |
| `CCD/CausalModel.lean` | SCM, intervention `eval`, descendants `de_𝒢(Y)`; **locality lemma** (`eval_eq_off_descendants`) — an attacker intervention changes only descendants of `Y` | ✅ proved |
| `CCD/Degradation.lean` | degraded mode, `Ptilde` (`P̃`), functionality `Phi` (`Φ`), `Contains`, `PreservesΦ` | ✅ defs |
| `CCD/Containment.lean` | Prop. *graphical criterion for containment* (`containment_of_disjoint`) | ✅ proved |
| `CCD/Functionality.lean` | Prop. *graphical criterion for essential functionality* (`functionality_invariant_of_disjoint`) | ✅ proved |
| `CCD/Algorithm.lean` | Prop. *correctness of CCD* (`ccd_correct`) | ✅ proved |
| `CCD/Checkable.lean` | criteria are `Decidable`; `ccd_correct_check`; `O(·)` complexity as doc-comments | ✅ decidable + documented |
| `CCD/AttackGraph.lean` | attack graph `Γ = ⟨P, E, 𝒱⟩` — scaffolding; privileges/exploits live as causal-graph nodes (`P ∪ E ⊆ V ∪ U`) | ⬜ stub |

`CCD.lean` is the library root and imports all of the above.

### Modeling notes
- **Abstract deterministic SCM.** The SCM is a ranked DAG with causal functions that read
  only their parents; exogenous samples are functions `ω`. `P̃` uses "attainable for some
  `ω`" (support) in place of Pearl's `P(P'=1) > 0` — no measure theory.
- **Containment direction.** The paper's Def. writes `P̃_𝓜 ⊆ P̃_{𝓜_a}` and the proof states
  `=`; we formalize the semantically faithful *"no new privileges"* statement
  `P̃_{𝓜_{u,a}} ⊆ P̃_{𝓜_u}` (`Contains`).
- **Complexity.** The `O(|V|+|U|+|𝓔|)` / `O(|X|(…)+c)` bounds are recorded as doc-comments;
  the criteria themselves are made `Decidable` (`CCD/Checkable.lean`).
- **Scope.** Theorems are stated on the degraded model `𝓜_u` with its graph `𝒢_u`; deriving
  `𝒢_u` from `𝒢` via edge-deactivation, and the monotone-optimal-strategy result, are future
  work.

Confirm the axiom footprint with:

```bash
echo 'import CCD.Algorithm
#print axioms CCD.ccd_correct' | lake env lean --stdin
```
