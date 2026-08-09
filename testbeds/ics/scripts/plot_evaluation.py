"""
Grouped bar plot of the ICS-testbed evaluation: measured vs inferred functionality per
recovery mode (nominal, D_1, D_2, D_3) plus two model-derived baselines, as % of
nominal Phi (bar labels also carry the absolute Phi).

Functionality is Phi(M) = E{S} + E{I} + epsilon*(G2_1 + G2_2) with epsilon = 0.5, where
S and I are indicators -- S = 1 iff the process is in its safe operating mode (recorded
safety margin >= 50, half the base margin), I = 1 iff web integrity is preserved
(recorded integrity score >= 70, the midpoint of the bimodal safe-mode/healthy
distribution, equivalent to the web server being up) -- and G2_1/G2_2 are the
engineering-station / control-station gateway policies (code names ``G2e``/``G2c``).
The indicators are thresholded from the recorded per-window scores, so no experiment is
re-run; the gateway terms are exact per mode.

Inferred values are identified conditionals from the nominal dataset (no fitting
needed at this granularity): E{I} is the marginal P(I >= 70) -- or 0 when the mode
pins W = 0 (safe mode) -- since W is I's only parent; E{S} under any mode with
Chat = 0 is P(S >= 50 | Chat = 0) (the known products force V = 0, the safe base),
and the marginal P(S >= 50) otherwise. Reporting convention: every component is
clipped at its nominal mean, so a degraded mode is never credited with above-nominal
component values (the identified P(S >= 50 | Chat = 0) = 1 exceeds the nominal 0.94
because supervisory commands raise the reactor pressure; the clip reports 0.94).
Baselines (inferred group only -- the attacker
software is not implemented): "attack" = full propagation (S = 0 shutdown, I = 0, both
gateways open); "containment" = naive block-every-vulnerability containment
do(W=0, G2e=0, G2c=0, Chat=0), which also closes the control-server path whose exploit
E3 only re-grants the conceded P3. Outputs ``evaluation_barplot.png`` and the per-mode
data as ``evaluation_barplot.csv``.

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

# Phi(M) = E{S} + E{I} + epsilon*(G2_1 + G2_2), epsilon = 0.5:
# G2_1 = engineering-station policy (G2e), G2_2 = control-station policy (G2c)
_EPSILON = 0.5          # must match IcsSystem.EPSILON
_ALPHA_FRACTION = 0.4   # must match IcsSystem.alpha_fraction
_GATEWAY_EPSILON = {"G2e": _EPSILON, "G2c": _EPSILON}
# indicator thresholds on the recorded scores: I >= 70 <=> web healthy (bimodal 48/88);
# S >= 50 <=> safety margin above half the base margin (safe operating mode)
_I_THRESHOLD = 70.0
_S_THRESHOLD = 50.0


def gateway_bonus(intervention: Dict[str, int]) -> float:
    """epsilon * (number of gateway policies left open under ``intervention``)."""
    return sum(eps for var, eps in _GATEWAY_EPSILON.items()
               if intervention.get(var, 1) != 0)


def inferred_components(data_path: str,
                        interventions: Dict[str, Dict[str, int]]
                        ) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Identified E{I}, E{S} per mode from the nominal dataset (indicators).

    E{I}: W is I's only parent (no backdoor), so a mode pinning W = 0 has E{I} = 0
    (safe-mode scores are below the threshold) and otherwise the marginal applies.
    E{S}: a mode pinning Chat = 0 forces V = 0 by the known products (the process runs
    at the safe base), identified by P(S >= thr | Chat = 0); otherwise the marginal.
    The attack baseline sets both to 0 (shutdown + compromised web server).
    """
    data = pd.read_csv(data_path)
    i_marginal = float((data["I"] >= _I_THRESHOLD).mean())
    s_marginal = float((data["S"] >= _S_THRESHOLD).mean())
    s_local = float((data.loc[data["Chat"] == 0, "S"] >= _S_THRESHOLD).mean())
    e_i: Dict[str, float] = {}
    e_s: Dict[str, float] = {}
    for mode, intervention in interventions.items():
        if mode == "attack":
            e_i[mode], e_s[mode] = 0.0, 0.0
            continue
        e_i[mode] = 0.0 if intervention.get("W", 1) == 0 else i_marginal
        e_s[mode] = s_local if intervention.get("Chat", 1) == 0 else s_marginal
    return e_i, e_s


def load_inferred_interventions(data_dir: str) -> Dict[str, Dict[str, int]]:
    """Each mode's intervention from the result JSONs, plus the baselines'."""
    interventions: Dict[str, Dict[str, int]] = {"nominal": {}, "attack": {}}
    for mode in ("d1", "d2", "d3"):
        with open(os.path.join(data_dir, f"eval_{mode}.json")) as f:
            result = json.load(f)
        interventions[mode] = dict(result["intervention"] or {})
    interventions["containment"] = {"W": 0, "G2e": 0, "G2c": 0, "Chat": 0}
    return interventions


def load_measured(data_dir: str) -> Dict[str, Tuple[float, float, float, float]]:
    """Measured (I+S indicator mean, standard deviation, E{I}, E{S}) per mode's run
    (error bars = std over the validation windows)."""
    measured: Dict[str, Tuple[float, float, float, float]] = {}
    for mode in _MODES:
        data = pd.read_csv(os.path.join(data_dir, f"validation_{mode}.csv"))
        i_b = (data["I"] >= _I_THRESHOLD).astype(float)
        s_b = (data["S"] >= _S_THRESHOLD).astype(float)
        values = np.asarray(i_b + s_b, dtype=float)
        measured[mode] = (float(values.mean()), float(values.std(ddof=1)),
                          float(i_b.mean()), float(s_b.mean()))
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
        ax.text(pos, top + 2.5, f"({absolute:.2f})", ha="center", fontsize=7, color="#555555")

    for pos, mode in zip(positions_measured, _MODES):
        mean, ci = measured_pct[mode]
        ax.bar(pos, mean, width, color=_MODE_COLORS[mode], yerr=ci, capsize=3,
               error_kw={"elinewidth": 1.0, "ecolor": "#333333"})
        annotate(pos, mean + max(ci, 1.0), mean, measured[mode][0])
    for pos, mode in zip(positions_inferred, _INFERRED_MODES):
        ax.bar(pos, inferred_pct[mode], width, color=_MODE_COLORS[mode])
        annotate(pos, inferred_pct[mode], inferred_pct[mode], inferred[mode])

    ax.axhline(100.0 * _ALPHA_FRACTION, linestyle="--", linewidth=1.0, color="#666666")
    ax.text(positions_inferred[-1] + 0.55, 100.0 * _ALPHA_FRACTION, r"$\alpha$",
            va="center", fontsize=11)
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
              measured_base: Dict[str, Tuple[float, float, float, float]],
              measured_phi: Dict[str, Tuple[float, float]],
              inferred_pct: Dict[str, float], inferred_base: Dict[str, float],
              inferred_i: Dict[str, float], inferred_s: Dict[str, float],
              inferred_phi: Dict[str, float], path: str) -> None:
    """CSV, one row per mode: measured/inferred as % of nominal Phi, the E{I}/E{S}
    indicator components (``*_i``/``*_s``), their sum (``*_base``), and the absolute Phi
    including the gateway terms (``*_phi``); std is the standard deviation over the
    validation windows (gateway terms exact per mode, so std_phi = std_base).
    Phi = E{S} + E{I} + epsilon*(G2_1 + G2_2),
    epsilon = 0.5. The attack/containment baselines are model-derived (inferred only),
    so their measured columns are ``nan``."""
    lines = ["mode,measured,std,inferred,measured_i,measured_s,inferred_i,inferred_s,"
             "measured_base,std_base,inferred_base,measured_phi,std_phi,inferred_phi"]
    for mode in _INFERRED_MODES:
        if mode in measured_pct:
            mean, ci = measured_pct[mode]
            base, base_ci, mean_i, mean_s = measured_base[mode]
            phi, phi_ci = measured_phi[mode]
            lines.append(f"{mode},{mean:.2f},{ci:.2f},{inferred_pct[mode]:.2f},"
                         f"{mean_i:.3f},{mean_s:.3f},"
                         f"{inferred_i[mode]:.3f},{inferred_s[mode]:.3f},"
                         f"{base:.3f},{base_ci:.3f},{inferred_base[mode]:.3f},"
                         f"{phi:.3f},{phi_ci:.3f},{inferred_phi[mode]:.3f}")
        else:
            lines.append(f"{mode},nan,nan,{inferred_pct[mode]:.2f},"
                         f"nan,nan,{inferred_i[mode]:.3f},{inferred_s[mode]:.3f},"
                         f"nan,nan,{inferred_base[mode]:.3f},"
                         f"nan,nan,{inferred_phi[mode]:.3f}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved data to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot measured vs inferred Phi per mode.")
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    parser.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "..", "evaluation"))
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    interventions = load_inferred_interventions(args.data_dir)
    with open(os.path.join(args.data_dir, "eval_d1.json")) as f:
        d1 = json.load(f)
    inferred_i, inferred_s = inferred_components(d1["data_path"], interventions)
    measured_base = load_measured(args.data_dir)

    # reporting convention: clip every component at its nominal mean, so a degraded mode
    # is never credited with above-nominal component values (E{S | Chat=0} = 1 > 0.94)
    for mode in _INFERRED_MODES:
        inferred_i[mode] = min(inferred_i[mode], inferred_i["nominal"])
        inferred_s[mode] = min(inferred_s[mode], inferred_s["nominal"])
    nom = measured_base["nominal"]
    for mode, (_, ci, mean_i, mean_s) in list(measured_base.items()):
        clipped_i, clipped_s = min(mean_i, nom[2]), min(mean_s, nom[3])
        measured_base[mode] = (clipped_i + clipped_s, ci, clipped_i, clipped_s)

    inferred_base = {mode: inferred_i[mode] + inferred_s[mode] for mode in _INFERRED_MODES}

    # Phi = E{S} + E{I} + epsilon*(G2_1 + G2_2); the gateway terms are exact per mode
    inferred_phi = {mode: base + gateway_bonus(interventions[mode])
                    for mode, base in inferred_base.items()}
    measured_phi = {mode: (base + gateway_bonus(interventions[mode]), ci)
                    for mode, (base, ci, _, _) in measured_base.items()}
    # one denominator for every bar -- the measured nominal Phi -- so all percentages
    # are reproducible by dividing the reported (Table) values
    measured_nominal = measured_phi["nominal"][0]
    measured_pct = {mode: (phi / measured_nominal * 100.0, ci / measured_nominal * 100.0)
                    for mode, (phi, ci) in measured_phi.items()}
    inferred_pct = {mode: phi / measured_nominal * 100.0 for mode, phi in inferred_phi.items()}

    for mode in _INFERRED_MODES:
        if mode in measured_pct:
            mean, ci = measured_pct[mode]
            measured_txt = (f"measured {mean:6.1f} +- {ci:.1f} % "
                            f"(phi {measured_phi[mode][0]:5.2f}, "
                            f"I {measured_base[mode][2]:4.2f}, S {measured_base[mode][3]:4.2f})")
        else:
            measured_txt = "measured    n/a                                 "
        print(f"{_MODE_LABELS[mode]:>8}: {measured_txt}   "
              f"inferred {inferred_pct[mode]:6.1f} % "
              f"(phi {inferred_phi[mode]:5.2f}, I {inferred_i[mode]:4.2f}, "
              f"S {inferred_s[mode]:4.2f})")
    plot(measured_pct, measured_phi, inferred_pct, inferred_phi,
         "ICS (Tennessee Eastman): functionality per recovery mode",
         os.path.join(args.out_dir, "evaluation_barplot.png"))
    write_csv(
        measured_pct, measured_base, measured_phi, inferred_pct, inferred_base,
        inferred_i, inferred_s, inferred_phi,
        os.path.join(args.out_dir, "evaluation_barplot.csv"))


if __name__ == "__main__":
    main()
