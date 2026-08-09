"""
Scalability evaluation of CCD's causal-inference step
"""

from __future__ import annotations
import json
import os
import sys
import time
from typing import Callable, Dict, List, Tuple
import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import numpy as np
from dowhy.gcm.config import disable_progress_bars
from ccd.ccd import select_intervention
from ccd.system.system_model import SystemModel
from ccd.system.it_system import ITSystem
from ccd.system.five_g_system import FiveGSystem
from ccd.system.ics_system import IcsSystem
from ccd.util.inference_util import estimate_phi, split_policy_weights
from ccd.util.synthetic import random_system

disable_progress_bars()

_DATASET_SIZES = [500, 1000, 2000, 4000, 8000]
_REPEATS = 1
_CACHE = "inference_scalability_cache.json"

_SYSTEMS: List[Tuple[str, Callable[[], SystemModel], str]] = [
    ("IT", lambda: ITSystem(10), "tab:blue"),
    ("5G", lambda: FiveGSystem(), "tab:green"),
    ("ICS", lambda: IcsSystem(), "tab:red"),
    ("synthetic", lambda: random_system(100, seed=0), "tab:purple"),
]


def measure(system: SystemModel, size: int, repeats: int = _REPEATS) -> float:
    """Measure inference time."""
    mode = select_intervention(system)
    do = mode.variables if mode is not None else {}
    data = system.generate_dataset(steps=size, seed=0)
    graph = system.throughput_graph()
    products = system.product_functions if system.use_known_product_mechanisms else None
    estimable, _ = split_policy_weights(system.functionality_weights, system.operator_controlled)
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        estimate_phi(data, graph, do, weights=estimable,
                     num_samples=size, product_functions=products)
        best = min(best, time.perf_counter() - start)
    return best


def run_sweep(sizes: List[int]) -> Tuple[Dict[str, int], Dict[str, List[float]]]:
    """Sweep over different system sizes"""
    cache: Dict[str, float] = {}
    if os.path.isfile(_CACHE):
        with open(_CACHE) as f:
            cache = json.load(f)

    graph_sizes: Dict[str, int] = {}
    curves: Dict[str, List[float]] = {}
    for name, build, _color in _SYSTEMS:
        system = build()
        graph_sizes[name] = system.throughput_graph().number_of_nodes()
        times: List[float] = []
        for size in sizes:
            key = f"{name}|{size}"
            if key not in cache:
                cache[key] = measure(system, size)
                with open(_CACHE, "w") as f:
                    json.dump(cache, f, indent=2)
            times.append(cache[key])
            print(f"  {name:10s} |graph|={graph_sizes[name]:4d}  |D|={size:5d}  "
                  f"inference = {cache[key]:8.3f} s")
        curves[name] = times
    return graph_sizes, curves


def plot(sizes: List[int], graph_sizes: Dict[str, int], curves: Dict[str, List[float]],
         path: str = "inference_scalability.png") -> None:
    xs = np.array(sizes)
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for name, _build, color in _SYSTEMS:
        ax.plot(xs, curves[name], "o-", color=color, markersize=6, linewidth=1.6,
                label=f"{name}  ($|\\mathbf{{V}}|={graph_sizes[name]}$)")
    ax.set_yscale("log")
    ax.set_xlabel(r"Dataset size  $|\mathcal{D}|$  (rows)")
    ax.set_ylabel("Causal-inference time [s]")
    ax.set_title("Scalability of CCD's causal-inference step")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(frameon=False, title="system (causal graph size)")
    ax.margins(x=0.02)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"\nSaved plot to {path}")


def plot_bars(sizes: List[int], graph_sizes: Dict[str, int], curves: Dict[str, List[float]],
              path: str = "inference_scalability_bars.png") -> None:
    ordered = sorted((n for n, _b, _c in _SYSTEMS), key=lambda n: graph_sizes[n])
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    x = np.arange(len(ordered))
    width = 0.15
    colors = plt.get_cmap("viridis")(np.linspace(0.15, 0.85, len(sizes)))
    for j, size in enumerate(sizes):
        heights = [curves[name][sizes.index(size)] for name in ordered]
        offset = (j - (len(sizes) - 1) / 2) * width
        ax.bar(x + offset, heights, width, color=colors[j], label=fr"$|\mathcal{{D}}|={size}$")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{n}\n($|\\mathbf{{V}}|={graph_sizes[n]}$)" for n in ordered])
    ax.set_ylabel("Causal-inference time [s]")
    ax.set_title("Scalability of CCD's causal-inference step")
    ax.yaxis.grid(True, which="both", alpha=0.3)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(frameon=False, ncol=len(sizes), fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"Saved bar plot to {path}")


def write_csv(sizes: List[int], graph_sizes: Dict[str, int], curves: Dict[str, List[float]],
              path: str = "inference_scalability.csv") -> None:
    lines = ["system,graph_size,dataset_size,time_s"]
    for name, _build, _color in _SYSTEMS:
        lines += [f"{name},{graph_sizes[name]},{int(size)},{t:.6f}"
                  for size, t in zip(sizes, curves[name])]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved data to {path}")


_PGF_MACROS = {"IT": "\\ccdinfit", "5G": "\\ccdinffiveg", "ICS": "\\ccdinfics",
               "synthetic": "\\ccdinfsynth"}


def write_pgf(sizes: List[int], curves: Dict[str, List[float]],
              path: str = "inference_scalability.tex") -> None:
    lines = ["% CCD causal-inference scalability: time [s] vs dataset size |D| (rows).",
             "% One table per system."]
    for name, _build, _color in _SYSTEMS:
        lines.append(f"% --- {name} ---")
        lines.append("\\pgfplotstableread{")
        lines.append("dsize time")
        lines += [f"{int(size)} {t:.6f}" for size, t in zip(sizes, curves[name])]
        lines.append(f"}}{_PGF_MACROS[name]}")
        lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved pgfplots tables to {path}")


def main() -> None:
    sizes = _DATASET_SIZES
    if len(sys.argv) > 1:
        cap = int(sys.argv[1])
        sizes = [s for s in _DATASET_SIZES if s <= cap] or [cap]
    # Warm-up
    measure(IcsSystem(), 200)
    graph_sizes, curves = run_sweep(sizes)
    plot(sizes, graph_sizes, curves)
    plot_bars(sizes, graph_sizes, curves)
    write_csv(sizes, graph_sizes, curves)
    write_pgf(sizes, curves)


if __name__ == "__main__":
    main()
