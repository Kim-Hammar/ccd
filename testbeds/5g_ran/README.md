# 5G cloud-RAN testbed

Runs the `FiveGSystem` example (`src/ccd/system/five_g_system.py`) on a real virtualized
RAN instead of the reference simulator: **srsRAN Project gNBs (release_25_10)** with a
**ZeroMQ virtual radio**, **srsUE** terminals (srsRAN_4G), and an **Open5GS 5G core**
(gradiant/open5gs 2.7.0), all as docker containers. The generic CCD core is untouched —
only the source of the dataset `D` changes (measured, not simulated) via the
`FiveGTestbedSystem` subclass (`src/ccd/system/five_g_testbed_system.py`).

Status: **Phase-2.** Both the 1-gNB smoke gate and the full **4-DU/4-CU split topology**
(4 `srsdu` + 4 `srscu` over F1 + 4 `srsue` + core) are up and carrying traffic. Collection
of the dataset `D` and mode enactment/validation are next (`PHASE2_PLAN.md`).

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

Split-topology gotchas (on top of the smoke ones below):
- A split gNB shares one `gnb_id` across its CU and DUs; the DU's served-cell NR-CGI is
  checked against it at F1 setup, so **DU_i's `gnb_id` must equal its CU's** (regenerated
  on reattach). Each CU gets a distinct `gnb_id` (= j) so the AMF separates them.
- **F1-U is moved to UDP 2153** (`F1U_PORT`): it is GTP-U like the CU's N3 (2152), and
  the two collide inside one CU container otherwise. The N3 socket is pinned per-CU with
  `cu_up.ngu.socket.bind_addr`.
- ZMQ pairing: `testbed.py up` force-recreates each DU+UE **pair together** after the
  initial up — a UE started against an already-running DU never syncs.

## Images

```bash
cd testbeds/5g_ran
docker build -t ccd-5g-gnb   --build-arg MAKE_JOBS=64 -f docker/gnb/Dockerfile   docker/gnb
docker build -t ccd-5g-srsue --build-arg MAKE_JOBS=32 -f docker/srsue/Dockerfile docker/srsue
```

Both build from source (srsRAN Project is archived upstream — we pin the last tagged
release, `release_25_10`). The core and Mongo images are pulled: `gradiant/open5gs:2.7.0`,
`mongo:6.0`.

## Smoke bring-up (1 gNB + 1 UE)

```bash
cd testbeds/5g_ran/docker
docker compose -f compose-smoke.yml up -d
docker logs -f ccd5g-ue        # expect: "Found Cell", "RRC Connected", "PDU Session ... IP 10.45.0.x"
docker exec ccd5g-ue ping -c 3 10.45.0.1   # user-plane traffic through the RAN to the UPF
docker compose -f compose-smoke.yml down
```

Network plan (bridge `10.53.1.0/24`, every service has a static IP — dynamic IPAM would
collide with AMF `.2`/UPF `.3`): AMF `.2`, UPF `.3`, gNB `.10`, UE `.20`, Mongo `.100`,
other NFs `.101+`. PLMN `00101`, TAC `7`; test SIM `001010000000001` (registered by
`docker/open5gs/add_subscriber.js` at compose-up). The ZMQ radio link is gNB
`tcp://10.53.1.10:2000` ↔ UE `tcp://10.53.1.20:2001` at `base_srate=23.04e6`
(band n3, 20 MHz, 106 PRB — the srsUE-compatible tutorial settings; srsUE also needs
the gNB's `coreset0_index: 12`, common SS#2, `qam64` MCS tables, and
`prach_config_index: 1` in `docker/gnb/gnb-smoke.yml`).

Verified gate (2026-07-22): RRC Connected → PDU session `10.45.0.2` → 0%-loss ping to
the UPF (`10.45.0.1`, ~35 ms RTT) → iperf3 through the tunnel ~5 Mbit/s UL / ~32 Mbit/s
DL. To measure through the RAN (not the docker bridge), route the server IP via
`tun_srsue` in the UE container and bind iperf3 to the PDU address (`-B`).

Gotchas:
- Host must have the `sctp` kernel module (NGAP) — `lsmod | grep sctp`.
- The ZMQ REQ/REP radio deadlocks if one endpoint restarts mid-stream: always restart
  the gNB and UE together (gNB first).
- SMF: CTF/freeDiameter is disabled in `smf.yaml` (5G SA only) — the default config
  aborts the SMF on unresolvable EPC hostnames.
