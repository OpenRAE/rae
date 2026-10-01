#!/usr/bin/env python3
"""Operator path admission and exact wheelhouse verification."""

from __future__ import annotations

import hashlib
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def operator_path(path: Path, *, purpose: str) -> Path:
    """Normalize and admit one operator-supplied path before any file access.

    Relative input is bound to the invoking working directory, a symlinked target
    is refused, and the result is canonicalized before any caller reads, stats, or
    writes it. Canonicalizing first is what keeps an operator-supplied path from
    reaching a filesystem sink with unresolved ``..`` components still in it; the
    containment rules each operation declares are then checked on the canonical
    path rather than on the raw argument.
    """

    anchored = path if path.is_absolute() else Path.cwd() / path
    if anchored.is_symlink():
        raise ValueError(f"{purpose} must not be a symbolic link")
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
        raise ValueError("candidate distribution must be a regular file")
    return sha256_file(path)


def require_empty_destination(path: Path, purpose: str) -> None:
    """Refuse to write into an existing non-empty destination."""

    if path.is_symlink() or path.exists() and any(path.iterdir()):
        raise ValueError(f"{purpose} must be an empty non-symlink directory")


def _require_wheelhouse_directory(wheelhouse: Path) -> None:
    try:
        mode = wheelhouse.lstat().st_mode
    except OSError as exc:
        raise ValueError("wheelhouse is missing") from exc
    if not stat.S_ISDIR(mode) or wheelhouse.is_symlink():
        raise ValueError("wheelhouse must be a regular directory")


def _expected_wheelhouse_artifacts(
    manifest: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("wheelhouse manifest has no artifacts")
    expected: dict[str, Mapping[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise ValueError("wheelhouse manifest artifact is invalid")
        filename = artifact.get("filename")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename or filename in expected:
            raise ValueError("wheelhouse manifest filenames must be unique portable basenames")
        expected[filename] = artifact
    return expected


def _require_wheelhouse_inventory(
    expected: Mapping[str, Mapping[str, Any]],
    observed: Mapping[str, Path],
) -> None:
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    if missing:
        raise ValueError(f"wheelhouse is missing {len(missing)} reviewed artifacts")
    if unexpected:
        raise ValueError(f"wheelhouse contains {len(unexpected)} unexpected artifacts")


def _require_wheelhouse_artifact(filename: str, path: Path, artifact: Mapping[str, Any]) -> None:
    mode = path.lstat().st_mode
    if path.is_symlink() or not stat.S_ISREG(mode):
        raise ValueError("wheelhouse entries must be regular files")
    if path.stat().st_size != artifact.get("size"):
        raise ValueError(f"wheelhouse artifact size mismatch: {filename}")
    if sha256_file(path) != artifact.get("sha256"):
        raise ValueError(f"wheelhouse artifact digest mismatch: {filename}")


def verify_wheelhouse(wheelhouse: Path, manifest: Mapping[str, Any]) -> None:
    """Reject a wheelhouse unless its regular files exactly match the manifest."""

    _require_wheelhouse_directory(wheelhouse)
    expected = _expected_wheelhouse_artifacts(manifest)
    observed = {path.name: path for path in wheelhouse.iterdir()}
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
