"""
Runs CCD for scenario 1 of the illustrative example system.

Usage: python run_scenario_1.py [m]     # m = number of application servers (default 10)
"""

from __future__ import annotations

import sys

from ccd.util.scenario_util import run_scenario
from ccd.system.illustrative_example_system import IllustrativeExampleSystem


def main(m: int = 10) -> None:
    system = IllustrativeExampleSystem(m)
    run_scenario(system, title="Scenario 1: attack detected -- containment mode (D_1)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
