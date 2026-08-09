"""
Runs CCD for the 5G cloud-RAN scenario (D_1: attack detected).
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
