"""Generate the observational dataset ``D`` of nominal system operation."""

from __future__ import annotations
import numpy as np
import pandas as pd
from ccd import system as S
from ccd.system import SystemModel

# Nominal-operation parameters.
_W_LOW, _W_HIGH = 100.0, 1000.0          # workload W ~ U[100, 1000] (req/s)
_LOAD_NOISE_SD = 2.0                     # SD of load-split noise eps_i
_CAP_MEAN, _CAP_SD = 600.0, 50.0         # processing capacity gamma_i (rarely the bottleneck)
_PCLOSE_LOW_W, _PCLOSE_HIGH_W = 0.30, 0.05   # maintenance-closure prob at low / high workload


def generate_dataset(system: SystemModel, steps: int = 10_000, seed: int = 0) -> pd.DataFrame:
    """Return a DataFrame of ``steps`` rows of nominal operation for ``system``."""
    m = system.m
    rng = np.random.RandomState(seed)

    workload = rng.uniform(_W_LOW, _W_HIGH, steps)
    # closure probability decreases linearly with workload
    frac = (workload - _W_LOW) / (_W_HIGH - _W_LOW)
    p_close = _PCLOSE_LOW_W - (_PCLOSE_LOW_W - _PCLOSE_HIGH_W) * frac

    data: dict[str, np.ndarray] = {S.W(): workload}
    total = np.zeros(steps)

    for i in range(1, m + 1):
        eps = rng.normal(0.0, _LOAD_NOISE_SD, steps)
        cap = rng.normal(_CAP_MEAN, _CAP_SD, steps)
        load = np.maximum(0.0, workload / m + eps)          # L_i ~ W/m, split evenly
        n_open = (rng.uniform(0.0, 1.0, steps) > p_close).astype(int)   # gateway -> n_i
        m_open = (rng.uniform(0.0, 1.0, steps) > p_close).astype(int)   # n_i -> database
        carried = m_open * np.minimum(load, cap)            # Tt_i = M_i * min(L_i, gam_i)
        throughput = n_open * carried                       # Th_i = N_i * Tt_i
        total += throughput

        data[S.eps(i)] = eps
        data[S.gam(i)] = cap
        data[S.L(i)] = load
        data[S.N(i)] = n_open
        data[S.M(i)] = m_open
        data[S.Tt(i)] = carried
        data[S.Th(i)] = throughput

    data[S.T()] = total
    return pd.DataFrame(data)
