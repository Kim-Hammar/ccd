"""
Construct the causal graph G from a descriptor plus a nominal dataset.

Pipeline (per the plan). First ``observable_columns`` drops constant columns (reused from
``validation_util``). The node set is partitioned by provenance: enacted nodes and derived
(mechanism-output) nodes are held EXOGENOUS during learning (their incoming edges come
from the enactment layer / the mechanisms, not from discovery), while measured nodes are
learnable. Keeping the derived products in the learn-set as exogenous lets them correctly
d-separate their ancestors from their measured descendants (so an upstream root is not
spuriously wired to a downstream process node it only reaches through a product chain),
while an edge from a product to a measured child (e.g. ICS ``V -> P``) is still
discovered. Index symmetry is then exploited -- structure learning runs on the subgraph at
a single representative dimension assignment and each discovered edge is replicated across
the product of its endpoints' shared dimensions, which keeps PC+KCI tractable (a handful
of nodes even for the 196-node 5G graph) and side-steps the Markov-equivalence between the
symmetric DU/CU/class subgraphs. Finally G is reassembled as the replicated discovered
edges (those into measured nodes) plus every mechanism edge (F-tilde products and the
deterministic aggregate) and the context-root fanout.

The generic core consumes only the descriptor and the data -- never ``ccd.system.*``.
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

Assignment = Mapping[str, str]              # dimension name -> value


@dataclass
class GConstruction:
    """The constructed G plus a record of how each edge arose (for reporting/tests)."""

    graph: nx.DiGraph
    representative: Dict[str, str]                 # the learned representative assignment
    learn_nodes: List[str]
    discovered_edges: Set[Tuple[str, str]]        # replicated measured edges
    mechanism_edges: Set[Tuple[str, str]]         # F-tilde products + aggregate
    context_edges: Set[Tuple[str, str]] = field(default_factory=set)   # context-root fanout
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
    enacted = set(desc.columns_by_source("enacted"))
    context_names = {root.name for root in desc.context_roots}

    # dimension ranges + the representative assignment; a node is in the representative
    # slice iff every dimension it carries is at its representative value (globals always
    # qualify). Context roots (the workload/demand confounder) are held out of learning.
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
    # confounders (e.g. demand) are added only to condition on -- exogenous, at the earliest
    # tier, and dropped from every discovered edge below
    confounders = [c for c in desc.confounders
                   if c in data.columns and data[c].nunique() > 1 and c not in learn_nodes]
    learn_all = learn_nodes + confounders
    base_tier = min((tier_of[n] for n in learn_nodes), default=0) - 1
    tier_ext = {**tier_of, **{c: base_tier for c in confounders}}
    # enacted roots, derived products, and confounders are exogenous during learning
    parentless = [n for n in learn_all if n in enacted or n in mech_output or n in confounders]

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
        # keep only edges into a *measured* node (edges into derived nodes are replaced by
        # the mechanism edges below); drop edges touching a confounder; replicate each
        for u, v in oriented.directed:
            if v in mech_output or u in confounders or v in confounders:
                continue
            discovered |= _replicate(u, v, group_of, dims_of, dim_values, lookup, present)

    # mechanism edges are known structure: added for every declared factor/output, even for
    # a declared-but-constant column (e.g. the 5G radios Uu pinned open, or attachment combos
    # the testbed never exercised) -- the edge is real, the column simply does not vary here.
    mechanism_edges: Set[Tuple[str, str]] = set()
    for mech in desc.product_mechanisms:
        if mech.output not in node_names:
            continue
        for factor in mech.factors:
            if factor in node_names:
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
    """Replicate a discovered representative edge ``u -> v`` across the two endpoints'
    dimensions.

    Iterating over the product of the values of every dimension either endpoint carries,
    each endpoint is remapped to the node with those dimension values (a global endpoint,
    carrying no dimensions, stays fixed). This turns e.g. ``L(1,1,U) -> Ladm(1,U)`` into
    ``L(i,k,d) -> Ladm(i,d)`` for every DU ``i``, class ``k`` and direction ``d``. Remapped
    endpoints absent from the data are dropped.
    """
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
