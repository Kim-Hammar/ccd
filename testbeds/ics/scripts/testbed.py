"""
Lifecycle for the ICS testbed: ``up`` / ``down`` / ``status``.

``up`` regenerates the compose, builds and starts the containers, waits for every service
to become healthy, and resets to nominal operation (gateway open, remote control, web up).

Usage:
  python testbed.py up
  python testbed.py status
  python testbed.py down
"""

from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
import ics_lib as il
import icsctl

_DOCKER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docker"))
_COMPOSE = os.path.join(_DOCKER_DIR, "docker-compose.yml")


def _compose(*args: str) -> None:
    subprocess.run(["docker", "compose", "-f", _COMPOSE, *args], cwd=_DOCKER_DIR, check=True)


def _wait_healthy(timeout: float = 240.0) -> None:
    deadline = time.time() + timeout
    targets = [il.WEB_CONTAINER, il.CONTROL_CONTAINER, il.PROCESS_CONTAINER]
    for container in targets:
        while True:
            try:
                out = subprocess.run(
                    ["docker", "exec", container, "curl", "-s",
                     f"http://localhost:{il.APP_PORT}/health"],
                    capture_output=True, text=True, timeout=5.0)
                if out.returncode == 0 and json.loads(out.stdout or "{}").get("ok"):
                    break
            except (subprocess.SubprocessError, ValueError, OSError):
                pass
            if time.time() > deadline:
                raise TimeoutError(f"timed out waiting for {container} to become healthy")
            time.sleep(2.0)
    print("web + control + process healthy.")


def up() -> None:
    if not os.path.exists(_COMPOSE):
        subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__),
                                                     "generate_compose.py")], check=True)
    _compose("up", "-d", "--build")
    _wait_healthy()
    icsctl.reset()
    print("Testbed is up. Gateway open, remote control, web up.")


def down() -> None:
    if os.path.exists(_COMPOSE):
        _compose("down", "-v")
    print("Testbed is down.")


def status() -> None:
    _compose("ps")
    print("\nService /metrics:")
    icsctl.status()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the ICS testbed lifecycle.")
    parser.add_argument("action", choices=["up", "down", "status"])
    args = parser.parse_args()
    {"up": up, "down": down, "status": status}[args.action]()


if __name__ == "__main__":
    main()
