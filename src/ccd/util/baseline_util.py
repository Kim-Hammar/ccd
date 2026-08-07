"""
Parsing and validation for the LLM-as-operator baseline: extract a proposed
intervention ``do(X' = R(X'))`` from a raw LLM reply and validate it against the
system model (only operator-controlled variables ``X``, only enactable values).
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
    """Extract ``(proposal, justification)`` from a raw LLM reply.

    The reply must contain a JSON object ``{"intervention": {...}, "justification": ...}``;
    the object may be the whole reply, inside a fenced code block, or embedded in prose.
    Raises ``ValueError`` when no such object parses.
    """
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
    """The enactable values per operator-controlled variable.

    Default: only the degraded value ``D(x)`` (binary links can only be closed; the
    nominal value is expressed by omitting the variable). ``FiveGSystem``: the admission
    thresholds ``QI_i`` accept any class 0..Q and the attachments ``AT_i`` any CU 1..n_cu
    (both genuinely multi-valued and enactable).
    """
    legal = {var: {system.degraded_value(var)} for var in system.operator_controlled}
    if isinstance(system, FiveGSystem):
        for i in range(1, system.num_du + 1):
            legal[system.QI(i)] = set(range(0, system.num_classes + 1))
            legal[system.AT(i)] = set(range(1, system.num_cu + 1))
    return legal


def _as_int(value: object) -> Optional[int]:
    """``value`` as an ``int`` when it is an integral JSON number, else ``None``."""
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
    """Validate a proposed intervention and return it as ``{var: int}``.

    Every key must be operator-controlled (in ``X``) and every value integral and in the
    variable's legal set (``legal_values`` by default). The empty proposal ``{}`` is the
    legal ``do()``. Raises ``ValueError`` listing every violation.
    """
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
