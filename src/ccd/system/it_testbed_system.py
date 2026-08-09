"""
The two-layer system model for the dockerized IT-system testbed
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
import pandas as pd
from ccd.system.it_system import ITSystem


@dataclass
class ITTestbedSystem(ITSystem):
    """The IT system instantiated on the dockerized IT-system testbed."""

    use_known_product_mechanisms: ClassVar[bool] = True

    def _build(self) -> None:
        super()._build()
        m = self.m
        for i in range(1, m + 1):
            self.graph.add_edge(self.N(i), self.Tt(i))
        self.throughput_nodes = self.throughput_nodes - (
            {self.eps(i) for i in range(1, m + 1)}
            | {self.gam(i) for i in range(1, m + 1)}
        )

    def generate_dataset(self, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
        """The testbed model has no simulator: D is measured on the running containers."""
        raise NotImplementedError(
            "ITTestbedSystem has no simulator; collect the dataset on the testbed with "
            "testbeds/it_system/scripts/generate_dataset.py and pass the CSV to ccd()."
        )
