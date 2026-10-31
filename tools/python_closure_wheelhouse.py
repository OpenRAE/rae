#!/usr/bin/env python3
"""Operator path admission and exact wheelhouse verification."""

from __future__ import annotations

import hashlib
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError, OperationalError  # noqa: E402


def _working_directory(purpose: str) -> Path:
    try:
        return Path.cwd()
    except OSError as exc:
        # The invoking working directory no longer exists, so a relative operator path has no anchor.
        raise OperationalError(f"{purpose} cannot be resolved without a working directory") from exc


def operator_path(path: Path, *, purpose: str) -> Path:
    """Normalize and admit one operator-supplied path before any file access.

    Relative input is bound to the invoking working directory, a symlinked target
    is refused, and the result is canonicalized before any caller reads, stats, or
    writes it. Canonicalizing first is what keeps an operator-supplied path from
    reaching a filesystem sink with unresolved ``..`` components still in it; the
    containment rules each operation declares are then checked on the canonical
    path rather than on the raw argument.
    """

    anchored = path if path.is_absolute() else _working_directory(purpose) / path
    if anchored.is_symlink():
        raise InvalidInputError(f"{purpose} must not be a symbolic link")
    return anchored.resolve(strict=False)


def sha256_file(path: Path) -> str:
    """Digest an already-admitted regular file in bounded chunks."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_digest(path: Path) -> str:
    """Digest an admitted candidate distribution, refusing anything irregular."""

    if path.is_symlink() or not path.is_file():
        raise InvalidInputError("candidate distribution must be a regular file")
    try:
        return sha256_file(path)
    except OSError as exc:
        raise InvalidInputError("candidate distribution is unreadable") from exc


def require_empty_destination(path: Path, purpose: str) -> None:
    """Refuse to write into an existing non-empty destination."""

    refusal = f"{purpose} must be an empty non-symlink directory"
    if path.is_symlink():
        raise InvalidInputError(refusal)
    if not path.exists():
        return
    try:
        occupied = not path.is_dir() or any(path.iterdir())
    except OSError as exc:
        # A destination that cannot be listed cannot be shown to be empty.
        raise InvalidInputError(refusal) from exc
    if occupied:
        raise InvalidInputError(refusal)


def _require_wheelhouse_directory(wheelhouse: Path) -> None:
    try:
        mode = wheelhouse.lstat().st_mode
    except OSError as exc:
        raise InvalidInputError("wheelhouse is missing") from exc
    if not stat.S_ISDIR(mode) or wheelhouse.is_symlink():
        raise InvalidInputError("wheelhouse must be a regular directory")


def _expected_wheelhouse_artifacts(
    manifest: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise InvalidInputError("wheelhouse manifest has no artifacts")
    expected: dict[str, Mapping[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise InvalidInputError("wheelhouse manifest artifact is invalid")
        filename = artifact.get("filename")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename or filename in expected:
            raise InvalidInputError("wheelhouse manifest filenames must be unique portable basenames")
        expected[filename] = artifact
    return expected


def _require_wheelhouse_inventory(
    expected: Mapping[str, Mapping[str, Any]],
    observed: Mapping[str, Path],
) -> None:
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    if missing:
        raise InvalidInputError(f"wheelhouse is missing {len(missing)} reviewed artifacts")
    if unexpected:
        raise InvalidInputError(f"wheelhouse contains {len(unexpected)} unexpected artifacts")


def _require_wheelhouse_artifact(filename: str, path: Path, artifact: Mapping[str, Any]) -> None:
    unreadable = f"wheelhouse artifact is unreadable: {filename}"
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise InvalidInputError(unreadable) from exc
    if path.is_symlink() or not stat.S_ISREG(mode):
        raise InvalidInputError("wheelhouse entries must be regular files")
    try:
        size = path.stat().st_size
        digest = sha256_file(path) if size == artifact.get("size") else None
    except OSError as exc:
        raise InvalidInputError(unreadable) from exc
    if size != artifact.get("size"):
        raise InvalidInputError(f"wheelhouse artifact size mismatch: {filename}")
    if digest != artifact.get("sha256"):
        raise InvalidInputError(f"wheelhouse artifact digest mismatch: {filename}")


def verify_wheelhouse(wheelhouse: Path, manifest: Mapping[str, Any]) -> None:
    """Reject a wheelhouse unless its regular files exactly match the manifest."""

    _require_wheelhouse_directory(wheelhouse)
    expected = _expected_wheelhouse_artifacts(manifest)
    try:
        observed = {path.name: path for path in wheelhouse.iterdir()}
    except OSError as exc:
        raise InvalidInputError("wheelhouse is unreadable") from exc
    _require_wheelhouse_inventory(expected, observed)
    for filename, artifact in expected.items():
        _require_wheelhouse_artifact(filename, observed[filename], artifact)


__all__ = (
    "candidate_digest",
    "operator_path",
    "require_empty_destination",
    "sha256_file",
    "verify_wheelhouse",
)
