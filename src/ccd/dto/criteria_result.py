"""The ``CriteriaResult`` data-transfer object."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Set


@dataclass
class CriteriaResult:
    """Outcome of checking the two graphical criteria for a candidate intervention."""

    contained: bool                # containment criterion: ch_{Gamma_u}(ch_{Gamma_u}(P-tilde)) <= P-tilde
    functional: bool               # functionality criterion: J disjoint from de_{G_u}(Y \\ X')
    reachable: Set[str]            # de_{G_u}(Y \\ X'), the attacker's reachable set in the intervened graph
    blocked: Set[str]              # exploits made infeasible by the intervention (removed in Gamma_u)
    violating_exploits: Set[str]   # unblocked exploits with a precondition in P-tilde and a postcondition outside it

    @property
    def ok(self) -> bool:
        return self.contained and self.functional
