"""
Run CCD on a dataset collected from the IT-system testbed and save the selected mode.

Builds the ``ITTestbedSystem`` two-layer model for the given scenario (the containers
are unchanged across scenarios -- only the attack graph / detected privileges differ),
runs CCD on the saved CSV, prints the standard report, and writes the selected mode to
JSON for ``enact_mode.py`` / ``validate_phi.py``.

Usage:
  python run_ccd.py --data ../data/dataset.csv --m 10               # D_1 (containment)
  python run_ccd.py --data ../data/dataset.csv --m 10 --patched     # D_2
  python run_ccd.py --data ../data/dataset.csv --m 10 --evicted     # D_3
"""

from __future__ import annotations
import argparse
import json
import os
import pandas as pd
from ccd.system.illustrative_example_system import IllustrativeExampleSystem
from ccd.system.it_testbed_system import ITTestbedSystem
from ccd.util.scenario_util import run_ccd_on_data

_DEFAULT_RESULT = os.path.join(os.path.dirname(__file__), "..", "data", "ccd_result.json")


def build_system(m: int, patched: bool, evicted: bool) -> ITTestbedSystem:
    patched_exploits = frozenset(
        IllustrativeExampleSystem.E(i) for i in range(2, m + 2)
    ) if (patched or evicted) else frozenset()
    return ITTestbedSystem(m, patched_exploits=patched_exploits, attacker_evicted=evicted)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CCD on a testbed dataset.")
    parser.add_argument("--data", required=True, help="collected dataset CSV")
    parser.add_argument("--m", type=int, default=10)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--patched", action="store_true", help="scenario D_2 (E_2..E_{m+1} patched)")
    group.add_argument("--evicted", action="store_true", help="scenario D_3 (attacker evicted)")
    parser.add_argument("--num-samples", type=int, default=None)
    parser.add_argument("--result-out", default=_DEFAULT_RESULT)
    args = parser.parse_args()

    scenario = "D_2 (patched)" if args.patched else "D_3 (evicted)" if args.evicted else "D_1"
    data = pd.read_csv(args.data)
    system = build_system(args.m, args.patched, args.evicted)

    result = run_ccd_on_data(
        system, data,
        title=f"IT-system testbed -- CCD ({scenario})",
        num_samples=args.num_samples,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.result_out)), exist_ok=True)
    payload = {
        "m": args.m,
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
