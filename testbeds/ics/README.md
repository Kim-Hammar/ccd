# Industrial control system (ICS) testbed

A dockerized ICS. It consists of an enterprise web server, a SCADA command client, a
supervisory control server, and a process container running the Tennessee Eastman process
via [`tep2py`](https://github.com/camaramm/tep2py), spread over an enterprise and a plant
container network; the G2 gateway is realized as iptables rules between them.

## Images

```bash
cd testbeds/ics
python scripts/generate_compose.py
docker compose -f docker/docker-compose.yml build
```

## Example Usage

```bash
cd testbeds/ics/scripts
python testbed.py up
python testbed.py status
python testbed.py down
```
