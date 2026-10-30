"""Support package for the repository noxfile (constants, runner, lanes).

Nox runs in the frozen tooling environment, which does not install the RAES
distribution, so the package puts the source tree on the import path. Its
modules then import the standard-library-only ``raes_contracts.errors``.
Nox owns logging for its sessions; these modules do not configure logging.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RAES_PACKAGES_ROOT = _REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (_REPO_ROOT, _RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))
