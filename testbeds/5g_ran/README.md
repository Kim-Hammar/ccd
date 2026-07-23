# 5G cloud-RAN testbed

Runs the `FiveGSystem` example (`src/ccd/system/five_g_system.py`) on a real virtualized
RAN instead of the reference simulator: **srsRAN Project gNBs (release_25_10)** with a
**ZeroMQ virtual radio**, **srsUE** terminals (srsRAN_4G), and an **Open5GS 5G core**
(gradiant/open5gs 2.7.0), all as docker containers. The generic CCD core is untouched —
only the source of the dataset `D` changes (measured, not simulated) via the
`FiveGTestbedSystem` subclass (`src/ccd/system/five_g_testbed_system.py`).

Status: **Phase-2 complete.** The full **4-DU/4-CU split topology** (4 `srsdu` + 4 `srscu`
over F1 + 4 `srsue` + core + sink + Xn/RIC stubs) is up and carrying traffic, and the
whole CCD workflow runs on it: nominal-ops collection of `D`, `run_ccd.py` (selects
D₁ = `do(AT3=1, E2=0, NG3=0, QI1=4)`), live enactment, and Φ validation.

## CCD workflow (a → d)

```bash
cd testbeds/5g_ran/scripts
python testbed.py up                          # topology (regenerates compose if missing)
python ranctl.py setup                        # CCDC counter chains + sink route
python generate_dataset.py                    # (a) nominal-ops D -> ../data/dataset.csv (~2 h)
python generate_dataset.py --quick            #     36-window quick pipeline test instead
python run_ccd.py --data ../data/dataset.csv  # (b) CCD -> ../data/ccd_result.json (D_1)
python enact_mode.py --result ../data/ccd_result.json   # (c) enact D_1 on the live RAN
python validate_phi.py --result ../data/ccd_result.json # (d) measured Phi vs Phi-hat
```

### Traffic + measurement plan (collection engine)

5QI class-k traffic of DU_i rides UDP port `flow_port(i,k) = 5000+100i+k` end to end
(UE_i ↔ sink through the PDU tunnel), so every byte counter attributes load per
(DU, class) by destination port alone — independent of the UPF's NAT and the runtime
PDU addresses. Per window (6 s measure + 2 s settle): sample demand + a nominal operator
configuration (QI thresholds vary as regular ops; NG/interface closures likelier at low
demand via `p_close` — the confounder), sync the `CCD` iptables chains, snapshot the
`CCDC` counter chains, drive paced UDP flows (`udp_load.py` inside each UE and the sink),
snapshot again, and map the deltas onto the schema:

- `L^{ik}` = offered bytes at the load generators (REJECTed sends still count — offered);
- `Ladm` = the exact admission filter `Uu·Σ_{k≥QI_i} L^{ik}` applied to measured L;
- `Chat^{ij}_U` = DU_i's F1-U egress counters per CU (physical, per-(i,j)); `Cbar_U` =
  their sum; `Cbar_D` = the sink's post-QI-filter egress counters (physical);
- `Chat_D` (attachment gate), `Ctil = NG_j·Chat`, and `C = Σ_j Ctil` use the *known*
  F̃ functions — per-DU attribution inside a CU's N3 tunnel would need GTP TEID
  inspection, and `fit_scm` assumes exactly these mechanisms for those nodes;
- `T^i_U` / `T^i_D` = delivered bytes at the sink / UE tun ingress counters (physical).

Enactments (`ran_lib.enactments_for`): `QI_i` REJECTs sub-threshold class ports before
they enter the RAN (UE egress for UL, sink egress for DL); `NG_j` REJECTs CU_j's N3
GTP-U both directions and **DROPs** (never REJECTs) its N2 — an ICMP error aborts the
SCTP association and tears down every UE context, which a nominal window could not
reverse; `N6` severs the UPF's `ogstun` forwarding; `Xn`/`E2`/`A1` sever their stub
containers; `AT_i` is a control-plane reattach (`generate_compose.py --reattach` +
DU+UE pair recreate). Two deliberate deviations from the simulator's nominal DGP, both
forced by the real radio: `Uu` stays open (blocking the ZMQ stream mid-run deadlocks
the radio until the pair is recreated), and `AT_i` varies per collection *phase*
(`collection.DEFAULT_PHASES`) rather than per window (a reattach is a ~30 s restart).

## 4-DU/4-CU topology (the paper's model)

```bash
cd testbeds/5g_ran
python scripts/generate_compose.py            # render docker/compose-ran.yml + docker/gen/*
python scripts/testbed.py up                  # core (compose-core.yml) + RAN, pairs recreated
python scripts/testbed.py status              # per-UE attach summary (expect 4x "PDU session")
python scripts/testbed.py down
```

Four gNBs are split into DU (`srsdu`, ZMQ radio) + CU (`srscu`, F1 server; N2/N3 to the
core). Nominal attachment is DU_i → CU_i; `generate_compose.py --reattach 3=1` moves DU_3
to CU_1 (D_1's `AT3=1`). Addressing (`scripts/ran_lib.py`): CU_j `10.53.1.3{j}`, DU_i
`10.53.1.2{i}`, UE_i `10.53.1.4{i}`; DU_i radio ports `20{i}0`/`20{i}1`; one subscriber
per UE (IMSI `001010000000001..004`). Verified gate (2026-07-22): all 4 UEs reach RRC
Connected + PDU session (`10.45.0.2..5`), 0%-loss ping to the UPF on every DU/CU chain.

Network plan (bridge `10.53.1.0/24`, every service has a static IP — dynamic IPAM would
collide with AMF `.2`/UPF `.3`): AMF `.2`, UPF `.3`, Mongo `.100`, other NFs `.101+`.
PLMN `00101`, TAC `7`; the subscribers are registered by `docker/open5gs/add_subscriber.js`
at compose-up. Each DU_i↔UE_i ZMQ radio link runs at `base_srate=23.04e6` (band n3,
20 MHz, 106 PRB) with the cell settings srsUE requires — `coreset0_index: 12`, common
SS#2, `qam64` MCS tables, `prach_config_index: 1` — rendered into the generated DU
configs by `ran_lib.py`.

Gotchas:
- Host must have the `sctp` kernel module (NGAP) — `lsmod | grep sctp`.
- The ZMQ REQ/REP radio deadlocks if one endpoint restarts mid-stream: always restart a
  DU and its UE together (DU first).
- SMF: CTF/freeDiameter is disabled in `smf.yaml` (5G SA only) — the default config
  aborts the SMF on unresolvable EPC hostnames.
- A split gNB shares one `gnb_id` across its CU and DUs; the DU's served-cell NR-CGI is
  checked against it at F1 setup, so **DU_i's `gnb_id` must equal its CU's** (regenerated
  on reattach). Each CU gets a distinct `gnb_id` (= j) so the AMF separates them.
- **F1-U is moved to UDP 2153** (`F1U_PORT`): it is GTP-U like the CU's N3 (2152), and
  the two collide inside one CU container otherwise. The N3 socket is pinned per-CU with
  `cu_up.ngu.socket.bind_addr`.
- ZMQ pairing: `testbed.py up` force-recreates each DU+UE **pair together** after the
  initial up — a UE started against an already-running DU never syncs.
- Every DU needs a unique `cell_cfg.sector_id`: the served cell's NR-CGI is
  `(gnb_id, sector_id)` and `sector_id` defaults to 0 for a single-cell DU, so a CU
  rejects its *second* DU's F1 setup with "Duplicate served cell CGI" (bites on every
  reattachment that shares a CU).

## Images

```bash
cd testbeds/5g_ran
docker build -t ccd-5g-gnb   --build-arg MAKE_JOBS=64 -f docker/gnb/Dockerfile   docker/gnb
docker build -t ccd-5g-srsue --build-arg MAKE_JOBS=32 -f docker/srsue/Dockerfile docker/srsue
docker build -t ccd-5g-sink  -f docker/sink/Dockerfile docker/sink
```

`ccd-5g-srsue` includes python3 (the UL load generator runs inside the UE's netns);
`ccd-5g-sink` is the data-network sink + the Xn/near-RT/non-RT RIC stub image.

Both build from source (srsRAN Project is archived upstream — we pin the last tagged
release, `release_25_10`). The core and Mongo images are pulled: `gradiant/open5gs:2.7.0`,
`mongo:6.0`.

To measure throughput through the RAN (not the docker bridge), route the server IP via
`tun_srsue` in the UE container and bind iperf3 to the PDU address (`-B`).
