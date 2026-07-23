"""
Collect the nominal-operation dataset D on the running IT-system testbed and save it
as CSV. Workload fluctuates around 100 req/s and the operator links toggle as regular
operations (closures likelier at low load): the variability needed for causal
inference plus the confounding that biases the naive baseline.

Usage:
  python generate_dataset.py --m 10 --out ../data/dataset.csv
  python generate_dataset.py --m 3 --quick --out ../data/quick.csv   # ~5 min test run
"""

from __future__ import annotations
import argparse
import csv
import os
import time
import numpy as np
import testbed_lib as tl
import linkctl
import loadgen
from collection import WindowConfig, run_windows

_DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "data", "dataset.csv")


def _warmup(m: int, seconds: float = 30.0) -> None:
    """Drive nominal load briefly (discarded) so caches/pools settle before measuring."""
    import asyncio
    from aiohttp import ClientSession, ClientTimeout
    linkctl.reset(m)

    async def _go() -> None:
        url = f"http://localhost:{tl.GATEWAY_HOST_PORT}/work"
        async with ClientSession(timeout=ClientTimeout(total=2.0)) as session:
            await loadgen.drive(url, 100.0, seconds, np.random.RandomState(0), session=session)

    print(f"Warming up for {seconds:.0f}s...")
    asyncio.run(_go())


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect dataset D on the IT-system testbed.")
    parser.add_argument("--m", type=int, default=10)
    parser.add_argument("--out", default=_DEFAULT_OUT)
    parser.add_argument("--windows", type=int, default=600)
    parser.add_argument("--window-seconds", type=float, default=6.0)
    parser.add_argument("--settle-seconds", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--quick", action="store_true", help="short test run (40 windows)")
    args = parser.parse_args()

    windows = 40 if args.quick else args.windows
    config = WindowConfig(
        m=args.m, windows=windows, window_seconds=args.window_seconds,
        settle_seconds=args.settle_seconds, seed=args.seed,
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    _warmup(args.m)

    # crash-safe incremental CSV: write the header, then flush each accepted row
    columns = tl.dataset_columns(args.m)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()

        def _write(row: dict) -> None:
            writer.writerow(row)
            f.flush()

        start = time.time()
        data = run_windows(config, on_row=_write)

    linkctl.reset(args.m)
    print(f"\nWrote {len(data)} rows to {os.path.abspath(args.out)} "
          f"in {time.time() - start:.0f}s (mean T = {data['T'].mean():.1f} req/s).")


if __name__ == "__main__":
    main()
