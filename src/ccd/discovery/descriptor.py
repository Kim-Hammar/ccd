"""
Testbed-agnostic descriptor for automatic two-layer-model construction.

A ``Descriptor`` is the single hand-authored input the construction tool consumes: it
names the causal node set (with provenance and orientation tiers), the reachability graph
and hosts, the operator enactment interface, the known product/aggregate mechanisms
(F-tilde), the exploit templates, and the attained privileges P-tilde. Everything the
tool *discovers* (G's measured edges, Gamma's host-exploitability grounding, the C/B
joins) is derived from these plus a dataset and a vulnerability scan.

This module is a leaf: it defines the dataclasses plus JSON load/validate/dump and never
imports anything from ``ccd`` (in particular never ``ccd.system.*``), keeping model
construction non-circular. Each testbed exports a ``Descriptor`` through a thin adapter
over its existing pure library (``testbeds/*/scripts/descriptor.py``).
"""

from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

# provenance source of a causal column (drives G construction):
#   measured -- structure learning may wire up its parents (the only such class)
#   enacted  -- an operator-controlled exogenous root; discovery forbids parents
#   derived  -- a deterministic mechanism output; parents frozen to the mechanism factors
PROVENANCE_SOURCES = ("measured", "enacted", "derived")
# product -- gated product (F-tilde, carries to the constructed model's product_functions)
# sum     -- an aggregation whose parents are known (e.g. a carried load summed over CUs)
# gate    -- a selection/gating whose parents are known (e.g. 5G attachment: which CU a DU
#            rides). sum/gate impose the same known incoming edges as product but are not
#            gated products, so they do not carry to product_functions.
MECHANISM_KINDS = ("product", "sum", "gate")
ENACTMENT_KINDS = ("iptables", "reattach", "mode")
EXPLOIT_CLASSES = ("netexploit", "credreuse", "radioinject", "conceded")


@dataclass(frozen=True)
class Host:
    """A scan target / privilege-bearing host. ``privilege_node`` is the ``P_i`` a
    compromise of this host grants (``None`` for hosts outside Gamma, e.g. the gateway);
    ``produces_vars`` are the causal columns holding this host confers control of (drives
    the capability edges C)."""

    id: str
    container: str
    ips: List[str] = field(default_factory=list)
    role: str = ""
    privilege_node: Optional[str] = None
    produces_vars: List[str] = field(default_factory=list)
    conceded: bool = False


@dataclass(frozen=True)
class Network:
    """A broadcast domain hosts attach to (reachability lives on networks)."""

    id: str
    cidr: str = ""


@dataclass(frozen=True)
class ReachEdge:
    """A directed reachability edge ``src_host -> dst_host`` over ``network``. ``link_var``
    is the operator variable whose enactment severs it (drives the blocking edges B); it is
    ``None`` for an always-on edge (e.g. the attacker's initial foothold)."""

    src_host: str
    dst_host: str
    network: str = ""
    protocol: str = "tcp"
    port: Optional[int] = None
    link_var: Optional[str] = None


@dataclass(frozen=True)
class NodeSpec:
    """A causal-graph (G) node. ``tier`` orders orientation (edges may only advance to a
    strictly higher tier). ``group`` plus ``index`` capture indexed replicas: ``index`` is
    a mapping of named dimensions to values (e.g. 5G ``L`` has ``{"du": "1", "cls": "1",
    "dir": "U"}``; IT ``L`` has ``{"srv": "3"}``). Symmetric subgraphs are learned once at
    a representative assignment and replicated across each edge's shared dimensions.
    ``index is None`` (or empty) marks a global node (e.g. an interface). Values are
    strings so the same schema serializes cleanly and mixes numeric indices with the
    direction label."""

    name: str
    tier: int = 0
    group: Optional[str] = None
    index: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class ColumnProvenance:
    """The provenance of one observed column. ``source`` in ``PROVENANCE_SOURCES``;
    ``enactment_var`` links an enacted column to its :class:`VarEnactment`; ``mechanism``
    references a :class:`Mechanism` output for derived columns."""

    column: str
    source: str
    host: Optional[str] = None
    enactment_var: Optional[str] = None
    mechanism: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source not in PROVENANCE_SOURCES:
            raise ValueError(f"provenance source {self.source!r} not in {PROVENANCE_SOURCES}")


@dataclass(frozen=True)
class VarEnactment:
    """An operator variable and how it is enacted on the live testbed. Mirrors the
    testbeds' ``LinkRule``/``Enactment``. ``reach_edge`` (a ``[src_host, dst_host]`` pair)
    ties the variable to the reachability edge it closes; ``name_map`` records a
    dataset<->model column rename (e.g. the ICS gateway recorded as ``G2`` but modeled as
    ``G2c``/``G2e``)."""

    var: str
    kind: str = "iptables"
    container: Optional[str] = None
    reach_edge: Optional[List[str]] = None
    name_map: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in ENACTMENT_KINDS:
            raise ValueError(f"enactment kind {self.kind!r} not in {ENACTMENT_KINDS}")


@dataclass(frozen=True)
class Mechanism:
    """A mechanism with a KNOWN parent set: ``output``'s parents are exactly ``factors``.
    ``kind`` is a gated ``product`` (the F-tilde products, e.g. ``Th_i = N_i * Tt_i``), a
    ``sum`` aggregate (e.g. ``T = sum Th_i``, or the 5G admitted load summed over classes),
    or a ``gate`` selection (e.g. the 5G attachment picking which CU a DU rides). All three
    impose the same G structure -- required edges ``factor -> output`` and a frozen parent
    set -- so discovery never rewires the output; only ``product`` mechanisms carry over to
    the constructed model's ``product_functions`` (sum/gate are not gated products)."""

    output: str
    factors: List[str]
    kind: str = "product"

    def __post_init__(self) -> None:
        if self.kind not in MECHANISM_KINDS:
            raise ValueError(f"mechanism kind {self.kind!r} not in {MECHANISM_KINDS}")


@dataclass(frozen=True)
class ContextRoot:
    """An exogenous context/fanout root (the workload/demand confounder). Its edges to the
    ``child_group`` nodes are known structure, not discovered, and the root is held out of
    per-index constraint learning: a load root ``L_i`` is near-collinear with ``W`` (it is
    essentially ``W/m``), so conditioning on ``W`` induces a context-specific independence
    that spuriously deletes the true ``L_i -> Tt_i`` edge. Mirrors the ``augment_context``
    step of the falsification harness."""

    name: str
    child_group: str


@dataclass(frozen=True)
class ExploitTemplate:
    """A candidate attacker move ``pre_privilege -> post_privilege``. ``exploit_class`` in
    ``EXPLOIT_CLASSES`` selects the MulVAL rule; ``via_reach_edge`` (a
    ``[src_host, dst_host]`` pair) and ``link_var`` tie the exploit to the reachability
    edge and operator variable that gate it (the latter drives the blocking edges B).
    ``requires_service`` names the service whose scan-confirmed presence grounds a
    ``netexploit``; ``conceded`` templates fire without an exploit (P-tilde concession)."""

    id: str
    pre_privilege: str
    post_privilege: str
    exploit_class: str
    via_reach_edge: Optional[List[str]] = None
    link_var: Optional[str] = None
    requires_service: Optional[str] = None

    def __post_init__(self) -> None:
        if self.exploit_class not in EXPLOIT_CLASSES:
            raise ValueError(f"exploit class {self.exploit_class!r} not in {EXPLOIT_CLASSES}")


@dataclass(frozen=True)
class Descriptor:
    """The complete construction input for one testbed instance."""

    testbed: str
    scale: Dict[str, int] = field(default_factory=dict)
    hosts: List[Host] = field(default_factory=list)
    networks: List[Network] = field(default_factory=list)
    reachability: List[ReachEdge] = field(default_factory=list)
    node_set: List[NodeSpec] = field(default_factory=list)
    columns: List[ColumnProvenance] = field(default_factory=list)
    enactments: List[VarEnactment] = field(default_factory=list)
    product_mechanisms: List[Mechanism] = field(default_factory=list)
    context_roots: List[ContextRoot] = field(default_factory=list)
    # observed confounder columns (e.g. the workload ``demand``) to condition on during
    # structure learning but NOT add to G -- they block spurious edges induced by the
    # confounder (5G: NG_j and T both fall at low demand) without appearing in the model.
    confounders: List[str] = field(default_factory=list)
    exploit_templates: List[ExploitTemplate] = field(default_factory=list)
    attained: List[str] = field(default_factory=list)                 # P-tilde
    attacker_start_hosts: List[str] = field(default_factory=list)
    metadata_columns: List[str] = field(default_factory=list)

    # --- convenience lookups -------------------------------------------------
    def node(self, name: str) -> NodeSpec:
        for spec in self.node_set:
            if spec.name == name:
                return spec
        raise KeyError(f"no NodeSpec named {name!r}")

    def provenance(self, column: str) -> ColumnProvenance:
        for prov in self.columns:
            if prov.column == column:
                return prov
        raise KeyError(f"no provenance for column {column!r}")

    def host(self, host_id: str) -> Host:
        for host in self.hosts:
            if host.id == host_id:
                return host
        raise KeyError(f"no Host with id {host_id!r}")

    def mechanism(self, output: str) -> Mechanism:
        for mech in self.product_mechanisms:
            if mech.output == output:
                return mech
        raise KeyError(f"no Mechanism producing {output!r}")

    def columns_by_source(self, source: str) -> List[str]:
        if source not in PROVENANCE_SOURCES:
            raise ValueError(f"provenance source {source!r} not in {PROVENANCE_SOURCES}")
        return [prov.column for prov in self.columns if prov.source == source]

    def column_rename(self) -> Dict[str, str]:
        """Dataset-column -> model-node renames, from enactment ``name_map``s that point at
        a causal node (e.g. the ICS gateway recorded as ``G2`` but modeled as ``G2c``)."""
        node_names = {spec.name for spec in self.node_set}
        return {en.name_map: en.var for en in self.enactments
                if en.name_map is not None and en.var in node_names}

    def validate(self) -> None:
        """Check internal referential integrity (raises ``ValueError`` on the first
        inconsistency). Cheap structural checks only -- not a data/scan validation."""
        node_names = {spec.name for spec in self.node_set}
        if len(node_names) != len(self.node_set):
            raise ValueError("duplicate NodeSpec name")
        col_names = {prov.column for prov in self.columns}
        if len(col_names) != len(self.columns):
            raise ValueError("duplicate ColumnProvenance column")
        enacted_vars = {en.var for en in self.enactments}
        for prov in self.columns:
            if prov.column not in node_names:
                raise ValueError(f"column {prov.column!r} has no NodeSpec")
            if prov.source == "enacted" and prov.enactment_var is not None \
                    and prov.enactment_var not in enacted_vars:
                raise ValueError(f"column {prov.column!r} references unknown enactment "
                                 f"{prov.enactment_var!r}")
            if prov.source == "derived":
                if prov.mechanism is None:
                    raise ValueError(f"derived column {prov.column!r} names no mechanism")
                self.mechanism(prov.mechanism)               # raises if missing
        for mech in self.product_mechanisms:
            if mech.output not in node_names:
                raise ValueError(f"mechanism output {mech.output!r} has no NodeSpec")
            for fac in mech.factors:
                if fac not in node_names:
                    raise ValueError(f"mechanism {mech.output!r} factor {fac!r} has no NodeSpec")
        privileges = {h.privilege_node for h in self.hosts if h.privilege_node is not None}
        for tmpl in self.exploit_templates:
            for priv in (tmpl.pre_privilege, tmpl.post_privilege):
                if priv not in privileges and priv not in self.attained:
                    raise ValueError(f"exploit {tmpl.id!r} references unknown privilege {priv!r}")
        for host_id in self.attacker_start_hosts:
            self.host(host_id)                               # raises if missing
        groups = {spec.group for spec in self.node_set if spec.group is not None}
        for root in self.context_roots:
            if root.name not in node_names:
                raise ValueError(f"context root {root.name!r} has no NodeSpec")
            if root.child_group not in groups:
                raise ValueError(f"context root {root.name!r} child group "
                                 f"{root.child_group!r} matches no node")

    # --- (de)serialization ---------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Descriptor":
        return cls(
            testbed=payload["testbed"],
            scale=dict(payload.get("scale", {})),
            hosts=[Host(**h) for h in payload.get("hosts", [])],
            networks=[Network(**n) for n in payload.get("networks", [])],
            reachability=[ReachEdge(**r) for r in payload.get("reachability", [])],
            node_set=[NodeSpec(**n) for n in payload.get("node_set", [])],
            columns=[ColumnProvenance(**c) for c in payload.get("columns", [])],
            enactments=[VarEnactment(**e) for e in payload.get("enactments", [])],
            product_mechanisms=[Mechanism(**m) for m in payload.get("product_mechanisms", [])],
            context_roots=[ContextRoot(**c) for c in payload.get("context_roots", [])],
            confounders=list(payload.get("confounders", [])),
            exploit_templates=[ExploitTemplate(**t) for t in payload.get("exploit_templates", [])],
            attained=list(payload.get("attained", [])),
            attacker_start_hosts=list(payload.get("attacker_start_hosts", [])),
            metadata_columns=list(payload.get("metadata_columns", [])),
        )

    def dump(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "Descriptor":
        with open(path) as f:
            descriptor = cls.from_dict(json.load(f))
        descriptor.validate()
        return descriptor
