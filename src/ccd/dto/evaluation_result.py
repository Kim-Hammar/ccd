"""The ``EvaluationResult`` data-transfer object."""

from __future__ import annotations
from dataclasses import dataclass
from ccd.dto.criteria_result import CriteriaResult
from ccd.dto.intervention import Intervention


@dataclass
class EvaluationResult:
    """Result of evaluating a fixed intervention: Phi-hat plus the two criteria verdicts."""

    intervention: Intervention     # the evaluated mode u = do(X' = R(X'))
    phi: float                     # estimated functionality Phi-hat(M_u), computed even if uncontained
    alpha: float                   # critical functionality level
    feasible: bool                 # phi >= alpha (functionality only; containment is in ``criteria``)
    criteria: CriteriaResult       # contained / functional / blocked / violating exploits
