"""
Runs CCD for the industrial control system (Tennessee Eastman) scenario (D_1: attack
detected). The attacker has code execution on the web server and the supervisory
control server; CCD selects do(W=0, G2=0, Chat=0).

Usage: python run_scenario_ics.py [steps]     # nominal-operation steps (default 6000)
"""

from __future__ import annotations
import sys
from ccd.util.scenario_util import run_scenario
from ccd.system.ics_system import IcsSystem


def main(steps: int = 6000) -> None:
    system = IcsSystem()
    run_scenario(
        system,
        title="Scenario (ICS): attack detected -- containment mode (D_1)",
        steps=steps,
        unit="score",
    )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6000)
