"""
LLM-as-operator baseline, WITH the system models disclosed: identical to
``llm_baseline.py`` except that each prompt additionally describes, in natural language,
the causal dependencies between the system variables (including the known gating
functions) and the attack paths together with the controls that block them -- i.e. the
information CCD receives as structured input.

Run both scripts to obtain the ablation: ``llm_baseline.py`` measures what an LLM
operator achieves from an incident report alone, this script what it achieves when the
two-layer model is handed over as prose. Artifacts are kept separate
(``llm_baseline_with_models_<tier>.{json,png,csv}``,
``llm_prompt_with_models_<testbed>.txt``), so no run overwrites another's cache or
figures -- neither across variants nor across model tiers.

Usage (same flags as llm_baseline.py):
  python llm_baseline_with_models.py --tier frontier --reps 5
  python llm_baseline_with_models.py --tier both --reps 5
  python llm_baseline_with_models.py --tier lightweight --plot-only
  python llm_baseline_with_models.py --emit-prompts
"""

from __future__ import annotations
import llm_baseline as base
from ccd.util.prompt_util import five_g_prompt_with_model, ics_prompt_with_model, it_prompt_with_model

# redirect every artifact and swap in the with-model prompts; base.main() resolves all of
# these at call time (see the note beside their definitions in llm_baseline.py)
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
