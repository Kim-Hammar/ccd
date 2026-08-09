"""The ``CCDResult`` data-transfer object."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from ccd.dto.intervention import Intervention


@dataclass
class CCDResult:
    """Result of running CCD: the selected degraded mode and its estimated functionality."""

    intervention: Optional[Intervention]
    phi: float
    alpha: float
    feasible: bool
