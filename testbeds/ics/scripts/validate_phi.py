"""
Validate CCD's functionality estimate against the live ICS testbed: enact the selected
mode, run the window loop with its variables pinned (demand and the other variables
keep toggling nominally -- Phi-hat is an expectation over the nominal regime under
do(mode)), and report measured Phi = E{I} + E{S} against Phi-hat. The mode stays
enacted afterwards (it is the containment).

Usage:
  python validate_phi.py --result ../data/ccd_result.json [--windows 100 --seed 1]
"""

from __future__ import annotations
import argparse
import json
import os
import pandas as pd
import icsctl
from collection import WindowConfig, run_windows
from ccd.system.ics_testbed_system import IcsTestbedSystem
from ccd.util.inference_util import policy_phi

_DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "data", "validation.csv")


def measured_phi(data: pd.DataFrame, weights) -> pd.Series:
    """Per-window functionality: the weighted sum over the observed columns (Phi = I + S)."""
    total = pd.Series(0.0, index=data.index)
    for col, w in weights.items():
        if col in data.columns:
            total = total + w * data[col]
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Phi on the ICS testbed.")
    parser.add_argument("--result", required=True, help="ccd_result.json from run_ccd.py")
    parser.add_argument("--windows", type=int, default=100)
    parser.add_argument("--window-seconds", type=float, default=6.0)
    parser.add_argument("--settle-seconds", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default=_DEFAULT_OUT)
    args = parser.parse_args()

    with open(args.result) as f:
        result = json.load(f)
    mode = {v: int(x) for v, x in (result.get("intervention") or {}).items()}

    icsctl.apply(mode)     # enact the mode, then measure with it pinned
    config = WindowConfig(
        windows=args.windows, window_seconds=args.window_seconds,
        settle_seconds=args.settle_seconds, seed=args.seed,
    )
    data = run_windows(config, pinned=mode)
    icsctl.apply(mode)     # leave exactly the enacted mode in place

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    data.to_csv(args.out, index=False)

    system = IcsTestbedSystem()
    weights = system.functionality_weights
    phi_series = measured_phi(data, weights)
    # gateway policy terms (G2e has no physical counterpart, G2c is recorded as "G2"):
    # no matching data column, so they are added deterministically from the enacted mode
    missing = {c: w for c, w in weights.items() if c not in data.columns}
    measured = float(phi_series.mean()) + policy_phi(missing, mode)
    std = float(phi_series.std(ddof=1)) if len(data) > 1 else float("nan")
    phi_hat = float(result["phi"])
    alpha = float(result["alpha"])
    rel_err = abs(measured - phi_hat) / phi_hat if phi_hat else float("nan")

    print(f"\nScenario: {result['scenario']}   mode: "
          f"do({', '.join(f'{v}={mode[v]}' for v in sorted(mode)) or ''})")
    print(f"Measured functionality  Phi        = {measured:8.2f} +/- {std:.2f} "
          f"(std, n={len(data)})")
    print(f"CCD causal estimate     Phi-hat    = {phi_hat:8.2f}   (rel. error {rel_err:5.1%})")
    print(f"Critical level          alpha      = {alpha:8.2f}")
    print(f"Measured Phi {'>=' if measured >= alpha else '<'} alpha  ->  "
          f"{'meets' if measured >= alpha else 'below'} the critical level")
    print(f"Wrote validation windows to {os.path.abspath(args.out)}.")


if __name__ == "__main__":
    main()
