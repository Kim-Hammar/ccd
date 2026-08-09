"""
The two-layer system model for the dockerized industrial control system (ICS) testbed
"""

from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from ccd.system.ics_system import IcsSystem


@dataclass
class IcsTestbedSystem(IcsSystem):
    """The ICS (Tennessee Eastman) example instantiated on the dockerized testbed."""

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """The testbed model has no simulator: D is measured on the running containers."""
        raise NotImplementedError(
            "IcsTestbedSystem has no simulator; collect the dataset on the testbed with "
            "testbeds/ics/scripts/generate_dataset.py and pass the CSV to ccd()."
        )
