"""
Runs the sensitivity analysis of CCD to model misspecification based on the illustrative example.

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
from ccd.util.inference_util import estimate_phi
from ccd.util.perturb_util import (
    add_dag_edges,
    evaluate_structural,
    overspecify,
    overspecify_attack,
    overspecify_privileges,
    remove_edges,
    underspecify,
    underspecify_attack,
    underspecify_privileges,
)
from ccd.system.illustrative_example_system import IllustrativeExampleSystem

disable_progress_bars()

_M = 10
_RHOS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]

PerturbFn = Callable[[IllustrativeExampleSystem, float, np.random.RandomState], IllustrativeExampleSystem]
GraphFn = Callable[[nx.DiGraph, float, np.random.RandomState], nx.DiGraph]

# structural study: (label, perturbation, color, linestyle, pgf-macro).
# Note the detection axes: under-detection makes the foothold exploit E_1 look
# feasible-and-unblockable, so CCD returns bottom (detected infeasibility); over-detection
# concedes the believed-held privileges, so containment can silently fail in the true model.
_N_SEEDS = 200
_STRUCT: List[Tuple[str, PerturbFn, str, str, str]] = [
    ("underspecified causal graph", underspecify, "tab:red", "-", "\\ccdundercausal"),
    ("overspecified causal graph", overspecify, "tab:green", "-", "\\ccdovercausal"),
    ("underspecified attack graph", underspecify_attack, "tab:purple", "-.", "\\ccdunderattack"),
    ("overspecified attack graph", overspecify_attack, "tab:brown", "-.", "\\ccdoverattack"),
    ("underspecified privileges", underspecify_privileges, "tab:orange", "--", "\\ccdunderpriv"),
    ("overspecified privileges", overspecify_privileges, "tab:blue", ":", "\\ccdoverpriv"),
]

# inference study (causal cases only; fixed correct mode)
_INF_STEPS = 2500
_INF_SEEDS = 8
_DO_STAR: Dict[str, int] = {"N1": 0, "M1": 0}
_INF: List[Tuple[str, GraphFn, str, str]] = [
    ("underspecified", remove_edges, "tab:red", "\\ccdinferrunder"),
    ("overspecified", add_dag_edges, "tab:green", "\\ccdinferrover"),
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
def inference_sweep(true: IllustrativeExampleSystem, graph_perturb: GraphFn) -> List[float]:
    data = true.generate_dataset(steps=_INF_STEPS, seed=0)
    true_graph = true.throughput_graph()
    phi_true = estimate_phi(data, true_graph, _DO_STAR, num_samples=_INF_STEPS)
    rel_err = []
    for rho in _RHOS:
        errs = []
        for seed in range(_INF_SEEDS):
            g = graph_perturb(true_graph, rho, np.random.RandomState(seed))
            phi = estimate_phi(data, g, _DO_STAR, num_samples=_INF_STEPS)
            errs.append(abs(phi - phi_true) / phi_true)
        rel_err.append(float(np.mean(errs)))
        print(f"  inference {graph_perturb.__name__:12s} rho={rho:.2f}  rel.err={rel_err[-1]:.3f}")
    return rel_err


def inference_all(true: IllustrativeExampleSystem) -> Dict[str, List[float]]:
    """Return the inference-error curves, loading from cache when the grid matches."""
    if os.path.exists(_INF_CACHE):
        with open(_INF_CACHE) as f:
            cached = json.load(f)
        same_grid = [round(x, 4) for x in cached.get("rhos", [])] == [round(x, 4) for x in _RHOS]
        if same_grid and all(name in cached for name, *_ in _INF):
            print("Using cached inference results.")
            return {name: cached[name] for name, *_ in _INF}
    result = {name: inference_sweep(true, fn) for name, fn, _c, _m in _INF}
    with open(_INF_CACHE, "w") as f:
        json.dump({"rhos": _RHOS, **result}, f, indent=2)
    return result


# --- plots -------------------------------------------------------------------
def plot_structural(results: Dict[str, Dict[str, List[float]]],
                    path: str = "sensitivity_structural.png") -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for name, _fn, color, ls, _macro in _STRUCT:
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


def plot_inference(results: Dict[str, List[float]],
                   path: str = "sensitivity_inference.png") -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for name, _fn, color, _macro in _INF:
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


# --- pgfplots tables ---------------------------------------------------------
def write_tables(struct: Dict[str, Dict[str, List[float]]], infer: Dict[str, List[float]],
                 path: str = "sensitivity_tables.tex") -> None:
    lines = [
        "% CCD sensitivity data for pgfplots.  x = misspecification level rho.",
        "% Structural tables: columns  rho  validity  containment_failure  "
        "functionality_failure  infeasible  mode_size.",
        "% Inference tables:  columns  rho  relative_error_of_Phi_hat.",
        "",
    ]
    for name, _fn, _color, _ls, macro in _STRUCT:
        r = struct[name]
        lines.append(f"% --- structural: {name} ---")
        lines.append("\\pgfplotstableread{")
        lines.append("rho validity containment_failure functionality_failure infeasible mode_size")
        for i, rho in enumerate(_RHOS):
            lines.append(f"{rho:.2f} {r['validity'][i]:.4f} {r['containment_failure'][i]:.4f} "
                         f"{r['functionality_failure'][i]:.4f} {r['infeasible'][i]:.4f} "
                         f"{r['mode_size'][i]:.3f}")
        lines += [f"}}{macro}", ""]
    for name, _fn, _color, macro in _INF:
        lines.append(f"% --- inference: {name} causal graph ---")
        lines.append("\\pgfplotstableread{")
        lines.append("rho relative_error")
        for rho, err in zip(_RHOS, infer[name]):
            lines.append(f"{rho:.2f} {err:.4f}")
        lines += [f"}}{macro}", ""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Saved pgfplots tables to {path}")


def main() -> None:
    true = IllustrativeExampleSystem(_M)

    print("Structural sweep...")
    struct = {name: structural_sweep(true, fn) for name, fn, _c, _ls, _m in _STRUCT}
    plot_structural(struct)
    for name, _fn, _c, _ls, _m in _STRUCT:
        v = struct[name]["validity"]
        print(f"  {name:28s} validity: rho0={v[0]:.2f} -> rho0.5={v[-1]:.2f}")

    print("Inference sweep (DoWhy)...")
    infer = inference_all(true)
    plot_inference(infer)
    write_tables(struct, infer)


if __name__ == "__main__":
    main()
