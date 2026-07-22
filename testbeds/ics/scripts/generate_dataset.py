"""
Collect the nominal-operation dataset D on the running ICS testbed and save it as CSV.
Demand fluctuates per window and the operator variables toggle as regular operations
(mutually exclusive maintenance, more likely at low demand), providing both the
variability needed for causal inference and the confounding that biases the naive baseline.

Usage:
  python generate_dataset.py --out ../data/dataset.csv
  python generate_dataset.py --quick --out ../data/smoke.csv    # short smoke run
"""

from __future__ import annotations
import argparse
import csv
import os
import time
import ics_lib as il
import icsctl
from collection import WindowConfig, run_windows

_DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "data", "dataset.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect dataset D on the ICS testbed.")
    parser.add_argument("--out", default=_DEFAULT_OUT)
    parser.add_argument("--windows", type=int, default=600)
    parser.add_argument("--window-seconds", type=float, default=6.0)
    parser.add_argument("--settle-seconds", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--quick", action="store_true", help="short smoke run (40 windows)")
    args = parser.parse_args()

    windows = 40 if args.quick else args.windows
    config = WindowConfig(
        windows=windows, window_seconds=args.window_seconds,
        settle_seconds=args.settle_seconds, seed=args.seed,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    columns = il.dataset_columns()
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()

        def _write(row: dict) -> None:
            writer.writerow(row)
            f.flush()

        start = time.time()
        data = run_windows(config, on_row=_write)

    icsctl.reset()
    print(f"\nWrote {len(data)} rows to {os.path.abspath(args.out)} "
          f"in {time.time() - start:.0f}s "
          f"(mean I={data['I'].mean():.1f}, S={data['S'].mean():.1f}).")


if __name__ == "__main__":
    main()
