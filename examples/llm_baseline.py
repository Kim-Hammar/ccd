"""
LLM-as-operator baseline: for each testbed's initial attack situation (the D_1
selection), query external LLMs (Anthropic, OpenAI, Gemini) with a natural-language
situation report, validate each proposed intervention, and evaluate it with the CCD
machinery (containment/functionality criteria + Phi-hat via DoWhy). The result is a
grouped bar plot -- one group per testbed, bars = CCD's D_1 mode plus one bar per LLM,
y = worst-case Phi-hat as % of nominal (mean +- std over repetitions) -- next to the
critical level alpha. Phi is evaluated under the worst-case
attacker intervention for each mode, so a mode that leaves a functionality variable
attacker-reachable is charged for the damage the attacker can still do. Containment is
reported separately (hatched bar + contained-count annotation).

API keys and model ids come from the repo-root ``.env`` (see ``.env.example``);
providers without a key are skipped. Each provider offers two model tiers, selected with
``--tier``: ``frontier`` (<PROVIDER>_MODEL_FRONTIER) and ``lightweight``
(<PROVIDER>_MODEL_LIGHTWEIGHT), or ``both`` to run them in sequence. Every tier keeps its
own artifacts -- ``llm_baseline_<tier>.{json,png,csv}`` -- so tiers never overwrite each
other, and query results are cached so plotting never re-queries.

Usage:
  python llm_baseline.py                        # frontier tier (the default)
  python llm_baseline.py --tier lightweight
  python llm_baseline.py --tier both --reps 5   # both tiers, 5 reps each
  python llm_baseline.py --providers anthropic,gemini
  python llm_baseline.py --tier both --plot-only   # re-plot from the caches, no queries
  python llm_baseline.py --refresh              # ignore the cache and re-query
  python llm_baseline.py --emit-prompts         # write llm_prompt_{it,5g,ics}.txt and exit
"""

from __future__ import annotations
import argparse
import json
import os
import warnings
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional
warnings.filterwarnings("ignore")
import matplotlib

matplotlib.use("Agg")   # headless backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from dowhy.gcm.config import disable_progress_bars
from ccd.ccd import select_intervention
from ccd.system.five_g_testbed_system import FiveGTestbedSystem
from ccd.system.ics_testbed_system import IcsTestbedSystem
from ccd.system.it_testbed_system import ITTestbedSystem
from ccd.system.system_model import SystemModel
from ccd.util.baseline_util import extract_llm_intervention, legal_values, validate_llm_intervention
from ccd.util.graph_util import check_criteria, worst_case_attack
from ccd.util.inference_util import estimate_phi, policy_phi, split_policy_weights
from ccd.util.llm_client import query_llm
from ccd.util.prompt_util import five_g_prompt, ics_prompt, it_prompt
from ccd.util.scenario_util import nominal_phi

disable_progress_bars()

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_STEM = "llm_baseline"
_CACHE = ""   # bound per tier by _bind_artifacts(); see run_tier()
_PNG = ""
_CSV = ""
_M = 10   # IT-testbed size (matches the testbed evaluation)
_TITLE = ""   # bound per tier by _bind_artifacts()
_TITLE_TEMPLATE = "CCD vs LLM-selected degraded modes, {tier} models ($D_1$ situation)"
_PROMPT_PREFIX = "llm_prompt_"
# A variant script (see llm_baseline_with_models.py) rebinds _PROMPTS, _STEM,
# _TITLE_TEMPLATE and _PROMPT_PREFIX before calling main(), so it writes its own
# artifacts; the tier suffix is appended to _STEM by _bind_artifacts().


def _bind_artifacts(tier: str) -> None:
    """Point the cache/figure/table paths and the plot title at ``tier``'s artifacts."""
    global _CACHE, _PNG, _CSV, _TITLE
    here = os.path.dirname(__file__)
    _CACHE = os.path.join(here, f"{_STEM}_{tier}_cache.json")
    _PNG = os.path.join(here, f"{_STEM}_{tier}.png")
    _CSV = os.path.join(here, f"{_STEM}_{tier}.csv")
    _TITLE = _TITLE_TEMPLATE.format(tier=tier)


_TESTBEDS = ["it", "5g", "ics"]
_TESTBED_LABELS = {"it": "IT system", "5g": "5G RAN", "ics": "ICS"}
_TESTBED_UNITS = {"it": "req/s", "5g": "Mbit/s", "ics": ""}
_PROVIDERS = ["anthropic", "openai", "gemini"]
_PROVIDER_LABELS = {"ccd": "CCD ($D_1$)", "anthropic": "Anthropic", "openai": "OpenAI",
                    "gemini": "Gemini"}
_TIERS = ["frontier", "lightweight"]
# fallback model ids per tier; .env (<PROVIDER>_MODEL_<TIER>) takes precedence
_DEFAULT_MODELS = {
    "frontier": {"anthropic": "claude-opus-5", "openai": "gpt-5.1",
                 "gemini": "gemini-2.5-pro"},
    "lightweight": {"anthropic": "claude-haiku-4-5", "openai": "gpt-5.1-mini",
                    "gemini": "gemini-2.5-flash"},
}


def model_for(provider: str, tier: str) -> str:
    """The model id for ``provider`` at ``tier``: <PROVIDER>_MODEL_<TIER> from .env,
    falling back to the untiered <PROVIDER>_MODEL and then to the built-in default."""
    return (os.getenv(f"{provider.upper()}_MODEL_{tier.upper()}")
            or os.getenv(f"{provider.upper()}_MODEL")
            or _DEFAULT_MODELS[tier][provider])


# validated categorical palette (dataviz reference): fixed hue per bar identity; the
# contrast WARN on the green is relieved by the direct value labels on every bar
_BAR_COLORS = {"ccd": "#2a78d6", "anthropic": "#eb6834", "openai": "#1baf7a",
               "gemini": "#8465a8"}

_PROMPTS: Dict[str, Callable[..., str]] = {"it": it_prompt, "5g": five_g_prompt, "ics": ics_prompt}

# Maximum attack impact per testbed, as % of nominal Phi: the NO DEGRADATION
# baseline, where the attacker reaches every privilege attainable in the attack graph and
# intervenes on every variable those privileges control. A mode that fails the containment
# criterion cannot bound the attack, so its functionality is reported at this level.
_MAX_IMPACT_PCT = {"it": 21.7, "5g": 40.5, "ics": 35.1}


def max_impact_phi(testbed: str, phi_nominal: float) -> float:
    """Phi under maximum attack impact (the NO DEGRADATION baseline) for ``testbed``."""
    return _MAX_IMPACT_PCT[testbed] / 100.0 * phi_nominal


def build_system(testbed: str) -> SystemModel:
    """The unpatched (D_1 situation) testbed system model."""
    if testbed == "it":
        return ITTestbedSystem(_M)
    if testbed == "5g":
        return FiveGTestbedSystem()
    if testbed == "ics":
        return IcsTestbedSystem()
    raise ValueError(f"unknown testbed {testbed!r}")


def load_data(testbed: str) -> pd.DataFrame:
    """The testbed's measured nominal dataset D (ICS renames G2 -> G2c, as its run_ccd)."""
    path = os.path.join(_ROOT, "testbeds",
                        {"it": "it_system", "5g": "5g_ran", "ics": "ics"}[testbed],
                        "data", "dataset.csv")
    data = pd.read_csv(path)
    if testbed == "ics":
        data = data.rename(columns={"G2": "G2c"})
    return data


def build_prompt(testbed: str, system: SystemModel, phi_nominal: float, alpha: float) -> str:
    """The natural-language operator prompt for ``testbed``'s D_1 situation."""
    return _PROMPTS[testbed](system, phi_nominal, alpha)


# ICS indicator functionality: I and S are 0/1 indicators,
# thresholded from the recorded 0-100 scores exactly as the ICS testbed evaluation
# (I = 1{score >= 70} web integrity preserved; S = 1{score >= 50} safe operating mode),
# NOT the 0.01-rescaled raw scores of ``IcsSystem.functionality_weights``.
_ICS_I_THRESHOLD = 70.0
_ICS_S_THRESHOLD = 50.0
_ICS_EPSILON = 0.5


def ics_nominal_phi(data: pd.DataFrame) -> float:
    """Nominal ICS Phi = E{I} + E{S} + epsilon*(G2_1 + G2_2) with indicator I, S."""
    i_marginal = float((data["I"] >= _ICS_I_THRESHOLD).mean())
    s_marginal = float((data["S"] >= _ICS_S_THRESHOLD).mean())
    return i_marginal + s_marginal + 2.0 * _ICS_EPSILON


def ics_indicator_phi(data: pd.DataFrame, do: Mapping[str, int]) -> float:
    """ICS Phi under the combined intervention ``do`` (operator mode + attacker action),
    via the identified conditionals of the ICS model.

    E{I}: W is I's only parent -- 0 when W is pinned to safe mode (W = 0) or tampered
    with by the attacker (W = 2), else the marginal.
    E{S}: the known products (Ctil = G2c*C, V = Chat*Ctil) force V = 0 whenever
    Chat = 0 or G2c = 0, identifying E{S | V = 0}; if instead the attacker drives the
    valves with malicious commands (C = 1 with V active), the process leaves its safe
    operating mode (S = 0); otherwise the marginal. Components are clipped at their
    nominal means, matching the testbed evaluation's reporting convention.
    """
    i_marginal = float((data["I"] >= _ICS_I_THRESHOLD).mean())
    s_marginal = float((data["S"] >= _ICS_S_THRESHOLD).mean())
    e_i = 0.0 if do.get("W", 1) != 1 else i_marginal
    if do.get("Chat", 1) == 0 or do.get("G2c", 1) == 0:
        e_s = float((data.loc[data["V"] == 0, "S"] >= _ICS_S_THRESHOLD).mean())
    elif do.get("C", 0) == 1:
        e_s = 0.0        # malicious supervisory commands reach the valves
    else:
        e_s = s_marginal
    e_s = min(e_s, s_marginal)
    bonus = sum(_ICS_EPSILON for var in ("G2e", "G2c") if do.get(var, 1) != 0)
    return e_i + e_s + bonus


def testbed_phi(testbed: str, system: SystemModel, data: pd.DataFrame,
                do: Mapping[str, int], num_samples: Optional[int]) -> float:
    """Phi under the (possibly combined operator+attacker) intervention ``do``."""
    if testbed == "ics":
        return ics_indicator_phi(data, do)
    estimable, policy = split_policy_weights(system.functionality_weights,
                                             system.operator_controlled)
    pf = system.product_functions if system.use_known_product_mechanisms else None
    return estimate_phi(data, system.throughput_graph(), do, weights=estimable,
                        num_samples=num_samples, product_functions=pf) + policy_phi(policy, do)


def worst_case_phi(testbed: str, system: SystemModel, data: pd.DataFrame,
                   do: Mapping[str, int], num_samples: Optional[int]) -> float:
    """Worst-case functionality of the mode ``do``: min over attacker interventions,
    i.e. Phi(M_{u,a}) with ``a`` the worst-case attack (the attacker
    reaches every privilege attainable in Gamma_u and intervenes on everything those
    privileges control). Equals Phi(M_u) whenever the functionality criterion holds."""
    combined = dict(do)
    combined.update(worst_case_attack(system, do))   # degradation takes priority on X n Y
    return testbed_phi(testbed, system, data, combined, num_samples)


def testbed_nominal_phi(testbed: str, system: SystemModel, data: pd.DataFrame) -> float:
    """Nominal Phi (indicator-based for the ICS)."""
    if testbed == "ics":
        return ics_nominal_phi(data)
    return nominal_phi(system, data)


def evaluate_response(testbed: str, system: SystemModel, data: pd.DataFrame, raw: str, *,
                      alpha: float, phi_nominal: float,
                      num_samples: Optional[int]) -> Dict[str, object]:
    """Parse, validate, and evaluate one raw LLM reply into a cache/rep entry.

    An unparseable or illegal proposal yields ``valid=False`` with the error message;
    a legal one always gets Phi-hat, with the criteria verdicts reported separately.
    The ICS Phi uses the indicator convention (``ics_indicator_phi``).
    """
    entry: Dict[str, object] = {"raw_response": raw}
    try:
        proposal, justification = extract_llm_intervention(raw)
        do = validate_llm_intervention(system, proposal, legal_values(system))
    except ValueError as error:
        entry.update(valid=False, error=str(error))
        return entry
    criteria = check_criteria(system, do)
    phi_nominal_mode = testbed_phi(testbed, system, data, do, num_samples)
    phi = (worst_case_phi(testbed, system, data, do, num_samples) if criteria.contained
           else max_impact_phi(testbed, phi_nominal))
    entry.update(valid=True, intervention=do, justification=justification, phi=phi,
                 phi_no_attack=phi_nominal_mode, feasible=phi >= alpha,
                 contained=criteria.contained, functional=criteria.functional,
                 violating_exploits=sorted(criteria.violating_exploits))
    return entry


def _load_cache() -> Dict[str, object]:
    if os.path.exists(_CACHE):
        with open(_CACHE) as f:
            return json.load(f)
    return {"ccd": {}, "llm": {}}


def _save_cache(cache: Dict[str, object]) -> None:
    with open(_CACHE, "w") as f:
        json.dump(cache, f, indent=2)


def run_ccd_reference(cache: Dict, testbed: str, system: SystemModel, data: pd.DataFrame,
                      phi_nominal: float, alpha: float, num_samples: Optional[int],
                      refresh: bool) -> None:
    """CCD's D_1 selection on ``data`` (cached): the reference bar of the comparison."""
    if testbed in cache["ccd"] and not refresh:
        return
    u = select_intervention(system)
    do = dict(u.variables) if u is not None else None
    if do is None:
        cache["ccd"][testbed] = {"intervention": None, "phi": float("nan"), "alpha": alpha,
                                 "phi_nominal": phi_nominal, "feasible": False}
    else:
        phi = (worst_case_phi(testbed, system, data, do, num_samples)
               if check_criteria(system, do).contained else max_impact_phi(testbed, phi_nominal))
        cache["ccd"][testbed] = {
            "intervention": do, "phi": phi, "alpha": alpha, "phi_nominal": phi_nominal,
            "phi_no_attack": testbed_phi(testbed, system, data, do, num_samples),
            "feasible": phi >= alpha,
        }
    _save_cache(cache)


def run_llm(cache: Dict, testbed: str, system: SystemModel, data: pd.DataFrame,
            prompt: str, provider: str, model: str, api_key: str, *, reps: int,
            alpha: float, phi_nominal: float, num_samples: Optional[int],
            refresh: bool) -> None:
    """Query ``provider`` ``reps`` times on ``testbed`` and evaluate each proposal."""
    slot = cache["llm"].setdefault(testbed, {}).setdefault(provider, {"model": model, "reps": []})
    if refresh or slot.get("model") != model:
        slot.update(model=model, reps=[])
    while len(slot["reps"]) < reps:
        rep = len(slot["reps"])
        print(f"  [{testbed}] querying {provider} ({model}), rep {rep + 1}/{reps}...")
        raw = query_llm(provider, model, prompt, api_key=api_key)
        entry = evaluate_response(testbed, system, data, raw, alpha=alpha,
                                  phi_nominal=phi_nominal, num_samples=num_samples)
        if entry.get("valid"):
            do = entry["intervention"]
            assert isinstance(do, dict)
            do_str = ", ".join(f"{k}={v}" for k, v in sorted(do.items())) or "-"
            print(f"    -> do({do_str})  Phi-hat={entry['phi']:.2f}  "
                  f"contained={entry['contained']}  functional={entry['functional']}")
        else:
            print(f"    -> invalid proposal: {entry['error']}")
        slot["reps"].append(entry)
        _save_cache(cache)


@dataclass
class _Stats:
    """Per-(testbed, provider) summary over the cached repetitions."""

    n: int              # total repetitions
    valid: int          # parseable + legal proposals
    contained: int      # valid reps satisfying the containment criterion
    feasible: int       # valid reps with Phi-hat >= alpha
    phi_mean: float     # worst-case Phi-hat (the reported bar)
    phi_std: float
    phi_no_attack: float  # Phi-hat(M_u) with no attacker action, for reference
    pct_mean: float     # worst-case Phi-hat as % of nominal (0 when no valid rep)
    pct_std: float


def _pct_stats(slot: Dict, phi_nominal: float) -> _Stats:
    """Mean/std of Phi-hat (% of nominal) over the valid reps, plus the count summary."""
    reps = slot["reps"]
    phis = [r["phi"] for r in reps if r.get("valid")]
    no_attack = [r.get("phi_no_attack", r["phi"]) for r in reps if r.get("valid")]
    pct = [100.0 * p / phi_nominal for p in phis]
    return _Stats(
        n=len(reps), valid=len(phis),
        contained=sum(1 for r in reps if r.get("valid") and r["contained"]),
        feasible=sum(1 for r in reps if r.get("valid") and r["feasible"]),
        phi_mean=float(np.mean(phis)) if phis else float("nan"),
        phi_std=float(np.std(phis, ddof=1)) if len(phis) > 1 else 0.0,
        phi_no_attack=float(np.mean(no_attack)) if no_attack else float("nan"),
        pct_mean=float(np.mean(pct)) if pct else 0.0,
        pct_std=float(np.std(pct, ddof=1)) if len(pct) > 1 else 0.0,
    )


def plot(cache: Dict, providers: List[str], path: Optional[str] = None) -> None:
    """Grouped bars: one group per testbed, bars = CCD + one per provider, y = Phi-hat
    as % of that testbed's nominal Phi; error bars = std over valid reps; dashed
    per-group alpha line; hatched bar when fewer than half the valid reps contain."""
    bars = ["ccd"] + [p for p in providers if any(p in cache["llm"].get(t, {}) for t in _TESTBEDS)]
    testbeds = [t for t in _TESTBEDS if t in cache["ccd"]]
    path = path or _PNG
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    x = np.arange(len(testbeds), dtype=float)
    width = 0.8 / len(bars)

    def annotate(pos: float, top: float, text: str, sub: str = "") -> None:
        ax.text(pos, top + 2.0, text, ha="center", fontsize=8)
        if sub:
            ax.text(pos, top + 9.5, sub, ha="center", fontsize=6.5, color="#555555")

    labeled: set = set()

    def bar_label(bar: str) -> Optional[str]:
        """Legend label on the first drawn bar of each identity only."""
        if bar in labeled:
            return None
        labeled.add(bar)
        return _PROVIDER_LABELS[bar]

    for j, bar in enumerate(bars):
        offset = (j - (len(bars) - 1) / 2) * width
        for i, testbed in enumerate(testbeds):
            ref = cache["ccd"][testbed]
            if bar == "ccd":
                pct = 100.0 * ref["phi"] / ref["phi_nominal"]
                ax.bar(x[i] + offset, pct, width * 0.94, color=_BAR_COLORS[bar],
                       label=bar_label(bar))
                annotate(x[i] + offset, pct, f"{pct:.1f}")
                continue
            slot = cache["llm"].get(testbed, {}).get(bar)
            if slot is None:
                continue
            s = _pct_stats(slot, ref["phi_nominal"])
            hatched = s.valid > 0 and s.contained < (s.valid + 1) // 2
            ax.bar(x[i] + offset, s.pct_mean, width * 0.94, color=_BAR_COLORS[bar],
                   yerr=s.pct_std if s.valid > 1 else None, capsize=3,
                   error_kw={"elinewidth": 1.0, "ecolor": "#333333"},
                   hatch="//" if hatched else None, edgecolor="#333333", linewidth=0.5,
                   label=bar_label(bar))
            label = f"{s.pct_mean:.1f}" if s.valid else "invalid"
            annotate(x[i] + offset, s.pct_mean + s.pct_std, label,
                     f"{s.contained}/{s.n} cont.")

    for i, testbed in enumerate(testbeds):
        ref = cache["ccd"][testbed]
        alpha_pct = 100.0 * ref["alpha"] / ref["phi_nominal"]
        ax.plot([x[i] - 0.45, x[i] + 0.45], [alpha_pct, alpha_pct],
                linestyle="--", linewidth=1.0, color="#666666")
        ax.text(x[i] + 0.47, alpha_pct, r"$\alpha$", va="center", fontsize=10)

    ax.set_xticks(x)
    ax.set_xticklabels([_TESTBED_LABELS[t] for t in testbeds])
    ax.set_ylabel(r"Worst-case $\hat{\Phi}$ (% of nominal)")
    ax.set_ylim(0, 118.0)
    ax.yaxis.grid(True, linewidth=0.5, alpha=0.4)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.set_title(_TITLE)
    ax.legend(frameon=False, ncol=len(bars), loc="upper center", bbox_to_anchor=(0.5, -0.08))
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.16)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Saved plot to {path}")


def write_csv(cache: Dict, providers: List[str], path: Optional[str] = None) -> None:
    """One row per (testbed, bar): Phi-hat mean/std, % of nominal, criteria counts."""
    path = path or _CSV
    lines = ["testbed,selector,model,reps,valid,contained,feasible,"
             "phi_mean,phi_std,phi_no_attack,pct_mean,pct_std,alpha,phi_nominal"]
    for testbed in _TESTBEDS:
        if testbed not in cache["ccd"]:
            continue
        ref = cache["ccd"][testbed]
        pct = 100.0 * ref["phi"] / ref["phi_nominal"]
        lines.append(f"{testbed},ccd,-,1,1,1,{int(ref['feasible'])},"
                     f"{ref['phi']:.3f},0.000,{ref.get('phi_no_attack', ref['phi']):.3f},"
                     f"{pct:.2f},0.00,"
                     f"{ref['alpha']:.3f},{ref['phi_nominal']:.3f}")
        for provider in providers:
            slot = cache["llm"].get(testbed, {}).get(provider)
            if slot is None:
                continue
            s = _pct_stats(slot, ref["phi_nominal"])
            lines.append(f"{testbed},{provider},{slot['model']},{s.n},{s.valid},"
                         f"{s.contained},{s.feasible},{s.phi_mean:.3f},"
                         f"{s.phi_std:.3f},{s.phi_no_attack:.3f},"
                         f"{s.pct_mean:.2f},{s.pct_std:.2f},"
                         f"{ref['alpha']:.3f},{ref['phi_nominal']:.3f}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved data to {path}")


def report(cache: Dict, providers: List[str]) -> None:
    """Stdout summary per testbed: the CCD mode and each provider's proposals."""
    for testbed in _TESTBEDS:
        if testbed not in cache["ccd"]:
            continue
        ref = cache["ccd"][testbed]
        unit = _TESTBED_UNITS[testbed]
        print(f"\n{_TESTBED_LABELS[testbed]}: Phi_nominal={ref['phi_nominal']:.2f} {unit}, "
              f"alpha={ref['alpha']:.2f} {unit}")
        do = ref["intervention"]
        do_str = ", ".join(f"{k}={v}" for k, v in sorted(do.items())) if do else "-"
        print(f"  CCD D_1: do({do_str})  worst-case Phi-hat={ref['phi']:.2f} "
              f"({100.0 * ref['phi'] / ref['phi_nominal']:.1f}% of nominal), "
              f"no attack {ref.get('phi_no_attack', ref['phi']):.2f}")
        for provider in providers:
            slot = cache["llm"].get(testbed, {}).get(provider)
            if slot is None:
                continue
            s = _pct_stats(slot, ref["phi_nominal"])
            print(f"  {provider} ({slot['model']}): {s.valid}/{s.n} valid, "
                  f"{s.contained}/{s.n} contained, {s.feasible}/{s.n} feasible, "
                  f"worst-case Phi-hat={s.phi_mean:.2f}+-{s.phi_std:.2f} "
                  f"({s.pct_mean:.1f}+-{s.pct_std:.1f}% of nominal), "
                  f"no attack {s.phi_no_attack:.2f}")
            for rep in slot["reps"]:
                if rep.get("valid"):
                    do_str = ", ".join(f"{k}={v}" for k, v in sorted(rep["intervention"].items())) or "-"
                    flags = (f"contained={rep['contained']}, functional={rep['functional']}, "
                             f"no attack {rep.get('phi_no_attack', rep['phi']):.2f}")
                    print(f"    do({do_str})  worst-case Phi-hat={rep['phi']:.2f}  ({flags})")
                else:
                    print(f"    invalid: {rep['error']}")


def emit_prompts() -> None:
    """Write the three rendered prompts to tracked ``llm_prompt_<testbed>.txt`` files."""
    for testbed in _TESTBEDS:
        system = build_system(testbed)
        data = load_data(testbed)
        phi_nominal = testbed_nominal_phi(testbed, system, data)
        prompt = build_prompt(testbed, system, phi_nominal, system.alpha_fraction * phi_nominal)
        path = os.path.join(os.path.dirname(__file__), f"{_PROMPT_PREFIX}{testbed}.txt")
        with open(path, "w") as f:
            f.write(prompt)
        print(f"Saved prompt to {path}")


def run_tier(tier: str, args: argparse.Namespace, providers: List[str]) -> None:
    """Query, evaluate, report and plot one model tier into its own artifacts."""
    _bind_artifacts(tier)
    cache = _load_cache()

    if not args.plot_only:
        for testbed in _TESTBEDS:
            system = build_system(testbed)
            try:
                data = load_data(testbed)
                phi_nominal = testbed_nominal_phi(testbed, system, data)
                alpha = system.alpha_fraction * phi_nominal
                prompt = build_prompt(testbed, system, phi_nominal, alpha)
                run_ccd_reference(cache, testbed, system, data, phi_nominal, alpha,
                                  args.num_samples, args.refresh)
            except (FileNotFoundError, KeyError) as error:
                # e.g. a dataset collected before a model change (missing columns):
                # re-collect it on the testbed, then re-run
                print(f"  [{testbed}] skipped: dataset unusable ({error})")
                continue
            for provider in providers:
                api_key = os.getenv(f"{provider.upper()}_API_KEY", "")
                if not api_key:
                    print(f"  [{testbed}] {provider}: no API key in .env, skipping")
                    continue
                model = model_for(provider, tier)
                run_llm(cache, testbed, system, data, prompt, provider, model, api_key,
                        reps=args.reps, alpha=alpha, phi_nominal=phi_nominal,
                        num_samples=args.num_samples, refresh=args.refresh)

    if not cache["ccd"]:
        raise SystemExit(f"no {tier} results to plot (run without --plot-only first)")
    report(cache, providers)
    plot(cache, providers)
    write_csv(cache, providers)


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-as-operator baseline vs CCD (D_1).")
    parser.add_argument("--reps", type=int, default=5, help="queries per provider per testbed")
    parser.add_argument("--providers", default=",".join(_PROVIDERS),
                        help="comma-separated subset of anthropic,openai,gemini")
    parser.add_argument("--num-samples", type=int, default=None, help="GCM sample count")
    parser.add_argument("--refresh", action="store_true", help="ignore cached queries")
    parser.add_argument("--plot-only", action="store_true", help="plot from cache, no queries")
    parser.add_argument("--tier", default="frontier", choices=_TIERS + ["both"],
                        help="model tier to evaluate (default: frontier)")
    parser.add_argument("--emit-prompts", action="store_true",
                        help="write llm_prompt_{it,5g,ics}.txt and exit")
    args = parser.parse_args()
    if args.emit_prompts:
        emit_prompts()
        return

    load_dotenv(os.path.join(_ROOT, ".env"))
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    unknown = [p for p in providers if p not in _PROVIDERS]
    if unknown:
        raise SystemExit(f"unknown provider(s): {', '.join(unknown)}")
    tiers = _TIERS if args.tier == "both" else [args.tier]
    for tier in tiers:
        print(f"\n{'=' * 20} {tier} models {'=' * 20}")
        run_tier(tier, args, providers)


if __name__ == "__main__":
    main()
