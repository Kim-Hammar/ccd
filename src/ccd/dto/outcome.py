"""The ``Outcome`` data-transfer object for the sensitivity analysis."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Outcome:
    """Result of evaluating a misspecified-model CCD run against the true model."""

    infeasible: bool
    contained: bool
    functional: bool
    mode_size: Optional[int]

    @property
    def valid(self) -> bool:
        return (not self.infeasible) and self.contained and self.functional

    @property
    def silent_containment_failure(self) -> bool:
        return (not self.infeasible) and (not self.contained)

    @property
    def silent_functionality_failure(self) -> bool:
        return (not self.infeasible) and self.contained and (not self.functional)
