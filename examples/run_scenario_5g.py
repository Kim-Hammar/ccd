"""
Runs CCD for the 5G cloud radio access network scenario (D_1: attack detected).

The attacker holds CU_3 (code execution) and DU_1 UEs in 5QI classes 1-3. CCD selects a
degraded mode that contains the attack (blocks access to the near-RT RIC and the core)
while preserving critical throughput: reject the attacker's 5QI classes on DU_1
(QI1=4), close the CU_3 midhaul (NG3=0), close the E2 interface (blocks near-RT RIC
access), and re-attach DU_3 to a healthy CU (AT3).

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
