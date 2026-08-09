"""The ``EvaluationResult`` data-transfer object."""

from __future__ import annotations
from dataclasses import dataclass
from ccd.dto.criteria_result import CriteriaResult
from ccd.dto.intervention import Intervention


@dataclass
class EvaluationResult:
    """Result of evaluating a fixed intervention: Phi-hat plus the two criteria verdicts."""

    intervention: Intervention
    phi: float
    alpha: float
    feasible: bool
    criteria: CriteriaResult
