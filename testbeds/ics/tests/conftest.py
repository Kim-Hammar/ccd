"""Put the testbed ``scripts/`` directory on sys.path for the pure-library tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
