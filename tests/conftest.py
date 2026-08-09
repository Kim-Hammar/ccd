"""
Shared fixtures for the top-level test suite.

``testbed_loader`` imports a testbed's ``scripts/<module>.py`` by file path under a unique
module name -- the three testbed adapters are all named ``descriptor.py`` (and share
sibling names like ``testbed_lib``/``ran_lib``), so a plain top-level import would clash.
The loader also puts the testbed's ``scripts/`` dir on ``sys.path`` so the adapter's own
``import testbed_lib``-style sibling imports resolve.
"""

from __future__ import annotations
import importlib.util
import os
import sys
from types import ModuleType
from typing import Callable
import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_testbed_module(testbed_dir: str, module_name: str) -> ModuleType:
    scripts = os.path.join(_REPO_ROOT, "testbeds", testbed_dir, "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    path = os.path.join(scripts, module_name + ".py")
    spec = importlib.util.spec_from_file_location(f"{testbed_dir}__{module_name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def testbed_loader() -> Callable[[str, str], ModuleType]:
    """Return ``load(testbed_dir, module_name) -> module`` for testbed script modules."""
    return _load_testbed_module
