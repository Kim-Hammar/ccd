# Industrial control system (ICS) testbed

A dockerized realization of the ICS example (`IcsSystem`, `src/ccd/system/ics_system.py`):
an enterprise web server, a SCADA command client, a supervisory control server, and a
process container running the Tennessee Eastman process via
[`tep2py`](https://github.com/camaramm/tep2py), with the G2 gateway realized as iptables
rules between the enterprise and plant container networks. CCD's dataset `D` is measured
on the running containers instead of simulated, via the `IcsTestbedSystem` subclass
(`src/ccd/system/ics_testbed_system.py`); the generic CCD core is unchanged.

The paper uses pyTEP, which requires a licensed MATLAB/Simulink; the testbed substitutes
the MATLAB-free tep2py (the Fortran TEP built with gfortran/f2py). tep2py is a
disturbance simulator with the manipulated variables fixed at the base operating point,
so the supervisory command's effect on the operating pressure is modeled as a
`PRESSURE_GAIN` shift, while tep2py supplies the base process dynamics and disturbance
noise (IDV(8) feed-composition variation).

## Topology

Two container networks, `enterprise` (172.31.1.0/24) and `plant` (172.31.2.0/24):

- `ccd-ics-web` (enterprise): the enterprise web server. State `W` (up / safe mode);
  reports web integrity `I`.
- `ccd-ics-scada` (enterprise): the SCADA command client; issues supervisory setpoint
  commands `C` toward the control server across the G2 gateway (run on demand via
  `docker exec`).
- `ccd-ics-control` (enterprise + plant): the supervisory control server. Receives the
  command that crossed the gateway (`Ctil`) and, in remote-control mode, forwards the
  valve setpoint `V = Chat·Ctil` to the process.
- `ccd-ics-process` (plant): the Tennessee Eastman process (tep2py). Reports process
  state `P` (reactor pressure) and safety `S` (margin to the 3000 kPa shutdown limit).

The attacker software is not implemented; the compromise is represented only in the
two-layer model, and the command stream `C` is the nominal supervisory traffic.

## Model ↔ measurement mapping

| var | meaning | how it is realized / measured |
|-----|---------|-------------------------------|
| `C` | supervisory command | setpoint magnitude the SCADA client offers (demand-driven) |
| `G2` | gateway availability | iptables REJECT of the enterprise subnet at the control server |
| `Ctil` | control state = `G2·C` | command the control server received (0 when the gateway is shut) |
| `Chat` | control mode | control-server app setting (remote / local) |
| `V` | valve state = `Chat·Ctil` | valve setpoint the control server forwards (0 in local mode) |
| `P` | process state | tep2py reactor pressure XMEAS(7) + command-proportional shift |
| `S` | process safety | margin of `P` to the 3000 kPa reactor shutdown limit (100 = safe base) |
| `W` | web-server state | web-server app setting (up / safe) |
| `I` | web integrity | reported by the web server (high up, reduced in safe mode) |

The two known products are physically gated: closing the gateway drops the command
(`Ctil = 0`) and local control withholds it from the valves (`V = 0`), which is why
`use_known_product_mechanisms=True`. Under containment (`V = 0`) the process runs at the
safe base case, so safety is maximal. Service `/metrics` are read via
`docker exec … curl localhost`, so the G2 firewall never blocks a measurement read.

## CCD workflow

```bash
cd testbeds/ics/scripts
python testbed.py up                            # build + start; resets to nominal
python generate_dataset.py                      # (a) nominal-ops D -> ../data/dataset.csv
python generate_dataset.py --quick              #     40-window test run instead
python run_ccd.py --data ../data/dataset.csv    # (b) CCD -> ../data/ccd_result.json
python enact_mode.py --result ../data/ccd_result.json   # (c) enact the mode on the live ICS
python validate_phi.py --result ../data/ccd_result.json # (d) measured Phi vs Phi-hat
python testbed.py down
```

CCD selects `D_1 = do(W=0, G2=0, Chat=0)`: seal the supervisory network from the
enterprise (blocking lateral movement E2/E3 and severing the attacker's commands from
the process), switch the field controllers to local control (blocking command injection
E4), and drive the web server to its safe state — keeping `Φ ≥ α = 0.5·Φ`.

During collection, the operator degradations (web safe-mode, gateway-closed,
local-control) are mutually exclusive per window and likelier at low demand
(`ics_lib.p_close`). Mutual exclusion means the joint degraded configuration never
occurs observationally, so the naive baseline is undefined and CCD must identify Φ.

## Images

```bash
cd testbeds/ics
python scripts/generate_compose.py         # render docker/docker-compose.yml
docker compose -f docker/docker-compose.yml build   # or let `testbed.py up --build` do it
```

The process image builds tep2py from source (gfortran + f2py; numpy pinned `<1.24` for
the classic distutils f2py backend and the `np.int` aliases tep2py still uses) and runs
a base-case simulation check at build time.
