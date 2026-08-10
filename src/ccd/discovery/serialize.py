"""
Serialize a constructed two-layer model ⟨Γ, G, L⟩ for downstream use.
"""

from __future__ import annotations
import json
import os
from typing import Any, Dict, List, Tuple
import networkx as nx
from ccd.discovery.model import ConstructedModel

_CrossEdge = Tuple[frozenset, str]


def _graph_dict(graph: nx.DiGraph) -> Dict[str, Any]:
    return {"nodes": sorted(graph.nodes),
            "edges": sorted([u, v] for u, v in graph.edges)}


def _cross_edges(edges) -> List[Dict[str, Any]]:
    return sorted(
        ({"required": sorted(reqs), "var": var} for reqs, var in edges),
        key=lambda e: (e["var"], e["required"]))


def model_to_dict(model: ConstructedModel) -> Dict[str, Any]:
    """A JSON-serializable dict of the full constructed model (deterministic ordering)."""
    falsification = None
    if model.falsification is not None:
        falsification = {
            "n_nodes": model.falsification.n_nodes,
            "n_edges": model.falsification.n_edges,
            "n_tests": model.falsification.n_tests,
            "given_violations": model.falsification.given_violations,
            "violation_rate": model.falsification.violation_rate,
            "p_lmc": model.falsification.p_lmc,
            "p_tpa": model.falsification.p_tpa,
            "falsifiable": model.falsification.falsifiable,
            "falsified": model.falsification.falsified,
        }
    return {
        "testbed": model.testbed,
        "causal_graph": _graph_dict(model.graph),                      # G
        "attack_graph": _graph_dict(model.attack_graph),               # Gamma
        "capability_edges": _cross_edges(model.capability_edges),      # C
        "blocking_edges": _cross_edges(model.blocking_edges),          # B
        "roles": {
            "privileges": sorted(model.privileges),
            "exploits": sorted(model.exploits),
            "attained": sorted(model.attained),
            "operator_controlled": sorted(model.operator_controlled),
            "functionality": sorted(model.functionality),
            "throughput_nodes": sorted(model.throughput_nodes),
            "attacker_controlled": sorted(model.attacker_controlled),
            "unattained": sorted(model.unattained),
        },
        "product_functions": {k: sorted(v) for k, v in sorted(model.product_functions.items())},
        "exploit_meta": {k: model.exploit_meta[k] for k in sorted(model.exploit_meta)},
        "falsification": falsification,
    }


def dump_json(model: ConstructedModel, path: str) -> None:
    """Write the constructed model as a single JSON document."""
    with open(path, "w") as f:
        json.dump(model_to_dict(model), f, indent=2)


def _tagged(graph: nx.DiGraph, kind_of) -> nx.DiGraph:
    """A copy with a ``kind`` node attribute so viewers can colour the layers."""
    out = graph.copy()
    for node in out.nodes:
        out.nodes[node]["kind"] = kind_of(node)
    return out


def dump_graphml(model: ConstructedModel, directory: str, prefix: str = "") -> List[str]:
    """Write G and Γ as GraphML into ``directory``; returns the paths written.

    Attack-graph nodes are tagged ``privilege``/``exploit``; causal-graph nodes are tagged
    ``enacted`` (operator-controlled), ``product`` (an F-tilde output), or ``measured``.
    """
    os.makedirs(directory, exist_ok=True)
    tag = f"{prefix}_" if prefix else ""

    def causal_kind(node: str) -> str:
        if node in model.operator_controlled:
            return "enacted"
        if node in model.product_functions:
            return "product"
        return "measured"

    def attack_kind(node: str) -> str:
        return "exploit" if node in model.exploits else "privilege"

    g_path = os.path.join(directory, f"{tag}causal_G.graphml")
    gamma_path = os.path.join(directory, f"{tag}attack_gamma.graphml")
    nx.write_graphml(_tagged(model.graph, causal_kind), g_path)
    nx.write_graphml(_tagged(model.attack_graph, attack_kind), gamma_path)
    return [g_path, gamma_path]
