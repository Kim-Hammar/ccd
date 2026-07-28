# IT-system testbed

A dockerized IT system. It consists of `m` Flask web-service replicas (`n_1..n_m`)
backed by a PostgreSQL database (`n_{m+1}`) behind a load-balancing gateway, with `n_1`
doubling as a management host, spread over a service, a database, and a management
container network; links are controlled with iptables rules in the containers.

## Images

```bash
cd testbeds/it_system
python scripts/generate_compose.py --m 3
docker compose -f docker/docker-compose.yml build
```

## Example Usage

```bash
cd testbeds/it_system/scripts
python testbed.py up --m 3
python testbed.py status
python testbed.py down
```
