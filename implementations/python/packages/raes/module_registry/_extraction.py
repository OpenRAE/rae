"""Resource bounds and tar-member admission for OCI module extraction."""

from __future__ import annotations

import os
import stat
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .._errors import SDLParseError
from ._cache_integrity import _CACHE_TREE_MANIFEST_NAME
from ._filesystem import _same_file_identity

_HTTP_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class _OCIResourceLimits:
    """Bounds for remote OCI fetches and bundle extraction (issue #12).

    The OCI import path pulls attacker-influenceable bytes from allowlisted
    registries; without caps a compromised registry, mirror, or oversized module
    can exhaust process memory (buffering an unbounded response) or disk/CPU
    (extracting an unbounded bundle). Compressed-download limits are kept separate
    from extracted-archive limits because a small gzip can expand into a large tar
    payload. This is the single extensibility seam: operator-tunable overrides
    should later extend ``RegistryTrustPolicy`` and merge with these defaults,
    rather than threading limit arguments through parser/compiler/runtime/CLI.
    """

    timeout_seconds: int = _HTTP_TIMEOUT_SECONDS
    max_metadata_bytes: int = 8 * 1024 * 1024
    max_bundle_bytes: int = 128 * 1024 * 1024
    max_bundle_members: int = 8192
    max_member_bytes: int = 64 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_tar_stream_bytes: int = 320 * 1024 * 1024
    max_gzip_expansion_ratio: int = 1024
    max_tree_depth: int = 256


def _invalid_member_name(member: tarfile.TarInfo) -> bool:
    pure_name = PurePosixPath(member.name)
    source_name = member.name.removesuffix("/") if member.isdir() else member.name
    windows_absolute = bool(pure_name.parts) and len(pure_name.parts[0]) == 2 and pure_name.parts[0][1] == ":"
    return any(
        (
            not member.name,
            "\x00" in member.name,
            "\\" in member.name,
            pure_name.is_absolute(),
            ".." in pure_name.parts,
            source_name != pure_name.as_posix(),
            windows_absolute,
        )
    )


def _validated_member_path(
    member: tarfile.TarInfo,
    *,
    dest: Path,
    resolved_dest: Path,
    limits: _OCIResourceLimits,
) -> Path:
    member_path = (dest / member.name).resolve()
    if not member_path.is_relative_to(resolved_dest):
        raise SDLParseError(f"Path traversal detected in OCI bundle tar member: {member.name!r}")
    if len(member_path.relative_to(resolved_dest).parts) > limits.max_tree_depth:
        raise SDLParseError(
            f"OCI bundle member {member.name!r} exceeds the {limits.max_tree_depth}-component path-depth limit"
        )
    if member_path == (dest / _CACHE_TREE_MANIFEST_NAME).resolve():
        raise SDLParseError("OCI module bundle contains a reserved cache metadata path")
    return member_path


def _require_supported_member_type(member: tarfile.TarInfo) -> None:
    if member.issym() or member.islnk():
        raise SDLParseError(f"Links are not allowed in OCI bundle tar: {member.name!r}")
    if not (member.isfile() or member.isdir()):
        raise SDLParseError(f"Unsupported tar member type in OCI bundle: {member.name!r}")


def _record_unique_member(member: tarfile.TarInfo, member_path: Path, seen_paths: set[str]) -> None:
    normalized = member_path.as_posix()
    if normalized in seen_paths:
        raise SDLParseError(f"Duplicate tar member path in OCI bundle: {member.name!r}")
    seen_paths.add(normalized)


def _require_bounded_member_size(member: tarfile.TarInfo, limits: _OCIResourceLimits) -> None:
    if member.isfile() and member.size > limits.max_member_bytes:
        raise SDLParseError(
            f"OCI bundle member {member.name!r} exceeds the {limits.max_member_bytes}-byte per-member limit"
        )


def _normalize_extracted_directory_modes(root: Path, entries: list[dict[str, Any]]) -> None:
    """Apply and verify bundle-derived safe modes on every extracted directory."""

    for entry in entries:
        if entry["type"] != "directory":
            continue
        relative = PurePosixPath(entry["path"])
        path = root if relative == PurePosixPath(".") else root.joinpath(*relative.parts)
        try:
            before = path.lstat()
            if not stat.S_ISDIR(before.st_mode):
                raise SDLParseError("OCI cache directory mode normalization found a non-directory entry")
            if os.name != "nt":
                os.chmod(path, entry["mode"], follow_symlinks=False)
            after = path.lstat()
        except (NotImplementedError, OSError, TypeError) as exc:
            raise SDLParseError("Unable to normalize OCI cache directory permissions") from exc
        if (
            not stat.S_ISDIR(after.st_mode)
            or not _same_file_identity(before, after)
            or stat.S_IMODE(after.st_mode) != entry["mode"]
        ):
            raise SDLParseError("OCI cache directory permissions changed during normalization")


def _extract_tar_to_stage(
    tar: tarfile.TarFile,
    *,
    members: list[tarfile.TarInfo],
    staging: Path,
    expected_entries: list[dict[str, Any]],
) -> None:
    tar.extractall(staging, members=members, filter="data")
    _normalize_extracted_directory_modes(staging, expected_entries)


def _validate_tar_member_shape(
    member: tarfile.TarInfo,
    *,
    dest: Path,
    resolved_dest: Path,
    seen_paths: set[str],
    limits: _OCIResourceLimits,
) -> None:
    """Fail closed on an unsafe or oversized single tar member (issues #12/#13).

    Rejects path traversal, symlinks, hard links, special files, and duplicate
    normalized paths, and enforces the per-member extracted-size cap. Records the
    member's normalized path in ``seen_paths`` so a later duplicate is caught.
    """

    if _invalid_member_name(member):
        raise SDLParseError(f"Path traversal detected in OCI bundle tar member: {member.name!r}")
    member_path = _validated_member_path(member, dest=dest, resolved_dest=resolved_dest, limits=limits)
    _require_supported_member_type(member)
    _record_unique_member(member, member_path, seen_paths)
    _require_bounded_member_size(member, limits)


def _safe_tar_members_with_limits(
    tar: tarfile.TarFile,
    dest: Path,
    *,
    limits: _OCIResourceLimits,
) -> list[tarfile.TarInfo]:
    """Validate every member before extraction under explicit resource limits."""

    safe: list[tarfile.TarInfo] = []
    resolved_dest = dest.resolve()
    seen_paths: set[str] = set()
    total_bytes = 0
    # Iterate lazily so an unbounded member list or extraction is rejected as
    # soon as a cap is crossed, before the rest of the archive is decompressed.
    for member_count, member in enumerate(tar, start=1):
        if member_count > limits.max_bundle_members:
            raise SDLParseError(f"OCI bundle exceeds the maximum of {limits.max_bundle_members} archive members")
        _validate_tar_member_shape(
            member,
            dest=dest,
            resolved_dest=resolved_dest,
            seen_paths=seen_paths,
            limits=limits,
        )
        if member.isfile():
            total_bytes += member.size
            if total_bytes > limits.max_total_bytes:
                raise SDLParseError(f"OCI bundle exceeds the {limits.max_total_bytes}-byte total extraction limit")
        member.mode &= 0o777
        safe.append(member)
    return safe


__all__ = [
    "_HTTP_TIMEOUT_SECONDS",
    "_OCIResourceLimits",
    "_extract_tar_to_stage",
    "_normalize_extracted_directory_modes",
    "_safe_tar_members_with_limits",
    "_validate_tar_member_shape",
]
