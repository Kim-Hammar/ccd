"""Scenario 3: the attacker has been evicted from n_1 (e.g. by re-imaging it).

This is the final step of the recovery sequence (D_2 -> D_3). With the attacker's code
execution removed, the attacker-controlled set is empty (Y = {}), so nothing can reach
the throughput or the unattained privileges. CCD therefore selects the empty intervention
do() -- no links need to be closed and full functionality is restored.

Usage::

    python run_scenario_3.py [m]     # m = number of application servers (default 10)
"""

from __future__ import annotations

import sys

from ccd.scenario import run_scenario
from ccd.illustrative_example_system import IllustrativeExampleSystem


def main(m: int = 10) -> None:
    system = IllustrativeExampleSystem(m, attacker_evicted=True)
    run_scenario(system, title="Scenario 3: attacker evicted (Y={}) -- full restore (D_3)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
