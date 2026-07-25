# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

An implementation of **CCD (Causal Controlled Degradation)**. The method
automatically recovers a networked system from an ongoing cyberattack by transitioning
it through a *sequence* of progressively less restrictive **degraded operating modes** —
containing the attack on detection, then restoring functionality as operators complete
recovery actions (e.g. patching).

The repository implements CCD and exercises it on an **example networked system**: a
gateway load-balancing across `m` application servers plus a database, with server `n_1`
compromised. The method and this example system are described below.

## Domain model (the "architecture")

The core is a **two-layer model** `⟨Γ, G, L⟩`: the attack graph, the causal graph, and
the cross-layer edges connecting them. Getting these layers and their coupling right is
the whole point; most code should map directly onto these concepts.

### Layer 1 — Attack graph `Γ = ⟨P, E, V⟩`
- `P` = privileges (**OR** nodes); `E` = exploits (**AND** nodes); `V` = bipartite edges.
- Edges privilege→exploit are exploit **preconditions**; edges exploit→privilege are
  **postconditions**.
- Privileges accumulate **monotonically** (gaining a privilege never invalidates a
  precondition).
- Detection localizes the attacker imprecisely: the IDS yields a set of **possible held
  privileges** `P̃ ⊆ P`. Operator recovery actions (patching) remove edges from `Γ` and
  shrink `P̃`.

### Layer 2 — Structural causal model (SCM) `M = ⟨U, V, F, P(U)⟩`
- `U` exogenous (e.g. attacker behavior, workload), `V` endogenous (service availability,
  performance). **No privilege/exploit nodes** — those live only in `Γ`.
- Distinguished endogenous subsets: `J` = **functionality** variables, `X` =
  **operator-controlled** variables, `Y` = **attacker-controlled** variables. Each
  `X ∈ X` has a **degraded-mode configuration** `D(X)` (close the link); each `Y ∈ Y` an
  attack configuration `A(Y)`.
- `F` = causal functions (one `f_Vi` per endogenous var); only a **known subset `F̃ ⊆ F`**
  is available in practice — the method must work without full `F`.
- `G` = the DAG (causal graph). Interventions use the `do(Z=z)` operator, producing
  `M_do(Z=z)` / `G_do(Z=z)` (assigned vars' functions replaced, inactive edges removed).
- `Φ(M) ∈ ℝ` = **functionality function**, depending on `M` only through `J`.

### Cross-layer edges `L = C ∪ B`
- **Capability edges** `C`: `(P', Y) ∈ C` means holding all privileges in `P'` lets the
  attacker control causal variable `Y`. **`Y` is derived**, not stored:
  `Y = { Y | (P', Y) ∈ C, P' ⊆ P̃ }` (`SystemModel.attacker_controlled` property).
- **Blocking edges** `B`: `(X'', E) ∈ B` means intervening on all vars in `X''` makes
  exploit `E` infeasible. An intervention `u = do(X'=D(X'))` yields the **intervened
  attack graph** `Γ_u` by removing the blocked exploits `{E | (X'', E) ∈ B, X'' ⊆ X'}`.

### Key definitions
- **Degraded mode**: an intervened SCM `M_do(Z=z)` with `Z ≠ ∅`.
- **Containment**: `u` contains the attack iff `de_{Γ_u}(P̃) ∩ P ⊆ P̃` — the
  attacker cannot reach any new privilege in the intervened attack graph.

## The algorithm

The **controlled degradation problem**: find an operator intervention `u = do(X'=D(X'))`
such that the degraded mode
1. meets the **functionality constraint** `Φ(M_{u,a}) ≥ α` for all attacker actions `a`, and
2. satisfies the **containment constraint** `de_{Γ_u}(P̃) ∩ P ⊆ P̃`.

(If `X ∩ Y` overlaps, the degradation intervention takes **priority** over attack
interventions on those vars.) Recovery = repeatedly re-solving this as recovery actions
remove edges from `Γ` and shrink `P̃`, yielding a monotone sequence of modes
`D_1 → D_2 → D_3 → …` up to full functionality.

**CCD** solves it *without knowing `F`*, using two graphical criteria and
causal inference:
- **Containment criterion:** `ch_{Γ_u}(ch_{Γ_u}(P̃)) ⊆ P̃` — every unblocked
  exploit with a precondition in `P̃` grants only privileges already in `P̃`. One pass
  over the exploits, `O(|P|+|E|+|V|+|B|)`. Note the semantics: privileges *in* `P̃` are
  **conceded** (exploits into them need no blocking), which is why over-detection is now
  a containment risk (see the sensitivity study) and under-detection makes the criterion
  unsatisfiable (detected `⊥`), since the foothold exploit `E_1` has no blocking edge.
- **Functionality criterion:** `J ∩ de_{G_u}(Y \ X') = ∅` — the attacker
  cannot reach any functionality var (intervened vars leave the attacker's seed set);
  then `Φ(M_{u,a}) = Φ(M_u)`, so a *single* `Φ(M_u)` evaluation suffices. One BFS,
  `O(|V|+|U|+|E_G|)`.

CCD sketch (keep it polynomial — `O(|X|(|V|+|U|+|E_G|+|P|+|E|+|V_Γ|+|B|))`):
1. Candidate set `X' = (X ∩ an_G(J)) ∪ ⋃{X'' | (X'', E) ∈ B, ch_Γ(E) ⊄ P̃}` — links
   that can affect `J`, plus the blocking sets of every exploit granting an unattained
   privilege.
2. `u = do(X' = D(X'))`; compute the blocked exploits and `de_{G_u}(Y \ X')`; if either
   criterion is violated, return `⊥`.
3. **Minimize** the intervention set: drop any `X` from `X'` whose removal still satisfies
   both criteria (recompute `Γ_{u'}` and the seed set `Y \ X'` per removal).
4. Estimate `Φ̂(M_u)` from an observational dataset `D` via **do-calculus** — `D` is
   nominal-operation data, so `Φ` under the degraded mode must be *identified* and
   estimated, not read off directly.
5. Return `u` if `Φ̂(M_u) ≥ α`, else `⊥`.

### Library decisions (made)
- **Graphs:** `networkx` `DiGraph`. Node names are plain strings so the same graph is
  shared by the criteria code and DoWhy.
- **Causal inference:** **DoWhy's GCM module** (`dowhy.gcm`), not the classic effect-
  estimation API. `Φ̂(M_u) = E[T | do(links=0)]` is estimated by fitting a
  `StructuralCausalModel` on the throughput subgraph and drawing `interventional_samples`.
- **GCM mechanisms are assigned manually, not via `gcm.auto`** (`src/ccd/util/inference_util.py:fit_scm`):
  roots get `EmpiricalDistribution`, non-roots get `AdditiveNoiseModel` with a
  **histogram gradient-boosting regressor**. This matters — the mechanisms are *gated
  products* (`Th_i = N_i·Tt_i`, `Tt_i = M_i·min(L_i,γ_i)`); a linear regressor cannot
  represent the binary×continuous interaction and biases the interventional estimate low
  (~82% of nominal instead of the analytic ~90%). Gradient boosting recovers it (~90%).

## Code map (`src/ccd/` package)

The generic CCD core (`ccd.py`, `util/graph_util.py`, `util/inference_util.py`) depends
only on the abstract `SystemModel` interface, so a **new system is added by subclassing
it** in its own module — the illustrative example is one such subclass.
- `system/system_model.py` — abstract base class `SystemModel`: the interface a concrete
  system must populate (`graph`=G, `attack_graph`=Γ, `capability_edges`=C,
  `blocking_edges`=B, role sets `operator_controlled`=X / `functionality`=J /
  `privileges` / `exploits` / `attained`=P̃, `throughput_nodes`,
  `product_functions`=F̃) plus the shared derived quantities: `unattained`,
  **`attacker_controlled` (Y, a derived property — P̃ through C; never a stored field)**,
  `throughput_graph()`, `degraded_value()`.
- `system/illustrative_example_system.py` — concrete `IllustrativeExampleSystem(m,
  patched_exploits=…, attacker_evicted=…)`: builds `G` (throughput subsystem only), `Γ`
  (with the explicit foothold exploit `E_1`), the cross-layer edges, and `F̃` for the
  gateway/servers/database example. Node-name helpers `W(), P(i), E(i), N(i), Tt(i)`.
  `patched_exploits` removes those exploits from `Γ` (and from `B`) — this is how
  operator recovery actions shrink the feasible attack paths. `attacker_evicted` shrinks
  `P̃` to `{P_0}` and patches `E_1` (re-imaging removes the foothold vuln).
- `util/scenario_util.py` — `run_scenario(system, *, title, …)`: shared runner that
  simulates `D`, runs `ccd`, and prints a mode-agnostic report (closed links + blocked
  exploits). The `examples/run_scenario_{1,2,3}.py` scripts are thin wrappers over it.
- `util/graph_util.py` — `ancestors`/`descendants`, `intervened_graph` (applies **AND
  deactivation**: a product output with a zeroed factor loses all incoming edges — this is
  what cuts `T̃_1→T_1` under `do(N_1=0)`), `blocked_exploits`/`intervened_attack_graph`
  (`Γ_u`), and `check_criteria` (containment on `Γ_u` in one exploit pass + functionality
  BFS from `Y \ X'`; returns `CriteriaResult` with `blocked` and `violating_exploits`
  evidence).
- `util/inference_util.py` — `fit_scm` / `estimate_phi` (GCM) and `naive_estimate`
  (biased baseline). `IllustrativeExampleSystem.generate_dataset` is the nominal DGP:
  maintenance closures are more likely at low workload, so a closed link is
  **confounded** with low load; this is why naive conditioning is biased and causal
  inference is needed.
- `ccd.py` — `select_intervention` (the graph-only mode selection, algorithm lines 1–9)
  and `ccd` (adds the DoWhy `Φ̂ ≥ α` check). Returns a `CCDResult`.
- `util/perturb_util.py` — misspecification helpers for the sensitivity study:
  `underspecify` / `overspecify` (remove/add causal-graph edges),
  `underspecify_attack` / `overspecify_attack` (same on `Γ`, bipartite-preserving),
  `underspecify_privileges` / `overspecify_privileges` (drop truly-held / add not-held
  privileges in `P̃`; Y follows automatically via the derived property;
  `perturb_detection` flips both directions at once), and `evaluate_structural` (run CCD
  on a misspecified copy, check the mode against the true model). `sensitivity.py`
  caches its DoWhy sweep to `sensitivity_inference_cache.json`.

### Scenarios (recovery progression D_1 → D_2 → D_3)
- **Scenario 1** (`examples/run_scenario_1.py`, unpatched): CCD isolates the compromised `n_1` →
  `do(N_1=0, M_1=0, A_2=0, …, A_m=0)` (the `A_i`/`M_1` closures block `E_2..E_{m+1}`; `N_1`
  cuts `T̃_1` from `T`), with `Φ̂ ≈ (m-1)/m · Φ_nominal ≥ α = 0.5·Φ_nominal`
  (feasible for all `m ≥ 2`; borderline at `m = 2`).
- **Scenario 2** (`examples/run_scenario_2.py`, `patched_exploits = {E_2..E_{m+1}}`): with lateral
  movement and DB access patched out of `Γ`, containment is free and CCD selects the
  strictly less restrictive `do(N_1=0)` (same `~(m-1)/m` throughput; `A_i`/`M_1` restored).
- **Scenario 3** (`examples/run_scenario_3.py`, `patched_exploits = {E_2..E_{m+1}}` +
  `attacker_evicted=True`): eviction shrinks `P̃` to `{P_0}` and patches `E_1`, so no
  exploit is feasible and the derived `Y = ∅`; both criteria hold with no closures and CCD
  returns the empty intervention `do()` — full functionality restored (`Φ̂ ≈ Φ_nominal`).
- The modes are monotone: `D_1 ⊃ D_2 ⊃ D_3 = ∅`. Nothing in the *algorithm* changes across
  scenarios — recovery actions only remove edges from `Γ` and shrink `P̃` (via
  `patched_exploits` / `attacker_evicted`), and `Y` shrinks with them through the
  capability edges. The model, not the algorithm, encodes recovery.

Complexity is quadratic in `m` (`O(|X|(|V|+|U|+|E_G|+|P|+|E|+|V_Γ|+|B|))` with `|X|` and
both graphs' sizes linear in `m`) — do **not** expect linear scaling.

## Second example: 5G cloud-RAN (`src/ccd/system/five_g_system.py`)

`FiveGSystem` encodes a 5G cloud radio access network (4 DUs, 4 CUs, a core, a near-RT/
non-RT RIC). The attacker holds CU₃ (code exec) and DU₁ UEs in 5QI classes 1–3. It is
richer than the IT system in three ways that drove a **core generalization** (below):
- **Per-DU/class/CU chain** (i=1..4, class k=1..10, CU j=1..4, dir d∈{U,D}):
  `UE^{ik}→L^{ik}→Ľ^i` (admission `Ľ^i_d = Uu·Σ_{k≥QI_i}L^{ik}_d`) `→C̄^i→Ĉ^{ij}`
  (attachment `Ĉ^{ij}_d = 1{𝒞_i=j}·C̄^i_d`) `→C̃^{ij}` (midhaul `C̃^{ij}_d = NG_j·Ĉ^{ij}_d`)
  `→C^i→T^i` (←A1,N6,Xn,E2). **Y** = `{UE^{1k}: k∈1,2,3}` (via P₁) ∪ `{Ĉ^{i3}}` (via P₂).
  **J** = `{T^i_{U,D}}` ∪ `{E2,A1}`. **Φ** = `Σ E{T^i_d} + ω·(E2+A1)` (ω=`OMEGA`=5).
- **Non-binary operator interventions:** `QI_i` (5QI admission threshold; `D(QI_i)=4`
  rejects the attacker's classes 1–3) and `𝒞_i` (helper `AT(i)`; which CU a DU attaches
  to; reattachment target). These need per-variable `degraded_value` and value-aware
  deactivation (a threshold cuts only sub-threshold `L^{ik}→Ľ^i` edges; attachment keeps
  only the chosen CU branch).
- **X∩J overlap:** `E2`,`A1` are both operator-controlled and functionality — closing E2
  to contain the attack (it is the only blocker of exploit EX3) forfeits the `ω·E2` term.
- **Name-collision:** the attack-graph exploit "E2" would clash with the causal
  interface "E2", so exploits are named `EX1..EX5`; the two graphs' node sets are disjoint.
- **Attack graph:** P̃={P0,P1,P2}; `EX3` (near-RT RIC) blocked by `do(E2)`, `EX4` (AMF)
  blocked by `do(NG3)`. Selected **D₁ = `do(AT3=1, E2=0, NG3=0, QI1=4)`** (block EX3/EX4,
  reject DU₁'s attacker classes, sever the CU₃ carried loads via NG3, reattach DU₃ off the
  closed CU₃), `Φ̂ ≈ 74%` of nominal, feasible. `run_scenario_5g.py` runs it on the
  reference simulator (`FiveGSystem.generate_dataset`). `use_known_product_mechanisms=True`
  makes the midhaul `Ĉ→C̃` (a gated product) exact; admission/attachment are learned by
  regressors from the DGP's nominal variation (the DoWhy estimate matches a ground-truth
  interventional simulation within ~1–2%).

### Core generalization — five additive `SystemModel` hooks (base = prior behavior)
Each hook's base implementation reproduces the IT/illustrative behavior exactly (the
regression gate: `tests/test_ccd.py` + `testbeds/it_system/tests/` unchanged), so only the
5G model exercises them:
1. **`degraded_value(var)`** (base `0`) — per-variable `D(X)`; `select_intervention` uses
   it instead of hardcoding 0. 5G: QI→4, AT→reattach target, interfaces/NG→0.
2. **`deactivated_edges(do)`** (base = product-zero rule, moved out of `intervened_graph`)
   — value-aware known-function deactivation. 5G overrides for the threshold/attachment
   gates and calls `super()` for the midhaul product.
3. **`degradation_cost(var)`** (base `0`) — orders the minimality drop loop
   (`-cost, sort_key`) so global sledgehammers (`Uu/N6/Xn` cost 4, `NG_j` cost 3) are
   attempted-dropped before the targeted `QI_i` (cost 1); **required** — without it the
   greedy keeps a global gate and returns an infeasible mode.
4. **`augment_mode(do)`** (base identity) — criteria-neutral functionality restoration
   after minimality. 5G reattaches DUs off any CU whose `NG_j` the mode closed; a test
   asserts `check_criteria` (mode) and (augmented) have the same `.ok` and `reachable`.
5. **`functionality_weights`** (base `{"T":1.0}`) — Φ as a weighted sum of observed
   columns; `estimate_phi`/`naive_estimate` take `weights`, `ccd` passes
   `system.functionality_weights`, `run_ccd_on_data` reports via it. 5G:
   `{T^i_d:1.0} ∪ {E2:ω, A1:ω}`.

Correctness is preserved: hooks 3–4 only reorder the (still criteria-gated) drop loop and
add criteria-neutral changes, so the returned mode still satisfies both criteria and Φ≥α.

## Third example: industrial control system (`src/ccd/system/ics_system.py`)

`IcsSystem` encodes an ICS running the **Tennessee Eastman process** across an enterprise
net (web server behind gateway G2), a supervisory net (control server + engineering
station), and a field net (valve controllers). The attacker has code exec on the web
server (P₁) and, at detection, the control server (P₃) — not the engineering station (P₂)
or field controllers (P₄), so `P̃ = {P0,P1,P3}`.
- **Causal chain:** `W→I`; `Ctil = G2c·C` (known); `V = Chat·Ctil` (known); `V,A,U→P→S`.
  The gateway is **split into two policies**: `G2c` (enterprise→control server, carries
  `Ctil`) and `G2e` (enterprise→engineering station, **no causal edges** — matters only
  through its blocking edge, like the IT `A_i`; unobserved, not in `throughput_nodes`).
  **X** = `{W, G2e, G2c, Ĉ}`; **Y** = `{W, C}` (`W` via P₁, supervisory commands `C` via
  P₃) — so `W ∈ X∩Y`; **J** = `{I, S}`. **Φ = E{I} + E{S}** in the model
  (`functionality_weights`); the evaluation reports Φ + κ_e·G2e + κ_c·G2c (κ=10 each,
  report-side in `plot_evaluation.py`). Exogenous `A`, `U` unobserved.
- **Attack graph:** `P0→E1→P1`; `P1→E2→P2` and `P1→E3→P3` (lateral); `P3→E4→P4`.
  `B = {(W,E1), (G2e,E2), (G2c,E3), (Ĉ,E4)}`. E3 grants the **conceded** P₃ ∈ P̃, so its
  blocking is not needed — this is what separates CCD from naive block-every-vulnerability
  containment (which closes `G2c` too).
- **Selected D₁ = `do(W=0, G2e=0, Chat=0)`** — `G2c` stays open: blocks E1/E2/E4
  (containment; E3 conceded) and severs the attacker from `J` (`Chat=0` zeroes `V`;
  `W∈X'`). Recovery: `patched_exploits={E2,E3}` → D₂ = `do(W=0, Chat=0)`;
  `attacker_evicted` → D₃ = `do()`. Maintenance (W/G2c/Chat) is **mutually exclusive per
  window** in `generate_dataset`, so the joint degraded config never occurs
  observationally → the naive baseline is `n/a` (must be *identified*), and closures are
  confounded with low demand. The testbed dataset schema records the physical gateway as
  `G2`; `run_ccd.py` renames the column to `G2c` on load, and `icsctl` maps `G2c`→`G2`
  and skips `G2e` (no physical counterpart).
- **No core changes.** The ICS overrides only `functionality_weights = {I:1, S:1}` and sets
  `use_known_product_mechanisms=True` (gated products); `degraded_value` (all X→0),
  `deactivated_edges` (base product rule), `degradation_cost`, `augment_mode` all use the
  base defaults — the strongest evidence that the 5G generalization is genuinely generic.
  `examples/run_scenario_ics.py` runs it; `tests/test_ics_system.py` is the regression gate.
  The dockerized testbed (`testbeds/ics/`, tep2py process + web/control servers + G2
  firewall) is at `testbeds/ics/`; pyTEP needs licensed MATLAB, so the testbed
  substitutes the MATLAB-free **tep2py** and the reference simulator is analytic.

## Dockerized testbed (`testbeds/`)

The IT-system example can be run on a real dockerized testbed instead of the simulator.
`testbeds/it_system/` is the first; more testbeds get sibling dirs of the same shape.
The generic CCD core is untouched — only the *source of `D`* changes (measured, not
simulated) and one new `SystemModel` subclass is added.

- **`src/ccd/system/it_testbed_system.py`** — `ITTestbedSystem(IllustrativeExampleSystem)`.
  Two measurement-driven deviations from the simulator model: (1) **adds edges
  `N_i → Tt_i`** — measured carried load (db-completions) is physically 0 when the
  gateway link is closed, unlike the simulator's counterfactual `Tt_i = M_i·min(L_i,γ_i)`;
  without the edge those zeros land in the noise term and Φ̂ is biased low by the
  open-fraction. (2) **`eps_i`/`gam_i` excluded from `throughput_nodes`** (unobservable;
  they stay in `graph`, harmless). Mode selection is identical to the base model (unit
  tested). `generate_dataset` raises — `D` comes from the testbed.
- **Known-mechanism inference.** Because the testbed's products are *gated* (`Tt_i = 0`
  when `N_i = 0`), a boosted regressor puts its split at the knife edge and misfires
  under interventional noise. `SystemModel.use_known_product_mechanisms` (True only for
  `ITTestbedSystem`) makes `fit_scm` use `F̃` as exact `ProductModel` mechanisms
  (`inference_util.py`). The simulator's carried load is ungated, so it keeps the boosted
  regressor (its numeric tests are calibrated to that).
- **`scenario_util.run_ccd_on_data(system, data, *, title, num_samples)`** — the report
  path extracted from `run_scenario` so the testbed reuses it on a measured dataset.

Testbed layout (`testbeds/it_system/`): `docker/` (gateway/server/db build contexts;
`docker-compose.yml` is **generated** and gitignored), `scripts/` (see below), `tests/`
(pure `test_testbed_lib.py` runs in the normal suite; `test_smoke_docker.py` skipped
unless `CCD_TESTBED_SMOKE=1`), `data/` (gitignored).

- `scripts/testbed_lib.py` — **pure, unit-tested**: address plan, `p_close(W)` (closure
  more likely at low load — the confounder), the link→iptables mapping
  (`rule_for`/`sync_commands`, flush-and-readd in a per-container `CCD` chain), the
  compose template, the dataset schema (`dataset_columns`).
- `scripts/{generate_compose, testbed, linkctl, loadgen, collection}.py` — compose
  generation, lifecycle (`up`/`down`/`status`), link control via `docker exec iptables`,
  the open-loop Poisson host loadgen, and the window measurement engine.
- Four workflow scripts: `generate_dataset.py` (a → CSV), `run_ccd.py` (b →
  `ccd_result.json`, supports `--patched`/`--evicted`), `enact_mode.py` (c, iptables),
  `validate_phi.py` (d, measured Φ vs Φ̂).

Link control: `N_i` blocks gateway→`n_i`, `M_i` blocks `n_i`→db, `A_i` blocks `n_1`→`n_i`,
all via `REJECT --reject-with tcp-reset` (fail-fast keeps `L_i ≈ W/m` and makes toggles
immediate). Collection defaults: `W ~ U[50,150]`, `p_close(W) = clip(0.30 − 0.25·(W−50)/100,
0.05, 0.30)`, 6 s measure + 2 s settle per window, 600 windows (≈80 min), 30 s warmup;
counter-reset windows (negative delta) are dropped. The attacker software is not
implemented — the compromise lives only in the two-layer model; `mgmt_net` exists to make
`A_i` physically meaningful. See `testbeds/it_system/README.md` for the full workflow.

Sibling testbeds of the same shape (pure `*_lib.py` + generated compose + `up/down/status`
+ collection/enact/validate; each `<name>_lib` tested in the normal suite):
- **`testbeds/5g_ran/`** — the 4-DU/4-CU cloud-RAN on real srsRAN/Open5GS/ZeroMQ. D₁ =
  `do(AT3=1, E2=0, NG3=0, QI1=4)`, validated live (measured Φ within ~3% of Φ̂).
- **`testbeds/ics/`** — the ICS (Tennessee Eastman) as four containers (web, scada,
  control, process) over an enterprise + plant network. The **G2 gateway is iptables**
  (REJECT the enterprise subnet at the control server), while **Chat/W are application
  modes** (control mode / web safe-mode) — so `icsctl` has two enactment kinds. The two
  known products are physically gated: the firewall drops the command (`Ctil = G2·C`) and
  local control withholds it from the valves (`V = Chat·Ctil`); `P`/`S` come from
  **tep2py** (reactor pressure XMEAS(7) + a command-proportional shift; safety = margin to
  the 3000 kPa shutdown limit). D₁ = `do(W=0, G2=0, Chat=0)`. Root wiring for each testbed:
  `.gitignore` compose line, `pyproject` testpaths, a separate `mypy` invocation in
  `type_checker.sh` (like-named modules), and `linter.sh` paths.

## Example system

Gateway load-balancing across servers `n_1..n_m`, database `n_{m+1}`; `n_1` compromised
(code execution) and also a management host.
- **Attack graph `Γ`:** root `P_0` (network access) → `E_1` → `P_1` (exec on `n_1`); from `P_1`,
  lateral `E_2..E_m` → `P_2..P_m`, and credential `E_{m+1}` → `P_{m+1}` (database).
  Detected state: `P̃ = {P_0, P_1}`.
- **Causal vars (G):** `W` workload (req/s); per server `N_i` (gateway→`n_i` open), `M_i`
  (`n_i`→db open), `A_i` (`n_1`→`n_i` mgmt open, `i≥2`; no causal edges — it matters only
  through its blocking edge); `L_i` load, `T̃_i` carried load, `T_i` end-to-end
  throughput; total `T`; noise `ε_i, γ_i`.
- `X = {N_i, M_i} ∪ {A_i : i≥2}`; degraded config `D(X)` closes the corresponding link.
- **Cross-layer edges:** `C = {({P_i}, T̃_i) : i=1..m}` (exec on `n_i` → control its
  carried load), so `Y = {T̃_1}` for `P̃ = {P_0, P_1}`; `B = {({A_i}, E_i) : i=2..m} ∪
  {({M_1}, E_{m+1})}`. `J = {T}`, `Φ(M) = E[T]`.
- Known functions `F̃`: `T_i = N_i·T̃_i`; `T = Σ T_i`. Remaining functions unknown.
- **Setup:** `α = 0.5·Φ(M)`; `W ~ U[100,1000]` split evenly (`L_i ≈ W/m`);
  `T̃_i = M_i·min(L_i, γ_i)`; `N_i, M_i` occasionally closed for maintenance. Dataset `D` =
  the observable throughput vars over `10^4` nominal steps. Default `m = 10`.

## Lean formalization (`lean/`)

The theoretical results are machine-checked in Lean 4 (v4.31.0 + pinned Mathlib);
correctness = `cd lean && lake build` succeeding (first build: `lake exe cache get`).
Modules (namespace `CCD`):
- `AttackGraph.lean` — `AttackGraph` (`pre`/`post` relations), AND-semantics `Reach`/`Closed`,
  and the two-layer additions: `intervene` (Γ_u, blocked exploits lose their edges),
  `GDescend` (**plain graph descendants** — NOT the AND-enabled `Reach`; the containment
  definition uses plain paths), `GContained`, `closed_of_gcontained` (bridge to AND semantics).
- `CausalModel.lean` — deterministic `SCM`, `eval` (well-founded recursion),
  `descendants`, and the locality lemma `eval_eq_off_descendants` (the structural heart
  of the functionality chain). Unchanged by the two-layer rewrite.
- `Degradation.lean` — `noI`, `Attacker`, `Phi`, `PreservesΦ` (instantiated with the
  effective attacker set `Y \ X'`). Containment no longer lives here.
- `Containment.lean` — the containment criterion: `contained_of_child_child` (core,
  induction on `GDescend`) and `contained_of_unblocked_child` (on `Γ_u`).
- `Functionality.lean` — the functionality criterion: `functionality_invariant_of_disjoint`.
- `Algorithm.lean` — `ccd_correct`: attack-graph containment hypothesis +
  causal functionality hypothesis + `Φ ≥ α₀` → both problem constraints.
- `Checkable.lean` — decidable `ContainmentHolds`/`CriteriaHold` (needs `Fintype P/E`,
  decidable `pre`/`post`/`blocked` as instance args) and `ccd_correct_check`
  (`P̃` is an input, so only the descendant set needs a faithfulness hypothesis `hD`).

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
python examples/inference_scalability.py  # inference time vs dataset size (3 graph sizes) -> png + csv
python examples/sensitivity.py          # robustness to causal/detection misspecification -> 2 png + csv

./unit_tests.sh           # full test suite (wraps pytest)
./linter.sh               # flake8 (config in .flake8, max line length 120)
./type_checker.sh         # mypy over src/ccd, tests, examples

cd lean && lake build     # check the Lean proofs (lake exe cache get first, once)

pytest -q                 # run tests directly
pytest -q tests/test_ccd.py::test_selects_isolate_n1_mode          # one test
pytest -q -k "not feasible"   # skip the slower DoWhy-backed numeric tests
```

Runtime note: the DoWhy GCM fit dominates wall-clock (tens of seconds at `m=10`); the
graph-only `select_intervention` is fast. Tests keep DoWhy to moderate `m` and use
smaller datasets.

## Code Style

- **PEP 8** enforced with `flake8` (max line length **120**); config in `.flake8`.
- **Imports**: list every import on its own line with **no blank lines between import
  statements** — do not group them PEP 8-style (stdlib / third-party / local). The only
  blank lines allowed in an import block are ones that separate an interleaved statement
  (e.g. `warnings.filterwarnings("ignore")`) from the surrounding imports.
- **snake_case** for functions and variables.
- **Type hints** on public functions; `mypy` must pass (`./type_checker.sh`). Note
  `Dict` is invariant — use `Mapping[str, float]` for read-only params that receive an
  `Intervention`'s `Dict[str, int]`.
- **Docstrings** on modules/classes/functions. Keep the mathematical notation in
  docstrings (e.g. `Phi`, `de_{G_u}(Y)`, `F-tilde`) so the code maps onto the method's
  formalism.
- Run `./linter.sh` and `./type_checker.sh` before committing; both are green today.

## Git Workflow

**Work directly on `main` — do not create feature/hotfix/topic branches.** Commit or push
only when asked. Add tests for new behavior and keep the linters green.
