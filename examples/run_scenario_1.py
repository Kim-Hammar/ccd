"""
Runs CCD for scenario 1 of the IT system.
"""

from __future__ import annotations
import sys
from ccd.util.scenario_util import run_scenario
from ccd.system.it_system import ITSystem


def main(m: int = 10) -> None:
    system = ITSystem(m)
    run_scenario(system, title="Scenario 1: attack detected -- containment mode (D_1)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
