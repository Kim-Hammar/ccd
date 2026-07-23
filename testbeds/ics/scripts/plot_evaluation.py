"""
Grouped bar plot of the ICS-testbed evaluation: measured vs CCD-inferred functionality
per recovery mode (nominal, D_1, D_2, D_3) plus two model-derived baselines, as % of
nominal Phi = E{I} + E{S} (bar labels also carry the absolute Phi).

Inputs (produced by run_ccd.py and validate_phi.py): ``eval_d{1,2,3}.json`` (inferred
``phi``, with Phi_nominal = 2*alpha) and ``validation_{nominal,d1,d2,d3}.csv``
(per-window measurements; measured Phi = mean of I + S, 95% CI from the window std).
Baselines (inferred group only -- the attacker software is not implemented): "attack" =
no degradation, full propagation (field controllers compromised -> TE safety shutdown
S = 0, web server attacker-controlled -> I = 0, so Phi = 0); "containment" = naive
containment applying all blocking-edge closures do(W=0, G2=0, Chat=0) regardless of
functionality -- identical to D_1 here, so its Phi-hat is read from ``eval_d1.json``.
Outputs ``evaluation_barplot.png`` and a pgfplots table ``evaluation_barplot.tex``.

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
from ccd.system.ics_testbed_system import IcsTestbedSystem

_MODES = ["nominal", "d1", "d2", "d3"]
_INFERRED_MODES = ["nominal", "attack", "containment", "d1", "d2", "d3"]
_MODE_LABELS = {"nominal": "Nominal", "attack": "Attack", "containment": "Contain",
                "d1": "$D_1$", "d2": "$D_2$", "d3": "$D_3$"}
# validated categorical palette (dataviz reference), one hue per mode in fixed order;
# the baselines wear grays so the mode palette stays reserved
_MODE_COLORS = {"nominal": "#2a78d6", "attack": "#4a4a4a", "containment": "#999999",
                "d1": "#eb6834", "d2": "#1baf7a", "d3": "#eda100"}

# model worst case: full propagation reaches the field controllers (P4) -> direct valve
# manipulation drives the TE process to its safety shutdown (S = 0), and the web server
# is attacker-controlled (I = 0), so Phi = E{I} + E{S} = 0
_PHI_ATTACK = 0.0


def load_inferred(data_dir: str) -> Tuple[Dict[str, float], float]:
    """Inferred Phi-hat per mode and Phi_nominal = 2*alpha from the result JSONs.
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
    """Measured (mean, 95% CI half-width) of Phi = sum_c w_c * c per mode's validation run."""
    weights = IcsTestbedSystem().functionality_weights
    measured: Dict[str, Tuple[float, float]] = {}
    for mode in _MODES:
        data = pd.read_csv(os.path.join(data_dir, f"validation_{mode}.csv"))
        phi = sum(w * data[col] for col, w in weights.items() if col in data.columns)
        values = np.asarray(phi, dtype=float)
        measured[mode] = (float(values.mean()),
                          float(1.96 * values.std(ddof=1) / np.sqrt(len(values))))
    return measured


def plot(measured_pct: Dict[str, Tuple[float, float]], measured: Dict[str, Tuple[float, float]],
         inferred_pct: Dict[str, float], inferred: Dict[str, float], title: str,
         path: str) -> None:
    """Two bar groups (measured: the modes | inferred: baselines + modes), y = % of
    nominal Phi; each bar labeled with the % and the absolute Phi."""
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    width, gap = 0.8, 1.2   # bar width and spacing between the two groups
    positions_measured = np.arange(len(_MODES), dtype=float)
    positions_inferred = positions_measured[-1] + gap + 1 + np.arange(len(_INFERRED_MODES))

    def annotate(pos: float, top: float, pct: float, absolute: float) -> None:
        ax.text(pos, top + 8.5, f"{pct:.1f}", ha="center", fontsize=9)
        ax.text(pos, top + 2.5, f"({absolute:.1f})", ha="center", fontsize=7, color="#555555")

    for pos, mode in zip(positions_measured, _MODES):
        mean, ci = measured_pct[mode]
        ax.bar(pos, mean, width, color=_MODE_COLORS[mode], yerr=ci, capsize=3,
               error_kw={"elinewidth": 1.0, "ecolor": "#333333"})
        annotate(pos, mean + max(ci, 1.0), mean, measured[mode][0])
    for pos, mode in zip(positions_inferred, _INFERRED_MODES):
        ax.bar(pos, inferred_pct[mode], width, color=_MODE_COLORS[mode])
        annotate(pos, inferred_pct[mode], inferred_pct[mode], inferred[mode])

    ax.axhline(50.0, linestyle="--", linewidth=1.0, color="#666666")
    ax.text(positions_inferred[-1] + 0.55, 50.0, r"$\alpha$", va="center", fontsize=11)
    all_positions = np.concatenate([positions_measured, positions_inferred])
    ax.set_xticks(all_positions)
    ax.set_xticklabels([_MODE_LABELS[m] for m in _MODES]
                       + [_MODE_LABELS[m] for m in _INFERRED_MODES])
    group_centers = [positions_measured.mean(), positions_inferred.mean()]
    for center, label in zip(group_centers, ["Measured (testbed)", "Inferred ($\\hat{\\Phi}$)"]):
        ax.text(center, -0.14, label, ha="center", fontsize=11,
                transform=ax.get_xaxis_transform())
    ax.set_ylabel("Functionality (% of nominal)")
    ymax = max(mean + ci for mean, ci in measured_pct.values())
    ax.set_ylim(0, max(118.0, ymax + 16.0))
    ax.yaxis.grid(True, linewidth=0.5, alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.set_title(title)
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.18)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot to {path}")


def write_pgf_table(measured_pct: Dict[str, Tuple[float, float]],
                    measured: Dict[str, Tuple[float, float]],
                    inferred_pct: Dict[str, float], inferred: Dict[str, float],
                    macro: str, comment: str, path: str) -> None:
    """pgfplots table, one row per mode: measured/inferred as % of nominal and as
    absolute Phi (``*phi`` columns); baselines have no measurement (``nan``)."""
    lines = [
        comment,
        "% measured/inferred in % of nominal; measuredphi/inferredphi = absolute Phi;",
        "% ci = 95% half-width. attack/containment are model-derived baselines",
        "% (inferred only -- the attacker software is not implemented): nan measured.",
        "\\pgfplotstableread{",
        "mode measured ci inferred measuredphi ciphi inferredphi",
    ]
    for mode in _INFERRED_MODES:
        label = _MODE_LABELS[mode].replace(" ", "")
        if mode in measured_pct:
            mean, ci = measured_pct[mode]
            mean_abs, ci_abs = measured[mode]
            lines.append(f"{label} {mean:.2f} {ci:.2f} {inferred_pct[mode]:.2f} "
                         f"{mean_abs:.2f} {ci_abs:.2f} {inferred[mode]:.2f}")
        else:
            lines.append(f"{label} nan nan {inferred_pct[mode]:.2f} "
                         f"nan nan {inferred[mode]:.2f}")
    lines.append(f"}}{macro}")
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
    inferred["attack"] = _PHI_ATTACK
    # naive containment do(W=0, G2=0, Chat=0) is identical to D_1 for the ICS
    inferred["containment"] = inferred["d1"]
    measured = load_measured(args.data_dir)
    measured_nominal = measured["nominal"][0]
    measured_pct = {m: (mean / measured_nominal * 100.0, ci / measured_nominal * 100.0)
                    for m, (mean, ci) in measured.items()}
    inferred_pct = {m: phi / phi_nominal * 100.0 for m, phi in inferred.items()}

    for mode in _INFERRED_MODES:
        if mode in measured_pct:
            mean, ci = measured_pct[mode]
            measured_txt = f"measured {mean:6.1f} +- {ci:.1f} % ({measured[mode][0]:6.1f})"
        else:
            measured_txt = "measured    n/a              "
        print(f"{_MODE_LABELS[mode]:>8}: {measured_txt}   "
              f"inferred {inferred_pct[mode]:6.1f} % ({inferred[mode]:6.1f})")
    plot(measured_pct, measured, inferred_pct, inferred,
         "ICS (Tennessee Eastman): functionality per recovery mode",
         os.path.join(args.out_dir, "evaluation_barplot.png"))
    write_pgf_table(
        measured_pct, measured, inferred_pct, inferred, "\\ccdicsevaluation",
        "% ICS-testbed evaluation: functionality per recovery mode (Phi = E{I} + E{S}).",
        os.path.join(args.out_dir, "evaluation_barplot.tex"))


if __name__ == "__main__":
    main()
