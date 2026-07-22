# 5G cloud-RAN testbed

Runs the `FiveGSystem` example (`src/ccd/system/five_g_system.py`) on a real virtualized
RAN instead of the reference simulator: **srsRAN Project gNBs (release_25_10)** with a
**ZeroMQ virtual radio**, **srsUE** terminals (srsRAN_4G), and an **Open5GS 5G core**
(gradiant/open5gs 2.7.0), all as docker containers. The generic CCD core is untouched —
only the source of the dataset `D` changes (measured, not simulated) via the
`FiveGTestbedSystem` subclass (`src/ccd/system/five_g_testbed_system.py`).

Status: **Phase-2 bring-up.** The smoke deployment below (1 gNB + 1 UE + core) is the
feasibility gate; the 4-DU/4-CU topology, collection scripts, and mode enactment follow
(`PHASE2_PLAN.md`).

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
