"""The ``CriteriaResult`` data-transfer object."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Set


@dataclass
class CriteriaResult:
    """Outcome of checking the two graphical criteria for a candidate intervention."""

    contained: bool
    functional: bool
    reachable: Set[str]
    blocked: Set[str]
    violating_exploits: Set[str]

    @property
    def ok(self) -> bool:
        return self.contained and self.functional
