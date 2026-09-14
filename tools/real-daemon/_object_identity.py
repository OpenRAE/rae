"""Pure object-identity verification for the live-runner harness (issue #1222).

Deliberately free of the ``libvirt`` import (unlike ``libvirt_smoke.py``) so the
fail-closed size/sha256 gate can be exercised by the hermetic test suite. Both
the smoke harness and its tests import this helper.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def verify_object_identity(path: str | Path, *, expected_sha256: str | None, expected_size: int | None) -> None:
    """Fail closed unless ``path`` is a regular file matching the pinned identity.

    Rejects a missing file, a symlink, an unpinned identity (either expected
    value absent), a size mismatch, or a digest mismatch. Returns ``None`` on a
    verified match.
    """

    image = Path(path)
    if not image.is_file() or image.is_symlink():
        raise RuntimeError(f"object is missing or not a regular file: {path}")
    if not expected_sha256 or expected_size is None:
        raise RuntimeError("object identity is not pinned: an expected sha256 and size are required")
    actual_size = image.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(f"object size {actual_size} != expected {expected_size}")
    digest = hashlib.sha256()
    with image.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise RuntimeError(f"object sha256 {actual_sha256} != expected {expected_sha256}")
