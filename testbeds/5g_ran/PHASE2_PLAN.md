# 5G cloud-RAN testbed — Phase 2 plan & handoff

This document is a self-contained handoff so a fresh Claude Code session (e.g. on a
Linux machine) can continue Phase 2 without the originating conversation. Read this plus
the repo's `CLAUDE.md` (auto-loaded) and `testbeds/it_system/` (the reference testbed).

## Where things stand

- **Phase 1 is done and committed** (`5G testbed [WIP]` commit): the generalized CCD core
  (five `SystemModel` hooks) + `src/ccd/system/five_g_system.py` (`FiveGSystem`) + its
  reference simulator + tests + `examples/run_scenario_5g.py`. All tests/lint/mypy green.
  See the "Second example: 5G cloud-RAN" section of `CLAUDE.md`.
- **Phase 2 (this doc) is the real testbed** — build the RAN as a virtual network of
  containers with **srsRAN Project (gNB) + srsUE + Open5GS (core) + ZeroMQ (virtual radio)**,
  collect the nominal dataset `D` from it, and enact/validate CCD's selected modes.
- Decisions (binding): use the **real** srsRAN/Open5GS/ZeroMQ stack; **work on `main`, no
  branches**; commit/push only when the user asks.

## Environment learnings from the Phase-2 feasibility spike (macOS/arm64)

The spike was run on macOS/arm64 with Docker Desktop; **Phase 2 should be built and run on
Linux** (native, no emulation, full RAM). Key facts discovered, still relevant on Linux:

- **srsRAN Project → OCUDU (Dec 2025).** `github.com/srsRAN/srsRAN_Project` is archived (main
  branch is a stub README pointing to `gitlab.com/ocudu/ocudu`). **Build from the last
  tagged release `release_25_10`** (`git clone --depth 1 --branch release_25_10
  https://github.com/srsran/srsRAN_Project.git`), or from OCUDU. The user's CSLE
  `cloud_ran_base` Dockerfile already does exactly this.
- **No prebuilt gNB images** exist (GHCR denied, empty DockerHub). Build from source:
  `cmake ../ -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON && make -j<N> gnb` (limit `-j` to fit RAM;
  srsRAN units need ~1–2 GB each). srsUE from `github.com/srsran/srsRAN_4G` (`make srsue`).
- **Open5GS runs natively** — either the `gradiant/open5gs` image (multi-arch) or the
  `ppa:open5gs/latest` apt path (v2.7.2) used by CSLE's `5g_core_base`. It is a ~12-NF
  deployment (nrf, scp, amf, smf, upf, ausf, udm, udr, pcf, bsf, nssf) + MongoDB; the NF
  configs reference each other by hostname and use PLMN 999/70 by default — must be
  customized to the gNB's PLMN/TAC and a subscriber added to Mongo.
- **Reference known-good builds:** the user's CSLE repo has working Dockerfiles —
  `github.com/Kim-Hammar/csle` → `emulation-system/base_images/docker_files/cloud_ran_base`
  (srsRAN + srsUE) and `.../5g_core_base` (Open5GS + Mongo + WebUI). Start from these.

## Spike artifacts already in the repo (starting points, under `testbeds/5g_ran/spike/`)

- `Dockerfile.srsran` — srsRAN Project gNB build (release_25_10, ZMQ). Builds partially;
  reduce `-j` on constrained RAM.
- `Dockerfile.srsue` — srsRAN_4G srsUE build (ZMQ).
- `gnb.yml` — minimal monolithic gNB config (band n3, 5/10 MHz, ZMQ ports, AMF addr,
  PLMN 00101, TAC 7). `ue.conf` — matching srsUE config (ZMQ, test SIM 001010000000001).
- `open5gs/*.yaml` — the default Open5GS NF configs extracted from `gradiant/open5gs:2.7.0`
  (PLMN 999/70 — needs changing to 00101/7 to match the gNB).

These are un-verified scaffolding from the spike, not a working testbed — treat as a head
start, not ground truth.

## Phase-2 build plan (mirror `testbeds/it_system/`)

Target layout `testbeds/5g_ran/` (drop the `spike/` dir once superseded):
```
testbeds/5g_ran/
├── README.md
├── docker/                # gNB (build), srsUE (build), open5gs core (compose/configs), RIC
├── scripts/
│   ├── testbed.py         # up/down/status
│   ├── generate_compose.py# render compose for the topology
│   ├── ranctl.py          # enact D(X): interface/bearer toggles, 5QI threshold, CU reattach
│   ├── collection.py      # window engine -> dataset D over throughput_nodes schema
│   ├── generate_dataset.py# (a) collect nominal D -> data/dataset.csv
│   ├── run_ccd.py         # (b) CSV -> FiveGTestbedSystem -> ccd() -> result.json
│   ├── enact_mode.py      # (c) apply the selected mode to the live RAN
│   └── validate_phi.py    # (d) measured Phi vs Phi-hat
├── tests/                 # pure-python lib tests + docker smoke (skipped unless env var)
└── data/                  # gitignored
```

### `FiveGTestbedSystem(FiveGSystem)` (new, `src/ccd/system/`)
Subclass exactly as `ITTestbedSystem(IllustrativeExampleSystem)`:
- `generate_dataset` raises (D comes from the testbed).
- Keep `use_known_product_mechanisms=True`.
- Add any measurement-driven graph deviations (analogous to the IT testbed's `N_i→Tt_i`
  edge) if a variable measured on the real RAN is physically gated in a way the simulator
  graph didn't capture — verify against real data.
- **Mode selection must stay identical to `FiveGSystem`** (unit test it).

### Dataset schema (what the collector must produce)
Columns = `FiveGTestbedSystem(...).throughput_nodes`: the per-DU/class/CU observed causal
variables (`L, Ladm, Cbar, Chat, Ctil, C, T` for i=1..4, d∈{U,D}, plus the operator vars
`Uu, E2, A1, N6, Xn, QI_i, AT_i, NG_j`). Map RAN/core KPMs (per-DU per-5QI UL/DL load,
carried, throughput; interface/bearer state; attachment; NG state) to these. Confounding:
vary the operator vars as regular ops, more likely to degrade at low demand (so the naive
baseline is biased and causal inference is needed) — mirror `generate_dataset` in
`five_g_system.py`.

### Enacting D(X) on the real RAN (the `ranctl` mapping)
- `Uu, E2, A1, N6, Xn, NG_j → 0`: disable the corresponding interface/bearer (config or
  iptables on the relevant container link).
- `QI_i → 4`: reconfigure DU_i's 5QI admission threshold to reject classes 1–3.
- `AT_i → j`: reattach DU_i to CU_j (O-RAN / near-RT RIC reconfiguration, or the
  gNB/DU–CU F1 wiring).
The selected **D₁ = `do(AT3=1, E2=0, NG3=0, QI1=4)`** (from Phase 1) is the mode to enact
and validate first.

### Topology note (resource-aware)
The paper's full topology is 4 gNBs (RU+DU+CU, DU/CU split) + 4 UEs + Open5GS core +
near-RT RIC. Start with a **1–2 gNB bring-up** to prove sync + collection + enact end-to-end
(as the IT testbed started at m=3), then scale to 4. The near-RT RIC (E2) can use FlexRIC or
the srsRAN RIC.

## Progress log

- **2026-07-22 — feasibility gate PASSED** on the Linux machine (96 cores/754 GB).
  Images: `ccd-5g-gnb` (srsRAN Project release_25_10, ZMQ; + `srscu`/`srsdu` split apps),
  `ccd-5g-srsue` (srsRAN_4G pinned `6bcbd9e5`; release_23_11 does not compile on
  gcc-13/Ubuntu 24.04), `gradiant/open5gs:2.7.0` + `mongo:6.0`.
  `docker/compose-smoke.yml`: full core (11 NFs, PLMN 00101/TAC 7, CTF disabled in SMF)
  + 1 gNB + 1 srsUE. Result: RRC Connected, PDU session 10.45.0.2, ping UPF 0% loss,
  iperf3 through the tunnel ~5 Mbit/s UL / ~32 Mbit/s DL. Working radio config = the
  official srsUE tutorial settings (20 MHz/23.04e6, coreset0 12, common SS#2, qam64,
  prach idx 1) — the 10 MHz/11.52e6 spike config never achieved sample flow.
  `FiveGTestbedSystem` added (`src/ccd/system/five_g_testbed_system.py`) with tests;
  suite/lint/mypy green. See `README.md` gotchas (ZMQ restart pairing, static IPs).

- **2026-07-22 — 4-DU/4-CU split topology UP and carrying traffic.** All 4 gNBs split
  into `srsdu` (ZMQ) + `srscu` (F1/N2/N3); `scripts/ran_lib.py` renders the per-node
  configs + `compose-ran.yml`, `generate_compose.py` writes them (`--reattach i=j` for
  AT_i), `testbed.py` does up/down/status. Gate: 4 UEs RRC-connected + PDU sessions
  (10.45.0.2..5), 0%-loss ping to UPF on every chain. Three split-specific fixes (now in
  ran_lib + README): DU shares its CU's `gnb_id` (NR-CGI check at F1 setup); F1-U moved to
  UDP 2153 to avoid the N3 GTP-U 2152 clash inside a CU (N3 pinned via `cu_up.ngu`);
  `testbed.py up` force-recreates each DU+UE ZMQ pair together. ran_lib tests: 19 pass.

- **2026-07-22 — Tasks 7 + 8 built (collection + enact/validate).** New:
  `scripts/{collection,generate_dataset,ranctl,enact_mode,validate_phi,udp_load}.py`,
  sink + Xn/RIC-stub containers (`docker/sink/`, image `ccd-5g-sink`; srsue image gained
  python3 for the in-netns UL loadgen), and the extended `ran_lib` (flow-port plan
  `5000+100i+k`, dual-side QI filter, both-direction NG/N6, self-ensuring full-coverage
  sync, CCDC counter plan + parser, window sampling, row assembly). Measurement mapping
  and the two DGP deviations (Uu pinned open, AT per phase) are documented in README.md.
  Hard-won: NG's N2 block must be DROP (REJECT aborts the SCTP association and drops all
  UE contexts), and every phase boundary/enactment must `ranctl.reset()` first — a stale
  NG closure outliving its window cuts the target CU from the AMF and wedges the UE's
  re-registration (observed live, fixed in `collection.run_windows`).

- **2026-07-22 — Phase 2 COMPLETE: full a→d workflow validated on the live RAN.**
  Two live-RAN fixes en route: unique `cell_cfg.sector_id` per DU (a CU rejects its
  second DU's F1 setup with "Duplicate served cell CGI" — bit on every shared-CU
  reattachment) and the phase-boundary `ranctl.reset()` above. Full run: 600/600
  nominal windows collected (0 dropped, ~96 min, 6 attachment phases);
  `run_ccd.py` on the measured `D` selected exactly **D₁ = do(AT3=1, E2=0, NG3=0,
  QI1=4)** (blocks EX3+EX4), Φ_nominal = 72.9 Mbit/s-weighted, Φ̂ = 43.1 (59.1%),
  feasible vs α = 36.5; `enact_mode.py` enacted D₁ (live DU_3→CU_1 reattach + iptables);
  `validate_phi.py` (100 pinned windows): **measured Φ = 41.7 ± 1.8 (95% CI) vs
  Φ̂ = 43.1 → 3.4% rel. error** (well inside the ~10% gate), Φ ≥ α. Suite 160 passed
  (39 ran_lib tests), lint + mypy green.

## Topology & measurement design for the 4-DU/4-CU scale-up (decided 2026-07-22)

Containers: 4 × `srsdu` (ZMQ radio each), 4 × `srscu` (F1 server; N2/N3 to core), the
Open5GS core, 4 × `srsue` (one per DU; UE_i pairs with DU_i's ZMQ ports), per-DU traffic
generators, later FlexRIC (E2/A1). DU_i's F1 client points at CU_{AT_i} (nominal
AT_i = i); reattachment (`AT_i -> j`) = restart `srsdu_i` with the other CU's F1 address.

Causal-variable realization (mirrors the IT testbed's iptables-REJECT link semantics):
- `L^{ik}` (k=1..10): 10 UDP flows per DU on distinct ports (class k <-> port 5000+k),
  offered load measured at the loadgen.
- `QI_i` threshold: iptables port-range REJECT on classes k < QI_i at the UE_i tunnel
  ingress (pre-radio admission gate). `Ladm^i` = post-filter offered load.
- `Uu = 0`: block the ZMQ radio port pairs (all DUs). `NG_j = 0`: block CU_j's N2+N3
  (SCTP 38412 + UDP 2152) to the core. `N6 = 0`: block UPF egress NAT. `Xn`, `E2`, `A1`:
  links to the RIC/inter-CU containers, iptables-toggled (real E2 once FlexRIC lands).
- `Cbar^i` (carried), `Chat^{ij}` (F1-U DU_i->CU_j byte counters; nonzero only for
  j = AT_i), `Ctil^{ij}` (CU_j N3 egress for DU_i's session), `C^i`, `T^i_d` (iperf/UDP
  goodput at the receivers, UL at server / DL at UE).
- Confounding (nominal ops in `generate_dataset` collection): interface/NG closures and
  QI/AT variation more likely at low offered demand, mirroring `FiveGSystem.generate_dataset`.

## REMAINING WORK — none (tasks "7" and "8" done, see progress log)

Both pieces below were built and validated on the live RAN on 2026-07-22 (kept for
reference; the workflow commands live in README.md). Possible follow-ons: scenarios
D₂/D₃ on the testbed (patched exploits / eviction knobs on `run_ccd.py`, as in the IT
testbed), and replacing the E2/A1 stubs with a real near-RT RIC (FlexRIC).

### Task 7 — `scripts/collection.py` (window engine → dataset `D`)
Produce `data/dataset.csv` with columns == `ran_lib.dataset_columns()` (verified equal to
`FiveGTestbedSystem().throughput_nodes` + metadata). Design already decided (see
"Causal-variable realization" below). Concretely:
- **Loadgen** (`scripts/loadgen.py`): per DU, 10 UDP flows (5QI class k on port 5000+k)
  from a sink container through the UE tunnel; measure offered `L^{ik}` and received
  goodput. Vary offered demand per window; drive the operator vars as *nominal ops* with
  closures likelier at low demand — use `ran_lib.p_close(demand_frac)` (the confounder).
- **Window engine**: per window pick demand + a nominal operator config, apply it
  (`ranctl.py` — the iptables/reattach enactment already mapped in `ran_lib.sync_commands`
  / `reattachments`), run traffic for a measure interval after a settle interval, and read
  the KPMs → one CSV row. Map: `L/Ladm` from loadgen (Ladm = post-QI-filter), `Chat` from
  F1-U DU→CU byte counters, `Ctil` from CU N3 egress, `C`/`T` from receiver goodput
  (UL at sink, DL at UE). Drop counter-reset windows. Mirror the IT testbed's
  `collection.py` shape and `generate_dataset.py` (a → CSV) wrapper.
- **Likely need**: `scripts/ranctl.py` (thin CLI over `ran_lib.sync_commands` +
  `reattachments`) if not built for task 8 first. Verify a collected `D` runs through
  `run_ccd.py` and still yields D₁ = `do(AT3=1, E2=0, NG3=0, QI1=4)`.

### Task 8 — `enact_mode.py` + `validate_phi.py` (live-RAN enact & validate)
- `scripts/enact_mode.py`: read `data/ccd_result.json` (from `run_ccd.py`) and enact the
  mode on the live RAN — iptables via `ran_lib.sync_commands` (E2/NG3/QI1) + DU reattach
  via `ran_lib.reattachments` (AT3=1 → `generate_compose.py --reattach 3=1` then recreate
  DU_3 against CU_1). For AT3=1 the ZMQ pair recreate recipe applies (DU+UE together).
- `scripts/validate_phi.py` (d): with the mode enacted, collect a short measured dataset,
  compute measured Φ (weighted per `FiveGTestbedSystem.functionality_weights`: Σ T^i_d +
  ω·(E2+A1), ω=OMEGA≈30) and compare to Φ̂ from `run_ccd.py`. Success = within ~10%.
- Keep `select_intervention(FiveGTestbedSystem())` == `select_intervention(FiveGSystem())`
  (already unit-tested) — the enactment must not change mode selection.

Verification for both: `./unit_tests.sh && ./linter.sh && ./type_checker.sh` stay green;
add pure-lib tests to `testbeds/5g_ran/tests/` for any new mapping logic; measured Φ within
~10% of Φ̂ at validation.

## Concrete next steps on the Linux machine

1. `git clone https://github.com/Kim-Hammar/ccd.git && cd ccd` (or `git pull` if already
   cloned); `pip install -e . --no-deps`; confirm `./unit_tests.sh` is green.
2. Feasibility bring-up: build the gNB (release_25_10) + srsUE natively, stand up the
   Open5GS core (from CSLE's `5g_core_base` or `gradiant/open5gs`), customize PLMN to 00101/
   TAC 7, add the subscriber to Mongo, and confirm **1 gNB + 1 UE sync over ZMQ + carry
   traffic** (ping the core). This is the gate.
3. Add `FiveGTestbedSystem`; build `collection.py` mapping RAN/core KPMs → the
   `throughput_nodes` schema; collect a small `D`.
4. `run_ccd.py` on the CSV (expect D₁ = `do(AT3=1, E2=0, NG3=0, QI1=4)`); then `enact_mode.py`
   + `validate_phi.py`.
5. Scale toward 4 gNBs + DU/CU split + near-RT RIC.

## Verification (each step)
`./unit_tests.sh && ./linter.sh && ./type_checker.sh` stay green; the 1-gNB sync + traffic
gate before building collection; measured Φ within ~10% of Φ̂ at validation; and
`select_intervention(FiveGTestbedSystem())` equals `select_intervention(FiveGSystem())`.
