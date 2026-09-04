"""One dashboard for the whole car: LED control and battery monitoring.

The two subsystems live in their own packages under lights/ and electrical/
and still run standalone. This package composes them into a single process on
a single port so the driver can work the lights and watch the packs on one
screen without switching tabs.

Neither package is installed, so make both importable from the repo root.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for _sub in ("lights", "electrical"):
    _path = str(ROOT / _sub)
    if _path not in sys.path:
        sys.path.insert(0, _path)

__version__ = "1.0.0"
