"""
Render the docker-compose file for the IT-system testbed at a given ``m``.

Usage: python generate_compose.py [--m 10] [--output ../docker/docker-compose.yml]
"""

from __future__ import annotations
import argparse
import os
import testbed_lib as tl

_DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "docker", "docker-compose.yml")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the IT-system testbed compose file.")
    parser.add_argument("--m", type=int, default=10, help="number of application servers")
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help="path to write docker-compose.yml")
    args = parser.parse_args()

    text = tl.generate_compose(args.m)
    with open(args.output, "w") as f:
        f.write(text)
    print(f"Wrote {os.path.abspath(args.output)} (m={args.m}).")


if __name__ == "__main__":
    main()
