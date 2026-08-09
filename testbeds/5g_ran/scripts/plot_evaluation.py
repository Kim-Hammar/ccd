"""
Grouped bar plot of the 5G cloud-RAN evaluation: CCD-inferred functionality per recovery
mode (nominal, D_1, D_2, D_3) plus two model-derived baselines, as % of nominal Phi.

Functionality is Phi(M) = sum_{i,d} E{T^i_d} + omega * (E2 + A1) with omega = 5 -- the
aggregate DU throughput plus the value of the near-RT (E2) and non-RT (A1) RIC control
interfaces. The inferred values come from the recorded CCD runs (eval_d{1,2,3}.json,
Phi computed with functionality_weights, so the stored ``phi`` already includes the
omega terms); the nominal Phi = alpha / 0.75 (the 5G essential level is
alpha = 0.75 * Phi(M)).

TESTBED MEASUREMENTS ARE PENDING: the live validation runs (validate_phi.py on the
srsRAN/Open5GS testbed) require the Linux RAN host, so only the inferred group is
plotted here and the measured columns of the CSV are ``nan``. Re-run this script after
copying back ``validation_{nominal,d1,d2,d3}.csv`` to fill the measured group.

Baselines (model-derived, inferred only): "attack" = no degradation, full propagation --
the attacker denies all DU throughput (sum E{T} = 0), but the operator applies no
degradation, so both RIC interfaces stay enabled and Phi = omega*(E2 + A1);
"containment" = naive block-every-vulnerability
containment do(E2=0, NG3=0, Uu_1=0): the blocking-set closures for EX3/EX4 (EX1/EX2/EX5
have no blocking edge) PLUS shutting the whole Uu radio of the compromised DU_1 -- lacking
CCD's surgical per-class admission control (QI1=6), naive containment can only cut DU_1's
attacker traffic by killing all of DU_1's throughput. Its throughput (DUs 2-4 only) is
estimated from the nominal dataset.

Usage:
  python plot_evaluation.py                 # reads ../data, writes ../evaluation
"""

from __future__ import annotations
import argparse
import json
import os
from typing import Dict, Optional, Tuple
import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_MODES = ["nominal", "d1", "d2", "d3"]
_INFERRED_MODES = ["nominal", "attack", "containment", "d1", "d2", "d3"]
_MODE_LABELS = {"nominal": "Nominal", "attack": "Attack", "containment": "Contain",
                "d1": "$D_1$", "d2": "$D_2$", "d3": "$D_3$"}
_MODE_COLORS = {"nominal": "#2a78d6", "attack": "#4a4a4a", "containment": "#999999",
                "d1": "#eb6834", "d2": "#1baf7a", "d3": "#eda100"}

_OMEGA = 5.0            # must match FiveGSystem.OMEGA
_ALPHA_FRACTION = 0.75  # must match FiveGSystem.alpha_fraction
_CONTAINMENT_CACHE = "baseline_containment.json"

# per-mode interventions (the recovery modes come from the CCD result JSONs; the
# baselines are model-derived). Attack: full propagation denies all DU throughput
# (sum E{T} = 0), but the operator applies no degradation, so both RIC interfaces
# stay enabled (E2, A1 at nominal availability) -> Phi_attack = omega*(E2 + A1).
# Containment: blocking-set closures + Uu_1=0 (shut DU_1's radio; naive containment has
# no per-class admission control, so it kills all of DU_1's throughput).
_INTERVENTIONS: Dict[str, Dict[str, int]] = {
    "nominal": {}, "attack": {}, "containment": {"E2": 0, "NG3": 0, "Uu1": 0},
}


def omega_term(intervention: Dict[str, int]) -> float:
    """omega * (E2 + A1) under the mode, at binary policy values: a pinned interface
    contributes 0, an open one its nominal policy value 1. Deterministic and exact
    (variations observed in D belong to the collection regime)."""
    e2 = 0.0 if intervention.get("E2") == 0 else 1.0
    a1 = 0.0 if intervention.get("A1") == 0 else 1.0
    return _OMEGA * (e2 + a1)


def containment_phi(data_dir: str, data_path: str) -> float:
    """Phi of the naive containment do(E2=0, NG3=0, Uu_1=0): the blocking-set closures
    plus shutting DU_1's radio (Uu_1=0), so DU_1 carries no throughput. Estimated as the
    aggregate throughput of DUs 2-4 under do(E2=0, NG3=0) + the surviving omega*A1 term
    (E2 closed); cached."""
    cache_path = os.path.join(data_dir, _CONTAINMENT_CACHE)
    if os.path.isfile(cache_path):
        with open(cache_path) as f:
            return float(json.load(f)["phi"])
    from ccd.system.five_g_testbed_system import FiveGTestbedSystem
    from ccd.util.inference_util import estimate_phi
    system = FiveGTestbedSystem()
    data = pd.read_csv(data_path)
    pf = system.product_functions if system.use_known_product_mechanisms else None
    # throughput of DUs 2-4 only (Uu_1=0 zeroes DU_1's throughput)
    weights = {system.T(i, d): 1.0 for i in range(2, 5) for d in ("U", "D")}
    throughput = estimate_phi(data, system.throughput_graph(), {"E2": 0, "NG3": 0},
                              weights=weights, product_functions=pf)
    phi = throughput + omega_term(_INTERVENTIONS["containment"])
    with open(cache_path, "w") as f:
        json.dump({"scenario": "containment baseline", "phi": phi, "throughput": throughput,
                   "intervention": {"E2": 0, "NG3": 0, "Uu1": 0}, "data_path": data_path}, f, indent=2)
    return float(phi)


def load_inferred(data_dir: str) -> Tuple[Dict[str, float], float, Dict[str, Dict[str, int]]]:
    """Inferred Phi per mode, nominal Phi = alpha / _ALPHA_FRACTION, and each mode's
    intervention from the result JSONs (merged with the model-derived baselines)."""
    inferred: Dict[str, float] = {}
    interventions = dict(_INTERVENTIONS)
    phi_nominal = 0.0
    for mode in ("d1", "d2", "d3"):
        with open(os.path.join(data_dir, f"eval_{mode}.json")) as f:
            result = json.load(f)
        inferred[mode] = float(result["phi"])
        interventions[mode] = dict(result["intervention"] or {})
        phi_nominal = float(result["alpha"]) / _ALPHA_FRACTION
    inferred["nominal"] = phi_nominal
    return inferred, phi_nominal, interventions


def load_measured(data_dir: str) -> Optional[Dict[str, Tuple[float, float]]]:
    """Measured (mean, standard deviation) of Phi per mode from the validation CSVs
    (error bars = std over the validation windows), or
    None if the testbed runs have not been done yet (files absent)."""
    from ccd.system.five_g_testbed_system import FiveGTestbedSystem
    weights = FiveGTestbedSystem().functionality_weights
    measured: Dict[str, Tuple[float, float]] = {}
    for mode in _MODES:
        path = os.path.join(data_dir, f"validation_{mode}.csv")
        if not os.path.isfile(path):
            return None
        data = pd.read_csv(path)
        phi = sum(w * data[col] for col, w in weights.items() if col in data.columns)
        values = np.asarray(phi, dtype=float)
        measured[mode] = (float(values.mean()), float(values.std(ddof=1)))
    return measured


def plot(inferred_pct: Dict[str, float], inferred: Dict[str, float],
         measured_pct: Optional[Dict[str, Tuple[float, float]]],
         measured: Optional[Dict[str, Tuple[float, float]]],
         title: str, path: str) -> None:
    """Bar plot; the inferred group always, plus the measured group once the testbed
    validation CSVs exist (y = % of nominal Phi, bar labels carry the absolute Phi)."""
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    width = 0.8

    def annotate(pos: float, top: float, pct: float, absolute: float) -> None:
        ax.text(pos, top + 8.5, f"{pct:.1f}", ha="center", fontsize=9)
        ax.text(pos, top + 2.5, f"({absolute:.1f})", ha="center", fontsize=7, color="#555555")

    positions_inferred = np.arange(len(_INFERRED_MODES), dtype=float)
    tick_positions, tick_labels = list(positions_inferred), [_MODE_LABELS[m] for m in _INFERRED_MODES]
    group_centers, group_labels = [positions_inferred.mean()], ["Inferred ($\\hat{\\Phi}$)"]
    if measured_pct is not None and measured is not None:
        positions_measured = positions_inferred[-1] + 2.2 + np.arange(len(_MODES))
        for pos, mode in zip(positions_measured, _MODES):
            mean, ci = measured_pct[mode]
            ax.bar(pos, mean, width, color=_MODE_COLORS[mode], yerr=ci, capsize=3,
                   error_kw={"elinewidth": 1.0, "ecolor": "#333333"})
            annotate(pos, mean + max(ci, 1.0), mean, measured[mode][0])
        tick_positions += list(positions_measured)
        tick_labels += [_MODE_LABELS[m] for m in _MODES]
        group_centers.append(positions_measured.mean())
        group_labels.append("Measured (testbed)")

    for pos, mode in zip(positions_inferred, _INFERRED_MODES):
        ax.bar(pos, inferred_pct[mode], width, color=_MODE_COLORS[mode])
        annotate(pos, inferred_pct[mode], inferred_pct[mode], inferred[mode])

    ax.axhline(100.0 * _ALPHA_FRACTION, linestyle="--", linewidth=1.0, color="#666666")
    ax.text(tick_positions[-1] + 0.55, 50.0, r"$\alpha$", va="center", fontsize=11)
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels)
    for center, label in zip(group_centers, group_labels):
        ax.text(center, -0.14, label, ha="center", fontsize=11,
                transform=ax.get_xaxis_transform())
    ax.set_ylabel("Functionality (% of nominal)")
    ax.set_ylim(0, 118.0)
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


def write_csv(inferred_pct: Dict[str, float], inferred: Dict[str, float],
              inferred_thr: Dict[str, float],
              measured_pct: Optional[Dict[str, Tuple[float, float]]],
              measured: Optional[Dict[str, Tuple[float, float]]], path: str) -> None:
    """CSV, one row per mode: measured/inferred as % of nominal Phi, the aggregate DU
    throughput sum E{T} in Mbit/s (``*_thr``), and the absolute Phi
    (``*_phi`` = throughput + omega*(E2+A1)); std is the standard deviation over the
    validation windows. Measured columns
    are ``nan`` until the testbed validation runs are copied back; the attack/containment
    baselines are model-derived (inferred only)."""
    lines = ["mode,measured,std,inferred,measured_thr,inferred_thr,"
             "measured_phi,std_phi,inferred_phi"]
    for mode in _INFERRED_MODES:
        if measured_pct is not None and measured is not None and mode in measured_pct:
            mean, ci = measured_pct[mode]
            phi, phi_ci = measured[mode]
            lines.append(f"{mode},{mean:.2f},{ci:.2f},{inferred_pct[mode]:.2f},"
                         f"nan,{inferred_thr[mode]:.2f},{phi:.2f},{phi_ci:.2f},{inferred[mode]:.2f}")
        else:
            lines.append(f"{mode},nan,nan,{inferred_pct[mode]:.2f},"
                         f"nan,{inferred_thr[mode]:.2f},nan,nan,{inferred[mode]:.2f}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved data to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot inferred (and, when available, measured) Phi per mode.")
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    parser.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "..", "evaluation"))
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    inferred, phi_nominal, interventions = load_inferred(args.data_dir)
    with open(os.path.join(args.data_dir, "eval_d1.json")) as f:
        d1 = json.load(f)
    inferred["containment"] = containment_phi(args.data_dir, d1["data_path"])
    # attack: all DU throughput denied (E{T} = 0); both RIC interfaces stay enabled, so
    # Phi is only the interface term omega*(E2 + A1)
    inferred["attack"] = omega_term(_INTERVENTIONS["attack"])
    inferred_pct = {mode: phi / phi_nominal * 100.0 for mode, phi in inferred.items()}
    # split throughput from the (exact, deterministic) interface term: E{T} = Phi - omega term
    inferred_thr = {mode: inferred[mode] - omega_term(interventions[mode])
                    for mode in _INFERRED_MODES}

    measured = load_measured(args.data_dir)
    measured_pct = (None if measured is None
                    else {mode: (phi / measured["nominal"][0] * 100.0,
                                 ci / measured["nominal"][0] * 100.0)
                          for mode, (phi, ci) in measured.items()})

    for mode in _INFERRED_MODES:
        if measured is not None and measured_pct is not None and mode in measured_pct:
            mean, ci = measured_pct[mode]
            measured_txt = f"measured {mean:6.1f} +- {ci:.1f} % ({measured[mode][0]:6.1f})"
        else:
            measured_txt = "measured    (pending)         "
        print(f"{_MODE_LABELS[mode]:>8}: {measured_txt}   inferred {inferred_pct[mode]:6.1f} % "
              f"(phi {inferred[mode]:6.1f}, thr {inferred_thr[mode]:5.1f})")
    plot(inferred_pct, inferred, measured_pct, measured,
         "5G cloud-RAN: functionality per recovery mode",
         os.path.join(args.out_dir, "evaluation_barplot.png"))
    write_csv(
        inferred_pct, inferred, inferred_thr, measured_pct, measured,
        os.path.join(args.out_dir, "evaluation_barplot.csv"))


if __name__ == "__main__":
    main()
