"""
Validates the causal layer G of the three two-layer models against the testbeds' measured nominal datasets
"""

from __future__ import annotations
import argparse
import dataclasses
import json
import os
import warnings
from typing import Dict, List, Optional

warnings.filterwarnings("ignore")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from dowhy.gcm.config import disable_progress_bars
from ccd.system.system_model import SystemModel
from ccd.system.it_testbed_system import ITTestbedSystem
from ccd.system.five_g_testbed_system import FiveGTestbedSystem
from ccd.system.ics_testbed_system import IcsTestbedSystem
from ccd.util.validation_util import FalsificationResult, augment_context, falsify, load_dataset, observable_columns

disable_progress_bars()

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_METADATA_COLUMNS = {"window", "t_start", "duration", "client_ok_rate", "demand"}
_IT_M = 10
_CACHE = "model_validation_cache.json"
_VERSION = "lmc-regression-v1"
_SEED = 0


@dataclasses.dataclass(frozen=True)
class TestbedSpec:
    key: str
    macro: str
    title: str
    data_path: str
    rename: Dict[str, str]
    n_permutations: int
    context: Optional[str] = None
    context_child_prefix: str = ""


_TESTBEDS = [
    TestbedSpec("it", "it", "IT system", os.path.join(_REPO_ROOT, "testbeds", "it_system", "data", "dataset.csv"),
                {}, 100),
    TestbedSpec("5g", "fiveg", "5G RAN", os.path.join(_REPO_ROOT, "testbeds", "5g_ran", "data", "dataset.csv"),
                {}, 20, context="demand", context_child_prefix="L_"),
    TestbedSpec("ics", "ics", "ICS", os.path.join(_REPO_ROOT, "testbeds", "ics", "data", "dataset.csv"),
                {"G2": "G2c"}, 100),
]


def build_system(key: str) -> SystemModel:
    """The testbed ``SystemModel`` whose causal graph G is validated."""
    if key == "it":
        return ITTestbedSystem(_IT_M)
    if key == "5g":
        return FiveGTestbedSystem()
    return IcsTestbedSystem()


def build_graph_and_data(spec: TestbedSpec, data_path: str) -> tuple[nx.DiGraph, pd.DataFrame]:
    """The graph under test """
    data = load_dataset(data_path, spec.rename)
    columns = observable_columns(data, _METADATA_COLUMNS)
    dropped = sorted(set(data.columns) - _METADATA_COLUMNS - set(columns))
    if dropped:
        print(f"{spec.title}: dropping {len(dropped)} constant column(s)")
    graph = build_system(spec.key).throughput_graph().subgraph(columns).copy()
    missing = sorted(set(columns) - set(graph.nodes))
    if missing:
        raise SystemExit(f"{spec.title}: dataset column(s) not in the causal graph: {', '.join(missing)}")
    if spec.context is not None:
        children = [c for c in columns if c.startswith(spec.context_child_prefix)]
        graph = augment_context(graph, spec.context, children)
        columns = columns + [spec.context]
        print(f"{spec.title}: added context root {spec.context} -> {len(children)} load roots")
    return graph, data[columns]


def run_testbed(spec: TestbedSpec, data_path: str, n_permutations: int) -> FalsificationResult:
    """Falsify one testbed's causal graph against its measured dataset."""
    graph, data = build_graph_and_data(spec, data_path)
    print(f"{spec.title}: falsifying G ({graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges) "
          f"against {len(data)} windows, {n_permutations} permutations...")
    result = falsify(graph, data, n_permutations, seed=_SEED)
    print(f"  LMC violations: {result.given_violations}/{result.n_tests} "
          f"({100 * result.violation_rate:.1f}%), permuted "
          f"{min(result.perm_violations)}-{max(result.perm_violations)}, "
          f"p_lmc={result.p_lmc:.2f}, p_tpa={result.p_tpa:.2f}, falsified={result.falsified}")
    return result

def results_all(paths: Dict[str, str], permutations: Dict[str, int],
                force: bool) -> Dict[str, FalsificationResult]:
    """Falsification results per testbed"""
    cache: Dict = {}
    if not force and os.path.exists(_CACHE):
        with open(_CACHE) as f:
            cache = json.load(f)
        if cache.get("version") != _VERSION:
            cache = {}
    results: Dict[str, FalsificationResult] = {}
    for spec in _TESTBEDS:
        n_rows = len(pd.read_csv(paths[spec.key], usecols=[0]))
        entry = cache.get(spec.key)
        if (entry is not None and entry["n_permutations"] == permutations[spec.key]
                and entry["n_rows"] == n_rows):
            print(f"{spec.title}: using cached falsification result.")
            results[spec.key] = FalsificationResult(**entry["result"])
            continue
        results[spec.key] = run_testbed(spec, paths[spec.key], permutations[spec.key])
        cache[spec.key] = {"n_permutations": permutations[spec.key], "n_rows": n_rows,
                           "result": dataclasses.asdict(results[spec.key])}
        cache["version"] = _VERSION
        with open(_CACHE, "w") as f:
            json.dump(cache, f, indent=2)
    return results

def plot(results: Dict[str, FalsificationResult], path: str = "model_validation.png") -> None:
    fig, axes = plt.subplots(1, 3, figsize=(10.0, 3.2))
    bar_color = plt.get_cmap("viridis")(0.4)
    for ax, spec in zip(axes, _TESTBEDS):
        r = results[spec.key]
        ax.hist(r.perm_violations, bins=12, color=bar_color, alpha=0.85, label="permuted DAGs")
        ax.axvline(r.given_violations, color="tab:red", linestyle="--", linewidth=1.8,
                   label="given DAG $G$")
        p_label = (f"$p_{{LMC}} < {1.0 / r.n_permutations:.2f}$" if r.p_lmc == 0.0
                   else f"$p_{{LMC}} = {r.p_lmc:.2f}$")
        ax.set_title(f"{spec.title}\n{r.given_violations}/{r.n_tests} LMCs violated, {p_label}",
                     fontsize=10)
        ax.set_xlabel("LMC violations")
        ax.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("permuted DAGs")
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    print(f"Saved plot to {path}")

def write_csv(results: Dict[str, FalsificationResult], path: str = "model_validation.csv") -> None:
    lines = ["testbed,metric,value"]
    for spec in _TESTBEDS:
        r = results[spec.key]
        perm = r.perm_violations
        metrics: List[tuple[str, float]] = [
            ("n_nodes", r.n_nodes), ("n_edges", r.n_edges), ("n_lmc_tests", r.n_tests),
            ("given_violations", r.given_violations), ("violation_rate", round(r.violation_rate, 4)),
            ("p_lmc", r.p_lmc), ("p_tpa", r.p_tpa), ("n_permutations", r.n_permutations),
            ("perm_violations_mean", round(sum(perm) / len(perm), 1)),
            ("perm_violations_min", min(perm)), ("perm_violations_max", max(perm)),
            ("falsifiable", float("nan") if r.falsifiable is None else int(r.falsifiable)),
            ("falsified", float("nan") if r.falsified is None else int(r.falsified)),
        ]
        lines.extend(f"{spec.key},{name},{value}" for name, value in metrics)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved data to {path}")

def write_pgf(results: Dict[str, FalsificationResult], path: str = "model_validation.tex") -> None:
    lines = ["% CCD model-validation data: LMC violations of node-permuted DAGs vs the given",
             "% causal graph G, per testbed (Eulig et al. 2023 falsification).",
             "% columns: violations (one row per permuted DAG)."]
    for spec in _TESTBEDS:
        r = results[spec.key]
        lines.append(f"% --- {spec.title} ---")
        lines.append("\\pgfplotstableread{")
        lines.append("violations")
        lines.extend(str(v) for v in r.perm_violations)
        lines.append(f"}}\\ccdval{spec.macro}")
        lines.append(f"\\def\\ccdval{spec.macro}given{{{r.given_violations}}}")
        lines.append(f"\\def\\ccdval{spec.macro}tests{{{r.n_tests}}}")
        lines.append(f"\\def\\ccdval{spec.macro}pvalue{{{r.p_lmc:.2f}}}")
        lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved pgfplots tables to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Graph falsification of the three testbed causal models against their measured datasets.")
    for spec in _TESTBEDS:
        parser.add_argument(f"--{spec.macro}-data", default=spec.data_path)
        parser.add_argument(f"--n-permutations-{spec.key}", type=int, default=spec.n_permutations)
    parser.add_argument("--force", action="store_true", help="recompute, ignoring the cache")
    args = parser.parse_args()
    paths = {spec.key: getattr(args, f"{spec.macro}_data") for spec in _TESTBEDS}
    permutations = {spec.key: getattr(args, f"n_permutations_{spec.key}") for spec in _TESTBEDS}

    results = results_all(paths, permutations, args.force)
    plot(results)
    write_csv(results)
    write_pgf(results)


if __name__ == "__main__":
    main()
