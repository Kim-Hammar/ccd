"""
Compose a ``ConstructedModel`` from a descriptor (+ dataset, + vulnerability scan).
"""

from __future__ import annotations
from typing import Optional, Set
import pandas as pd
from ccd.discovery.attack.scanner import ScannerInterface
from ccd.discovery.causal.build_g import build_g
from ccd.discovery.descriptor import Descriptor
from ccd.discovery.model import ConstructedModel
from causallearn.utils.cit import kci


def build_model(
    desc: Descriptor,
    data: pd.DataFrame,
    *,
    with_attack: bool = True,
    scanner: Optional[ScannerInterface] = None,
    alpha: float = 0.05,
    indep_test: str = kci,
    validate_permutations: int = 0,
) -> ConstructedModel:
    """Construct <Gamma, G, L> for ``desc``."""
    desc.validate()
    rename = desc.column_rename()
    if rename:
        data = data.rename(columns={k: v for k, v in rename.items() if k in data.columns})
    g = build_g(desc, data, alpha=alpha, indep_test=indep_test)

    model = ConstructedModel(testbed=desc.testbed, graph=g.graph)
    model.throughput_nodes = set(g.graph.nodes)
    model.product_functions = {
        m.output: frozenset(m.factors)
        for m in desc.product_mechanisms
        if m.kind == "product" and m.output in g.graph}
    model.operator_controlled = set(desc.columns_by_source("operator_controlled"))

    if validate_permutations > 0:
        from ccd.discovery.causal.validation import validate_graph
        model.falsification = validate_graph(g.graph, data, validate_permutations)

    if with_attack:
        from ccd.discovery.attack.build_gamma import build_gamma
        from ccd.discovery.cross_layer.build_l import build_l
        if scanner is None:
            from ccd.discovery.attack.scanner import StaticScanner
            scanner = StaticScanner.from_descriptor(desc)
        gamma = build_gamma(desc, scanner)
        model.attack_graph = gamma.graph
        model.privileges = gamma.privileges
        model.exploits = gamma.exploits
        model.attained = set(desc.attained)
        model.exploit_meta = gamma.exploit_meta
        capability, blocking = build_l(desc, gamma)
        model.capability_edges = capability
        model.blocking_edges = blocking
        model.functionality = _functionality_nodes(desc, model)

    return model


def _functionality_nodes(desc: Descriptor, model: ConstructedModel) -> Set[str]:
    """Functionality J: the aggregate sink(s) (sum mechanisms) present in G."""
    return {m.output for m in desc.product_mechanisms
            if m.kind == "sum" and m.output in model.graph}


def main() -> None:
    """Build and export a testbed's constructed two-layer model ⟨Γ, G, L⟩."""
    import argparse
    from ccd.discovery.adapters import TESTBEDS, load_testbed
    from ccd.discovery.serialize import dump_graphml, dump_json, model_to_dict

    parser = argparse.ArgumentParser(
        description="Construct and export a testbed's two-layer model.")
    parser.add_argument("--testbed", required=True, choices=list(TESTBEDS))
    parser.add_argument("-m", type=int, default=10, help="IT-system server count")
    parser.add_argument("--data", default=None, help="dataset CSV (default: committed one)")
    parser.add_argument("--out", default=None, help="write the model JSON here")
    parser.add_argument("--graphml-dir", default=None,
                        help="also write G and Gamma as GraphML into this directory")
    parser.add_argument("--no-attack", action="store_true", help="construct G only")
    parser.add_argument("--live", action="store_true",
                        help="ground Gamma with a live nmap scan (needs nmap + testbed up)")
    parser.add_argument("--permutations", type=int, default=0,
                        help="also falsify G against the data with this many permutations")
    args = parser.parse_args()

    desc, data = load_testbed(args.testbed, args.m, args.data)
    scanner = None
    if not args.no_attack and args.live:
        from ccd.discovery.attack.nmap_scanner import NmapScanner
        scanner = NmapScanner.from_descriptor(desc)
    model = build_model(desc, data, with_attack=not args.no_attack, scanner=scanner,
                        validate_permutations=args.permutations)

    summary = model_to_dict(model)
    print(f"[{model.testbed}] constructed: "
          f"G {model.graph.number_of_nodes()} nodes / {model.graph.number_of_edges()} edges; "
          f"Gamma {model.attack_graph.number_of_nodes()} nodes / "
          f"{model.attack_graph.number_of_edges()} edges; "
          f"|C|={len(summary['capability_edges'])} |B|={len(summary['blocking_edges'])}")
    if model.falsification is not None:
        print(f"  falsification: falsified={model.falsification.falsified} "
              f"p_lmc={model.falsification.p_lmc:.3f}")
    if args.out:
        dump_json(model, args.out)
        print(f"  wrote model JSON -> {args.out}")
    if args.graphml_dir:
        for path in dump_graphml(model, args.graphml_dir, prefix=model.testbed):
            print(f"  wrote GraphML   -> {path}")
    if not args.out and not args.graphml_dir:
        print("  (pass --out FILE.json or --graphml-dir DIR to export)")


if __name__ == "__main__":
    main()
