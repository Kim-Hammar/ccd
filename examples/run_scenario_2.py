"""
Runs CCD for scenario 2 (second degraded mode) of the illustrative example system.

Usage: python run_scenario_2.py [m]     # m = number of application servers (default 10)
"""

from __future__ import annotations

import sys

from ccd.scenario import run_scenario
from ccd.illustrative_example_system import E, IllustrativeExampleSystem


def main(m: int = 10) -> None:
    patched = {E(i) for i in range(2, m + 2)}   # E_2..E_{m+1}
    system = IllustrativeExampleSystem(m, patched_exploits=frozenset(patched))
    result = run_scenario(
        system, title="Scenario 2: E_2..E_{m+1} patched -- recovery step (D_2)"
    )
    if result.intervention is not None:
        print("\nNote: vs Scenario 1 (D_1), the management links A_i and the DB link M_1 "
              "are no longer restricted -- only n_1's gateway link stays closed.")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
