"""
Acceptance harness: build a ``ConstructedModel`` and diff it against the designed model ``SystemModel``.
"""

from __future__ import annotations
import argparse
from dataclasses import dataclass
from typing import Optional
import networkx as nx
import pandas as pd
from ccd.discovery.descriptor import Descriptor
from ccd.discovery.evaluation.graph_diff import EdgeDiff, diff_cross_edges, diff_graphs
from ccd.discovery.model import ConstructedModel
from ccd.discovery.pipeline import build_model
from ccd.system.system_model import SystemModel


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
    live: bool = False,
) -> tuple[ConstructedModel, AcceptanceReport]:
    """Construct the model for ``desc`` and diff it against the target ``SystemModel``."""
    scanner = None
    if with_attack and live:
        from ccd.discovery.attack.nmap_scanner import NmapScanner
        scanner = NmapScanner.from_descriptor(desc)
    model = build_model(desc, data, with_attack=with_attack, scanner=scanner,
                        validate_permutations=validate_permutations)
    target = build_target(desc.testbed, desc.scale)

    target_g: nx.DiGraph = target.throughput_graph().subgraph(model.graph.nodes).copy()
    report = AcceptanceReport(testbed=desc.testbed, g=diff_graphs(model.graph, target_g))
    if with_attack:
        report.gamma = diff_graphs(model.attack_graph, target.attack_graph)
        report.capability = diff_cross_edges(model.capability_edges, target.capability_edges)
        report.blocking = diff_cross_edges(model.blocking_edges, target.blocking_edges)
    return model, report


def main() -> None:
    from ccd.discovery.adapters import TESTBEDS, load_testbed
    parser = argparse.ArgumentParser(description="Run construction acceptance for a testbed.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--testbed", choices=list(TESTBEDS))
    group.add_argument("--all", action="store_true", help="run every testbed in turn")
    parser.add_argument("-m", type=int, default=10)
    parser.add_argument("--data", default=None)
    parser.add_argument("--no-attack", action="store_true")
    parser.add_argument("--permutations", type=int, default=0)
    parser.add_argument("--live", action="store_true",
                        help="ground Gamma with a live nmap scan (needs nmap + testbed up)")
    args = parser.parse_args()

    testbeds = list(TESTBEDS) if args.all else [args.testbed]
    for testbed in testbeds:
        data_path = None if args.all else args.data
        desc, data = load_testbed(testbed, args.m, data_path)
        _model, report = accept(desc, data, with_attack=not args.no_attack,
                                validate_permutations=args.permutations, live=args.live)
        print(report.summary())


if __name__ == "__main__":
    main()
