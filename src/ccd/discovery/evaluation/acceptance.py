"""
Acceptance harness: build a ``ConstructedModel`` and diff it against the hand-authored
testbed ``SystemModel``.

This is the **only** module in ``ccd.discovery`` that imports ``ccd.system`` -- keeping
construction itself non-circular. The acceptance targets are the *testbed* variants
(``ITTestbedSystem`` etc.), because the tool consumes testbed CSVs and those variants drop
unmeasured nodes and add measured edges. G is judged primarily by falsification (a
not-falsified constructed G is acceptable even when it differs edge-wise); C and B are
judged by exact set-diff; Gamma by isomorphism + edge F1.
"""

from __future__ import annotations
import argparse
import os
from dataclasses import dataclass
from typing import Optional
import networkx as nx
import pandas as pd
from ccd.discovery.descriptor import Descriptor
from ccd.discovery.evaluation.graph_diff import EdgeDiff, diff_cross_edges, diff_graphs
from ccd.discovery.model import ConstructedModel
from ccd.discovery.pipeline import build_model
from ccd.system.system_model import SystemModel
from ccd.util.validation_util import load_dataset

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))


@dataclass
class AcceptanceReport:
    """The per-layer diffs for one testbed."""

    testbed: str
    g: EdgeDiff
    gamma: Optional[EdgeDiff] = None
    capability: Optional[EdgeDiff] = None
    blocking: Optional[EdgeDiff] = None

    def summary(self) -> str:
        lines = [f"[{self.testbed}] acceptance:"]
        lines.append(f"  G:     {_fmt(self.g)}")
        if self.gamma is not None:
            lines.append(f"  Gamma: {_fmt(self.gamma)}")
        if self.capability is not None:
            lines.append(f"  C:     {_fmt(self.capability)}")
        if self.blocking is not None:
            lines.append(f"  B:     {_fmt(self.blocking)}")
        return "\n".join(lines)


def _fmt(d: EdgeDiff) -> str:
    return (f"P={d.precision:.2f} R={d.recall:.2f} F1={d.f1:.2f} iso={d.isomorphic} "
            f"(tp={d.true_positive}/{d.n_target}, +{len(d.extra)} extra, -{len(d.missing)} missing)")


def build_target(testbed: str, scale: dict) -> SystemModel:
    """The hand-authored testbed ``SystemModel`` to accept against."""
    if testbed == "it_system":
        from ccd.system.it_testbed_system import ITTestbedSystem
        return ITTestbedSystem(scale.get("m", 10))
    if testbed == "ics":
        from ccd.system.ics_testbed_system import IcsTestbedSystem
        return IcsTestbedSystem()
    if testbed == "5g_ran":
        from ccd.system.five_g_testbed_system import FiveGTestbedSystem
        return FiveGTestbedSystem()
    raise ValueError(f"unknown testbed {testbed!r}")


def accept(
    desc: Descriptor,
    data: pd.DataFrame,
    *,
    with_attack: bool = True,
    validate_permutations: int = 0,
) -> tuple[ConstructedModel, AcceptanceReport]:
    """Construct the model for ``desc`` and diff it against the target ``SystemModel``."""
    model = build_model(desc, data, with_attack=with_attack,
                        validate_permutations=validate_permutations)
    target = build_target(desc.testbed, desc.scale)

    target_g: nx.DiGraph = target.throughput_graph().subgraph(model.graph.nodes).copy()
    report = AcceptanceReport(testbed=desc.testbed, g=diff_graphs(model.graph, target_g))
    if with_attack:
        report.gamma = diff_graphs(model.attack_graph, target.attack_graph)
        report.capability = diff_cross_edges(model.capability_edges, target.capability_edges)
        report.blocking = diff_cross_edges(model.blocking_edges, target.blocking_edges)
    return model, report


def _load_it(m: int, data_path: Optional[str]) -> tuple[Descriptor, pd.DataFrame]:
    import importlib.util
    scripts = os.path.join(_REPO_ROOT, "testbeds", "it_system", "scripts")
    import sys
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(
        "it_descriptor_adapter", os.path.join(scripts, "descriptor.py"))
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    desc = adapter.build_descriptor(m)
    path = data_path or os.path.join(_REPO_ROOT, "testbeds", "it_system", "data", "dataset.csv")
    return desc, load_dataset(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run construction acceptance for a testbed.")
    parser.add_argument("--testbed", default="it_system", choices=["it_system"])
    parser.add_argument("-m", type=int, default=10)
    parser.add_argument("--data", default=None)
    parser.add_argument("--no-attack", action="store_true")
    parser.add_argument("--permutations", type=int, default=0)
    args = parser.parse_args()

    desc, data = _load_it(args.m, args.data)
    _model, report = accept(desc, data, with_attack=not args.no_attack,
                            validate_permutations=args.permutations)
    print(report.summary())


if __name__ == "__main__":
    main()
