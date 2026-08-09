"""
Compose a ``ConstructedModel`` from a descriptor (+ dataset, + vulnerability scan).

This is the top-level generic entry point: it wires the causal (``build_g``), attack
(``build_gamma``), and cross-layer (``build_l``) constructors together and never imports
``ccd.system`` (only the evaluation harness does). The attack/cross-layer stages are
optional -- callers that only need G (e.g. the causal-pipeline acceptance) pass
``with_attack=False`` and get a model with just the graph populated.
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
    """Construct <Gamma, G, L> for ``desc``.

    ``with_attack`` toggles the Gamma/L stages (they need the descriptor's exploit
    templates + a scanner). ``validate_permutations > 0`` additionally falsifies the
    constructed G against ``data`` and stores the summary on the model.
    """
    desc.validate()
    g = build_g(desc, data, alpha=alpha, indep_test=indep_test)

    model = ConstructedModel(testbed=desc.testbed, graph=g.graph)
    model.throughput_nodes = set(g.graph.nodes)
    model.product_functions = {
        m.output: frozenset(m.factors)
        for m in desc.product_mechanisms
        if m.kind == "product" and m.output in g.graph}
    model.operator_controlled = set(desc.columns_by_source("enacted"))

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
