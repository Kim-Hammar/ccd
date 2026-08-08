"""
Print the with-model prompts of the LLM baselines (see ``llm_baseline_with_models.py``):
the incident report plus the causal dependencies and the attack paths in natural
language. Use ``print_prompts.py`` for the baseline prompts that withhold them.

Usage:
  python print_prompts_with_models.py            # all three testbeds (it, 5g, ics)
  python print_prompts_with_models.py ics        # a single prompt, bare (pipe-friendly)
  python print_prompts_with_models.py it 5g      # a subset
"""

from __future__ import annotations
import sys
import llm_baseline_with_models   # noqa: F401  (rebinds the prompt map on llm_baseline)
from llm_baseline import _TESTBEDS, build_prompt, build_system, load_data, testbed_nominal_phi


def main() -> None:
    testbeds = sys.argv[1:] or list(_TESTBEDS)
    unknown = [t for t in testbeds if t not in _TESTBEDS]
    if unknown:
        raise SystemExit(f"unknown testbed(s): {', '.join(unknown)} (choose from {', '.join(_TESTBEDS)})")
    for testbed in testbeds:
        system = build_system(testbed)
        data = load_data(testbed)
        phi_nominal = testbed_nominal_phi(testbed, system, data)
        prompt = build_prompt(testbed, system, phi_nominal, system.alpha_fraction * phi_nominal)
        if len(testbeds) > 1:
            print(f"{'=' * 24} {testbed} {'=' * 24}")
        print(prompt)


if __name__ == "__main__":
    main()
