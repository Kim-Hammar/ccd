"""Tests for the LLM-baseline parsing and validation helpers (``baseline_util``)."""

from __future__ import annotations
import json
import pytest
from ccd.system.five_g_system import FiveGSystem
from ccd.system.ics_system import IcsSystem
from ccd.system.it_system import ITSystem
from ccd.util.baseline_util import extract_llm_intervention, legal_values, validate_llm_intervention


def test_extracts_bare_json_object():
    proposal, justification = extract_llm_intervention(
        '{"intervention": {"N1": 0}, "justification": "isolate server 1"}')
    assert proposal == {"N1": 0}
    assert justification == "isolate server 1"


def test_extracts_fenced_json_block():
    reply = 'Here is my response:\n```json\n{"intervention": {"W": 0}, "justification": "x"}\n```\nDone.'
    proposal, _ = extract_llm_intervention(reply)
    assert proposal == {"W": 0}


def test_extracts_object_embedded_in_prose():
    reply = ('I would isolate the server. {"intervention": {"M1": 0, "A2": 0}, '
             '"justification": "block {lateral} movement"} Let me know.')
    proposal, justification = extract_llm_intervention(reply)
    assert proposal == {"M1": 0, "A2": 0}
    assert justification == "block {lateral} movement"


def test_extracts_empty_intervention():
    proposal, _ = extract_llm_intervention('{"intervention": {}, "justification": "no action"}')
    assert proposal == {}


def test_extraction_fails_on_garbage():
    with pytest.raises(ValueError):
        extract_llm_intervention("I would close the gateway link to server 1.")


def test_extraction_fails_on_json_without_intervention():
    with pytest.raises(ValueError):
        extract_llm_intervention('{"action": {"N1": 0}}')


def test_legal_values_cover_exactly_the_operator_variables():
    for system in (ITSystem(3), FiveGSystem(), IcsSystem()):
        assert set(legal_values(system)) == system.operator_controlled


def test_it_legal_values_are_degraded_only():
    system = ITSystem(3)
    assert all(values == {0} for values in legal_values(system).values())


def test_five_g_legal_values():
    system = FiveGSystem()
    legal = legal_values(system)
    assert legal["QI1"] == set(range(0, 11))
    assert legal["AT2"] == {1, 2, 3, 4}
    assert legal["E2"] == {0}
    assert legal["NG3"] == {0}


def test_ics_legal_values():
    legal = legal_values(IcsSystem())
    assert legal["W"] == {0}  # domain {0,1,2}, but only the degraded 0 is enactable
    assert legal["Chat"] == {0}


def test_valid_proposal_is_normalized():
    system = ITSystem(3)
    do = validate_llm_intervention(system, {"N1": 0, "M1": 0.0, "A2": 0})
    assert do == {"N1": 0, "M1": 0, "A2": 0}
    assert all(isinstance(v, int) for v in do.values())


def test_empty_proposal_is_legal():
    assert validate_llm_intervention(ITSystem(3), {}) == {}


@pytest.mark.parametrize("proposal", [{"Z9": 0}, {"T": 0}, {"Th1": 0}])
def test_non_operator_variables_are_rejected(proposal):
    with pytest.raises(ValueError, match="not an operator-controlled variable"):
        validate_llm_intervention(ITSystem(3), proposal)


def test_nominal_value_is_rejected():
    with pytest.raises(ValueError, match="omit the variable"):
        validate_llm_intervention(ITSystem(3), {"N1": 1})


@pytest.mark.parametrize("raw", [True, "0", 0.5, None])
def test_non_integer_values_are_rejected(raw):
    with pytest.raises(ValueError, match="not an integer"):
        validate_llm_intervention(ITSystem(3), {"N1": raw})


def test_five_g_multi_valued_controls():
    system = FiveGSystem()
    legal = legal_values(system)
    assert validate_llm_intervention(system, {"QI1": 3, "AT2": 4}, legal) == {"QI1": 3, "AT2": 4}
    with pytest.raises(ValueError):
        validate_llm_intervention(system, {"QI1": 11}, legal)
    with pytest.raises(ValueError):
        validate_llm_intervention(system, {"AT2": 5}, legal)


def test_all_errors_reported_at_once():
    with pytest.raises(ValueError) as excinfo:
        validate_llm_intervention(ITSystem(3), {"N1": 1, "Z9": 0})
    assert "N1" in str(excinfo.value) and "Z9" in str(excinfo.value)


def test_round_trip_through_json():
    """A serialized proposal (as the evaluation cache stores it) validates unchanged."""
    system = IcsSystem()
    reply = json.dumps({"intervention": {"W": 0, "Chat": 0}, "justification": "contain"})
    proposal, _ = extract_llm_intervention(reply)
    assert validate_llm_intervention(system, proposal) == {"W": 0, "Chat": 0}
