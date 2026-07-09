# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

An implementation of **CCD (Causal Controlled Degradation)**. The method
automatically recovers a networked system from an ongoing cyberattack by transitioning
it through a *sequence* of progressively less restrictive **degraded operating modes** —
containing the attack on detection, then restoring functionality as operators complete
recovery actions (e.g. patching).

The first concrete goal is the paper's **illustrative example** (Section "Illustrative
Example"): a gateway + `m` application servers + a database, with `n_1` compromised. This
is not yet implemented — implement it against the domain model below.

## Domain model (the "architecture")

The core is a **two-layer model**. Getting these two layers and their coupling right is
the whole point; most code should map directly onto these concepts.

### Layer 1 — Attack graph `Γ = ⟨P, E, V⟩`
- `P` = privileges (**OR** nodes); `E` = exploits (**AND** nodes); `V` = bipartite edges.
- Edges privilege→exploit are exploit **preconditions**; edges exploit→privilege are
  **postconditions**.
- Privileges accumulate **monotonically** (gaining a privilege never invalidates a
  precondition).
- Detection localizes the attacker imprecisely: the IDS yields a set of **possible held
  privileges** `P̃ ⊆ P`. Operator recovery actions (patching) remove edges and shrink `P̃`.

### Layer 2 — Structural causal model (SCM) `M = ⟨U, V, F, P(U)⟩` (Pearl)
- `U` exogenous (e.g. attacker behavior, workload), `V` endogenous (service availability,
  performance).
- Distinguished endogenous subsets: `J` = **functionality** variables, `X` =
  **operator-controlled** variables, `Y` = **attacker-controlled** variables.
- `F` = causal functions (one `f_Vi` per endogenous var); only a **known subset `F̃ ⊆ F`**
  is available in practice — the method must work without full `F`.
- `G` = the DAG (causal graph). Interventions use Pearl's `do(Z=z)`, producing
  `M_do(Z=z)` / `G_do(Z=z)` (assigned vars' functions replaced, inactive edges removed).
- **Coupling between layers:** `P ∪ E ⊆ V ∪ U`. A privilege var = 1 iff the attacker
  holds it; an exploit var = 1 iff executed. `P̃_M = { P' ∈ P | Pr(P'=1) > 0 }`.
- `Φ(M) ∈ ℝ` = **functionality function**, depending on `M` only through `J`.

### Key definitions
- **Degraded mode**: an intervened SCM `M_do(Z=z)` with `Z ≠ ∅`.
- **Containment**: a mode contains the attack iff no attacker intervention can add
  privileges, i.e. `P̃_M` is invariant under all `do(Y'=y')`.

## The algorithm (implement this)

The **controlled degradation problem** (`eq:degradation_problem`): find an operator
intervention `u = do(X'=x')` such that the degraded mode
1. meets the **functionality constraint** `Φ(M_{u,a}) ≥ α` for all attacker actions `a`, and
2. satisfies the **containment constraint** `P̃_{M_{u,a}} = P̃_{M_u}` for all `a`.

Recovery = repeatedly re-solving this as `P̃` shrinks, yielding a monotone sequence of
modes `D_1 → D_2 → D_3 → …` up to full functionality.

**CCD** (paper Algorithm 1) solves it *without knowing `F`*, using two graphical criteria
and causal inference. Both criteria depend on the **same descendant set** `de_{G_u}(Y)`,
so compute it in **one graph traversal**:
- **Containment criterion:** `containment_targets ∩ de_{G_u}(Y) = ∅` — no directed path
  from attacker-controlled vars to any protected privilege. The implementation protects
  `containment_targets = unattained ∪ lateral_targets` (`src/ccd/system.py`): the unattained
  privileges *and* all lateral-movement targets `P_2..P_{m+1}`. Including the lateral
  targets regardless of `P̃` also *prevents lateral movement* into believed-compromised
  servers (isolates them), so an over-estimated `P̃` stays safe. (Base = the paper's
  `(P \ P̃) ∩ de(Y) = ∅` since the lateral targets are already unattained there.)
- **Functionality criterion:** `J ∩ de_{G_u}(Y) = ∅` — attacker cannot reach any
  functionality var; then `Φ(M_{u,a}) = Φ(M_u)`, so a *single* `Φ(M_u)` evaluation suffices.

CCD sketch (keep it polynomial — `O(|X|(|V|+|U|+|E|) + c)`):
1. Restrict candidates to `X' = X ∩ an_G((P \ P̃_M) ∪ J)` (only ancestors of unattained
   privileges / functionality vars can matter).
2. `u = do(X' = R(X'))`, where `R(·)` are the **known degraded-mode configurations** (e.g.
   the config that blocks a link).
3. Compute `de_{G_u}(Y)`; if either criterion is violated, return `⊥`.
4. **Minimize** the intervention set: drop any `X` from `X'` whose removal still satisfies
   both criteria (intervening on fewer vars never reduces functionality).
5. Estimate `Φ̂(M_u)` from an observational dataset `D` via **do-calculus** (Pearl Thm
   3.4.1) — `D` is nominal-operation data, so `Φ` under the degraded mode must be
   *identified* and estimated, not read off directly.
6. Return `u` if `Φ̂(M_u) ≥ α`, else `⊥`.

### Library decisions (made)
- **Graphs:** `networkx` `DiGraph`. Node names are plain strings so the same graph is
  shared by the criteria code and DoWhy.
- **Causal inference:** **DoWhy's GCM module** (`dowhy.gcm`), not the classic effect-
  estimation API. `Φ̂(M_u) = E[T | do(links=0)]` is estimated by fitting a
  `StructuralCausalModel` on the throughput subgraph and drawing `interventional_samples`.
- **GCM mechanisms are assigned manually, not via `gcm.auto`** (`src/ccd/inference.py:fit_scm`):
  roots get `EmpiricalDistribution`, non-roots get `AdditiveNoiseModel` with a
  **histogram gradient-boosting regressor**. This matters — the mechanisms are *gated
  products* (`Th_i = N_i·Tt_i`, `Tt_i = M_i·min(L_i,γ_i)`); a linear regressor cannot
  represent the binary×continuous interaction and biases the interventional estimate low
  (~82% of nominal instead of the analytic ~90%). Gradient boosting recovers it (~90%).

## Code map (`src/ccd/` package)
- `system.py` — `SystemModel(m, patched_exploits=…)`: builds the causal graph `G`, role
  sets (`operator_controlled`=X, `attacker_controlled`=Y, `functionality`=J, `privileges`,
  `attained`=P̃), the known product functions `F̃` (`product_functions`), and the
  throughput subgraph used for inference. Node-name helpers `W(), P(i), E(i), N(i), Tt(i)`.
  `patched_exploits` removes those exploits from `Y` — this is how operator recovery
  actions shrink the attacker's reach (see the two scenarios below).
- `scenario.py` — `run_scenario(system, *, title, …)`: shared runner that simulates `D`,
  runs `ccd`, and prints a mode-agnostic report. The `examples/run_scenario_{1,2,3}.py`
  scripts are thin wrappers over it (there is no `main.py`).
- `graph_ops.py` — `ancestors`/`descendants`, `intervened_graph` (applies **AND
  deactivation**: a product output with a zeroed factor loses all incoming edges — this is
  what cuts `T̃_1→T_1` under `do(N_1=0)`), and `check_criteria` (one traversal → both criteria).
- `simulator.py` — `generate_dataset`: nominal-operation data `D`. Maintenance closures
  are more likely at low workload, so a closed link is **confounded** with low load; this
  is why naive conditioning is biased and causal inference is needed.
- `inference.py` — `fit_scm` / `estimate_phi` (GCM) and `naive_estimate` (biased baseline).
- `ccd.py` — `select_intervention` (graph-only Algorithm 1 lines 1–8) and `ccd`
  (adds the DoWhy `Φ̂ ≥ α` check). Returns a `CCDResult`.
- `perturb.py` — misspecification helpers for the sensitivity study: `underspecify` /
  `overspecify` (remove/add causal-graph edges), `underspecify_privileges` /
  `overspecify_privileges` (drop truly-held / add not-held privileges in `P̃`, with
  `attacker_capabilities` deriving `Y` from held privileges; `perturb_detection` flips both
  directions at once), and `evaluate_structural` (run CCD on a misspecified copy, check the
  mode against the true model). `sensitivity.py` caches its DoWhy sweep to
  `sensitivity_inference_cache.json`.

### Scenarios (recovery progression D_1 → D_2 → D_3)
- **Scenario 1** (`examples/run_scenario_1.py`, unpatched): CCD isolates the compromised `n_1` →
  `do(N_1=0, M_1=0, A_2=0, …, A_m=0)`, with `Φ̂ ≈ (m-1)/m · Φ_nominal ≥ α = 0.5·Φ_nominal`
  (feasible for all `m ≥ 2`; borderline at `m = 2`).
- **Scenario 2** (`examples/run_scenario_2.py`, `patched_exploits = {E_2..E_{m+1}}`): with lateral
  movement and DB access patched, `Y = {T̃_1}`, so containment is free and CCD selects the
  strictly less restrictive `do(N_1=0)` (same `~(m-1)/m` throughput; `A_i`/`M_1` restored).
- **Scenario 3** (`examples/run_scenario_3.py`, `attacker_evicted=True`): the attacker is evicted
  from `n_1`, so `Y = ∅`; both criteria hold with no closures and CCD returns the empty
  intervention `do()` — full functionality restored (`Φ̂ ≈ Φ_nominal`).
- The modes are monotone: `D_1 ⊃ D_2 ⊃ D_3 = ∅`. Nothing in the *algorithm* changes across
  scenarios — only the attacker-controlled set `Y` shrinks (via `patched_exploits` /
  `attacker_evicted`). The model, not the algorithm, encodes recovery.

Complexity is quadratic in `m` (the paper's `O(|X|(|V|+|U|+|E|))` with `|X|` and graph
size both linear in `m`) — do **not** expect linear scaling.

## Illustrative example target (Section "Illustrative Example")

Gateway load-balancing across servers `n_1..n_m`, database `n_{m+1}`; `n_1` compromised
(code execution) and also a management host.
- **Attack graph:** root `P_0` (network access) → `E_1` → `P_1` (exec on `n_1`); from `P_1`,
  lateral `E_2..E_m` → `P_2..P_m`, and credential `E_{m+1}` → `P_{m+1}` (database).
  Detected state: `P̃ = {P_0, P_1}`.
- **Causal vars:** `W` workload (req/s); per server `N_i` (gateway→`n_i` open), `M_i`
  (`n_i`→db open), `A_i` (`n_1`→`n_i` mgmt open, `i≥2`); `L_i` load, `T̃_i` carried load,
  `T_i` end-to-end throughput; total `T`; noise `ε_i, γ_i`.
- `X = {N_i, M_i} ∪ {A_i : i≥2}`; degraded config closes the corresponding link.
- `Y = {T̃_1, E_2, …, E_{m+1}}`. `J = {T}`, `Φ(M) = E[T]`.
- Known functions: `T_i = N_i·T̃_i`; `T = Σ T_i`; `P_i = E_i·A_i·P_1` (`i=2..m`);
  `P_{m+1} = E_{m+1}·M_1·P_1`. Remaining functions unknown.
- **Experiment setup:** `α = 0.5·Φ(M)`; `W ~ U[100,1000]` split evenly (`L_i ≈ W/m`);
  `T̃_i = M_i·min(L_i, γ_i)`; `N_i, M_i` occasionally closed for maintenance. Dataset `D` =
  all non-privilege vars over `10^4` nominal steps. Default `m = 10`.

## Commands

Interpreter is the conda base env at `~/miniconda3` (Python 3.11); DoWhy, networkx,
pandas, numpy are already installed there.

```bash
# Install the package only (deps are already present; a full resolve tries to rebuild
# numba/llvmlite from source and fails, so use --no-deps):
pip install -e . --no-deps

python examples/run_scenario_1.py       # Scenario 1 (D_1), default m = 10
python examples/run_scenario_2.py       # Scenario 2 (D_2), patched exploits
python examples/run_scenario_3.py       # Scenario 3 (D_3), attacker evicted (full restore)
python examples/run_scenario_1.py 50    # run with m = 50 servers
python examples/scalability.py          # CCD mode-selection time vs graph size -> scalability.png
python examples/inference_scalability.py  # inference time vs dataset size (3 graph sizes) -> png + tex
python examples/sensitivity.py          # robustness to causal/detection misspecification -> 2 png + tex

./unit_tests.sh           # full test suite (wraps pytest)
./linter.sh               # flake8 (config in .flake8, max line length 120)
./type_checker.sh         # mypy over src/ccd, tests, examples

pytest -q                 # run tests directly
pytest -q tests/test_ccd.py::test_selects_isolate_n1_mode          # one test
pytest -q -k "not feasible"   # skip the slower DoWhy-backed numeric tests
```

Runtime note: the DoWhy GCM fit dominates wall-clock (tens of seconds at `m=10`); the
graph-only `select_intervention` is fast. Tests keep DoWhy to moderate `m` and use
smaller datasets.

## Code Style

Mirrors the conventions of the related CSLE project:
- **PEP 8** enforced with `flake8` (max line length **120**); config in `.flake8`.
- **snake_case** for functions and variables.
- **Type hints** on public functions; `mypy` must pass (`./type_checker.sh`). Note
  `Dict` is invariant — use `Mapping[str, float]` for read-only params that receive an
  `Intervention`'s `Dict[str, int]`.
- **Docstrings** on modules/classes/functions. Keep the paper's notation in docstrings
  (e.g. `Phi`, `de_{G_u}(Y)`, `F-tilde`) so code maps onto the paper.
- Run `./linter.sh` and `./type_checker.sh` before committing; both are green today.

## Git Workflow

Git-Flow branching (as in CSLE):
- `master` — stable releases
- `develop` — integration branch
- `feature/*` — new features
- `hotfix/*` — critical fixes

Commit or push only when asked. Add tests for new behavior and keep the linters green.
