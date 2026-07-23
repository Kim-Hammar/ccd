"""
Optional end-to-end docker smoke test (skipped unless ``CCD_TESTBED_SMOKE=1`` and
docker is available): bring up a tiny instance, collect a few windows, check that
throughput flows, run CCD, and enact the D_1 mode.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CCD_TESTBED_SMOKE") != "1" or shutil.which("docker") is None,
    reason="set CCD_TESTBED_SMOKE=1 with docker available to run the testbed smoke test",
)

_SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")


def _run(script: str, *args: str) -> None:
    subprocess.run([sys.executable, os.path.join(_SCRIPTS, script), *args], check=True)


@pytest.fixture()
def testbed():
    _run("testbed.py", "up", "--m", "2")
    try:
        yield 2
    finally:
        _run("testbed.py", "down")


def test_collect_and_enact(testbed, tmp_path):
    import pandas as pd
    csv = str(tmp_path / "smoke.csv")
    _run("generate_dataset.py", "--m", "2", "--windows", "3",
         "--window-seconds", "3", "--out", csv)
    data = pd.read_csv(csv)
    assert len(data) >= 1
    assert data["T"].max() > 0            # some throughput flows nominally

    result = str(tmp_path / "result.json")
    _run("run_ccd.py", "--data", csv, "--m", "2", "--num-samples", "1000",
         "--result-out", result)
    _run("enact_mode.py", "--result", result)
