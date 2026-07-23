"""
Lifecycle for the 4-DU/4-CU 5G testbed: ``up`` / ``down`` / ``status``.

Combines the fixed core (``compose-core.yml``) with the generated RAN
(``compose-ran.yml``) on the shared ``ccd5g`` project. ``up`` regenerates the RAN compose
first (nominal attachment unless ``compose-ran.yml`` already exists) so a fresh checkout
just works.

Usage:
  python testbed.py up          # bring up core + RAN
  python testbed.py status      # per-container state + UE attach summary
  python testbed.py down        # tear everything down
"""

from __future__ import annotations
import argparse
import os
import subprocess
import sys
import ran_lib as rl

_DOCKER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docker"))
_CORE = os.path.join(_DOCKER_DIR, "compose-core.yml")
_RAN = os.path.join(_DOCKER_DIR, "compose-ran.yml")


def _compose(*args: str) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "-f", _CORE, "-f", _RAN, *args]
    return subprocess.run(cmd, cwd=_DOCKER_DIR)


def up() -> None:
    if not os.path.exists(_RAN):
        print("compose-ran.yml missing; generating nominal topology first.")
        subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "generate_compose.py")],
                       check=True)
    _compose("up", "-d")
    # The ZMQ radio is a REQ/REP pair: a DU and its UE must be (re)started together as a
    # fresh pair or the UE never syncs. The CUs are already up, so F1 re-setup and cell
    # sync succeed after the recreate.
    for i in range(1, rl.NUM_DU + 1):
        _compose("up", "-d", "--force-recreate", f"du{i}", f"ue{i}")


def down() -> None:
    _compose("down")


def status() -> None:
    _compose("ps")
    print("\nUE attach summary:")
    for i in range(1, rl.NUM_DU + 1):
        name = rl.ue_container(i)
        out = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
        log = out.stdout + out.stderr
        state = "PDU session" if "PDU Session Establishment successful" in log \
            else "RRC connected" if "RRC Connected" in log \
            else "attaching" if "Attaching UE" in log else "down"
        print(f"  UE_{i} ({name}): {state}")


def main() -> None:
    parser = argparse.ArgumentParser(description="4-DU/4-CU 5G testbed lifecycle.")
    parser.add_argument("action", choices=["up", "down", "status"])
    args = parser.parse_args()
    {"up": up, "down": down, "status": status}[args.action]()


if __name__ == "__main__":
    main()
