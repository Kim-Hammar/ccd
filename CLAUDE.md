# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

An implementation of **CCD (Causal Controlled Degradation)**: automatic recovery of a
networked system from an ongoing cyberattack by transitioning through progressively less
restrictive **degraded operating modes** — containing the attack on detection, then
restoring functionality as operators complete recovery actions (patching). Exercised on
three example systems (IT, 5G cloud-RAN, ICS), each with a dockerized testbed.

## Domain model

Two-layer model `⟨Γ, G, L⟩`; most code should map directly onto it.

- **Attack graph `Γ = ⟨P, E, V⟩`**: privileges `P` (OR nodes), exploits `E` (AND nodes),
  bipartite pre/postcondition edges. Privileges accumulate monotonically. Detection
  yields possible held privileges `P̃ ⊆ P`; recovery actions remove edges and shrink `P̃`.
- **SCM `M = ⟨U, V, F, P(U)⟩`** with DAG `G`: no privilege/exploit nodes. Role subsets:
  `J` functionality, `X` operator-controlled (each with degraded config `D(X)`), `Y`
  attacker-controlled. Only a known subset `F̃ ⊆ F` is available. `Φ(M) ∈ ℝ` =
  functionality, depends on `M` only through `J`.
- **Cross-layer edges `L = C ∪ B`**: capability edges `C` ((P',Y): holding P' controls Y)
  — **`Y` is derived, never stored**: `Y = {Y | (P',Y) ∈ C, P' ⊆ P̃}`
  (`SystemModel.attacker_controlled`). Blocking edges `B` ((X'',E): intervening on X''
  blocks exploit E), yielding the intervened attack graph `Γ_u`.
- **Containment**: `u` contains the attack iff `de_{Γ_u}(P̃) ∩ P ⊆ P̃`.

## The algorithm

Find `u = do(X'=D(X'))` s.t. (1) `Φ(M_{u,a}) ≥ α` for all attacker actions `a`, and
(2) `de_{Γ_u}(P̃) ∩ P ⊆ P̃` (degradation takes priority on `X ∩ Y`). Recovery =
re-solving as `Γ`/`P̃` shrink → monotone mode sequence `D_1 ⊃ D_2 ⊃ D_3 = ∅`. The model,
not the algorithm, encodes recovery.

CCD solves this *without knowing `F`* via two graphical criteria plus causal inference:
- **Containment criterion**: `ch_{Γ_u}(ch_{Γ_u}(P̃)) ⊆ P̃` (one exploit pass).
  Privileges in `P̃` are **conceded** — over-detection is a containment risk;
  under-detection makes the criterion unsatisfiable (foothold `E_1` has no blocking edge).
- **Functionality criterion**: `J ∩ de_{G_u}(Y \ X') = ∅` (one BFS); then a single
  `Φ(M_u)` evaluation suffices.

### Library decisions (made)
- **Graphs**: `networkx.DiGraph`, plain-string node names (shared with DoWhy).
- **Causal inference**: **DoWhy's GCM module** (`dowhy.gcm`), not the classic API: fit a
  `StructuralCausalModel` on the throughput subgraph, draw `interventional_samples`.
- **Mechanisms assigned manually, not `gcm.auto`** (`inference_util.py:fit_scm`): roots
  `EmpiricalDistribution`, non-roots `AdditiveNoiseModel` with **histogram
  gradient-boosting**. The mechanisms are gated products (binary×continuous); a linear
  regressor biases `Φ̂` low.

## Code map (`src/ccd/`)

The generic core (`ccd.py`, `util/graph_util.py`, `util/inference_util.py`) depends only
on the abstract `SystemModel`; a new system = one subclass in its own module.
- `system/system_model.py` — abstract `SystemModel`: `graph`=G, `attack_graph`=Γ,
  `capability_edges`=C, `blocking_edges`=B, role sets, `throughput_nodes`,
  `product_functions`=F̃, `alpha_fraction` (α = fraction·Φ_nominal); derived
  `unattained`, `attacker_controlled`, `throughput_graph()`, `degraded_value()`.
- `system/illustrative_example_system.py` — the IT example (`m` servers, gateway, DB;
  `n_1` compromised). `Φ = E{T} + κ·Σ E{A_i}` (κ=`KAPPA`; J includes the A_i).
  `patched_exploits=…` removes exploits from `Γ`/`B`; `attacker_evicted=True` shrinks
  `P̃` to `{P_0}` and patches `E_1`.
- `ccd.py` — `select_intervention` (graph-only) + `ccd` (adds the DoWhy `Φ̂ ≥ α` check).
  **Policy terms**: weighted variables that are operator-controlled (IT `A_i`, ICS
  `G2e/G2c`, 5G `E2/A1`) are deterministic per mode — `split_policy_weights`/
  `policy_phi` evaluate them at the intervened value or nominal 1, never from data.
- `util/graph_util.py` — descendants/ancestors, `intervened_graph` (AND deactivation: a
  product output with a zeroed factor loses all incoming edges), `blocked_exploits`,
  `check_criteria`.
- `util/inference_util.py` — `fit_scm`/`estimate_phi` (GCM), `naive_estimate` (biased
  baseline; maintenance closures are confounded with low load — why naive conditioning
  fails and causal inference is needed).
- `util/scenario_util.py` — `run_scenario` (simulate `D`, run ccd, report) and
  `run_ccd_on_data` (same report on a measured dataset, used by the testbeds).
- `util/perturb_util.py` — misspecification helpers for the sensitivity study
  (under/overspecify causal graph and attack graph; `evaluate_structural`).
- `util/synthetic.py` — `random_system(n, avg_degree, seed)`: ER two-layer model for the
  scalability benchmarks (tuned so a containing mode exists and the minimality loop
  runs); linear-Gaussian `generate_dataset` for the inference benchmark (only fit cost
  matters).

### Scenarios (IT recovery progression, `examples/run_scenario_{1,2,3}.py`)
1. Unpatched: the full degraded mode `D_1`.
2. `patched_exploits={E_2..E_{m+1}}`: containment is cheaper → a smaller `D_2`.
3. \+ `attacker_evicted=True`: `Y = ∅` → `do()`, full restore.

## Second example: 5G cloud-RAN (`system/five_g_system.py`)

`FiveGSystem`: 4 DUs, 4 CUs, core, near-/non-RT RIC (constructor-parameterized for the
scalability sweep; Γ invariant, attacker pinned to CU₃/DU₁ with dedicated attacker UE
classes). Chain per DU/class/CU/dir: `UE→L→Ľ` (admission `Ľ = Uu_i·Σ_{k≤QI_i}L^{ik}` —
`QI_i` is the *maximal admitted* class, per-DU `Uu_i`) `→C̄→Ĉ` (attachment `𝒞_i`) `→C̃`
(midhaul `NG_j` gate) `→C→T`. `Φ = Σ E{T^i_d} + ω·(E2+A1)` (ω=`OMEGA`). `X∩J` overlap
(E2, A1). Exploits named `EX1..EX5` (avoid clash with causal `E2`). `D(QI_i)` lowers the
maximal admitted class (rejecting the attacker classes); `D(𝒞_i)` = the partner CU
(pair-swap 1↔2, 3↔4).

It drove the **core generalization** — five additive `SystemModel` hooks whose base
implementations reproduce prior behavior exactly (regression gate: `tests/test_ccd.py` +
IT testbed tests unchanged):
1. `degraded_value(var)` (base 0) — per-variable `D(X)`.
2. `deactivated_edges(do)` (base = product-zero rule) — value-aware deactivation
   (threshold cuts only super-threshold `k > QI` edges; attachment keeps the chosen
   branch).
3. `degradation_cost(var)` (base 0) — orders the minimality drop loop so global gates
   are attempted-dropped before targeted controls; **required** for a feasible 5G mode.
4. `augment_mode(do)` (base identity) — criteria-neutral restoration (5G: reattach DUs
   off closed CUs).
5. `functionality_weights` (base `{"T":1.0}`) — Φ as a weighted sum of observed columns.

## Third example: ICS (`system/ics_system.py`)

`IcsSystem`: Tennessee Eastman process; enterprise/supervisory/field nets. `P̃ =
{P0,P1,P3}` (web server + control server; P₃ **conceded**). Chain: `W→I`;
`Ctil = G2c·C`, `V = Chat·Ctil` (both known, gated); `V,A,U→P→S`. Gateway split into
`G2c` (carries Ctil) and `G2e` (no causal edges, matters only via its blocking edge).
`W ∈ X∩Y` and `{G2e, G2c} ⊂ X∩J`. `Φ = E{I} + E{S} + ε·(G2e+G2c)` (ε=`EPSILON`; the
`I`/`S` weights rescale the recorded 0–100 scores to [0,1] indicators). W domain
{0,1,2} (2 = tampered, the attack config A(W)=2; nominal DGP emits {0,1}).
`B = {(W,E1), (G2e,E2), (G2c,E3), (Ĉ,E4)}`; E3 grants conceded P₃ so the selected
mode keeps `G2c` open — what separates CCD from naive block-everything containment.
Maintenance closures are mutually exclusive per window → joint degraded config never
observed → naive baseline `n/a`. **No core-hook overrides** — only
`functionality_weights`/`alpha_fraction` and `use_known_product_mechanisms=True`.

## Testbeds (`testbeds/`)

Each testbed swaps the *source of `D`* (measured, not simulated) plus one `SystemModel`
subclass; the core is untouched. Shared shape: pure unit-tested `*_lib.py`, generated
gitignored compose, `testbed.py up/down/status`, workflow scripts
`generate_dataset.py` → `run_ccd.py` → `enact_mode.py` → `validate_phi.py`. Attacker
software is not implemented — the compromise lives only in the two-layer model.

- **`it_system/`** — gateway/servers/db as containers; links toggled via iptables
  `REJECT --reject-with tcp-reset` in a per-container `CCD` chain. `ITTestbedSystem`
  deviates from the simulator: adds `N_i → Tt_i` edges (measured carried load is
  physically 0 when the link is closed) and drops `eps_i/gam_i` from `throughput_nodes`.
  Gated products break the boosted regressor under intervention →
  `use_known_product_mechanisms=True` uses `F̃` as exact `ProductModel` mechanisms (the
  simulator keeps the regressor; its numeric tests are calibrated to that).
- **`5g_ran/`** — srsRAN (DU/CU split) + srsUE + Open5GS over ZeroMQ radios (needs a
  Linux host). ZMQ radio deadlocks if one endpoint restarts mid-stream — always
  recreate DU+UE pairs together.
- **`ics/`** — web/scada/control/process containers over enterprise + plant nets;
  process = **tep2py** (MATLAB-free TEP; pyTEP needs licensed MATLAB). G2 = iptables at
  the control server; `Chat`/`W` are application modes (two enactment kinds in `icsctl`).
  Dataset records the physical gateway as `G2`; `run_ccd.py` renames to `G2c` on load.

Root wiring per testbed: `.gitignore` compose line, `pyproject` testpaths, separate
`mypy` invocation in `type_checker.sh` (like-named modules), `linter.sh` paths.

## Lean formalization (`lean/`)

Theoretical results machine-checked in Lean 4 (v4.31.0 + pinned Mathlib); correctness =
`cd lean && lake build` (first build: `lake exe cache get`). Namespace `CCD`:
`AttackGraph` (AND-semantics `Reach`/`Closed`, `intervene`, `GDescend` = plain-path
descendants used by containment), `CausalModel` (deterministic SCM, locality lemma
`eval_eq_off_descendants`), `Containment` / `Functionality` (the two criteria),
`Algorithm` (`ccd_correct`), `Checkable` (decidable criteria + `ccd_correct_check`).

## Commands

Interpreter is the conda base env at `~/miniconda3` (Python 3.11); DoWhy, networkx,
pandas, numpy already installed.

```bash
pip install -e . --no-deps     # full resolve tries to rebuild numba/llvmlite and fails

python examples/run_scenario_1.py         # IT scenario 1 (D_1); _2, _3 likewise; arg = m
python examples/run_scenario_5g.py        # 5G on the reference simulator
python examples/run_scenario_ics.py       # ICS
python examples/scalability.py            # mode-selection time vs graph size
python examples/inference_scalability.py  # inference time vs dataset size
python examples/sensitivity.py            # robustness to model misspecification
python examples/model_validation.py       # falsify the causal graphs against the testbed datasets
python examples/correlation_matrices.py   # correlation heatmaps of the measured datasets
python examples/llm_baseline.py           # LLM-operator baseline (needs provider API keys)

./unit_tests.sh           # full test suite (wraps pytest)
./linter.sh               # flake8 (max line length 120)
./type_checker.sh         # mypy over src/ccd, tests, examples
cd lean && lake build     # check the Lean proofs

pytest -q -k "not feasible"   # skip the slower DoWhy-backed numeric tests
```

## Code Style

- PEP 8 via flake8, max line length **120** (`.flake8`); snake_case.
- **Imports**: one per line, **no blank lines between import statements** (no PEP 8
  stdlib/third-party/local grouping).
- Type hints on public functions; mypy must pass. `Dict` is invariant — use
  `Mapping[str, float]` for read-only params receiving an `Intervention`.
- Docstrings everywhere; keep the mathematical notation (`Phi`, `de_{G_u}(Y)`,
  `F-tilde`) so the code maps onto the formalism.
- Run `./linter.sh` and `./type_checker.sh` before committing; keep both green.

## Git Workflow

**Work directly on `main` — do not create feature/hotfix/topic branches.** Commit or push
only when asked. Add tests for new behavior and keep the linters green.
