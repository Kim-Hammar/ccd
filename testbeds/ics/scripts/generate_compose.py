"""
Generate ``docker/docker-compose.yml`` for the ICS testbed (web + scada + control +
process on an enterprise and a plant network). The compose is rendered from the pure
``ics_lib.generate_compose`` template and is gitignored (regenerate on a fresh checkout).

Usage:
  python generate_compose.py
"""

from __future__ import annotations
import os
import ics_lib as il

_COMPOSE = os.path.join(os.path.dirname(__file__), "..", "docker", "docker-compose.yml")


def main() -> None:
    with open(_COMPOSE, "w") as f:
        f.write(il.generate_compose())
    print(f"Generated {os.path.abspath(_COMPOSE)}")


if __name__ == "__main__":
    main()
