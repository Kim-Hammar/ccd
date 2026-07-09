"""The ``CriteriaResult`` data-transfer object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Set


@dataclass
class CriteriaResult:
    """Outcome of checking the two graphical criteria for a candidate intervention."""

    contained: bool          # containment criterion: containment_targets (unattained + lateral) disjoint from de(Y)
    functional: bool         # functionality criterion: J disjoint from de(Y)
    reachable: Set[str]      # de_{G_u}(Y), the attacker's reachable set in the intervened graph

    @property
    def ok(self) -> bool:
        return self.contained and self.functional
