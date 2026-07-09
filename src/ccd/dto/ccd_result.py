"""The ``CCDResult`` data-transfer object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ccd.dto.intervention import Intervention


@dataclass
class CCDResult:
    """Result of running CCD: the selected degraded mode and its estimated functionality."""

    intervention: Optional[Intervention]   # candidate mode (None if no mode satisfies the criteria)
    phi: float                             # estimated functionality Phi-hat(M_u) (nan if no candidate)
    alpha: float                           # critical functionality level
    feasible: bool                         # True iff a mode was found AND phi >= alpha
