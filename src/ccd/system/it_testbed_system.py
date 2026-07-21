"""
The two-layer system model for the dockerized IT-system testbed
(``testbeds/it_system/``).

The testbed realizes the illustrative example as a virtual network of containers:
``m`` Flask web-service replicas backed by a PostgreSQL database behind a
load-balancing gateway, with ``n_1`` doubling as a management host. The model is the
same two-layer graph as ``IllustrativeExampleSystem`` except for two deviations that
reflect *measurement* on a real system rather than simulation:

1. **Edges ``N_i -> Tt_i`` are added to the causal graph.** On the testbed, ``Tt_i`` is
   the *measured* rate of requests server ``n_i`` completes against the database. When
   the gateway link ``N_i`` is closed, no requests reach the server, so the measured
   ``Tt_i`` is physically 0 -- unlike the simulator's counterfactual carried load
   ``Tt_i = M_i * min(L_i, gam_i)``, which ignores ``N_i``. Without the edge, the
   ``N_i = 0`` zeros are unexplained by ``Tt_i``'s parents and end up in the fitted
   mechanism's noise term; interventional sampling then draws ``N_i`` and ``Tt_i``
   independently, biasing ``Phi-hat`` low by roughly the nominal open-fraction. With
   the edge, the fitted mechanism learns the gate. Mode selection is unchanged: every
   ``N_i`` is already an ancestor of ``T``, the new edges point *into* ``Tt_i`` so
   ``de(Tt_1)`` is unchanged, and AND deactivation via ``Th_i = N_i * Tt_i`` still cuts
   ``Tt_1 -> Th_1`` under ``do(N_1=0)``.

2. **The noise roots ``eps_i``/``gam_i`` are unobserved.** They remain nodes of the
   causal graph ``G`` (harmless for the graphical criteria -- they are in neither X, Y,
   nor J), but they are excluded from ``throughput_nodes``, so the DoWhy fit runs on
   the observed subgraph only and the noise is absorbed by the additive-noise
   mechanisms.

The dataset ``D`` is collected on the running testbed
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
