"""
Run CCD on a dataset collected from the ICS testbed and write the selected mode to
JSON for ``enact_mode.py`` / ``validate_phi.py``.

Usage:
  python run_ccd.py --data ../data/dataset.csv        # expect D_1 = do(W=0, G2=0, Chat=0)
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
    args = parser.parse_args()

    data = pd.read_csv(args.data)
    system = IcsTestbedSystem()

    result = run_ccd_on_data(
        system, data,
        title="ICS (Tennessee Eastman) testbed -- CCD (D_1)",
        num_samples=args.num_samples,
        unit="score",
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.result_out)), exist_ok=True)
    payload = {
        "scenario": "D_1",
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
