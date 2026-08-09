"""
Parsing and validation for the LLM-as-operator baseline.
"""

from __future__ import annotations
import json
from typing import AbstractSet, Dict, List, Mapping, Optional, Set, Tuple
from ccd.system.five_g_system import FiveGSystem
from ccd.system.system_model import SystemModel


def _balanced_objects(text: str) -> List[str]:
    """Top-level balanced ``{...}`` substrings of ``text`` (string-literal aware)."""
    objects: List[str] = []
    depth, start, in_string, escaped = 0, -1, False, False
    for pos, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = pos
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                objects.append(text[start:pos + 1])
    return objects


def extract_llm_intervention(text: str) -> Tuple[Dict[str, object], str]:
    """Extract ``(proposal, justification)`` from a raw LLM reply. """
    candidates = [text.strip()]
    candidates += _balanced_objects(text)
    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("intervention"), dict):
            return dict(obj["intervention"]), str(obj.get("justification", ""))
    raise ValueError('no JSON object with an "intervention" mapping found in the LLM reply')


def legal_values(system: SystemModel) -> Dict[str, Set[int]]:
    """The enactable values per operator-controlled variable."""
    legal = {var: {system.degraded_value(var)} for var in system.operator_controlled}
    if isinstance(system, FiveGSystem):
        for i in range(1, system.num_du + 1):
            legal[system.QI(i)] = set(range(0, system.num_classes + 1))
            legal[system.AT(i)] = set(range(1, system.num_cu + 1))
    return legal


def _as_int(value: object) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def validate_llm_intervention(
    system: SystemModel,
    proposal: Mapping[str, object],
    legal: Optional[Mapping[str, AbstractSet[int]]] = None,
) -> Dict[str, int]:
    """Validate a proposed intervention and return it as ``{var: int}``."""
    if legal is None:
        legal = legal_values(system)
    errors: List[str] = []
    do: Dict[str, int] = {}
    for var in sorted(proposal):
        raw = proposal[var]
        if var not in system.operator_controlled:
            errors.append(f"{var}: not an operator-controlled variable")
            continue
        value = _as_int(raw)
        if value is None:
            errors.append(f"{var}: value {raw!r} is not an integer")
            continue
        allowed = legal.get(var, {system.degraded_value(var)})
        if value not in allowed:
            errors.append(f"{var}: value {value} is not enactable (legal: {sorted(allowed)}; "
                          "omit the variable to leave it at its nominal setting)")
            continue
        do[var] = value
    if errors:
        raise ValueError("invalid LLM intervention: " + "; ".join(errors))
    return do
