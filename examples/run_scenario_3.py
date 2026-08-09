"""
Runs CCD for scenario 3 (third degraded mode) of the IT system.
"""

from __future__ import annotations
import sys
from ccd.util.scenario_util import run_scenario
from ccd.system.it_system import ITSystem


def main(m: int = 10) -> None:
    patched = {ITSystem.E(i) for i in range(2, m + 2)}   # E_2..E_{m+1}
    system = ITSystem(
        m, patched_exploits=frozenset(patched), attacker_evicted=True
    )
    run_scenario(
        system,
        title="Scenario 3: attacker evicted (P-tilde={P0}, E_1 patched) -- full restore (D_3)",
    )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
