"""
Grouped bar plot of the IT-testbed evaluation: measured vs CCD-inferred functionality
per recovery mode (nominal, D_1, D_2, D_3) plus two model-derived baselines, as % of
nominal Phi (bar labels also carry the absolute Phi).

Functionality is Phi(M) = E{T} + kappa * sum_{i=2}^m A_i (throughput plus the
availability of the management network, kappa = 2): the throughput part comes from the
recorded experiments, and the management term is exact per mode (each mode's
intervention pins the A_i; the nominal regime never closes them), so no experiment is
re-run and the throughputs are reported unchanged in separate ``*thr`` columns.

Inputs (produced by run_ccd.py and validate_phi.py): ``eval_d{1,2,3}.json`` (inferred
throughput ``phi``, with E{T}_nominal = 2*alpha) and ``validation_{nominal,d1,d2,d3}.csv``
(per-window measurements; measured throughput = mean of ``T``, 95% CI from the window
std). Baselines (inferred group only -- the attacker software is not implemented, so
neither can be measured): "attack" = no degradation, full propagation (T = 0 by the
known functions; the management links stay open, so Phi = kappa*(m-1)); "containment" =
naive containment applying all blocking-edge closures do(M1=0, A2..A10=0) regardless of
functionality, with the throughput estimated from the nominal dataset (cached to
``baseline_containment.json``). Outputs ``evaluation_barplot.png`` and the per-mode data
as ``evaluation_barplot.csv``.

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
_INFERRED_MODES = ["nominal", "attack", "containment", "d1", "d2", "d3"]
_MODE_LABELS = {"nominal": "Nominal", "attack": "Attack", "containment": "Contain",
                "d1": "$D_1$", "d2": "$D_2$", "d3": "$D_3$"}
# validated categorical palette (dataviz reference), one hue per mode in fixed order;
# the baselines wear grays so the mode palette stays reserved
_MODE_COLORS = {"nominal": "#2a78d6", "attack": "#4a4a4a", "containment": "#999999",
                "d1": "#eb6834", "d2": "#1baf7a", "d3": "#eda100"}

# model worst case: full propagation grants every P_i and the attacker zeroes all
# carried loads T-tilde_i, so T = sum_i N_i * T-tilde_i = 0 exactly (known functions
# F-tilde); the operator closes nothing, so the management links stay open and the
# attack baseline keeps the kappa-term: Phi_attack = kappa * (m - 1)
_CONTAINMENT_CACHE = "baseline_containment.json"
# Phi(M) = E{T} + kappa * sum_{i=2}^m A_i: value of the management functions per link
_KAPPA = 2.0


def management_bonus(intervention: Dict[str, int], m: int) -> float:
    """kappa * (number of open management links A_2..A_m under ``intervention``)."""
    closed = sum(1 for var, value in intervention.items()
                 if var.startswith("A") and value == 0)
    return _KAPPA * (m - 1 - closed)


def containment_phi(data_dir: str, m: int, data_path: str) -> float:
    """Phi-hat of the naive-containment baseline do(M1=0, A2..A10=0) (all blocking-edge
    closures, ignoring functionality), estimated from the nominal dataset and cached.
    Only M1 has causal edges, so the estimate conditions on do(M1=0)."""
    cache_path = os.path.join(data_dir, _CONTAINMENT_CACHE)
    if os.path.isfile(cache_path):
        with open(cache_path) as f:
            return float(json.load(f)["phi"])
    from ccd.system.it_testbed_system import ITTestbedSystem
    from ccd.util.inference_util import estimate_phi
    system = ITTestbedSystem(m=m)
    data = pd.read_csv(data_path)
    phi = estimate_phi(
        data, system.throughput_graph(), {"M1": 0},
        weights=system.functionality_weights,
        product_functions=system.product_functions if system.use_known_product_mechanisms else None,
    )
    intervention = {"M1": 0} | {f"A{i}": 0 for i in range(2, m + 1)}
    with open(cache_path, "w") as f:
        json.dump({"scenario": "containment baseline", "intervention": intervention,
                   "phi": phi, "data_path": data_path}, f, indent=2)
    return float(phi)


def load_inferred(data_dir: str) -> Tuple[Dict[str, float], float, Dict[str, Dict[str, int]]]:
    """Inferred throughput per mode (req/s), the nominal throughput E{T} = 2*alpha, and
    each mode's intervention from the result JSONs."""
    inferred: Dict[str, float] = {}
    interventions: Dict[str, Dict[str, int]] = {"nominal": {}}
    thr_nominal = 0.0
    for mode in ("d1", "d2", "d3"):
        with open(os.path.join(data_dir, f"eval_{mode}.json")) as f:
            result = json.load(f)
        inferred[mode] = float(result["phi"])
        interventions[mode] = dict(result["intervention"] or {})
        thr_nominal = 2.0 * float(result["alpha"])
    inferred["nominal"] = thr_nominal
    return inferred, thr_nominal, interventions


def load_measured(data_dir: str) -> Dict[str, Tuple[float, float]]:
    """Measured (mean, 95% CI half-width) of T in req/s per mode's validation run."""
    measured: Dict[str, Tuple[float, float]] = {}
    for mode in _MODES:
        data = pd.read_csv(os.path.join(data_dir, f"validation_{mode}.csv"))
        t = data["T"].to_numpy(dtype=float)
        measured[mode] = (float(t.mean()), float(1.96 * t.std(ddof=1) / np.sqrt(len(t))))
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


def write_csv(measured_pct: Dict[str, Tuple[float, float]],
              measured_thr: Dict[str, Tuple[float, float]],
              measured_phi: Dict[str, Tuple[float, float]],
              inferred_pct: Dict[str, float], inferred_thr: Dict[str, float],
              inferred_phi: Dict[str, float], path: str) -> None:
    """CSV, one row per mode: measured/inferred as % of nominal Phi, the raw throughput
    (``*thr``, req/s), and the absolute Phi = E{T} + kappa*sum A_i (``*phi``); ci is the
    95% half-width (the management term is exact per mode, so ciphi = cithr). The
    attack/containment baselines are model-derived (inferred only), so their measured
    columns are ``nan``."""
    lines = ["mode,measured,ci,inferred,measured_thr,ci_thr,inferred_thr,"
             "measured_phi,ci_phi,inferred_phi"]
    for mode in _INFERRED_MODES:
        if mode in measured_pct:
            mean, ci = measured_pct[mode]
            thr, thr_ci = measured_thr[mode]
            phi, phi_ci = measured_phi[mode]
            lines.append(f"{mode},{mean:.2f},{ci:.2f},{inferred_pct[mode]:.2f},"
                         f"{thr:.2f},{thr_ci:.2f},{inferred_thr[mode]:.2f},"
                         f"{phi:.2f},{phi_ci:.2f},{inferred_phi[mode]:.2f}")
        else:
            lines.append(f"{mode},nan,nan,{inferred_pct[mode]:.2f},"
                         f"nan,nan,{inferred_thr[mode]:.2f},"
                         f"nan,nan,{inferred_phi[mode]:.2f}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved data to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot measured vs inferred Phi per mode.")
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    parser.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "..", "evaluation"))
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    inferred_thr, thr_nominal, interventions = load_inferred(args.data_dir)
    with open(os.path.join(args.data_dir, "eval_d1.json")) as f:
        d1 = json.load(f)
    m = int(d1["m"])
    inferred_thr["attack"] = 0.0
    inferred_thr["containment"] = containment_phi(args.data_dir, m, d1["data_path"])
    interventions["containment"] = {"M1": 0} | {f"A{i}": 0 for i in range(2, m + 1)}
    measured_thr = load_measured(args.data_dir)

    # Phi = E{T} + kappa * sum A_i; the management term is exact per mode (the attack
    # baseline closes nothing, so it keeps the full term despite T = 0)
    inferred_phi = {mode: thr + management_bonus(interventions.get(mode, {}), m)
                    for mode, thr in inferred_thr.items()}
    measured_phi = {mode: (thr + management_bonus(interventions[mode], m), ci)
                    for mode, (thr, ci) in measured_thr.items()}
    phi_nominal = inferred_phi["nominal"]
    measured_nominal = measured_phi["nominal"][0]
    measured_pct = {mode: (phi / measured_nominal * 100.0, ci / measured_nominal * 100.0)
                    for mode, (phi, ci) in measured_phi.items()}
    inferred_pct = {mode: phi / phi_nominal * 100.0 for mode, phi in inferred_phi.items()}

    for mode in _INFERRED_MODES:
        if mode in measured_pct:
            mean, ci = measured_pct[mode]
            measured_txt = (f"measured {mean:6.1f} +- {ci:.1f} % "
                            f"(phi {measured_phi[mode][0]:6.1f}, thr {measured_thr[mode][0]:6.1f})")
        else:
            measured_txt = "measured    n/a                            "
        print(f"{_MODE_LABELS[mode]:>8}: {measured_txt}   "
              f"inferred {inferred_pct[mode]:6.1f} % "
              f"(phi {inferred_phi[mode]:6.1f}, thr {inferred_thr[mode]:6.1f})")
    plot(measured_pct, measured_phi, inferred_pct, inferred_phi,
         "IT system: functionality per recovery mode",
         os.path.join(args.out_dir, "evaluation_barplot.png"))
    write_csv(
        measured_pct, measured_thr, measured_phi, inferred_pct, inferred_thr, inferred_phi,
        os.path.join(args.out_dir, "evaluation_barplot.csv"))


if __name__ == "__main__":
    main()
