"""
Validate CCD's functionality estimate against the live testbed: enact the selected
mode, run the window loop with the mode's links pinned closed (workload and the other
links keep toggling nominally -- Phi-hat = E[T | do(mode)] is an expectation over the
nominal regime), and report measured Phi against Phi-hat.

Usage:
  python validate_phi.py --result ../data/ccd_result.json [--windows 100 --seed 1]
"""

from __future__ import annotations
import argparse
import json
import math
import os
import linkctl
from collection import WindowConfig, run_windows

_DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "data", "validation.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Phi on the testbed.")
    parser.add_argument("--result", required=True, help="ccd_result.json from run_ccd.py")
    parser.add_argument("--windows", type=int, default=100)
    parser.add_argument("--window-seconds", type=float, default=6.0)
    parser.add_argument("--settle-seconds", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default=_DEFAULT_OUT)
    args = parser.parse_args()

    with open(args.result) as f:
        result = json.load(f)
    m = int(result["m"])
    mode = result.get("intervention") or {}
    pinned = {v: int(x) for v, x in mode.items()}

    # enact the mode, then measure with those links pinned and the rest toggling nominally
    linkctl.reset(m)
    if pinned:
        linkctl.apply(pinned, m)
    config = WindowConfig(
        m=m, windows=args.windows, window_seconds=args.window_seconds,
        settle_seconds=args.settle_seconds, seed=args.seed,
    )
    data = run_windows(config, pinned=pinned)
    linkctl.reset(m)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    data.to_csv(args.out, index=False)

    phi_hat = float(result["phi"])
    alpha = float(result["alpha"])
    measured = float(data["T"].mean())
    stderr = float(data["T"].std(ddof=1) / math.sqrt(len(data))) if len(data) > 1 else float("nan")
    rel_err = abs(measured - phi_hat) / phi_hat if phi_hat else float("nan")

    print(f"\nScenario: {result['scenario']}   mode: do({', '.join(sorted(pinned)) or ''})")
    print(f"Measured functionality  Phi        = {measured:8.2f} +/- {1.96 * stderr:.2f} req/s "
          f"(95% CI, n={len(data)})")
    print(f"CCD causal estimate     Phi-hat    = {phi_hat:8.2f} req/s   (rel. error {rel_err:5.1%})")
    print(f"Critical level          alpha      = {alpha:8.2f} req/s")
    print(f"Measured Phi {'>=' if measured >= alpha else '<'} alpha  ->  "
          f"{'meets' if measured >= alpha else 'below'} the critical level")
    print(f"Wrote validation windows to {os.path.abspath(args.out)}.")


if __name__ == "__main__":
    main()
