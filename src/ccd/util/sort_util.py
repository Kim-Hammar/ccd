"""Ordering helper for link variables."""

from __future__ import annotations
import re
from typing import Tuple


def sort_key(var: str) -> Tuple[str, int]:
    """Order link variables by letter then numeric index (N1, M1, A2, A3, ...)."""
    match = re.match(r"([A-Za-z]+)(\d+)", var)
    if match:
        return (match.group(1), int(match.group(2)))
    return (var, 0)
