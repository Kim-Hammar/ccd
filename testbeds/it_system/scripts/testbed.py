"""
Lifecycle for the IT-system testbed. ``up`` regenerates the compose for ``m``, builds
and starts the containers, waits for health, and verifies the CCD iptables chains;
``down`` tears everything down; ``status`` prints container and link state.

Usage:
  python testbed.py up [--m 10]
  python testbed.py down
  python testbed.py status [--m 10]
"""

from __future__ import annotations
import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import testbed_lib as tl
import linkctl

_DOCKER_DIR = os.path.join(os.path.dirname(__file__), "..", "docker")
_COMPOSE = os.path.join(_DOCKER_DIR, "docker-compose.yml")


def _compose(*args: str) -> None:
    subprocess.run(["docker", "compose", "-f", _COMPOSE, *args], check=True)


def _get_json(url: str, timeout: float = 2.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _wait_healthy(m: int, timeout: float = 180.0) -> None:
    deadline = time.time() + timeout
    endpoints = [f"http://localhost:{tl.GATEWAY_HOST_PORT}/health"] + [
        f"http://localhost:{tl.SERVER_HOST_PORT_BASE + i}/health" for i in range(1, m + 1)
    ]
    for url in endpoints:
        while True:
            try:
                if _get_json(url).get("ok"):
                    break
            except (urllib.error.URLError, ConnectionError, OSError, ValueError):
                pass
            if time.time() > deadline:
                raise TimeoutError(f"timed out waiting for {url}")
            time.sleep(1.0)
    print(f"All {m} servers + gateway healthy.")


def up(m: int) -> None:
    from generate_compose import main as _  # noqa: F401  (keep import graph explicit)
    with open(_COMPOSE, "w") as f:
        f.write(tl.generate_compose(m))
    print(f"Generated compose for m={m}; building and starting...")
    _compose("up", "-d", "--build")
    _wait_healthy(m)
    linkctl.reset(m)   # start from all links open + verify the chains exist
    print("Testbed is up. All links open.")


def down() -> None:
    if os.path.exists(_COMPOSE):
        _compose("down", "-v")
    print("Testbed is down.")


def status(m: int) -> None:
    _compose("ps")
    print("\nLink state (CCD chains):")
    linkctl.status(m)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the IT-system testbed lifecycle.")
    parser.add_argument("action", choices=["up", "down", "status"])
    parser.add_argument("--m", type=int, default=10, help="number of application servers")
    args = parser.parse_args()

    if args.action == "up":
        up(args.m)
    elif args.action == "down":
        down()
    else:
        status(args.m)


if __name__ == "__main__":
    main()
