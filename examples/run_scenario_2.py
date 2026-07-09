"""Scenario 2: operators have patched the exploits E_2..E_{m+1}.

This is the next step of the recovery sequence (D_1 -> D_2). With lateral movement and
DB-credential access patched, the attacker -- still on n_1 -- can no longer escalate
privileges, so CCD no longer needs to close the management links A_i or the DB link M_1.
It selects the strictly less restrictive mode do(N_1=0): the management network and
database link are restored, while n_1 remains isolated from the gateway to preserve the
throughput guarantee (the attacker can still drop requests on n_1).

Usage::

    python run_scenario_2.py [m]     # m = number of application servers (default 10)
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
