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
