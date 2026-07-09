"""The ``Outcome`` data-transfer object for the sensitivity analysis."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Outcome:
    """Result of evaluating a misspecified-model CCD run against the true model."""

    infeasible: bool          # CCD returned no mode (bottom) -- a detected, non-silent failure
    contained: bool           # selected mode contains the attack in the TRUE model
    functional: bool          # selected mode preserves functionality in the TRUE model
    mode_size: Optional[int]  # number of links closed (None if infeasible)

    @property
    def valid(self) -> bool:
        return (not self.infeasible) and self.contained and self.functional

    @property
    def silent_containment_failure(self) -> bool:
        return (not self.infeasible) and (not self.contained)

    @property
    def silent_functionality_failure(self) -> bool:
        return (not self.infeasible) and self.contained and (not self.functional)
