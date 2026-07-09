"""The ``Intervention`` data-transfer object."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
from ccd.util.sort_util import sort_key


@dataclass(frozen=True)
class Intervention:
    """A degraded-mode intervention do(X' = R(X')); here R closes each link (value 0)."""

    variables: Dict[str, int]

    def __str__(self) -> str:
        assigns = ", ".join(f"{v}={self.variables[v]}" for v in sorted(self.variables, key=sort_key))
        return f"do({assigns})"
