"""Repo policy enforcement helpers for RAES SDL.

The frozen tooling environment does not install the RAES distribution, so the
package puts the source tree on the import path. Its modules then import the
standard-library-only ``raes_contracts.errors`` and
``raes_contracts.operational_logging`` from that tree.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))
