"""
Runs CCD for scenario 3 (third degraded mode) of the illustrative example system.

Usage: python run_scenario_3.py [m]     # m = number of application servers (default 10)
"""

from __future__ import annotations
import sys
from ccd.util.scenario_util import run_scenario
from ccd.system.illustrative_example_system import IllustrativeExampleSystem


def main(m: int = 10) -> None:
    patched = {IllustrativeExampleSystem.E(i) for i in range(2, m + 2)}   # E_2..E_{m+1}
    system = IllustrativeExampleSystem(
        m, patched_exploits=frozenset(patched), attacker_evicted=True
    )
    run_scenario(
        system,
        title="Scenario 3: attacker evicted (P-tilde={P0}, E_1 patched) -- full restore (D_3)",
    )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
