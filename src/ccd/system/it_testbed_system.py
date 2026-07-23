"""
The two-layer system model for the dockerized IT-system testbed
(``testbeds/it_system/``).

Same two-layer graph as ``IllustrativeExampleSystem`` except for two measurement-driven
deviations:

1. Edges ``N_i -> Tt_i`` are added: measured carried load is physically 0 when the
   gateway link is closed (unlike the simulator's counterfactual
   ``Tt_i = M_i * min(L_i, gam_i)``). Without the edge those zeros land in the fitted
   mechanism's noise term and interventional sampling draws ``N_i``/``Tt_i``
   independently, biasing ``Phi-hat`` low by roughly the nominal open-fraction. Mode
   selection is unchanged: ``N_i`` is already an ancestor of ``T``, the edges point
   *into* ``Tt_i`` so ``de(Tt_1)`` is unchanged, and AND deactivation via
   ``Th_i = N_i * Tt_i`` still cuts ``Tt_1 -> Th_1`` under ``do(N_1=0)``.

2. The noise roots ``eps_i``/``gam_i`` are unobserved: they stay in ``G`` (in neither
   X, Y, nor J, so harmless for the criteria) but are excluded from
   ``throughput_nodes``; the additive-noise mechanisms absorb them.

``D`` is collected on the running testbed
(``testbeds/it_system/scripts/generate_dataset.py``), so ``generate_dataset`` raises.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar
import pandas as pd
from ccd.system.illustrative_example_system import IllustrativeExampleSystem


@dataclass
class ITTestbedSystem(IllustrativeExampleSystem):
    """The illustrative example instantiated on the dockerized IT-system testbed."""

    # the measured products Th_i = N_i * Tt_i are gated (Tt_i = 0 when N_i = 0), so use
    # the known functions as exact mechanisms to avoid the boosted-regressor knife-edge
    use_known_product_mechanisms: ClassVar[bool] = True

    def _build(self) -> None:
        super()._build()
        m = self.m
        # measured carried load is gated by the gateway link (deviation 1 above)
        for i in range(1, m + 1):
            self.graph.add_edge(self.N(i), self.Tt(i))
        # the noise roots are unobservable on the real system (deviation 2 above)
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
