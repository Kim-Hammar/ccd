"""Scenario 1: an attack has just been detected on the illustrative example.

The attacker holds code execution on n_1 and the lateral-movement / DB-credential
exploits E_2..E_{m+1} are still available. CCD selects the containment mode D_1 that
isolates n_1 (closes the gateway link N_1, the DB link M_1, and every management link
A_i) while preserving throughput.

Usage::

    python run_scenario_1.py [m]     # m = number of application servers (default 10)
"""

from __future__ import annotations

import sys

from ccd.scenario import run_scenario
from ccd.system import SystemModel


def main(m: int = 10) -> None:
    system = SystemModel(m)
    run_scenario(system, title="Scenario 1: attack detected -- containment mode (D_1)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
