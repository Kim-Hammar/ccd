"""
Pure (docker-free) library for the IT-system testbed: address plan, nominal closure
probability, link -> iptables mapping, compose-file generation, and the dataset schema.
Deterministic and unit-tested without docker (``tests/test_testbed_lib.py``); the
docker-facing scripts (``linkctl.py``, ``testbed.py``, ``collection.py``) build on it.
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Mapping

# --- address plan -------------------------------------------------------------
SERVICE_SUBNET = "172.28.1.0/24"     # gateway <-> servers
DB_SUBNET = "172.28.2.0/24"          # servers <-> database
MGMT_SUBNET = "172.28.3.0/24"        # n_1 (management host) <-> servers

GATEWAY_SERVICE_IP = "172.28.1.10"
DB_IP = "172.28.2.10"

GATEWAY_CONTAINER = "ccd_gateway"
DB_CONTAINER = "ccd_db"

# host port of the gateway's client endpoint; overridable when 8080 is taken on the host
GATEWAY_HOST_PORT = int(os.environ.get("CCD_GATEWAY_HOST_PORT", "8080"))
SERVER_HOST_PORT_BASE = 5000         # server i publishes /metrics on host port 5000 + i
SERVER_PORT = 5000                   # container-internal web-service port
MAX_M = 150                          # the .{100+i} host-address scheme caps m

DB_USER = "ccd"
DB_PASSWORD = "ccd"
DB_NAME = "ccd"

_LINK_RE = re.compile(r"^([NMA])(\d+)$")


def server_container(i: int) -> str:
    return f"ccd_server{i}"


def server_service_ip(i: int) -> str:
    """Address of server ``n_i`` on the service network (gateway -> n_i link N_i)."""
    return f"172.28.1.{100 + i}"


def server_db_ip(i: int) -> str:
    """Address of server ``n_i`` on the database network (n_i -> db link M_i)."""
    return f"172.28.2.{100 + i}"


def server_mgmt_ip(i: int) -> str:
    """Address of server ``n_i`` on the management network (n_1 -> n_i link A_i)."""
    return f"172.28.3.{100 + i}"


# --- nominal-mode closure probability ----------------------------------------
def p_close(w: float) -> float:
    """Probability that a link is closed for a window at workload ``w`` (req/s).

    The confounder: closures are likelier at low workload (0.30 at w=50 down to 0.05
    at w=150), which biases the naive observational estimate.
    """
    return float(min(0.30, max(0.05, 0.30 - 0.25 * (w - 50.0) / 100.0)))


# --- link -> iptables mapping -------------------------------------------------
@dataclass(frozen=True)
class LinkRule:
    """The iptables rule (in the container-local ``CCD`` chain) that closes a link."""

    link: str            # e.g. "N1", "M3", "A2"
    container: str       # container in which the rule is installed
    rule_args: str       # iptables arguments after ``-A CCD``


def rule_for(link: str) -> LinkRule:
    """The closed-state iptables rule for ``link`` (``N_i``, ``M_i``, or ``A_i``)."""
    match = _LINK_RE.match(link)
    if match is None:
        raise ValueError(f"unknown link variable: {link!r}")
    kind, i = match.group(1), int(match.group(2))
    if kind == "N":
        return LinkRule(
            link=link,
            container=GATEWAY_CONTAINER,
            rule_args=f"-d {server_service_ip(i)} -p tcp --dport {SERVER_PORT} "
                      f"-j REJECT --reject-with tcp-reset",
        )
    if kind == "M":
        return LinkRule(
            link=link,
            container=server_container(i),
            rule_args=f"-d {DB_IP} -p tcp --dport 5432 -j REJECT --reject-with tcp-reset",
        )
    if i < 2:
        raise ValueError(f"unknown link variable: {link!r} (A_i requires i >= 2)")
    return LinkRule(
        link=link,
        container=server_container(1),
        rule_args=f"-d {server_mgmt_ip(i)} -j REJECT",
    )


def sync_commands(desired: Mapping[str, int], m: int) -> List[List[str]]:
    """The ``docker exec`` commands that synchronize all links to ``desired``.

    ``desired`` maps link variables to 0 (closed) / 1 (open); unmentioned links are
    open. Idempotent: each container's ``CCD`` chain is flushed and the closed rules
    re-added in one ``docker exec`` (no incremental bookkeeping).
    """
    closed = sorted(v for v, state in desired.items() if state == 0)
    rules_by_container: Dict[str, List[str]] = {
        GATEWAY_CONTAINER: [],
        **{server_container(i): [] for i in range(1, m + 1)},
    }
    for link in closed:
        rule = rule_for(link)
        if rule.container not in rules_by_container:
            raise ValueError(f"link {link!r} maps to unknown container {rule.container!r} (m={m})")
        rules_by_container[rule.container].append(rule.rule_args)
    commands = []
    for container in sorted(rules_by_container):
        script = "; ".join(["iptables -F CCD"]
                           + [f"iptables -A CCD {args}" for args in rules_by_container[container]])
        commands.append(["docker", "exec", container, "sh", "-c", script])
    return commands


# --- dataset schema -----------------------------------------------------------
METADATA_COLUMNS = ["window", "t_start", "duration", "client_ok_rate"]


def dataset_columns(m: int) -> List[str]:
    """Column order of the collected dataset D (observable vars first, then metadata)."""
    cols = ["W"]
    for prefix in ("L", "N", "M", "Tt", "Th"):
        cols += [f"{prefix}{i}" for i in range(1, m + 1)]
    return cols + ["T"] + METADATA_COLUMNS


# --- compose generation -------------------------------------------------------
def generate_compose(m: int) -> str:
    """Render the docker-compose file for ``m`` servers (deterministic text; the file
    is generated, not checked in -- changing ``m`` requires ``down``, regenerate, ``up``)."""
    if not 2 <= m <= MAX_M:
        raise ValueError(f"m must be in [2, {MAX_M}], got {m}")

    backends = ",".join(f"{server_service_ip(i)}:{SERVER_PORT}" for i in range(1, m + 1))
    lines = [
        "# GENERATED by testbeds/it_system/scripts/generate_compose.py -- do not edit.",
        f"# m = {m} servers + gateway + database.",
        "",
        "services:",
        "  gateway:",
        "    build: ./gateway",
        f"    container_name: {GATEWAY_CONTAINER}",
        "    cap_add: [NET_ADMIN]",
        "    environment:",
        f"      BACKENDS: \"{backends}\"",
        "    ports:",
        f"      - \"{GATEWAY_HOST_PORT}:8080\"",
        "    networks:",
        "      service_net:",
        f"        ipv4_address: {GATEWAY_SERVICE_IP}",
    ]
    for i in range(1, m + 1):
        lines += [
            f"  server{i}:",
            "    build: ./server",
            f"    container_name: {server_container(i)}",
            f"    hostname: n{i}",
            "    cap_add: [NET_ADMIN]",
            "    environment:",
            f"      SERVER_ID: \"{i}\"",
            f"      DB_HOST: {DB_IP}",
            f"      DB_USER: {DB_USER}",
            f"      DB_PASSWORD: {DB_PASSWORD}",
            f"      DB_NAME: {DB_NAME}",
            "    ports:",
            f"      - \"{SERVER_HOST_PORT_BASE + i}:{SERVER_PORT}\"",
            "    depends_on:",
            "      db:",
            "        condition: service_healthy",
            "    networks:",
            "      service_net:",
            f"        ipv4_address: {server_service_ip(i)}",
            "      db_net:",
            f"        ipv4_address: {server_db_ip(i)}",
            "      mgmt_net:",
            f"        ipv4_address: {server_mgmt_ip(i)}",
        ]
    lines += [
        "  db:",
        "    image: postgres:16",
        f"    container_name: {DB_CONTAINER}",
        "    environment:",
        f"      POSTGRES_USER: {DB_USER}",
        f"      POSTGRES_PASSWORD: {DB_PASSWORD}",
        f"      POSTGRES_DB: {DB_NAME}",
        "    volumes:",
        "      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro",
        "    healthcheck:",
        f"      test: [\"CMD-SHELL\", \"pg_isready -U {DB_USER} -d {DB_NAME}\"]",
        "      interval: 2s",
        "      timeout: 2s",
        "      retries: 30",
        "    networks:",
        "      db_net:",
        f"        ipv4_address: {DB_IP}",
        "",
        "networks:",
        "  service_net:",
        "    ipam:",
        f"      config: [{{subnet: {SERVICE_SUBNET}}}]",
        "  db_net:",
        "    ipam:",
        f"      config: [{{subnet: {DB_SUBNET}}}]",
        "  mgmt_net:",
        "    ipam:",
        f"      config: [{{subnet: {MGMT_SUBNET}}}]",
        "",
    ]
    return "\n".join(lines)
