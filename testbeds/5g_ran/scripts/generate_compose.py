"""
Generate the RAN half of the 4-DU/4-CU topology: ``docker/compose-ran.yml`` plus the
per-node configs under ``docker/gen/`` (one srscu, srsdu, and srsue config per CU/DU/UE).

The core is the fixed ``docker/compose-core.yml``; this renders only the RAN, on the
same ``ran`` network / ``ccd5g`` project, combined via ``docker compose -f ... -f ...``.
``--reattach i=j`` regenerates for a DU reattachment (e.g. ``3=1`` for D_1's ``AT3=1``);
only the DU config's F1 target and the compose ``depends_on`` change.

Usage:
  python generate_compose.py                    # nominal DU_i -> CU_i
  python generate_compose.py --reattach 3=1     # DU_3 -> CU_1
"""

from __future__ import annotations
import argparse
import os
from typing import Dict
import ran_lib as rl

_DOCKER_DIR = os.path.join(os.path.dirname(__file__), "..", "docker")
_GEN_DIR = os.path.join(_DOCKER_DIR, "gen")


def _parse_reattach(items: list[str]) -> Dict[int, int]:
    out: Dict[int, int] = {}
    for item in items:
        du, _, cu = item.partition("=")
        out[int(du)] = int(cu)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the 4-DU/4-CU RAN compose + configs.")
    parser.add_argument("--reattach", nargs="*", default=[], metavar="i=j",
                        help="reattach DU_i to CU_j (e.g. 3=1)")
    args = parser.parse_args()

    at_map = rl.attachment_map(_parse_reattach(args.reattach))
    os.makedirs(_GEN_DIR, exist_ok=True)

    for j in range(1, rl.NUM_CU + 1):
        _write(os.path.join(_GEN_DIR, f"cu{j}.yml"), rl.render_cu_config(j))
    for i in range(1, rl.NUM_DU + 1):
        _write(os.path.join(_GEN_DIR, f"du{i}.yml"), rl.render_du_config(i, at_map[i]))
        _write(os.path.join(_GEN_DIR, f"ue{i}.conf"), rl.render_ue_config(i))
    _write(os.path.join(_DOCKER_DIR, "compose-ran.yml"), rl.render_ran_compose(at_map))

    print(f"Generated compose-ran.yml + {2 * rl.NUM_DU + rl.NUM_CU} configs in {os.path.abspath(_GEN_DIR)}")
    print(f"Attachment map DU->CU: {at_map}")


def _write(path: str, text: str) -> None:
    with open(path, "w") as f:
        f.write(text)


if __name__ == "__main__":
    main()
