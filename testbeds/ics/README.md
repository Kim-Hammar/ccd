# Industrial control system (ICS) testbed

Runs the `IcsSystem` example (`src/ccd/system/ics_system.py`) on a real dockerized
industrial control system instead of the reference simulator: an enterprise **web server**,
a supervisory **control server**, a **SCADA command client**, and a **process** container
running the **Tennessee Eastman process** via [`tep2py`](https://github.com/camaramm/tep2py),
with the **G2 gateway** realized as iptables firewall rules between the enterprise and
plant container networks. The generic CCD core is untouched — only the source of the
dataset `D` changes (measured, not simulated) via the `IcsTestbedSystem` subclass
(`src/ccd/system/ics_testbed_system.py`).

> **Process simulator.** The paper uses pyTEP, which requires a licensed MATLAB/Simulink.
> The testbed substitutes the MATLAB-free **tep2py** (the Fortran TEP built with
> gfortran/f2py). tep2py is a *disturbance* simulator (the manipulated variables are fixed
> at the base operating point), so the supervisory command's effect on the operating
> pressure is modeled as a `PRESSURE_GAIN` shift while tep2py supplies the base process
> dynamics and disturbance noise (IDV(8) feed-composition variation).

## Topology

Two container networks — `enterprise` (172.31.1.0/24) and `plant` (172.31.2.0/24):

- **web** (`ccd-ics-web`, enterprise): the enterprise web server. State `W` (up / safe
  mode); reports web integrity `I`.
- **scada** (`ccd-ics-scada`, enterprise): the SCADA command client; issues supervisory
  setpoint commands `C` toward the control server across the G2 gateway (run on demand via
  `docker exec`).
- **control** (`ccd-ics-control`, enterprise + plant): the supervisory control server.
  Receives the command that crossed the gateway (`Ctil`), and in remote-control mode
  forwards the valve setpoint (`V = Chat*Ctil`) to the process.
- **process** (`ccd-ics-process`, plant): the Tennessee Eastman process (tep2py). Reports
  process state `P` (reactor pressure) and safety `S` (margin to the 3000 kPa shutdown
  limit).

## Model ↔ measurement mapping

| var | meaning | how it is realized / measured |
|-----|---------|-------------------------------|
| `C` | supervisory command | setpoint magnitude the SCADA client offers (demand-driven) |
| `G2` | gateway availability | **iptables REJECT** of the enterprise subnet at the control server |
| `Ctil` | control state = `G2·C` | command the control server received (0 when the gateway is shut) |
| `Chat` | control mode | control-server app setting (remote / local) |
| `V` | valve state = `Chat·Ctil` | valve setpoint the control server forwards (0 in local mode) |
| `P` | process state | tep2py reactor pressure XMEAS(7) + command-proportional shift |
| `S` | process safety | margin of `P` to the 3000 kPa reactor shutdown limit (100 = safe base) |
| `W` | web-server state | web-server app setting (up / safe) |
| `I` | web integrity | reported by the web server (high up, reduced in safe mode) |

The two known products are **physically gated**: closing the gateway drops the command
(`Ctil = 0`) and local control withholds it from the valves (`V = 0`), which is why
`use_known_product_mechanisms=True`. Under containment (`V = 0`) the process runs at the
safe base case, so safety is maximal.

## Images

```bash
cd testbeds/ics
python scripts/generate_compose.py         # render docker/docker-compose.yml
docker compose -f docker/docker-compose.yml build   # or let `testbed.py up --build` do it
```

The process image builds tep2py from source (gfortran + f2py; numpy pinned `<1.24` for the
classic distutils f2py backend and the `np.int`/`np.integer` aliases tep2py still uses) and
smoke-tests a base-case simulation at build time.

## CCD workflow (a → d)

```bash
cd testbeds/ics/scripts
python testbed.py up                            # build + start; resets to nominal
python generate_dataset.py                      # (a) nominal-ops D -> ../data/dataset.csv
python generate_dataset.py --quick              #     40-window pipeline smoke instead
python run_ccd.py --data ../data/dataset.csv    # (b) CCD -> ../data/ccd_result.json (D_1)
python enact_mode.py --result ../data/ccd_result.json   # (c) enact D_1 on the live ICS
python validate_phi.py --result ../data/ccd_result.json # (d) measured Phi vs Phi-hat
python testbed.py down
```

CCD selects **D₁ = `do(W=0, G2=0, Chat=0)`**: seal the supervisory network from the
enterprise (blocking lateral movement E2/E3 and severing the attacker's commands from the
process), switch the field controllers to local control (blocking command injection E4),
and drive the web server to its safe state — keeping web integrity and process safety
above the critical level `α = 0.5·Φ`.

### Confounder

Operator degradations (web safe-mode, gateway-closed, local-control) are **mutually
exclusive per window** and more likely at low demand (`ics_lib.p_close`). Mutual exclusion
means the joint degraded config `do(W=0,G2=0,Chat=0)` never occurs observationally, so the
naive baseline is undefined and CCD must *identify* Φ, not read it off.

## Gotchas

- The G2 firewall REJECTs the **enterprise subnet** on the control server's `INPUT` (CCD
  chain). Service `/metrics` are read via `docker exec … curl localhost` (source-agnostic),
  so the firewall never blocks a measurement read.
- tep2py's committed `.so` is for cpython-36; the image rebuilds the Fortran extension for
  Python 3.11. It also needs `SETUPTOOLS_USE_DISTUTILS=stdlib` so `numpy.distutils` finds
  the stdlib `distutils.msvccompiler`.
- The attacker software is not implemented — the compromise lives only in the two-layer
  model; the command stream `C` is the nominal supervisory traffic.
