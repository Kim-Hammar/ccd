"""
Tests for exporting a constructed two-layer model to JSON / GraphML. Uses a small
hand-built ``ConstructedModel`` (no data, no docker) so it stays fast.
"""

from __future__ import annotations
import json
import networkx as nx
from ccd.discovery.model import ConstructedModel
from ccd.discovery.serialize import dump_graphml, dump_json, model_to_dict


def _toy_model() -> ConstructedModel:
    g = nx.DiGraph([("N1", "Tt1"), ("Tt1", "Th1"), ("N1", "Th1"), ("Th1", "T")])
    gamma = nx.DiGraph([("P0", "E1"), ("E1", "P1")])
    return ConstructedModel(
        testbed="toy",
        graph=g,
        attack_graph=gamma,
        operator_controlled={"N1"},
        functionality={"T"},
        privileges={"P0", "P1"},
        exploits={"E1"},
        attained={"P0", "P1"},
        throughput_nodes=set(g.nodes),
        capability_edges=frozenset({(frozenset({"P1"}), "Tt1")}),
        blocking_edges=frozenset({(frozenset({"A1"}), "E1")}),
        product_functions={"Th1": frozenset({"N1", "Tt1"})},
        exploit_meta={"E1": {"class": "netexploit"}},
    )


def test_model_to_dict_has_all_layers_and_sorted():
    payload = model_to_dict(_toy_model())
    assert set(payload) == {"testbed", "causal_graph", "attack_graph", "capability_edges",
                            "blocking_edges", "roles", "product_functions", "exploit_meta",
                            "falsification"}
    assert payload["causal_graph"]["edges"] == sorted(payload["causal_graph"]["edges"])
    assert payload["capability_edges"] == [{"required": ["P1"], "var": "Tt1"}]
    assert payload["blocking_edges"] == [{"required": ["A1"], "var": "E1"}]
    # derived quantities are exported too
    assert payload["roles"]["attacker_controlled"] == ["Tt1"]
    assert payload["product_functions"] == {"Th1": ["N1", "Tt1"]}
    assert payload["falsification"] is None


def test_dump_json_round_trips(tmp_path):
    model = _toy_model()
    path = tmp_path / "model.json"
    dump_json(model, str(path))
    assert json.loads(path.read_text()) == model_to_dict(model)


def test_dump_graphml_writes_tagged_layers(tmp_path):
    paths = dump_graphml(_toy_model(), str(tmp_path), prefix="toy")
    assert len(paths) == 2 and all(p.endswith(".graphml") for p in paths)
    g = nx.read_graphml(next(p for p in paths if "causal" in p))
    assert g.nodes["N1"]["kind"] == "enacted"        # operator-controlled
    assert g.nodes["Th1"]["kind"] == "product"       # F-tilde output
    assert g.nodes["Tt1"]["kind"] == "measured"
    gamma = nx.read_graphml(next(p for p in paths if "attack" in p))
    assert gamma.nodes["E1"]["kind"] == "exploit"
    assert gamma.nodes["P0"]["kind"] == "privilege"
