"""
Run CCD on a dataset collected from the ICS testbed and write the selected mode to
JSON for ``enact_mode.py`` / ``validate_phi.py``.

Usage:
  python run_ccd.py --data ../data/dataset.csv             # D_1 = do(W=0, G2=0, Chat=0)
  python run_ccd.py --data ../data/dataset.csv --patched   # D_2 = do(W=0, Chat=0)
  python run_ccd.py --data ../data/dataset.csv --evicted   # D_3 = do()
"""

from __future__ import annotations
import argparse
import json
import os
import pandas as pd
from ccd.system.ics_testbed_system import IcsTestbedSystem
from ccd.util.scenario_util import run_ccd_on_data

_DEFAULT_RESULT = os.path.join(os.path.dirname(__file__), "..", "data", "ccd_result.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CCD on an ICS-testbed dataset.")
    parser.add_argument("--data", required=True, help="collected dataset CSV")
    parser.add_argument("--num-samples", type=int, default=None)
    parser.add_argument("--result-out", default=_DEFAULT_RESULT)
    scenario_group = parser.add_mutually_exclusive_group()
    scenario_group.add_argument("--patched", action="store_true",
                                help="supervisory-net vulns patched (E2/E3 removed) -> D_2")
    scenario_group.add_argument("--evicted", action="store_true",
                                help="attacker evicted (E2/E3 patched + re-imaged hosts) -> D_3")
    args = parser.parse_args()

    data = pd.read_csv(args.data)
    if args.evicted:
        scenario = "D_3 (evicted)"
        system = IcsTestbedSystem(patched_exploits=frozenset({"E2", "E3"}), attacker_evicted=True)
    elif args.patched:
        scenario = "D_2 (patched)"
        system = IcsTestbedSystem(patched_exploits=frozenset({"E2", "E3"}))
    else:
        scenario = "D_1"
        system = IcsTestbedSystem()

    result = run_ccd_on_data(
        system, data,
        title=f"ICS (Tennessee Eastman) testbed -- CCD ({scenario})",
        num_samples=args.num_samples,
        unit="score",
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.result_out)), exist_ok=True)
    payload = {
        "scenario": scenario,
        "intervention": dict(result.intervention.variables) if result.intervention else None,
        "phi": result.phi,
        "alpha": result.alpha,
        "feasible": result.feasible,
        "data_path": os.path.abspath(args.data),
    }
    with open(args.result_out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote result to {os.path.abspath(args.result_out)}.")


if __name__ == "__main__":
    main()
