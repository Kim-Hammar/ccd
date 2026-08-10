"""
Load a testbed's descriptor adapter and its dataset.
"""

from __future__ import annotations
import importlib.util
import os
import sys
from types import ModuleType
from typing import Optional
import pandas as pd
from ccd.discovery.descriptor import Descriptor
from ccd.util.validation_util import load_dataset

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
TESTBEDS = ("it_system", "ics", "5g_ran")


def _load_adapter(testbed: str) -> ModuleType:
    scripts = os.path.join(_REPO_ROOT, "testbeds", testbed, "scripts")
    if not os.path.isdir(scripts):
        raise ValueError(f"unknown testbed {testbed!r} (no {scripts})")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(
        f"{testbed}_descriptor_adapter", os.path.join(scripts, "descriptor.py"))
    assert spec is not None and spec.loader is not None
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter


def load_descriptor(testbed: str, m: int = 10) -> Descriptor:
    """Build a testbed's construction descriptor (``m`` applies to the IT system only)."""
    adapter = _load_adapter(testbed)
    descriptor: Descriptor = (adapter.build_descriptor(m) if testbed == "it_system"
                              else adapter.build_descriptor())
    descriptor.validate()
    return descriptor


def default_data_path(testbed: str) -> str:
    """The committed nominal dataset for ``testbed``."""
    return os.path.join(_REPO_ROOT, "testbeds", testbed, "data", "dataset.csv")


def load_testbed(testbed: str, m: int = 10,
                 data_path: Optional[str] = None) -> tuple[Descriptor, pd.DataFrame]:
    """Descriptor + dataset for ``testbed`` (dataset renames handled by the pipeline)."""
    desc = load_descriptor(testbed, m)
    return desc, load_dataset(data_path or default_data_path(testbed))
