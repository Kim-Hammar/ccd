# 5G cloud-RAN testbed

A dockerized realization of the 5G example (`FiveGSystem`, `src/ccd/system/five_g_system.py`):
four srsRAN Project gNBs (release_25_10) split into DU (`srsdu`, ZeroMQ virtual radio) and
CU (`srscu`) over F1, four srsUE terminals (srsRAN_4G), an Open5GS core
(gradiant/open5gs 2.7.0), a data-network sink, and Xn/RIC stub containers. CCD's dataset
`D` is measured on the running containers instead of simulated, via the
`FiveGTestbedSystem` subclass (`src/ccd/system/five_g_testbed_system.py`); the generic CCD
core is unchanged. On this topology CCD selects `D_1 = do(AT3=1, E2=0, NG3=0, QI1=4)`.

## CCD workflow

```bash
cd testbeds/5g_ran/scripts
python testbed.py up                          # start the topology (regenerates compose if missing)
python ranctl.py setup                        # CCDC counter chains + sink route
python generate_dataset.py                    # (a) nominal-ops D -> ../data/dataset.csv (~2 h)
python generate_dataset.py --quick            #     36-window test run instead
python run_ccd.py --data ../data/dataset.csv  # (b) CCD -> ../data/ccd_result.json
python enact_mode.py --result ../data/ccd_result.json   # (c) enact the mode on the live RAN
python validate_phi.py --result ../data/ccd_result.json # (d) measured Phi vs Phi-hat
```

## Topology

```bash
cd testbeds/5g_ran
python scripts/generate_compose.py            # render docker/compose-ran.yml + docker/gen/*
python scripts/testbed.py up                  # core (compose-core.yml) + RAN, pairs recreated
python scripts/testbed.py status              # per-UE attach summary (expect 4x "PDU session")
python scripts/testbed.py down
```

Nominal attachment is DU_i → CU_i; `generate_compose.py --reattach 3=1` moves DU_3 to
CU_1 (`AT3=1`). All services sit on one bridge (`10.53.1.0/24`) with static IPs, since
dynamic IPAM would collide with the AMF/UPF addresses: AMF `.2`, UPF `.3`, DU_i `.2{i}`,
CU_j `.3{j}`, UE_i `.4{i}`, Mongo `.100`, other NFs `.101+` (see `scripts/ran_lib.py`).
PLMN `00101`, TAC `7`; one subscriber per UE (IMSI `001010000000001..004`), registered by
`docker/open5gs/add_subscriber.js` at compose-up. Each DU_i↔UE_i ZMQ link uses radio
ports `20{i}0`/`20{i}1` at `base_srate=23.04e6` (band n3, 20 MHz, 106 PRB) with the cell
settings srsUE requires (`coreset0_index: 12`, common SS#2, `qam64` MCS tables,
`prach_config_index: 1`), rendered into the generated DU configs by `ran_lib.py`.

## Measurement

5QI class-k traffic of DU_i rides UDP port `flow_port(i,k) = 5000+100i+k` end to end
(UE_i ↔ sink through the PDU tunnel), so byte counters attribute load per (DU, class) by
destination port alone, independent of the UPF's NAT and the runtime PDU addresses.

Each window (6 s measure + 2 s settle) samples a demand level and a nominal operator
configuration (QI thresholds vary as regular operations; NG/interface closures are
likelier at low demand via `p_close` — the confounder), syncs the `CCD` iptables chains,
snapshots the `CCDC` counter chains, drives paced UDP flows (`udp_load.py` in each UE and
the sink), snapshots again, and maps the deltas onto the schema:

- `L^{ik}`: offered bytes at the load generators (REJECTed sends still count — offered);
- `Ladm`: the admission filter `Uu·Σ_{k≥QI_i} L^{ik}` applied to measured L;
- `Chat^{ij}_U`: DU_i's F1-U egress counters per CU; `Cbar_U`: their sum; `Cbar_D`: the
  sink's post-QI-filter egress counters;
- `Chat_D` (attachment gate), `Ctil = NG_j·Chat`, `C = Σ_j Ctil`: computed from the known
  F̃ functions — per-DU attribution inside a CU's N3 tunnel would require GTP TEID
  inspection, and `fit_scm` assumes exactly these mechanisms for those nodes;
- `T^i_U` / `T^i_D`: delivered bytes at the sink / UE tun ingress counters.

## Enactment

`ran_lib.enactments_for` maps each intervention to container-level actions: `QI_i`
REJECTs sub-threshold class ports before they enter the RAN (UE egress for UL, sink
egress for DL); `NG_j` REJECTs CU_j's N3 GTP-U in both directions and DROPs its N2 (an
ICMP error would abort the SCTP association and tear down every UE context); `N6` severs
the UPF's `ogstun` forwarding; `Xn`/`E2`/`A1` sever their stub containers; `AT_i` is a
control-plane reattach (`generate_compose.py --reattach` + DU+UE pair recreate).

Two deviations from the simulator's nominal DGP are forced by the real radio: `Uu` stays
open (blocking the ZMQ stream mid-run deadlocks the radio until the pair is recreated),
and `AT_i` varies per collection phase (`collection.DEFAULT_PHASES`) rather than per
window, since a reattach is a ~30 s restart.

## Images

```bash
cd testbeds/5g_ran
docker build -t ccd-5g-gnb   --build-arg MAKE_JOBS=64 -f docker/gnb/Dockerfile   docker/gnb
docker build -t ccd-5g-srsue --build-arg MAKE_JOBS=32 -f docker/srsue/Dockerfile docker/srsue
docker build -t ccd-5g-sink  -f docker/sink/Dockerfile docker/sink
```

`ccd-5g-gnb` and `ccd-5g-srsue` build from source (srsRAN Project is archived upstream;
the last tagged release, `release_25_10`, is pinned). `ccd-5g-srsue` includes python3
(the UL load generator runs inside the UE's netns); `ccd-5g-sink` doubles as the Xn and
RIC stub image. The core and Mongo images are pulled (`gradiant/open5gs:2.7.0`,
`mongo:6.0`).

## Notes / caveats

- The host must have the `sctp` kernel module (NGAP): `lsmod | grep sctp`.
- The ZMQ REQ/REP radio deadlocks if one endpoint restarts mid-stream; `testbed.py up`
  therefore force-recreates each DU+UE pair together after the initial up (a UE started
  against an already-running DU never syncs). Always restart a DU and its UE together,
  DU first.
- A split gNB shares one `gnb_id` across its CU and DUs (the DU's served-cell NR-CGI is
  checked against it at F1 setup), so DU_i's `gnb_id` must equal its CU's; each CU gets a
  distinct `gnb_id` (= j) so the AMF separates them. Regenerated on reattach.
- Every DU needs a unique `cell_cfg.sector_id`: the served-cell NR-CGI is
  `(gnb_id, sector_id)`, which defaults to 0 for a single-cell DU, so a CU rejects its
  second DU's F1 setup ("Duplicate served cell CGI") whenever a reattachment shares a CU.
- F1-U runs on UDP 2153 (`F1U_PORT`): it is GTP-U like the CU's N3 (2152) and the two
  would collide inside one CU container. The N3 socket is pinned per CU with
  `cu_up.ngu.socket.bind_addr`.
- CTF/freeDiameter is disabled in `smf.yaml` (5G SA only); the default config aborts the
  SMF on unresolvable EPC hostnames.
- To measure throughput through the RAN (not the docker bridge), route the server IP via
  `tun_srsue` in the UE container and bind iperf3 to the PDU address (`-B`).
