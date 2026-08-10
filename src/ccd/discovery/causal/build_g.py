"""
Construct the causal graph G from a descriptor plus a nominal dataset.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from itertools import product as iproduct
from typing import Dict, FrozenSet, List, Mapping, Optional, Set, Tuple
import networkx as nx
import pandas as pd
from ccd.discovery.causal.orientation import orient_by_tier
from ccd.discovery.causal.structure_learning import (
    DEFAULT_ALPHA, LearnedEdges, build_background_knowledge, learn_edges)
from ccd.discovery.descriptor import Descriptor
from ccd.util.validation_util import observable_columns
from causallearn.utils.cit import kci

Assignment = Mapping[str, str]


@dataclass
class GConstruction:
    """The constructed G plus a record of how each edge arose (for reporting/tests)."""

    graph: nx.DiGraph
    representative: Dict[str, str]
    learn_nodes: List[str]
    discovered_edges: Set[Tuple[str, str]]
    mechanism_edges: Set[Tuple[str, str]]
    context_edges: Set[Tuple[str, str]] = field(default_factory=set)
    unresolved: List[FrozenSet[str]] = field(default_factory=list)
    indep_test: str = ""


def _rep_value(values: Set[str]) -> str:
    """The representative value of a dimension: the numerically-smallest if the values are
    integers, else the lexicographically-smallest."""
    try:
        return min(values, key=lambda v: (int(v),))
    except ValueError:
        return sorted(values)[0]


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
    group_of: Dict[str, Optional[str]] = {spec.name: spec.group for spec in desc.node_set}
    dims_of: Dict[str, Dict[str, str]] = {
        spec.name: dict(spec.index) if spec.index else {} for spec in desc.node_set}

    mech_output = {m.output for m in desc.product_mechanisms}
    operator_controlled = set(desc.columns_by_source("operator_controlled"))
    context_names = {root.name for root in desc.context_roots}

    dim_values: Dict[str, Set[str]] = {}
    for name in present:
        for dim, val in dims_of[name].items():
            dim_values.setdefault(dim, set()).add(val)
    representative = {dim: _rep_value(vals) for dim, vals in dim_values.items()}
    lookup = {(group_of[n], frozenset(dims_of[n].items())): n
              for n in node_names if dims_of[n]}

    def in_rep_slice(name: str) -> bool:
        return all(dims_of[name].get(dim) == representative[dim] for dim in dims_of[name])

    learn_nodes = sorted(n for n in present if n not in context_names and in_rep_slice(n))
    confounders = [c for c in desc.confounders
                   if c in data.columns and data[c].nunique() > 1 and c not in learn_nodes]
    learn_all = learn_nodes + confounders
    base_tier = min((tier_of[n] for n in learn_nodes), default=0) - 1
    tier_ext = {**tier_of, **{c: base_tier for c in confounders}}
    parentless = [n for n in learn_all
                  if n in operator_controlled or n in mech_output or n in confounders]

    discovered: Set[Tuple[str, str]] = set()
    indep_used = ""
    unresolved: List[FrozenSet[str]] = []
    if len(learn_all) >= 2:
        bk = build_background_knowledge(learn_all, tier_of=tier_ext, parentless=parentless)
        learned: LearnedEdges = learn_edges(
            data, learn_all, bk, alpha=alpha, indep_test=indep_test,
            allow_fallback=allow_fallback)
        oriented = orient_by_tier(learned.directed, learned.undirected, tier_ext)
        indep_used = learned.indep_test
        unresolved = oriented.unresolved
        for u, v in oriented.directed:
            if v in mech_output or u in confounders or v in confounders:
                continue
            discovered |= _replicate(u, v, group_of, dims_of, dim_values, lookup, present)
    mechanism_edges: Set[Tuple[str, str]] = set()
    for mech in desc.product_mechanisms:
        if mech.output not in node_names:
            continue
        for factor in mech.factors:
            if factor in node_names:
                mechanism_edges.add((factor, mech.output))

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
        graph=graph, representative=representative, learn_nodes=learn_nodes,
        discovered_edges=discovered, mechanism_edges=mechanism_edges,
        context_edges=context_edges, unresolved=unresolved, indep_test=indep_used)


def _replicate(
    u: str,
    v: str,
    group_of: Mapping[str, Optional[str]],
    dims_of: Mapping[str, Dict[str, str]],
    dim_values: Mapping[str, Set[str]],
    lookup: Mapping[Tuple[Optional[str], FrozenSet[Tuple[str, str]]], str],
    present: Set[str],
) -> Set[Tuple[str, str]]:
    """Replicate a discovered representative edge ``u -> v`` across the two endpoints' dimensions."""
    du, dv = dims_of[u], dims_of[v]
    all_dims = sorted(set(du) | set(dv))
    if not all_dims:
        return {(u, v)}
    ranges = [sorted(dim_values.get(dim, set())) for dim in all_dims]
    out: Set[Tuple[str, str]] = set()
    for combo in iproduct(*ranges):
        assignment = dict(zip(all_dims, combo))
        mu = _remap(u, group_of[u], du, assignment, lookup)
        mv = _remap(v, group_of[v], dv, assignment, lookup)
        if mu is not None and mv is not None and mu in present and mv in present:
            out.add((mu, mv))
    return out


def _remap(
    node: str,
    group: Optional[str],
    dims: Dict[str, str],
    assignment: Assignment,
    lookup: Mapping[Tuple[Optional[str], FrozenSet[Tuple[str, str]]], str],
) -> Optional[str]:
    """The node of ``group`` whose dimensions take ``assignment``'s values; ``node`` itself
    when it carries no dimensions (a global endpoint)."""
    if not dims:
        return node
    key = (group, frozenset((dim, assignment[dim]) for dim in dims))
    return lookup.get(key)
