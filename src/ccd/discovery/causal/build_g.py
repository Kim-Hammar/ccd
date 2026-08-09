"""
Construct the causal graph G from a descriptor plus a nominal dataset.

Pipeline (per the plan). First ``observable_columns`` drops constant columns (reused from
``validation_util``). The node set is partitioned by provenance: enacted nodes are
exogenous roots, derived nodes have parents frozen to their mechanism factors, and only
measured nodes are learnable. Index symmetry is then exploited -- structure learning runs
on the subgraph at a single representative index and the discovered per-index edges are
replicated across all indices, which keeps PC+KCI tractable and side-steps the
Markov-equivalence between symmetric server/DU subgraphs. Finally G is reassembled as the
replicated discovered edges plus every mechanism edge (F-tilde products and the
deterministic aggregate) and the context-root fanout, over the full index range.

The generic core consumes only the descriptor and the data -- never ``ccd.system.*``.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set, Tuple
import networkx as nx
import pandas as pd
from ccd.discovery.causal.orientation import orient_by_tier
from ccd.discovery.causal.structure_learning import (
    DEFAULT_ALPHA, LearnedEdges, build_background_knowledge, learn_edges)
from ccd.discovery.descriptor import Descriptor
from ccd.util.validation_util import observable_columns
from causallearn.utils.cit import kci


@dataclass
class GConstruction:
    """The constructed G plus a record of how each edge arose (for reporting/tests)."""

    graph: nx.DiGraph
    representative_index: Optional[int]
    learn_nodes: List[str]
    discovered_edges: Set[Tuple[str, str]]        # replicated measured edges
    mechanism_edges: Set[Tuple[str, str]]         # F-tilde products + aggregate
    context_edges: Set[Tuple[str, str]] = field(default_factory=set)   # context-root fanout
    unresolved: List[FrozenSet[str]] = field(default_factory=list)
    indep_test: str = ""


def _index_lookup(desc: Descriptor) -> Dict[Tuple[Optional[str], Optional[int]], str]:
    """Map ``(group, index) -> node name`` for replication."""
    out: Dict[Tuple[Optional[str], Optional[int]], str] = {}
    for spec in desc.node_set:
        out[(spec.group, spec.index)] = spec.name
    return out


def build_g(
    desc: Descriptor,
    data: pd.DataFrame,
    *,
    alpha: float = DEFAULT_ALPHA,
    indep_test: str = kci,
    allow_fallback: bool = True,
) -> GConstruction:
    """Construct G for ``desc`` from ``data`` (see module docstring)."""
    metadata = set(desc.metadata_columns)
    observable = set(observable_columns(data, metadata))
    node_names = {spec.name for spec in desc.node_set}
    present = observable & node_names

    tier_of = {spec.name: spec.tier for spec in desc.node_set}
    index_of = {spec.name: spec.index for spec in desc.node_set}
    lookup = _index_lookup(desc)

    mech_output = {m.output for m in desc.product_mechanisms}
    frozen_parents: Dict[str, FrozenSet[str]] = {
        m.output: frozenset(m.factors) for m in desc.product_mechanisms}
    enacted = set(desc.columns_by_source("enacted"))
    context_names = {root.name for root in desc.context_roots}

    # --- representative learn-set: rep-index nodes + global (indexless) roots ----
    # context roots (the workload/demand confounder) are held out: a load root is
    # near-collinear with its context, so conditioning on it deletes the true fanout-child
    # -> downstream edge. Their fanout edges are added as known structure below.
    # derived nodes are held out too: they are deterministic mechanism outputs (e.g.
    # Th = N * Tt), and a deterministic function of a candidate parent breaks the CI tests
    # (singular covariance, spurious independencies). Their edges are added from the
    # mechanisms below; only measured/enacted nodes are ever wired by discovery.
    index_set: Set[int] = set()
    for n in present:
        idx = index_of[n]
        if idx is not None:
            index_set.add(idx)
    indices = sorted(index_set)
    rep_index = indices[0] if indices else None
    learn_nodes = sorted(
        n for n in present
        if n not in context_names and n not in mech_output
        and index_of[n] in (rep_index, None))

    # constraints restricted to the learn-set
    required = [(f, m.output) for m in desc.product_mechanisms for f in m.factors
                if f in learn_nodes and m.output in learn_nodes]
    frozen_here = {c: p for c, p in frozen_parents.items() if c in learn_nodes}
    parentless = [n for n in enacted if n in learn_nodes]

    discovered: Set[Tuple[str, str]] = set()
    indep_used = ""
    unresolved: List[FrozenSet[str]] = []
    if len(learn_nodes) >= 2:
        bk = build_background_knowledge(
            learn_nodes, tier_of=tier_of, required_edges=required,
            frozen_parents=frozen_here, parentless=parentless)
        learned: LearnedEdges = learn_edges(
            data, learn_nodes, bk, alpha=alpha, indep_test=indep_test,
            allow_fallback=allow_fallback)
        oriented = orient_by_tier(learned.directed, learned.undirected, tier_of)
        indep_used = learned.indep_test
        unresolved = oriented.unresolved
        # keep only the discovered *measured* edges (mechanism edges are added below over
        # the full index range); replicate each across all indices
        for u, v in oriented.directed:
            if v in mech_output and u in frozen_parents.get(v, frozenset()):
                continue                                      # a mechanism edge; added below
            discovered |= _replicate(u, v, index_of, indices, rep_index, lookup, present)

    mechanism_edges: Set[Tuple[str, str]] = set()
    for mech in desc.product_mechanisms:
        for factor in mech.factors:
            if factor in present and mech.output in present:
                mechanism_edges.add((factor, mech.output))

    # context roots fan out to every present node of their child group (known structure)
    context_edges: Set[Tuple[str, str]] = set()
    group_members: Dict[str, List[str]] = {}
    for spec in desc.node_set:
        if spec.group is not None:
            group_members.setdefault(spec.group, []).append(spec.name)
    for root in desc.context_roots:
        if root.name not in present:
            continue
        for child in group_members.get(root.child_group, []):
            if child in present:
                context_edges.add((root.name, child))

    graph = nx.DiGraph()
    graph.add_nodes_from(sorted(present))
    graph.add_edges_from(discovered | mechanism_edges | context_edges)
    return GConstruction(
        graph=graph, representative_index=rep_index, learn_nodes=learn_nodes,
        discovered_edges=discovered, mechanism_edges=mechanism_edges,
        context_edges=context_edges, unresolved=unresolved, indep_test=indep_used)


def _replicate(
    u: str,
    v: str,
    index_of: Dict[str, Optional[int]],
    indices: List[int],
    rep_index: Optional[int],
    lookup: Dict[Tuple[Optional[str], Optional[int]], str],
    present: Set[str],
) -> Set[Tuple[str, str]]:
    """Replicate a discovered representative-index edge ``u -> v`` across all indices.

    A global endpoint (``index is None``) is kept as-is; an indexed endpoint is remapped
    to each target index via ``(group, index)``. Edges whose remapped nodes are absent
    from the data are dropped.
    """
    from_group = _group_of(u, lookup)
    to_group = _group_of(v, lookup)
    iu, iv = index_of.get(u), index_of.get(v)
    out: Set[Tuple[str, str]] = set()
    targets: List[Optional[int]] = [None] if (iu is None and iv is None) else list(indices)
    for t in targets:
        mu = u if iu is None else lookup.get((from_group, t))
        mv = v if iv is None else lookup.get((to_group, t))
        if mu in present and mv in present and mu is not None and mv is not None:
            out.add((mu, mv))
    return out


def _group_of(name: str, lookup: Dict[Tuple[Optional[str], Optional[int]], str]) -> Optional[str]:
    for (group, _index), node in lookup.items():
        if node == name:
            return group
    return None
