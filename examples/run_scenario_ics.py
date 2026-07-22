"""
Runs CCD for the industrial control system (Tennessee Eastman) scenario (D_1: attack
detected).

The attacker has code execution on the enterprise web server and, via lateral movement,
on the supervisory control server; from there it can inject commands that drive the
chemical process toward unsafe conditions. CCD selects a degraded mode that contains the
attack while keeping web integrity and process safety above the critical level: drive the
web server to its safe state (W=0, blocking the web exploit and cutting W -> integrity from
the attacker), close the enterprise->supervisory gateway (G2=0, blocking lateral movement),
and switch the field controllers to local control (Chat=0, blocking command injection and
severing the attacker's commands from the process).

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
