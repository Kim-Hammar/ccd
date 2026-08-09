# Prototype: automatic construction of the two-layer model ⟨Γ, G, L⟩ from testbeds

## Context

Today the three two-layer models (`src/ccd/system/{it,ics,five_g}_testbed_system.py`) are
hand-authored. We want a prototype tool that **constructs** ⟨Γ (attack graph), G (causal
graph), L = C ∪ B (cross-layer edges)⟩ from testbed measurements + testbed metadata, and
reproduces graphs identical or similar to the hand-built ones. This is an architecture /
prototype effort; the acceptance bar is "run on all three testbeds, compare to the
hand-built models."

**The three layers have fundamentally different discoverability, so each gets its own
construction strategy:**
- **G** is learnable from `testbeds/*/data/dataset.csv`. The operator supplies the *node
  set*; the tool discovers only the *edge structure*.
- **Γ** carries no signal in the nominal data (no attacker was ever implemented). It is
  built MulVAL-style from reachability + a live vulnerability scan + attained privileges P̃.
- **L** is derived structurally: C from measurement provenance × Γ, B from the enactment
  interface × Γ's exploit paths.

**Decisions (locked with the user):** structure-learning over a fixed node set; MulVAL via
**pyDatalog**; a **real live nmap scan** of the running containers; a **testbed-agnostic
descriptor** each testbed exports via a thin adapter over its existing pure libs.

**Key correction from design review:** the acceptance targets are the *testbed* variants
(`ITTestbedSystem(10)`, `IcsTestbedSystem`, `FiveGTestbedSystem`) — the tool consumes
testbed CSVs, and those variants drop unmeasured nodes (`eps`,`gam`) and add measured edges
(`N_i→Tt_i`). Three provenance classes fall straight out of existing code and drive
everything: **enacted** cols (exogenous roots), **derived-from-F̃** cols (deterministic
products — parents fixed, discovery forbidden; this is what broke faithfulness in the
falsification work), **measured** cols (the only ones structure learning may wire up).

**Environment (verified on the dev machine; re-verify on the Linux server):** causal-learn
0.1.4.4, dowhy 0.14, networkx, scipy, sklearn installed; docker present. **Not installed —
must add:** `pyDatalog` (pip), `python-nmap` (pip), and the **`nmap` binary** (system;
`apt-get install nmap` on Linux). causal-learn is installed but undeclared in
`pyproject.toml`.

## Package layout

New generic package `src/ccd/discovery/` (consumes only descriptors; never imports
`ccd.system.*` except in the evaluation harness — keeps construction non-circular):

```
src/ccd/discovery/
  descriptor.py          # dataclasses + JSON/YAML load/validate/dump (leaf)
  model.py               # ConstructedModel: mirrors SystemModel public attrs
  causal/  build_g.py, structure_learning.py, orientation.py, validation.py
  attack/  scanner.py (ABC+VulnFact), nmap_scanner.py, datalog_rules.py, build_gamma.py
  cross_layer/ build_l.py
  pipeline.py            # descriptor(+data+scan) -> ConstructedModel
  evaluation/ graph_diff.py, acceptance.py   # ONLY place importing ccd.system.*
testbeds/{it_system,5g_ran,ics}/scripts/descriptor.py   # thin adapters over existing libs
tests/test_discovery_{descriptor,causal,attack,acceptance}.py
```
Dependency direction is strictly downward: `descriptor.py`/`model.py` are leaves;
`causal/`,`attack/`,`cross_layer/` depend only on those; `pipeline.py` composes them;
`evaluation/` alone imports the hand-built models.

## Descriptor schema (one schema, all three testbeds)

Root `Descriptor`: `testbed`, `scale` (e.g. `{m:10}`), `hosts`, `networks`,
`reachability`, `node_set`, `columns`, `enactments`, `product_mechanisms`,
`exploit_templates`, `attained` (P̃), `attacker_start_hosts`. Key records:
- **Host**: `id`, `container` (scan target), `ips`, `role`, `privilege_node` (`P_i`),
  `produces_vars` (→ drives C), `conceded` (e.g. ICS control server).
- **ReachEdge**: `src_host`,`dst_host`,`network`,`protocol`,`port`, `link_var` (operator
  var whose enactment closes this edge → drives B).
- **NodeSpec**: `name`, `tier` (orientation layering), `provenance` ref.
- **ColumnProvenance**: `column`, `source∈{measured,enacted,derived}`, `host`,
  `enactment_var`, `mechanism` ref.
- **VarEnactment** (mirrors `LinkRule`/`Enactment`): `var`,`kind∈{iptables,reattach,mode}`,
  `container`, `reach_edge`, `name_map` (captures `G2c/G2e↔G2`; `G2e` has no physical link).
- **ProductMechanism (F̃)**: `output`,`factors` → required edges + frozen parent set.
- **ExploitTemplate**: `id`,`pre_privilege`,`post_privilege`,`via_reach_edge`,
  `requires_service`, `class∈{netexploit,credreuse,radioinject,conceded}` — carries the
  moves nmap can't see (IT DB-cred reuse, 5G UE radio injection).

## G construction (`causal/build_g.py`)

1. `observable_columns(data, metadata)` from `validation_util` (reuse verbatim).
2. Partition by provenance: enacted→tier-0 exogenous; derived→parents from F̃; measured→learnable.
3. `BackgroundKnowledge` (causal-learn): F̃ product edges **required**; enacted nodes get no
   parents; derived nodes' parent sets frozen; tier constraints forbid backward-in-tier
   edges (this orients the CPDAG).
4. `causallearn.search.ConstraintBased.PC.pc(data, alpha=0.05, indep_test=kci, background_knowledge=bk)`.
   KCI = nonparametric analog of the `regression_based` test in `falsify()`, robust to the
   `min`/`exp`/gating mechanisms. `fisherz` fallback for 5G scale; GES (BIC) score-based
   fallback; **exploit DU/class/server symmetry** — learn one representative index's
   subgraph, replicate (documented). LiNGAM rejected (products+binaries violate its
   assumptions).
5. `orientation.py` resolves residual undirected edges by descriptor tier order.
6. Reassemble G = discovered measured edges ∪ F̃ edges ∪ enacted→child edges.
7. `validation.py` wraps `augment_context(G, "W"/"demand", exogenous)` + `falsify(G, data,
   n_permutations)` from `validation_util` → `FalsificationResult`.

## Γ construction (`attack/build_gamma.py`)

1. `nmap_scanner.py` implements `ScannerInterface.scan(hosts)→[VulnFact(host,port,service,
   vulnerability,privilege_gained)]` via `nmap -sV` (needs docker up + nmap binary). A
   `StaticScanner` backend (canned facts) is provided for CI.
2. `datalog_rules.py` assembles pyDatalog facts (`reachable`, `vulExists`,
   `exploitTemplate`, `attackerLocated`, `conceded`) and the **MulVAL interaction rules**:
   `netAccess ← attackerLocated & reachable`; `execCode(H,priv) ← netAccess & vulExists`
   (netexploit); `execCode ← exploitTemplate(credreuse|radioinject) & compromised(src)`;
   `compromised ← execCode`; `compromised ← conceded` (P̃ concession keeps ICS E3 open
   without an exploit); lateral chains via `compromised(S) & reachable & exploitTemplate`.
   **P̃ enters** as `attackerLocated`/`conceded` seeds and as the accepted terminal set.
3. Derivation → Γ: each `compromised(host)` → privilege `P_i` (via `Host.privilege_node`);
   each advancing rule firing → exploit `E` with `P_pre→E→P_post`, tagged with the enabling
   `link_var`/reach-edge (kept in `exploit_meta` for L).

## L derivation (`cross_layer/build_l.py`)

- **C** = provenance × Γ: for each compromised host `h` and `var ∈ h.produces_vars`, emit
  `(frozenset({h.privilege_node}), var)`. Reproduces IT `({P_i},Tt_i)`, ICS
  `({P1},W)/({P3},C)`, 5G `({P1},UE_1_k)/({P2},Chat_i_3_d)`.
- **B** = enactment × Γ exploit paths: for each exploit `E`, take its `link_var` from
  `exploit_meta`, find the `VarEnactment` whose `reach_edge` matches, emit
  `(frozenset({link_var}), E)`. Reproduces IT `({A_i},E_i)/({M_1},E_{m+1})`, ICS
  `({W},E1)/({G2e},E2)/({G2c},E3)/({Chat},E4)`, 5G `({E2},EX3)/({NG3},EX4)`. `name_map`
  resolves `G2c/G2e↔G2`; conceded E3 keeps its blocking edge but its post-privilege is
  seeded compromised.

## Per-testbed adapters (thin, over existing libs — reimplement nothing)

- **IT** (`testbed_lib.py`): hosts/networks/reach from the subnet constants + `server_*_ip`;
  `link_var` from `rule_for`; provenance from `collection.py` (`Tt_i` measured, `N_i/M_i`
  enacted, `Th_i` derived); F̃ `Th_i={N_i,Tt_i}`; exploits E1 foothold / E_i lateral(A_i) /
  E_{m+1} credreuse(M_1).
- **ICS** (`ics_lib.py`): web/scada/control(dual-homed = G2 gateway)/process; `enactment_for`
  with `name_map` for `G2c/G2e`; provenance from `assemble_row`; F̃ `Ctil={G2c,C}`,
  `V={Chat,Ctil}`; conceded control server; exploits E1(W)/E2(G2e)/E3(G2c,conceded)/E4(Chat).
- **5G** (`ran_lib.py`): DU/CU/UE/UPF/SINK/XN/RIC from `controlled_containers()`; `link_var`
  from `enactments_for` (`E2`,`NG_j` iptables, `AT_i` reattach); provenance from
  `assemble_row` + CCDC counter plan; F̃ `Ctil_ijd={NG_j,Chat_ijd}`; exploits
  EX1(UE radioinject)/EX2(CU_3)/EX3(RIC via E2)/EX4(core via NG3)/EX5(wider RAN).

## Acceptance harness (`evaluation/`)

Per testbed: build `ConstructedModel` from descriptor + `dataset.csv` (+ static or live
scan); load the target testbed model; `graph_diff.py` reports edge **precision/recall/F1**
and `nx.is_isomorphic` (typed) for Γ and G, and exact **set-diff** for C and B; **G is
validated** by `falsify(G_constructed, data)` vs `falsify(G_target, data)` — a not-falsified
constructed G is acceptable even when it differs edge-wise. Runs as pytest with
`StaticScanner` (no docker); a `--live` marker switches to `nmap_scanner`.

## New dependencies

`pyproject.toml` `[project.optional-dependencies]`:
`discovery = ["causal-learn==0.1.4.4", "pyDatalog>=0.17", "python-nmap>=0.7"]`. System
`nmap` binary is an external prereq (document in `testbeds/*/README.md` with the
"testbeds must be up (docker)" note). Add `src/ccd/discovery` to `[tool.mypy] files`.

## Build order

1. **IT first** (simplest): descriptor dataclasses + IT adapter + `build_g` (PC+KCI, one F̃
   product, 3 tiers) + `graph_diff` + acceptance vs `ITTestbedSystem`. Prove the causal
   pipeline before Datalog. Then StaticScanner + Datalog rules for the 3-exploit IT Γ + C/B.
2. **ICS**: adds `mode` enactments, dual-homed G2 gateway, `G2c/G2e` name translation, a
   conceded privilege (E3 kept open), two-level products.
3. **5G** (hardest): hundreds of columns, `reattach`, per-CU/class products, radio/midhaul
   exploits invisible to nmap, DU/class symmetry (symmetry-reduction + `fisherz`).
4. Wire live `nmap_scanner` (docker-up) last, after all three static pipelines pass.

## Verification

```bash
pip install -e '.[discovery]'          # + apt-get install nmap  (Linux server)
python -m pytest tests/test_discovery_*.py -q   # static scanner, no docker
./linter.sh && ./type_checker.sh
# end-to-end per testbed (docker up for the live scan):
python -m ccd.discovery.pipeline --testbed it_system --data testbeds/it_system/data/dataset.csv
python -m ccd.discovery.evaluation.acceptance --all   # precision/recall/iso + falsify report
```

## Honest risks

- **Real-scan Γ vs curated Γ.** nmap `-sV` sees services/versions, not abstract exploits;
  patched images may yield zero or many irrelevant CVEs. IT DB-cred reuse and 5G UE radio
  injection are not nmap-discoverable. So Γ's *topology* is driven by descriptor
  reachability + P̃ + `ExploitTemplate`; the scan only grounds a host-exploitability
  *existence* predicate. Frame it as "MulVAL over a hand-authored reachability+template
  model, scan-confirmed," not "Γ discovered from scanning."
- **G won't fully match.** Deterministic products (mitigated by F̃ fixing), the
  workload/demand→`p_close` confounder (mitigated by `augment_context` + tier-0
  exogeneity), QI-threshold gating / `min` / `where` context-specific independencies, `T=Σ`
  and symmetric DUs → Markov-equivalence resolved only by tiers, and only ~600 windows.
  Expect precision/recall < 1; **the falsification check is the real acceptance gate**, not
  edge isomorphism.
- **Descriptor annotation burden.** `node_set`+tiers, `produces_vars`, `link_var`,
  `product_mechanisms`, `exploit_templates`, per-column provenance re-encode much of the
  model by hand. The tool genuinely automates: (a) discovering G's measured-subgraph edges,
  (b) data-validating G via `falsify()`, (c) grounding Γ host-exploitability with a live
  scan, (d) mechanizing the C/B joins. It does **not** eliminate operator modeling — the
  descriptor's correctness dominates whether ⟨Γ,G,L⟩ matches.
