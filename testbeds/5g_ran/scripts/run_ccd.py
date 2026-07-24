"""
Run CCD on a dataset collected from the 5G cloud-RAN testbed and save the selected mode.

Builds the ``FiveGTestbedSystem`` two-layer model, runs CCD on the saved CSV, prints the
standard report, and writes the selected mode to JSON for ``enact_mode.py`` /
``validate_phi.py``.

Usage:
  python run_ccd.py --data ../data/dataset.csv             # D_1 = do(AT3=1,E2=0,NG3=0,QI1=4)
  python run_ccd.py --data ../data/dataset.csv --patched   # D_2 = do(AT3=1,NG3=0,QI1=4)
  python run_ccd.py --data ../data/dataset.csv --evicted   # D_3 = do()
"""

from __future__ import annotations
import argparse
import json
import os
import pandas as pd
from ccd.system.five_g_testbed_system import FiveGTestbedSystem
from ccd.util.scenario_util import run_ccd_on_data

_DEFAULT_RESULT = os.path.join(os.path.dirname(__file__), "..", "data", "ccd_result.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CCD on a 5G-testbed dataset.")
    parser.add_argument("--data", required=True, help="collected dataset CSV")
    parser.add_argument("--num-samples", type=int, default=None)
    parser.add_argument("--result-out", default=_DEFAULT_RESULT)
    scenario_group = parser.add_mutually_exclusive_group()
    scenario_group.add_argument("--patched", action="store_true",
                                help="near-RT RIC / AMF exploits patched (EX3/EX4 removed) -> D_2")
    scenario_group.add_argument("--evicted", action="store_true",
                                help="attacker evicted (EX3/EX4 patched + RU_1/CU_3 re-imaged) -> D_3")
    args = parser.parse_args()

    data = pd.read_csv(args.data)
    if args.evicted:
        scenario = "D_3 (evicted)"
        system = FiveGTestbedSystem(patched_exploits=frozenset({"EX3", "EX4"}), attacker_evicted=True)
    elif args.patched:
        scenario = "D_2 (patched)"
        system = FiveGTestbedSystem(patched_exploits=frozenset({"EX3", "EX4"}))
    else:
        scenario = "D_1"
        system = FiveGTestbedSystem()

    result = run_ccd_on_data(
        system, data,
        title=f"5G cloud-RAN testbed -- CCD ({scenario})",
        num_samples=args.num_samples,
        unit="Mbit/s",
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
