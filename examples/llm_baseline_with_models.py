"""
LLM-as-operator baseline, WITH the system models disclosed
"""

from __future__ import annotations
import llm_baseline as base
from ccd.util.prompt_util import five_g_prompt_with_model, ics_prompt_with_model, it_prompt_with_model

base._PROMPTS = {"it": it_prompt_with_model, "5g": five_g_prompt_with_model,
                 "ics": ics_prompt_with_model}
base._STEM = "llm_baseline_with_models"
base._PROMPT_PREFIX = "llm_prompt_with_models_"
base._TITLE_TEMPLATE = ("CCD vs LLM-selected degraded modes, models disclosed, "
                        "{tier} models ($D_1$ situation)")


def main() -> None:
    base.main()


if __name__ == "__main__":
    main()
