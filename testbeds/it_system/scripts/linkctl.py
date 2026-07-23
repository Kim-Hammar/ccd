"""
Link control for the IT-system testbed: synchronize the operator-controlled links
(N_i, M_i, A_i) to a desired open/closed state via ``docker exec`` iptables commands
(idempotent flush-and-readd, see ``testbed_lib.sync_commands``). The same mechanism
drives nominal maintenance toggles during collection and enacts CCD's selected mode.

Usage:
  python linkctl.py close N1 M1 A2 --m 10       # close these links, open the rest
  python linkctl.py open --m 10                 # open all links
  python linkctl.py reset --m 10                # flush the CCD chain everywhere
  python linkctl.py status --m 10               # print each container's CCD chain
  add --dry-run to any command to print the docker commands without running them
"""

from __future__ import annotations
import argparse
import subprocess
from typing import List, Mapping
import testbed_lib as tl


def apply(desired: Mapping[str, int], m: int, *, dry_run: bool = False) -> List[List[str]]:
    """Synchronize all links to ``desired`` (missing links treated as open)."""
    commands = tl.sync_commands(desired, m)
    for cmd in commands:
        if dry_run:
            print(" ".join(cmd))
        else:
            subprocess.run(cmd, check=True)
    return commands


def reset(m: int, *, dry_run: bool = False) -> None:
    """Open every link (flush the CCD chain in every controlled container)."""
    apply({}, m, dry_run=dry_run)


def status(m: int) -> None:
    """Print the CCD chain of the gateway and every server."""
    containers = [tl.GATEWAY_CONTAINER] + [tl.server_container(i) for i in range(1, m + 1)]
    for container in containers:
        print(f"--- {container} ---")
        subprocess.run(["docker", "exec", container, "iptables", "-S", "CCD"], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Control the testbed's operator links.")
    parser.add_argument("action", choices=["close", "open", "reset", "status"])
    parser.add_argument("links", nargs="*", help="link variables to close, e.g. N1 M1 A2")
    parser.add_argument("--m", type=int, default=10, help="number of application servers")
    parser.add_argument("--dry-run", action="store_true", help="print commands without running")
    args = parser.parse_args()

    if args.action == "status":
        status(args.m)
    elif args.action in ("open", "reset"):
        reset(args.m, dry_run=args.dry_run)
    else:  # close
        apply({link: 0 for link in args.links}, args.m, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
