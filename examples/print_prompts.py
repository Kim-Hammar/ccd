"""
Print the prompts of the LLM baselines
"""

from __future__ import annotations
import sys
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
