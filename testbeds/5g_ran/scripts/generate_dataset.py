"""
Collect the nominal-operation dataset D on the running 5G RAN testbed and save it as
CSV. Demand fluctuates per window and the operator variables toggle as regular
operations, providing both the variability needed for causal inference and the
confounding that biases the naive baseline.

Usage:
  python generate_dataset.py --out ../data/dataset.csv
  python generate_dataset.py --quick --out ../data/quick.csv    # ~8 min quick test run
"""

from __future__ import annotations
import argparse
import csv
import os
import time
import ran_lib as rl
import ranctl
from collection import WindowConfig, run_windows

_DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "data", "dataset.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect dataset D on the 5G RAN testbed.")
    parser.add_argument("--out", default=_DEFAULT_OUT)
    parser.add_argument("--windows", type=int, default=600)
    parser.add_argument("--window-seconds", type=float, default=6.0)
    parser.add_argument("--settle-seconds", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--quick", action="store_true", help="short test run (36 windows)")
    args = parser.parse_args()

    windows = 36 if args.quick else args.windows
    config = WindowConfig(
        windows=windows, window_seconds=args.window_seconds,
        settle_seconds=args.settle_seconds, seed=args.seed,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    # crash-safe incremental CSV: write the header, then flush each accepted row
    columns = rl.dataset_columns()
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()

        def _write(row: dict) -> None:
            writer.writerow(row)
            f.flush()

        start = time.time()
        data = run_windows(config, on_row=_write)

    ranctl.reset()
    total = sum(data[f"T_{i}_{d}"].mean() for i in range(1, rl.NUM_DU + 1) for d in rl.DIRECTIONS)
    print(f"\nWrote {len(data)} rows to {os.path.abspath(args.out)} "
          f"in {time.time() - start:.0f}s (mean sum-T = {total:.2f} Mbit/s).")


if __name__ == "__main__":
    main()
