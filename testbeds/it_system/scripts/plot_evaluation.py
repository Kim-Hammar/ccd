"""
Grouped bar plot of the IT-testbed evaluation: measured vs CCD-inferred functionality
per recovery mode (nominal, D_1, D_2, D_3), as % of nominal Phi.

Inputs (produced by run_ccd.py and validate_phi.py): ``eval_d{1,2,3}.json`` (inferred
``phi``, with Phi_nominal = 2*alpha) and ``validation_{nominal,d1,d2,d3}.csv`` (per-window
measurements; measured Phi = mean of ``T``, 95% CI from the window std). Outputs
``evaluation_barplot.png`` and a pgfplots table ``evaluation_barplot.tex``.

Usage:
  python plot_evaluation.py                 # reads ../data, writes ../evaluation
"""

from __future__ import annotations
import argparse
import json
import os
from typing import Dict, Tuple
import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_MODES = ["nominal", "d1", "d2", "d3"]
_MODE_LABELS = {"nominal": "Nominal", "d1": "$D_1$", "d2": "$D_2$", "d3": "$D_3$"}
# validated categorical palette (dataviz reference), one hue per mode in fixed order
_MODE_COLORS = {"nominal": "#2a78d6", "d1": "#eb6834", "d2": "#1baf7a", "d3": "#eda100"}


def load_inferred(data_dir: str) -> Tuple[Dict[str, float], float]:
    """Inferred Phi-hat per mode (req/s) and Phi_nominal = 2*alpha from the result JSONs.
    The nominal 'estimate' is Phi_nominal itself (the dataset mean CCD normalizes by)."""
    inferred: Dict[str, float] = {}
    phi_nominal = 0.0
    for mode in ("d1", "d2", "d3"):
        with open(os.path.join(data_dir, f"eval_{mode}.json")) as f:
            result = json.load(f)
        inferred[mode] = float(result["phi"])
        phi_nominal = 2.0 * float(result["alpha"])
    inferred["nominal"] = phi_nominal
    return inferred, phi_nominal


def load_measured(data_dir: str) -> Dict[str, Tuple[float, float]]:
    """Measured (mean, 95% CI half-width) of T in req/s per mode's validation run."""
    measured: Dict[str, Tuple[float, float]] = {}
    for mode in _MODES:
        data = pd.read_csv(os.path.join(data_dir, f"validation_{mode}.csv"))
        t = data["T"].to_numpy(dtype=float)
        measured[mode] = (float(t.mean()), float(1.96 * t.std(ddof=1) / np.sqrt(len(t))))
    return measured


def plot(measured_pct: Dict[str, Tuple[float, float]], inferred_pct: Dict[str, float],
         path: str) -> None:
    """Two bar groups (measured | inferred), one bar per mode, y = % of nominal Phi."""
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    width, gap = 0.8, 1.2   # bar width and spacing between the two groups
    positions_measured = np.arange(len(_MODES), dtype=float)
    positions_inferred = positions_measured + len(_MODES) - 1 + gap + 1

    for pos, mode in zip(positions_measured, _MODES):
        mean, ci = measured_pct[mode]
        ax.bar(pos, mean, width, color=_MODE_COLORS[mode], yerr=ci, capsize=3,
               error_kw={"elinewidth": 1.0, "ecolor": "#333333"})
        ax.text(pos, mean + max(ci, 1.0) + 1.5, f"{mean:.1f}", ha="center", fontsize=9)
    for pos, mode in zip(positions_inferred, _MODES):
        value = inferred_pct[mode]
        ax.bar(pos, value, width, color=_MODE_COLORS[mode])
        ax.text(pos, value + 1.5, f"{value:.1f}", ha="center", fontsize=9)

    ax.axhline(50.0, linestyle="--", linewidth=1.0, color="#666666")
    ax.text(positions_inferred[-1] + 0.55, 50.0, r"$\alpha$", va="center", fontsize=11)
    all_positions = np.concatenate([positions_measured, positions_inferred])
    ax.set_xticks(all_positions)
    ax.set_xticklabels([_MODE_LABELS[m] for m in _MODES] * 2)
    group_centers = [positions_measured.mean(), positions_inferred.mean()]
    for center, label in zip(group_centers, ["Measured (testbed)", "Inferred ($\\hat{\\Phi}$)"]):
        ax.text(center, -0.14, label, ha="center", fontsize=11,
                transform=ax.get_xaxis_transform())
    ax.set_ylabel("Functionality (% of nominal)")
    ymax = max(mean + ci for mean, ci in measured_pct.values())
    ax.set_ylim(0, max(112.0, ymax + 10.0))
    ax.yaxis.grid(True, linewidth=0.5, alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.set_title("IT system: functionality per recovery mode")
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.18)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot to {path}")


def write_pgf_table(measured_pct: Dict[str, Tuple[float, float]],
                    inferred_pct: Dict[str, float], path: str) -> None:
    """pgfplots table: one row per mode with measured %, 95% CI half-width, inferred %."""
    lines = [
        "% IT-testbed evaluation: functionality per recovery mode, % of nominal Phi.",
        "% measured = live testbed (mean of T over 100 windows), ci = 95% half-width,",
        "% inferred = CCD's causal estimate Phi-hat from the nominal dataset.",
        "\\pgfplotstableread{",
        "mode measured ci inferred",
    ]
    for mode in _MODES:
        mean, ci = measured_pct[mode]
        lines.append(f"{_MODE_LABELS[mode].replace(' ', '')} {mean:.2f} {ci:.2f} "
                     f"{inferred_pct[mode]:.2f}")
    lines.append("}\\ccditevaluation")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved pgfplots table to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot measured vs inferred Phi per mode.")
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    parser.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "..", "evaluation"))
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    inferred, phi_nominal = load_inferred(args.data_dir)
    measured = load_measured(args.data_dir)
    measured_nominal = measured["nominal"][0]
    measured_pct = {m: (mean / measured_nominal * 100.0, ci / measured_nominal * 100.0)
                    for m, (mean, ci) in measured.items()}
    inferred_pct = {m: phi / phi_nominal * 100.0 for m, phi in inferred.items()}

    for mode in _MODES:
        mean, ci = measured_pct[mode]
        print(f"{_MODE_LABELS[mode]:>8}: measured {mean:6.1f} +- {ci:.1f} %   "
              f"inferred {inferred_pct[mode]:6.1f} %")
    plot(measured_pct, inferred_pct, os.path.join(args.out_dir, "evaluation_barplot.png"))
    write_pgf_table(measured_pct, inferred_pct,
                    os.path.join(args.out_dir, "evaluation_barplot.tex"))


if __name__ == "__main__":
    main()
