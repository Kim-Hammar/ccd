"""
Release script for the ``ccd`` package.
"""

import io
import shutil
import subprocess

VERSION_FILE = "src/ccd/__version__.py"

# The version to release. Bump this before running the script.
NEW_VERSION = "0.1.0"

# Set to False to bump and build only, without uploading to PyPI.
UPLOAD = True


def read_version() -> str:
    """Return the version string currently declared in ``src/ccd/__version__.py``."""
    with io.open(VERSION_FILE, "r", encoding="utf-8") as f:
        # Grab the right-hand side of ``__version__ = "x.y.z"`` and strip quotes/whitespace.
        raw = f.read().strip().split("=")[-1].strip()
    return raw.replace("'", "").replace('"', "")


def write_version(old_version: str, new_version: str) -> None:
    """Replace ``old_version`` with ``new_version`` in ``src/ccd/__version__.py``."""
    with io.open(VERSION_FILE, "r", encoding="utf-8") as f:
        contents = f.read()
    with io.open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(contents.replace(old_version, new_version))


def run(cmd: str) -> int:
    """Run ``cmd`` in a shell, streaming its output, and return the exit code."""
    p = subprocess.Popen(cmd, shell=True)
    p.communicate()
    return p.wait()


if __name__ == "__main__":
    # Verify the version actually changes.
    print("Verifying version")
    old_version = read_version()
    if old_version == NEW_VERSION:
        raise ValueError(f"Release with version {old_version} of ccd already exists")

    # Update the single source of truth for the version.
    print(f"Updating {VERSION_FILE} from version {old_version} to {NEW_VERSION}")
    write_version(old_version, NEW_VERSION)

    # Delete the old build directory.
    print("Deleting old build directory")
    shutil.rmtree("dist", ignore_errors=True)

    # Build the source distribution and wheel.
    print("Building ccd")
    exit_code = run("python -m build")
    if exit_code != 0:
        raise SystemExit(f"There was an error building ccd; exit code: {exit_code}")
    print("ccd built successfully")

    # Upload to PyPI.
    if UPLOAD:
        print("Uploading ccd to PyPI")
        exit_code = run("python -m twine upload --config-file ~/.pypirc dist/*")
        if exit_code != 0:
            raise SystemExit(f"There was an error uploading ccd to PyPI; exit code: {exit_code}")
        print("Successfully uploaded ccd to PyPI")
    else:
        print("Skipping upload (UPLOAD=False); built artifacts are in dist/")
