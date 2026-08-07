"""Tests for the natural-language operator prompts (``prompt_util``)."""

from __future__ import annotations
import pytest
from ccd.system.five_g_system import FiveGSystem
from ccd.system.ics_system import IcsSystem
from ccd.system.illustrative_example_system import IllustrativeExampleSystem
from ccd.util.baseline_util import extract_llm_intervention, legal_values, validate_llm_intervention
from ccd.util.prompt_util import five_g_prompt, ics_prompt, it_prompt


def _cases():
    return [
        (IllustrativeExampleSystem(10), it_prompt),
        (FiveGSystem(), five_g_prompt),
        (IcsSystem(), ics_prompt),
    ]


@pytest.mark.parametrize("system,prompt_fn", _cases())
def test_prompt_lists_every_operator_variable(system, prompt_fn):
    prompt = prompt_fn(system, 100.0, 50.0)
    missing = [v for v in system.operator_controlled if f'"{v}"' not in prompt]
    assert not missing, f"operator variables absent from the prompt: {missing}"


@pytest.mark.parametrize("system,prompt_fn", _cases())
def test_prompt_example_parses_and_validates(system, prompt_fn):
    """The format-illustration example must itself be a legal response."""
    prompt = prompt_fn(system, 100.0, 50.0)
    example = prompt.rsplit("Format illustration only (not a recommendation): ", 1)[1]
    proposal, _ = extract_llm_intervention(example)
    validate_llm_intervention(system, proposal, legal_values(system))


@pytest.mark.parametrize("system,prompt_fn", _cases())
def test_prompt_states_alpha_and_nominal_and_is_deterministic(system, prompt_fn):
    prompt = prompt_fn(system, 123.45, 61.72)
    assert "123.45" in prompt and "61.72" in prompt
    assert prompt == prompt_fn(system, 123.45, 61.72)


@pytest.mark.parametrize("system,prompt_fn", _cases())
def test_prompt_does_not_leak_internals(system, prompt_fn):
    """Natural language only: no formal-model vocabulary from the CCD formalism."""
    prompt = prompt_fn(system, 100.0, 50.0).lower()
    for term in ("attack graph", "blocking edge", "capability edge", "criterion",
                 "p-tilde", "descendant"):
        assert term not in prompt, f"prompt leaks internal term {term!r}"


def test_it_prompt_action_list_follows_m():
    for m in (3, 10):
        system = IllustrativeExampleSystem(m)
        prompt = it_prompt(system, 100.0, 50.0)
        assert f'"N{m}"' in prompt and f'"M{m}"' in prompt and f'"A{m}"' in prompt
        assert f'"N{m + 1}"' not in prompt and f'"A{m + 1}"' not in prompt


def test_five_g_prompt_states_value_ranges():
    prompt = five_g_prompt(FiveGSystem(), 100.0, 75.0)
    assert "0..10" in prompt          # admission thresholds QI_i
    assert "1..4" in prompt           # attachment targets AT_i
