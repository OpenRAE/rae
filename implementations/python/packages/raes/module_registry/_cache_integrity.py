"""Bounded integrity manifests and tree admission for OCI cache versions."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from raes_contracts.errors import OperationalError

from .._errors import SDLParseError
from ._filesystem import _O_BINARY, _O_NOFOLLOW, _same_file_identity

if TYPE_CHECKING:
    from . import _OCIResourceLimits

_CACHE_TREE_MANIFEST_NAME = ".raes-cache-tree.json"
_CACHE_TREE_SCHEMA = "raes-cache-tree/v1"
_CACHE_INTEGRITY_ERROR = "OCI module cache tree failed integrity validation"
_CACHE_MANIFEST_FIELDS = frozenset({"content_digest", "entries", "root_file", "schema", "tree_digest"})
_DECOMPRESSION_CHUNK_BYTES = 1024 * 1024


class _CacheIntegrityError(OperationalError):
    """Local OCI cache content does not match the inventory derived from verified bundle bytes."""


def _representable_directory_mode() -> int:
    """Return the safe directory mode representable by the current platform."""

    return {"nt": 0o777}.get(os.name, 0o700)


def _limits() -> _OCIResourceLimits:
    # Keep the historical package-facade test/operator seam authoritative.
    from . import _OCI_LIMITS

    return _OCI_LIMITS


def _hash_cache_file(path: Path, expected: os.stat_result) -> tuple[int, str]:
    """Hash one regular file without following a last-component symlink."""

    if expected.st_size > _limits().max_member_bytes:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
    flags = os.O_RDONLY | _O_BINARY | _O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR) from exc
    digest = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            actual = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(actual.st_mode)
                or not _same_file_identity(expected, actual)
                or actual.st_size != expected.st_size
                or stat.S_IMODE(actual.st_mode) != stat.S_IMODE(expected.st_mode)
            ):
                raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
            while chunk := handle.read(_DECOMPRESSION_CHUNK_BYTES):
                total += len(chunk)
                if total > _limits().max_member_bytes:
                    raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
                digest.update(chunk)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR) from exc
    if total != expected.st_size:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
    return total, f"sha256:{digest.hexdigest()}"


def _cache_lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR) from exc


def _append_bounded_child(children: list[Path], child_path: str, *, max_children: int) -> None:
    if len(children) >= max_children:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
    children.append(Path(child_path))


def _validated_directory_children(
    path: Path,
    *,
    before: os.stat_result,
    mode: int,
    max_children: int,
    excluded_names: frozenset[str],
) -> list[Path]:
    try:
        children: list[Path] = []
        with os.scandir(path) as iterator:
            for child in iterator:
                if child.name in excluded_names:
                    continue
                _append_bounded_child(children, child.path, max_children=max_children)
        children.sort(key=lambda child: child.name)
        after = path.lstat()
    except OSError as exc:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR) from exc
    if not stat.S_ISDIR(after.st_mode) or not _same_file_identity(before, after) or stat.S_IMODE(after.st_mode) != mode:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
    return children


def _cache_tree_node(
    path: Path,
    relative: PurePosixPath,
    *,
    max_children: int,
) -> tuple[dict[str, Any], list[Path], int]:
    before = _cache_lstat(path)
    mode = stat.S_IMODE(before.st_mode)
    relative_name = relative.as_posix()
    if stat.S_ISLNK(before.st_mode):
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
    if stat.S_ISREG(before.st_mode):
        size, digest = _hash_cache_file(path, before)
        entry = {"digest": digest, "mode": mode, "path": relative_name, "size": size, "type": "file"}
        return entry, [], size
    if not stat.S_ISDIR(before.st_mode):
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
    children = _validated_directory_children(
        path,
        before=before,
        mode=mode,
        max_children=max_children,
        excluded_names=frozenset({_CACHE_TREE_MANIFEST_NAME}) if relative == PurePosixPath(".") else frozenset(),
    )
    return {"mode": mode, "path": relative_name, "type": "directory"}, children, 0


def _child_relative_path(parent: PurePosixPath, child: Path) -> PurePosixPath:
    if parent == PurePosixPath("."):
        return PurePosixPath(child.name)
    return parent / child.name


def _cache_tree_entries(root: Path) -> list[dict[str, Any]]:
    """Return a canonical, bounded inventory of a cache version's extracted tree."""

    limits = _limits()
    if limits.max_bundle_members < 0 or limits.max_tree_depth < 0:
        raise ValueError("OCI cache tree limits must be non-negative")
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    pending: list[tuple[Path, PurePosixPath, int]] = [(root, PurePosixPath("."), 0)]
    entry_limit = limits.max_bundle_members + 1
    while pending:
        path, relative, depth = pending.pop()
        if depth > limits.max_tree_depth:
            raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
        entry, children, size = _cache_tree_node(
            path,
            relative,
            max_children=entry_limit - len(entries) - len(pending) - 1,
        )
        total_bytes += size
        if total_bytes > limits.max_total_bytes:
            raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
        entries.append(entry)
        for child in reversed(children):
            pending.append((child, _child_relative_path(relative, child), depth + 1))
    return entries


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _cache_tree_manifest(*, root: Path, content_digest: str, root_file: str) -> dict[str, Any]:
    entries = _cache_tree_entries(root)
    return {
        "content_digest": content_digest,
        "entries": entries,
        "root_file": root_file,
        "schema": _CACHE_TREE_SCHEMA,
        "tree_digest": f"sha256:{hashlib.sha256(_canonical_json_bytes(entries)).hexdigest()}",
    }


def _write_cache_tree_manifest(*, root: Path, content_digest: str, root_file: str) -> None:
    manifest_path = root / _CACHE_TREE_MANIFEST_NAME
    if manifest_path.exists() or manifest_path.is_symlink():
        raise SDLParseError("OCI module bundle contains a reserved cache metadata path")
    manifest_bytes = _canonical_json_bytes(
        _cache_tree_manifest(root=root, content_digest=content_digest, root_file=root_file)
    )
    if len(manifest_bytes) > _limits().max_metadata_bytes:
        raise SDLParseError("OCI module cache integrity manifest exceeds the metadata limit")
    try:
        manifest_path.write_bytes(manifest_bytes)
    except OSError as exc:
        raise OperationalError("Unable to write the OCI module cache integrity manifest") from exc


def _read_cache_manifest_bytes(path: Path) -> bytes:
    """Read a small regular manifest without following a last-component link."""

    try:
        expected = path.lstat()
    except OSError as exc:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR) from exc
    if not stat.S_ISREG(expected.st_mode):
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
    flags = os.O_RDONLY | _O_BINARY | _O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            actual = os.fstat(handle.fileno())
            if not stat.S_ISREG(actual.st_mode) or not _same_file_identity(expected, actual):
                raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
            payload = handle.read(_limits().max_metadata_bytes + 1)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR) from exc
    if len(payload) > _limits().max_metadata_bytes:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
    return payload


def _trusted_entry_projection(entries: list[Any]) -> list[dict[str, Any]]:
    """Project a local inventory onto properties determined by bundle bytes."""

    projected: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
        if entry.get("type") == "directory" and isinstance(entry.get("mode"), int):
            projected.append({"mode": entry["mode"], "path": entry["path"], "type": "directory"})
        elif entry.get("type") == "file" and all(
            isinstance(entry.get(field), field_type)
            for field, field_type in (("digest", str), ("mode", int), ("size", int))
        ):
            projected.append(
                {
                    "digest": entry["digest"],
                    "mode": entry["mode"],
                    "path": entry["path"],
                    "size": entry["size"],
                    "type": "file",
                }
            )
        else:
            raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)
    return projected


def _require_cache_integrity(condition: bool) -> None:
    if not condition:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR)


def _require_cache_manifest(value: object) -> dict[str, Any]:
    _require_cache_integrity(isinstance(value, dict))
    manifest: dict[str, Any] = value
    _require_cache_integrity(set(manifest) == _CACHE_MANIFEST_FIELDS)
    _require_cache_integrity(manifest["schema"] == _CACHE_TREE_SCHEMA)
    _require_cache_integrity(isinstance(manifest["entries"], list))
    return manifest


def _expected_manifest_projection(expected_manifest: object) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _require_cache_manifest(expected_manifest)
    entries = manifest["entries"]
    expected_tree_digest = f"sha256:{hashlib.sha256(_canonical_json_bytes(entries)).hexdigest()}"
    _require_cache_integrity(manifest["tree_digest"] == expected_tree_digest)
    return manifest, _trusted_entry_projection(entries)


def _read_trusted_cache_manifest(version: Path) -> dict[str, Any]:
    raw = _read_cache_manifest_bytes(version / _CACHE_TREE_MANIFEST_NAME)
    try:
        decoded = json.loads(raw.decode("utf-8"))
        manifest = _require_cache_manifest(decoded)
        canonical = _canonical_json_bytes(manifest)
    except (RecursionError, ValueError) as exc:
        raise _CacheIntegrityError(_CACHE_INTEGRITY_ERROR) from exc
    _require_cache_integrity(raw == canonical)
    return manifest


def _require_matching_manifest_identity(
    manifest: dict[str, Any],
    expected_manifest: dict[str, Any],
) -> None:
    identity_fields = ("content_digest", "root_file", "schema")
    _require_cache_integrity(all(manifest[field] == expected_manifest[field] for field in identity_fields))


def _require_matching_cache_inventory(
    *,
    version: Path,
    manifest: dict[str, Any],
    expected_entries: list[dict[str, Any]],
) -> None:
    entries = _cache_tree_entries(version)
    _require_cache_integrity(manifest["entries"] == entries)
    tree_digest = f"sha256:{hashlib.sha256(_canonical_json_bytes(entries)).hexdigest()}"
    _require_cache_integrity(manifest["tree_digest"] == tree_digest)
    _require_cache_integrity(_trusted_entry_projection(entries) == expected_entries)


def _validated_root_path(version: Path, root_relative: PurePosixPath) -> Path:
    root_path = version.joinpath(*root_relative.parts)
    _require_cache_integrity(not root_path.is_symlink())
    _require_cache_integrity(root_path.is_file())
    _require_cache_integrity(root_path.resolve(strict=True).is_relative_to(version.resolve(strict=True)))
    return root_path


def _validated_cache_root(
    *,
    version: Path,
    expected_manifest: dict[str, Any],
    root_relative: PurePosixPath,
) -> Path | None:
    """Return the root only when it matches inventory derived from verified bytes."""

    try:
        trusted_expected, expected_entries = _expected_manifest_projection(expected_manifest)
        manifest = _read_trusted_cache_manifest(version)
        _require_matching_manifest_identity(manifest, trusted_expected)
        _require_matching_cache_inventory(
            version=version,
            manifest=manifest,
            expected_entries=expected_entries,
        )
        root_path = _validated_root_path(version, root_relative)
    except OSError, _CacheIntegrityError:
        return None
    return root_path
