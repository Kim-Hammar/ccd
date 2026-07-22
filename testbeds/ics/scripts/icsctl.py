"""
Control plane for the live ICS testbed: enact operator interventions (the G2 firewall +
the Chat/W application modes), read each service's /metrics, and drive the SCADA command
client. Thin docker-facing layer over the pure mapping in ``ics_lib`` (every rule string
and command list is built and unit-tested there).

Usage (CLI):
  python icsctl.py apply W=0 G2=0 Chat=0      # enact the operator assignments
  python icsctl.py reset                      # nominal: gateway open, remote control, web up
  python icsctl.py status                     # print each service's /metrics
  add --dry-run to print the docker commands without running them
"""

from __future__ import annotations
import argparse
import json
import subprocess
from typing import Dict, List, Mapping
import ics_lib as il


def _run(cmd: List[str], *, dry_run: bool = False, check: bool = True) -> str:
    if dry_run:
        print(" ".join(cmd))
        return ""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"command failed ({' '.join(cmd)}): {res.stderr.strip()}")
    return res.stdout


def _mode_command(enact: il.Enactment) -> List[str]:
    """The ``docker exec ... curl`` command that sets an application mode (Chat / W)."""
    return ["docker", "exec", enact.container, "curl", "-s", "-X", "POST",
            f"http://localhost:{il.APP_PORT}/admin/mode", "-d", f"mode={enact.mode}"]


def apply(mode: Mapping[str, int], *, dry_run: bool = False) -> None:
    """Enact ``mode``: sync the G2 firewall chain and set the Chat/W application modes."""
    for cmd in il.sync_commands(mode):
        _run(cmd, dry_run=dry_run)
    for enact in il.mode_settings(mode):
        _run(_mode_command(enact), dry_run=dry_run)


def reset(*, dry_run: bool = False) -> None:
    """Restore nominal operation: gateway open, remote control, web up."""
    apply({"W": 1, "G2": 1, "Chat": 1}, dry_run=dry_run)


def read_metrics(container: str) -> Dict[str, float]:
    """Read one service's /metrics via ``docker exec ... curl localhost`` (source-agnostic,
    so the G2 firewall never blocks the read)."""
    out = _run(["docker", "exec", container, "curl", "-s",
                f"http://localhost:{il.APP_PORT}/metrics"])
    return json.loads(out)


def drive_command(level: float, duration: float) -> int:
    """Run the SCADA client for ``duration`` s sending setpoint ``level`` to the control
    server; returns the number of accepted commands."""
    url = f"http://{il.CONTROL_ENTERPRISE_IP}:{il.APP_PORT}{il.COMMAND_PATH}"
    out = _run(["docker", "exec", il.SCADA_CONTAINER, "python3", "/client.py",
                "--url", url, "--level", str(level), "--duration", str(duration)])
    try:
        return int(out.strip().splitlines()[-1]) if out.strip() else 0
    except ValueError:
        return 0


def status() -> None:
    for name, container in (("web", il.WEB_CONTAINER), ("control", il.CONTROL_CONTAINER),
                            ("process", il.PROCESS_CONTAINER)):
        try:
            print(f"  {name}: {read_metrics(container)}")
        except Exception as exc:                       # noqa: BLE001 (status is best-effort)
            print(f"  {name}: unavailable ({exc})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Control the ICS testbed's operator variables.")
    parser.add_argument("action", choices=["apply", "reset", "status"])
    parser.add_argument("assignments", nargs="*", metavar="VAR=VALUE",
                        help="operator assignments for 'apply', e.g. W=0 G2=0 Chat=0")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running")
    args = parser.parse_args()

    if args.action == "status":
        status()
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
