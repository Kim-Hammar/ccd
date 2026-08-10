"""Unit tests for the construction descriptor + the IT adapter (docker-free)."""

from __future__ import annotations
import pytest
from ccd.discovery.descriptor import (
    ColumnProvenance, Descriptor, ExploitTemplate, Host, Mechanism, NodeSpec)


def test_provenance_source_validated():
    with pytest.raises(ValueError):
        ColumnProvenance("X", "bogus")
    assert ColumnProvenance("X", "measured").source == "measured"


def test_mechanism_and_exploit_kinds_validated():
    with pytest.raises(ValueError):
        Mechanism("Y", ["a", "b"], kind="ratio")
    with pytest.raises(ValueError):
        ExploitTemplate("E", "P0", "P1", "teleport")


def test_it_descriptor_builds_and_validates(testbed_loader):
    adapter = testbed_loader("it_system", "descriptor")
    desc = adapter.build_descriptor(10)
    desc.validate()
    assert desc.testbed == "it_system"
    assert desc.scale == {"m": 10}
    assert set(desc.columns_by_source("operator_controlled")) == {f"N{i}" for i in range(1, 11)} \
        | {f"M{i}" for i in range(1, 11)}
    assert set(desc.columns_by_source("derived")) == {f"Th{i}" for i in range(1, 11)} | {"T"}
    assert "W" in desc.columns_by_source("measured")
    assert {f"Tt{i}" for i in range(1, 11)} <= set(desc.columns_by_source("measured"))


def test_it_descriptor_mechanisms(testbed_loader):
    desc = testbed_loader("it_system", "descriptor").build_descriptor(4)
    products = {m.output: set(m.factors) for m in desc.product_mechanisms if m.kind == "product"}
    assert products == {f"Th{i}": {f"N{i}", f"Tt{i}"} for i in range(1, 5)}
    aggregate = [m for m in desc.product_mechanisms if m.kind == "sum"]
    assert len(aggregate) == 1 and aggregate[0].output == "T"
    assert set(aggregate[0].factors) == {f"Th{i}" for i in range(1, 5)}


def test_it_descriptor_exploit_chain(testbed_loader):
    desc = testbed_loader("it_system", "descriptor").build_descriptor(3)
    by_id = {e.id: e for e in desc.exploit_templates}
    assert by_id["E1"].exploit_class == "netexploit" and by_id["E1"].link_var is None
    assert by_id["E2"].link_var == "A2" and by_id["E2"].pre_privilege == "P1"
    assert by_id["E3"].link_var == "A3"
    assert by_id["E4"].exploit_class == "credreuse" and by_id["E4"].link_var == "M1"


def test_descriptor_round_trips_through_json(testbed_loader, tmp_path):
    desc = testbed_loader("it_system", "descriptor").build_descriptor(5)
    path = tmp_path / "it.json"
    desc.dump(str(path))
    reloaded = Descriptor.load(str(path))
    assert reloaded.to_dict() == desc.to_dict()


def test_validate_rejects_dangling_mechanism_factor():
    desc = Descriptor(
        testbed="t",
        node_set=[NodeSpec("A"), NodeSpec("B")],
        columns=[ColumnProvenance("B", "derived", mechanism="B")],
        product_mechanisms=[Mechanism("B", ["A", "MISSING"])],
        hosts=[Host("h", "c")],
    )
    with pytest.raises(ValueError):
        desc.validate()
