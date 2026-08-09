"""
Runs the sensitivity analysis of CCD to model misspecification based on the illustrative example.

Each study is drawn as both a line plot and a grouped-bar plot
(``sensitivity_{structural,inference}.png`` and ``..._bars.png``).

Usage: python sensitivity.py
"""

from __future__ import annotations
import json
import os
import warnings
from typing import Callable, Dict, List, Tuple

warnings.filterwarnings("ignore")

import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from dowhy.gcm.config import disable_progress_bars
from ccd.util.inference_util import estimate_phi, policy_phi, split_policy_weights
from ccd.util.perturb_util import (
    add_dag_edges,
    evaluate_structural,
    overspecify,
    overspecify_attack,
    remove_edges,
    underspecify,
    underspecify_attack,
)
from ccd.system.illustrative_example_system import IllustrativeExampleSystem

disable_progress_bars()

_M = 10
_RHOS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]

PerturbFn = Callable[[IllustrativeExampleSystem, float, np.random.RandomState], IllustrativeExampleSystem]
GraphFn = Callable[[nx.DiGraph, float, np.random.RandomState], nx.DiGraph]

# structural study: (label, perturbation, color, linestyle) over the causal graph G and
# the attack graph Gamma
_N_SEEDS = 200
_STRUCT: List[Tuple[str, PerturbFn, str, str]] = [
    ("underspecified causal graph", underspecify, "tab:red", "-"),
    ("overspecified causal graph", overspecify, "tab:green", "-"),
    ("underspecified attack graph", underspecify_attack, "tab:purple", "-."),
    ("overspecified attack graph", overspecify_attack, "tab:brown", "-."),
]

# inference study (causal cases only; fixed correct mode)
_INF_STEPS = 2500
_INF_SEEDS = 8
_DO_STAR: Dict[str, int] = {"N1": 0, "M1": 0}
_INF: List[Tuple[str, GraphFn, str]] = [
    ("underspecified", remove_edges, "tab:red"),
    ("overspecified", add_dag_edges, "tab:green"),
]
_INF_CACHE = "sensitivity_inference_cache.json"


# --- structural study --------------------------------------------------------
def structural_sweep(true: IllustrativeExampleSystem, perturb: PerturbFn) -> Dict[str, List[float]]:
    validity, cont_fail, func_fail, infeasible, sizes = [], [], [], [], []
    for rho in _RHOS:
        outs = [evaluate_structural(true, perturb(true, rho, np.random.RandomState(seed)))
                for seed in range(_N_SEEDS)]
        validity.append(float(np.mean([o.valid for o in outs])))
        cont_fail.append(float(np.mean([o.silent_containment_failure for o in outs])))
        func_fail.append(float(np.mean([o.silent_functionality_failure for o in outs])))
        infeasible.append(float(np.mean([o.infeasible for o in outs])))
        got = [o.mode_size for o in outs if o.mode_size is not None]
        sizes.append(float(np.mean(got)) if got else float("nan"))
    return dict(validity=validity, containment_failure=cont_fail,
                functionality_failure=func_fail, infeasible=infeasible, mode_size=sizes)


# --- inference study (cached) ------------------------------------------------
_PHI_VERSION = "policy-phi"   # relative error on Phi = E{T} + kappa * sum E{A_i}


def inference_sweep(true: IllustrativeExampleSystem, graph_perturb: GraphFn) -> List[float]:
    data = true.generate_dataset(steps=_INF_STEPS, seed=0)
    true_graph = true.throughput_graph()
    # Phi = E{T} + kappa * sum E{A_i}: the data-estimable E{T | do} plus the kappa policy
    # term of the A_i left open by _DO_STAR (constant, so shared by every estimate)
    estimable, policy = split_policy_weights(true.functionality_weights, true.operator_controlled)
    policy_term = policy_phi(policy, _DO_STAR)
    phi_true = estimate_phi(data, true_graph, _DO_STAR, weights=estimable,
                            num_samples=_INF_STEPS) + policy_term
    rel_err = []
    for rho in _RHOS:
        errs = []
        for seed in range(_INF_SEEDS):
            g = graph_perturb(true_graph, rho, np.random.RandomState(seed))
            phi = estimate_phi(data, g, _DO_STAR, weights=estimable,
                               num_samples=_INF_STEPS) + policy_term
            errs.append(abs(phi - phi_true) / phi_true)
        rel_err.append(float(np.mean(errs)))
        print(f"  inference {graph_perturb.__name__:12s} rho={rho:.2f}  rel.err={rel_err[-1]:.3f}")
    return rel_err


def inference_all(true: IllustrativeExampleSystem) -> Dict[str, List[float]]:
    """Return the inference-error curves, loading from cache when the grid and the Phi
    definition match (the ``phi`` marker invalidates caches from older Phi versions)."""
    if os.path.exists(_INF_CACHE):
        with open(_INF_CACHE) as f:
            cached = json.load(f)
        same_grid = [round(x, 4) for x in cached.get("rhos", [])] == [round(x, 4) for x in _RHOS]
        same_phi = cached.get("phi") == _PHI_VERSION
        if same_grid and same_phi and all(name in cached for name, *_ in _INF):
            print("Using cached inference results.")
            return {name: cached[name] for name, *_ in _INF}
    result = {name: inference_sweep(true, fn) for name, fn, _c in _INF}
    with open(_INF_CACHE, "w") as f:
        json.dump({"rhos": _RHOS, "phi": _PHI_VERSION, **result}, f, indent=2)
    return result


# --- plots -------------------------------------------------------------------
def plot_structural(results: Dict[str, Dict[str, List[float]]],
                    path: str = "sensitivity_structural.png") -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for name, _fn, color, ls in _STRUCT:
        ax.plot(_RHOS, results[name]["validity"], marker="o", color=color, linestyle=ls,
                markersize=6, linewidth=1.8, label=name)
    ax.set_xlabel(r"Misspecification level  $\rho$  (fraction perturbed)")
    ax.set_ylabel("P(selected mode valid in true model)")
    ax.set_title("Sensitivity of CCD to model misspecification")
    ax.set_ylim(-0.03, 1.03)
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False, title="misspecification")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"Saved plot to {path}")


# short mathtext labels for the bar-plot x-axis (the full names are too long there)
_STRUCT_SHORT: Dict[str, str] = {
    "underspecified causal graph": "under $G$",
    "overspecified causal graph": "over $G$",
    "underspecified attack graph": r"under $\Gamma$",
    "overspecified attack graph": r"over $\Gamma$",
}
# misspecification levels for the bars; rho=0 is the unperturbed baseline (validity ~ 1),
# then fine steps through the low-rho region where the decrease happens
_BAR_RHOS = [0.0, 0.05, 0.10, 0.15, 0.20]


def plot_structural_bars(results: Dict[str, Dict[str, List[float]]],
                         path: str = "sensitivity_structural_bars.png") -> None:
    """Grouped bar version of the structural sensitivity: one group per perturbation
    type, one bar per representative misspecification level rho (validity on the y-axis)."""
    names = [name for name, _fn, _c, _ls in _STRUCT]
    idx = [_RHOS.index(r) for r in _BAR_RHOS]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    x = np.arange(len(names))
    width = 0.8 / len(_BAR_RHOS)
    colors = plt.get_cmap("viridis")(np.linspace(0.15, 0.85, len(_BAR_RHOS)))
    for j, (rho, i) in enumerate(zip(_BAR_RHOS, idx)):
        heights = [results[name]["validity"][i] for name in names]
        offset = (j - (len(_BAR_RHOS) - 1) / 2) * width
        ax.bar(x + offset, heights, width, color=colors[j], label=fr"$\rho={rho:.2f}$")
    ax.set_xticks(x)
    ax.set_xticklabels([_STRUCT_SHORT[name] for name in names])
    ax.set_ylabel("P(selected mode valid in true model)")
    ax.set_title("Sensitivity of CCD to model misspecification")
    ax.set_ylim(0.0, 1.05)
    ax.yaxis.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    # every group's rho=0 bar reaches 1.0, so the top is full -> place the legend below
    ax.legend(frameon=False, ncol=len(_BAR_RHOS), title="misspecification level",
              loc="upper center", bbox_to_anchor=(0.5, -0.10))
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)
    fig.savefig(path, dpi=150)
    print(f"Saved bar plot to {path}")


def plot_inference(results: Dict[str, List[float]],
                   path: str = "sensitivity_inference.png") -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for name, _fn, color in _INF:
        ax.plot(_RHOS, results[name], "o-", color=color, markersize=6, linewidth=1.6,
                label=f"{name} causal graph")
    ax.set_xlabel(r"Misspecification level  $\rho$  (fraction perturbed)")
    ax.set_ylabel(r"Relative error of $\hat{\Phi}$")
    ax.set_title("Sensitivity of CCD's causal inference to graph misspecification")
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"Saved plot to {path}")


def plot_inference_bars(results: Dict[str, List[float]],
                        path: str = "sensitivity_inference_bars.png") -> None:
    """Grouped bar version of the inference sensitivity: one group per misspecification
    level rho, one bar per causal-graph perturbation (relative error of Phi-hat)."""
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    x = np.arange(len(_RHOS))
    width = 0.8 / len(_INF)
    for j, (name, _fn, color) in enumerate(_INF):
        offset = (j - (len(_INF) - 1) / 2) * width
        ax.bar(x + offset, results[name], width, color=color, label=f"{name} causal graph")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{r:.2f}" for r in _RHOS])
    ax.set_xlabel(r"Misspecification level  $\rho$  (fraction perturbed)")
    ax.set_ylabel(r"Relative error of $\hat{\Phi}$")
    ax.set_title("Sensitivity of CCD's causal inference to graph misspecification")
    ax.yaxis.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"Saved bar plot to {path}")


# --- CSV output --------------------------------------------------------------
def write_csv(struct: Dict[str, Dict[str, List[float]]], infer: Dict[str, List[float]],
              struct_path: str = "sensitivity_structural.csv",
              infer_path: str = "sensitivity_inference.csv") -> None:
    """Write the sensitivity sweeps as long-format CSV: the structural study
    (per series and misspecification level rho: validity and the failure rates) and
    the inference study (relative error of Phi-hat vs rho)."""
    struct_lines = ["series,rho,validity,containment_failure,functionality_failure,"
                    "infeasible,mode_size"]
    for name, _fn, _color, _ls in _STRUCT:
        r = struct[name]
        for i, rho in enumerate(_RHOS):
            struct_lines.append(f"{name},{rho:.2f},{r['validity'][i]:.4f},"
                                f"{r['containment_failure'][i]:.4f},"
                                f"{r['functionality_failure'][i]:.4f},"
                                f"{r['infeasible'][i]:.4f},{r['mode_size'][i]:.3f}")
    with open(struct_path, "w") as f:
        f.write("\n".join(struct_lines) + "\n")
    print(f"Saved data to {struct_path}")

    infer_lines = ["series,rho,relative_error"]
    for name, _fn, _color in _INF:
        for rho, err in zip(_RHOS, infer[name]):
            infer_lines.append(f"{name},{rho:.2f},{err:.4f}")
    with open(infer_path, "w") as f:
        f.write("\n".join(infer_lines) + "\n")
    print(f"Saved data to {infer_path}")


# --- pgfplots output ---------------------------------------------------------
_STRUCT_MACROS: Dict[str, str] = {
    "underspecified causal graph": "\\ccdsensundercausal",
    "overspecified causal graph": "\\ccdsensovercausal",
    "underspecified attack graph": "\\ccdsensunderattack",
    "overspecified attack graph": "\\ccdsensoverattack",
}
_INF_MACROS: Dict[str, str] = {"underspecified": "\\ccdsensinferunder",
                               "overspecified": "\\ccdsensinferover"}


def write_pgf(struct: Dict[str, Dict[str, List[float]]], infer: Dict[str, List[float]],
              struct_path: str = "sensitivity_structural.tex",
              infer_path: str = "sensitivity_inference.tex") -> None:
    """pgfplots tables (one ``\\pgfplotstableread{...}\\macro`` per series). Structural:
    columns ``rho validity containment_failure functionality_failure infeasible
    mode_size``; inference: columns ``rho relative_error``. x = misspecification level."""
    struct_lines = ["% CCD structural-sensitivity data.  x = misspecification level rho.",
                    "% columns: rho validity containment_failure functionality_failure "
                    "infeasible mode_size",
                    "% (mode_size = nan where no valid mode is selected; use "
                    "'unbounded coords=jump' if you plot it)."]
    for name, _fn, _color, _ls in _STRUCT:
        r = struct[name]
        struct_lines.append(f"% --- {name} ---")
        struct_lines.append("\\pgfplotstableread{")
        struct_lines.append("rho validity containment_failure functionality_failure "
                            "infeasible mode_size")
        for i, rho in enumerate(_RHOS):
            struct_lines.append(f"{rho:.2f} {r['validity'][i]:.4f} "
                                f"{r['containment_failure'][i]:.4f} "
                                f"{r['functionality_failure'][i]:.4f} "
                                f"{r['infeasible'][i]:.4f} {r['mode_size'][i]:.3f}")
        struct_lines.append(f"}}{_STRUCT_MACROS[name]}")
        struct_lines.append("")
    with open(struct_path, "w") as f:
        f.write("\n".join(struct_lines) + "\n")
    print(f"Saved pgfplots tables to {struct_path}")

    infer_lines = ["% CCD inference-sensitivity data.  x = misspecification level rho.",
                   "% columns: rho relative_error (of Phi-hat)."]
    for name, _fn, _color in _INF:
        infer_lines.append(f"% --- {name} causal graph ---")
        infer_lines.append("\\pgfplotstableread{")
        infer_lines.append("rho relative_error")
        for rho, err in zip(_RHOS, infer[name]):
            infer_lines.append(f"{rho:.2f} {err:.4f}")
        infer_lines.append(f"}}{_INF_MACROS[name]}")
        infer_lines.append("")
    with open(infer_path, "w") as f:
        f.write("\n".join(infer_lines) + "\n")
    print(f"Saved pgfplots tables to {infer_path}")


def main() -> None:
    true = IllustrativeExampleSystem(_M)

    print("Structural sweep...")
    struct = {name: structural_sweep(true, fn) for name, fn, _c, _ls in _STRUCT}
    plot_structural(struct)
    plot_structural_bars(struct)
    for name, _fn, _c, _ls in _STRUCT:
        v = struct[name]["validity"]
        print(f"  {name:28s} validity: rho0={v[0]:.2f} -> rho0.5={v[-1]:.2f}")

    print("Inference sweep (DoWhy)...")
    infer = inference_all(true)
    plot_inference(infer)
    plot_inference_bars(infer)
    write_csv(struct, infer)
    write_pgf(struct, infer)


if __name__ == "__main__":
    main()
