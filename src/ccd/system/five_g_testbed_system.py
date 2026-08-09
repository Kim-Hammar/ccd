"""
The two-layer system model for the dockerized 5G cloud-RAN testbed
"""

from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from ccd.system.five_g_system import FiveGSystem


@dataclass
class FiveGTestbedSystem(FiveGSystem):
    """The 5G cloud-RAN example instantiated on the dockerized srsRAN/Open5GS testbed."""

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """The testbed model has no simulator: D is measured on the running containers."""
        raise NotImplementedError(
            "FiveGTestbedSystem has no simulator; collect the dataset on the testbed "
            "with testbeds/5g_ran/scripts/generate_dataset.py and pass the CSV to ccd()."
        )
