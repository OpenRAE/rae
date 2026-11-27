"""Support package for the published-schema coverage gate (ASR-501, issue #1330).

``tools/check_schema_coverage.py`` is the entry point; the closed key sets, the
evidence checks, and the declaration validator live here so no single module
carries the whole rule.

The package puts the source tree on the import path, so its modules import the
standard-library-only ``raes_contracts.errors`` also in the frozen tooling
environment, which does not install the RAES distribution.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))
