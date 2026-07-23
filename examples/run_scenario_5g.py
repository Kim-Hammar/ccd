"""
Runs CCD for the 5G cloud-RAN scenario (D_1: attack detected). The attacker holds CU_3
and DU_1 UEs in 5QI classes 1-3; CCD selects do(AT3=1, E2=0, NG3=0, QI1=4).

Usage: python run_scenario_5g.py [steps]     # nominal-operation steps (default 6000)
"""

from __future__ import annotations
import sys
from ccd.util.scenario_util import run_scenario
from ccd.system.five_g_system import FiveGSystem


def main(steps: int = 6000) -> None:
    system = FiveGSystem()
    run_scenario(
        system,
        title="Scenario (5G): attack detected -- containment mode (D_1)",
        steps=steps,
        unit="Mbit/s",
    )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6000)
