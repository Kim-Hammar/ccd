"""
Control plane for the live 5G RAN testbed: enact operator interventions (iptables +
DU reattachment), install/read the byte-counter chains, and manage UE attachment state.

Thin docker-facing layer over the pure mapping in ``ran_lib``: every rule string and
command list is built there (unit-tested); this module only executes them, in parallel
where the containers are independent. Used by ``collection.py`` (nominal-ops windows),
``enact_mode.py`` (enact a CCD-selected mode), and ``validate_phi.py``.

Usage (CLI):
  python ranctl.py apply E2=0 NG3=0 QI1=4      # enact iptables-kind assignments
  python ranctl.py reset                       # open every link (flush all CCD chains)
  python ranctl.py setup                       # install counter chains + static routes
  python ranctl.py status                      # attachment map + PDU sessions
  add --dry-run to print the docker commands without running them
"""

from __future__ import annotations
import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Mapping, Optional
import ran_lib as rl

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DOCKER_DIR = os.path.abspath(os.path.join(_SCRIPTS_DIR, "..", "docker"))
_GEN_DIR = os.path.join(_DOCKER_DIR, "gen")
_CORE = os.path.join(_DOCKER_DIR, "compose-core.yml")
_RAN = os.path.join(_DOCKER_DIR, "compose-ran.yml")
_TUN_RE = re.compile(r"inet (10\.45\.\d+\.\d+)/")


def _run_many(commands: List[List[str]], *, dry_run: bool = False, check: bool = True) -> None:
    """Run independent docker commands in parallel (each touches one container)."""
    if dry_run:
        for cmd in commands:
            print(" ".join(cmd))
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda cmd: subprocess.run(cmd, capture_output=True, text=True), commands))
    for cmd, res in zip(commands, results):
        if check and res.returncode != 0:
            raise RuntimeError(f"command failed ({' '.join(cmd)}): {res.stderr.strip()}")


# --- iptables-kind enactment ---------------------------------------------------
def apply(mode: Mapping[str, int], *, dry_run: bool = False) -> None:
    """Synchronize every container's CCD chain to ``mode`` (AT_i handled separately)."""
    _run_many(rl.sync_commands(mode), dry_run=dry_run)


def reset(*, dry_run: bool = False) -> None:
    """Open every link (flush the CCD chain in every controlled container)."""
    apply({}, dry_run=dry_run)


# --- byte counters ---------------------------------------------------------------
def setup_counters(containers: Optional[List[str]] = None, *, dry_run: bool = False) -> None:
    """Install the CCDC counting chains (resets their counters)."""
    commands = [cmd for cmd in rl.count_setup_commands()
                if containers is None or cmd[2] in containers]
    _run_many(commands, dry_run=dry_run)


def snapshot() -> Dict[str, Dict[rl.CounterKey, int]]:
    """One parallel snapshot of every counter container's CCDC byte counters."""
    containers = rl.counter_containers()
    with ThreadPoolExecutor(max_workers=len(containers)) as pool:
        outputs = list(pool.map(
            lambda c: subprocess.run(rl.counter_read_command(c),
                                     capture_output=True, text=True).stdout,
            containers))
    return {c: rl.parse_counters(out) for c, out in zip(containers, outputs)}


# --- static routes (sink <-> PDU subnet through the UPF; UE -> sink via the tun) --
def ensure_sink_route(*, dry_run: bool = False) -> None:
    _run_many([["docker", "exec", rl.SINK_CONTAINER, "ip", "route", "replace",
                rl.PDU_SUBNET, "via", rl.UPF_IP]], dry_run=dry_run)


def ensure_ue_route(i: int, *, dry_run: bool = False) -> None:
    """Route the sink through the PDU tunnel: a /32 wins over the shared bridge subnet,
    so the UE's uplink traverses the RAN instead of the docker network."""
    _run_many([["docker", "exec", rl.ue_container(i), "ip", "route", "replace",
                f"{rl.SINK_IP}/32", "dev", "tun_srsue"]], dry_run=dry_run)


# --- attachment state ------------------------------------------------------------
def pdu_ip(i: int) -> Optional[str]:
    """UE_i's PDU address, or None if it has no established session."""
    res = subprocess.run(["docker", "exec", rl.ue_container(i), "ip", "-4", "addr",
                          "show", "tun_srsue"], capture_output=True, text=True)
    match = _TUN_RE.search(res.stdout)
    return match.group(1) if match else None


def current_at_map() -> Dict[int, int]:
    """The DU -> CU attachment of the *rendered* configs (what the containers run)."""
    out = {}
    for i in range(1, rl.NUM_DU + 1):
        with open(os.path.join(_GEN_DIR, f"du{i}.yml")) as f:
            out[i] = rl.parse_du_target_cu(f.read())
    return out


def _compose(*args: str) -> None:
    subprocess.run(["docker", "compose", "-f", _CORE, "-f", _RAN, *args],
                   cwd=_DOCKER_DIR, check=True, capture_output=True, text=True)


def recreate_pair(i: int) -> None:
    """Recreate DU_i + UE_i together (the ZMQ REQ/REP pairing rule, see README)."""
    _compose("up", "-d", "--force-recreate", f"du{i}", f"ue{i}")


def wait_for_pdu(i: int, *, timeout: float = 90.0, retries: int = 2) -> str:
    """Wait for UE_i's PDU session, recreating the DU+UE pair if it never comes up."""
    for attempt in range(retries + 1):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ip = pdu_ip(i)
            if ip is not None:
                ensure_ue_route(i)
                return ip
            time.sleep(2.0)
        if attempt < retries:
            print(f"  UE_{i}: no PDU session after {timeout:.0f}s, recreating pair "
                  f"(attempt {attempt + 2}/{retries + 1})")
            recreate_pair(i)
    raise RuntimeError(f"UE_{i} failed to establish a PDU session")


def apply_attachment(at_map: Mapping[int, int], *, dry_run: bool = False) -> None:
    """Reconfigure the DU -> CU attachment: regenerate the compose/configs and recreate
    exactly the DU+UE pairs whose target CU changed (control-plane AT_i enactment)."""
    current = current_at_map()
    changed = sorted(i for i, j in at_map.items() if current.get(i) != j)
    reattach_args = [f"{i}={j}" for i, j in sorted(at_map.items()) if j != i]
    gen_cmd = [sys.executable, os.path.join(_SCRIPTS_DIR, "generate_compose.py"),
               "--reattach", *reattach_args]
    if dry_run:
        print(" ".join(gen_cmd))
        for i in changed:
            print(f"docker compose up -d --force-recreate du{i} ue{i}  # DU_{i} -> CU_{at_map[i]}")
        return
    if not changed:
        return
    subprocess.run(gen_cmd, check=True, capture_output=True, text=True)
    for i in changed:
        print(f"  reattaching DU_{i} -> CU_{at_map[i]} (recreating du{i}+ue{i})")
        recreate_pair(i)
    for i in changed:
        wait_for_pdu(i)
    setup_counters([rl.du_container(i) for i in changed] + [rl.ue_container(i) for i in changed])


def ensure_attached(at_map: Mapping[int, int]) -> Dict[int, str]:
    """Health check used before each window: every UE has a live PDU session (recreating
    dead pairs), the sink route + counter chains exist. Returns the PDU addresses."""
    ips: Dict[int, str] = {}
    for i in range(1, rl.NUM_DU + 1):
        ip = pdu_ip(i)
        if ip is None:
            print(f"  UE_{i}: PDU session lost, recreating DU+UE pair")
            recreate_pair(i)
            ip = wait_for_pdu(i)
            setup_counters([rl.du_container(i), rl.ue_container(i)])
        ensure_ue_route(i)
        ips[i] = ip
    return ips


def setup(*, dry_run: bool = False) -> None:
    """Install counter chains and the sink route (run once after ``testbed.py up``)."""
    setup_counters(dry_run=dry_run)
    ensure_sink_route(dry_run=dry_run)


def status() -> None:
    at_map = current_at_map()
    print(f"Attachment map DU->CU: {at_map}")
    for i in range(1, rl.NUM_DU + 1):
        ip = pdu_ip(i)
        print(f"  UE_{i}: {'PDU session ' + ip if ip else 'no PDU session'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Control the 5G testbed's operator links.")
    parser.add_argument("action", choices=["apply", "reset", "setup", "status"])
    parser.add_argument("assignments", nargs="*", metavar="VAR=VALUE",
                        help="operator assignments for 'apply', e.g. E2=0 NG3=0 QI1=4")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running")
    args = parser.parse_args()

    if args.action == "status":
        status()
    elif args.action == "setup":
        setup(dry_run=args.dry_run)
    elif args.action == "reset":
        reset(dry_run=args.dry_run)
    else:
        mode = {}
        for item in args.assignments:
            var, _, value = item.partition("=")
            mode[var] = int(value)
        apply(mode, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
