"""Unit tests for the 5G cloud-RAN testbed system model."""

import pytest
from ccd.ccd import select_intervention
from ccd.system.five_g_system import FiveGSystem
from ccd.system.five_g_testbed_system import FiveGTestbedSystem


def test_mode_selection_identical_to_reference_model():
    """The testbed subclass must select exactly the reference model's mode (D_1)."""
    reference = select_intervention(FiveGSystem())
    testbed = select_intervention(FiveGTestbedSystem())
    assert testbed is not None and reference is not None
    assert testbed.variables == reference.variables


def test_two_layer_model_is_unchanged():
    """Same graphs, role sets, and cross-layer edges as the reference model."""
    ref = FiveGSystem()
    tb = FiveGTestbedSystem()
    assert set(tb.graph.edges) == set(ref.graph.edges)
    assert set(tb.attack_graph.edges) == set(ref.attack_graph.edges)
    assert tb.operator_controlled == ref.operator_controlled
    assert tb.functionality == ref.functionality
    assert tb.attained == ref.attained
    assert tb.capability_edges == ref.capability_edges
    assert tb.blocking_edges == ref.blocking_edges
    assert tb.throughput_nodes == ref.throughput_nodes
    assert tb.product_functions == ref.product_functions
    assert tb.use_known_product_mechanisms is True


def test_generate_dataset_raises():
    """D is measured on the testbed; the subclass must refuse to simulate."""
    with pytest.raises(NotImplementedError):
        FiveGTestbedSystem().generate_dataset()
