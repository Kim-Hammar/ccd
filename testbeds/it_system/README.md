# IT-system testbed

A dockerized realization of the IT-system example: `m` Flask web-service replicas
(`n_1..n_m`) backed by a PostgreSQL database (`n_{m+1}`) behind a load-balancing
gateway, with `n_1` doubling as a management host. CCD's dataset `D` is measured on the
running containers instead of simulated, via the `ITTestbedSystem` subclass
(`src/ccd/system/it_testbed_system.py`); the generic CCD core is unchanged.

## Architecture

```
             clients (host loadgen, ~100 req/s)
                      |  8080
                 [ gateway ]  --- round-robin, no health checks --->  n_1 .. n_m
                                                                        |  (each)
   service_net 172.28.1.0/24   db_net 172.28.2.0/24   mgmt_net 172.28.3.0/24
   gateway .10, n_i .{100+i}    db .10, n_i .{100+i}   n_1 (mgmt host) -> n_i .{100+i}
                                       |
                                  [ postgres ]
```

- `ccd_gateway`: async round-robin reverse proxy with no health checks or
  skip-on-failure, so the per-server offered load stays `L_i ≈ W/m` even when a link is
  closed. Counters `attempted[i]` (= `L_i`) and `ok[i]` (= `Th_i`); endpoints
  `/metrics`, `/work`.
- `ccd_server{i}` (hostname `n{i}`): Flask + gunicorn (1 worker); `/work` does an
  upsert+read against postgres. Counter `requests_completed_db` (= `Tt_i`); `/metrics`
  published on host port `5000+i`, bypassing the blockable links.
- `ccd_db`: postgres:16 with a `pg_isready` healthcheck, ephemeral.

Links are controlled with iptables (cap `NET_ADMIN`) in a per-container `CCD` chain:
`N_i` blocks gateway→`n_i` at the gateway, `M_i` blocks `n_i`→db at server `i`, `A_i`
blocks the management link `n_1`→`n_i` at server 1. Closures use
`REJECT --reject-with tcp-reset` (fail-fast, so `L_i` is preserved and toggles take
effect immediately). The same mechanism drives nominal maintenance toggling during
collection and enacts CCD's mode. If the iptables nft backend misbehaves under Docker
Desktop, switch the images to the legacy backend (see the Dockerfile comment).

The attacker software is not implemented; the compromise of `n_1` and its capabilities
are represented only in the two-layer model. `mgmt_net` exists so the `A_i` management
links are physically meaningful.

## Model ↔ measurement mapping

One CSV row per measurement window (offered load ÷ measured duration):

| Column | Source |
|---|---|
| `W`    | requests the loadgen sent / duration (measured offered rate) |
| `L_i`  | Δ gateway `attempted[i]` / duration |
| `N_i`, `M_i` | link states set for the window (0/1) |
| `Tt_i` | Δ server-`i` `requests_completed_db` / duration (carried load) |
| `Th_i` | Δ gateway `ok[i]` / duration (end-to-end successes) |
| `T`    | `Σ_i Th_i` |

The testbed model (`ITTestbedSystem`, in `src/ccd/system/`) differs from the simulator
model in two measurement-driven ways: (1) it adds edges `N_i → Tt_i` (measured carried
load is 0 when the gateway link is closed), and (2) `eps_i`/`gam_i` are unobserved
(excluded from the fit graph). Because those products are gated, CCD uses the known
functions `F̃` as exact GCM mechanisms here (`use_known_product_mechanisms`).

## CCD workflow

```bash
pip install -e ".[testbed]" --no-deps          # from the repo root (adds aiohttp)
cd testbeds/it_system

python scripts/testbed.py up --m 3             # generate compose, build, start, health-wait
python scripts/generate_dataset.py --m 3 --quick --out data/quick.csv   # ~5 min
python scripts/run_ccd.py --data data/quick.csv --m 3          # -> data/ccd_result.json
python scripts/enact_mode.py --result data/ccd_result.json --dry-run    # inspect iptables plan
python scripts/enact_mode.py --result data/ccd_result.json
python scripts/validate_phi.py --result data/ccd_result.json --windows 20   # measured Phi vs Phi-hat
python scripts/testbed.py down

# recovery progression (same containers, different attack-graph scenario):
python scripts/run_ccd.py --data data/quick.csv --m 3 --patched   # D_2 -> do(N1=0)
python scripts/run_ccd.py --data data/quick.csv --m 3 --evicted   # D_3 -> do()
```

Full-scale run: `--m 10` and `generate_dataset.py --windows 600` (≈80 min). Changing `m`
requires `testbed.py down`, then `up` again (the compose file and static IPs are
regenerated). The static-IP scheme (`.{100+i}`) caps `m ≤ 150`; host ports
`5001..5000+m` must be free.

## Layout

- `docker/` — `gateway/`, `server/`, `db/` build contexts; `docker-compose.yml` is
  generated (gitignored) by `scripts/generate_compose.py`.
- `scripts/testbed_lib.py` — pure, unit-tested logic (addresses, `p_close`, the
  link→iptables mapping, compose template, dataset schema).
- `scripts/{generate_compose,testbed,linkctl,loadgen,collection,generate_dataset,run_ccd,enact_mode,validate_phi}.py`
  — orchestration (import the installed `ccd` package).
- `tests/` — pure tests (`test_testbed_lib.py`) run in the normal suite; the docker
  smoke test (`test_smoke_docker.py`) is skipped unless `CCD_TESTBED_SMOKE=1`.
- `data/` — collected datasets and results (gitignored).
