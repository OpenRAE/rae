"""Trusted OCI archive inventory derived without extracting filesystem content."""

from __future__ import annotations

import os
import tarfile
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from raes_contracts.digests import sha256_digest, sha256_hasher

from .._errors import SDLParseError
from ._cache_integrity import (
    _CACHE_TREE_SCHEMA,
    _DECOMPRESSION_CHUNK_BYTES,
    _canonical_json_bytes,
    _representable_directory_mode,
)

if TYPE_CHECKING:
    from . import _OCIResourceLimits

_ARCHIVE_PATH_CONFLICT_ERROR = "OCI bundle contains conflicting file and directory paths"


def _limits() -> _OCIResourceLimits:
    from . import _OCI_LIMITS

    return _OCI_LIMITS


def _filtered_file_mode(mode: int) -> int:
    """Return the host representation of the PEP 706-filtered regular-file mode."""

    filtered = mode & 0o755
    if not filtered & 0o100:
        filtered &= ~0o111
    return {"nt": 0o666}.get(os.name, filtered | 0o600)


def _add_directory_node(nodes: dict[str, dict[str, Any]], relative: PurePosixPath) -> None:
    relative_name = relative.as_posix()
    existing = nodes.get(relative_name)
    if existing is not None and existing["type"] != "directory":
        raise SDLParseError(_ARCHIVE_PATH_CONFLICT_ERROR)
    nodes[relative_name] = {
        "mode": _representable_directory_mode(),
        "path": relative_name,
        "type": "directory",
    }


def _add_parent_directories(nodes: dict[str, dict[str, Any]], relative: PurePosixPath) -> None:
    for parent in reversed(relative.parents):
        if parent != PurePosixPath("."):
            _add_directory_node(nodes, parent)


def _hash_archive_member(tar: tarfile.TarFile, member: tarfile.TarInfo) -> tuple[int, str]:
    extracted = tar.extractfile(member)
    if extracted is None:
        raise SDLParseError("Unable to read a regular file from the OCI module bundle")
    digest = sha256_hasher()
    size = 0
    with extracted:
        while chunk := extracted.read(_DECOMPRESSION_CHUNK_BYTES):
            size += len(chunk)
            if size > member.size:
                raise SDLParseError("OCI bundle member payload exceeds its declared size")
            digest.update(chunk)
    if size != member.size:
        raise SDLParseError("OCI bundle member payload is shorter than its declared size")
    return size, f"sha256:{digest.hexdigest()}"


def _add_archive_member(
    nodes: dict[str, dict[str, Any]],
    *,
    tar: tarfile.TarFile,
    member: tarfile.TarInfo,
    relative: PurePosixPath,
) -> None:
    if member.isdir():
        _add_directory_node(nodes, relative)
        return
    relative_name = relative.as_posix()
    if relative_name in nodes:
        raise SDLParseError(_ARCHIVE_PATH_CONFLICT_ERROR)
    size, digest = _hash_archive_member(tar, member)
    nodes[relative_name] = {
        "digest": digest,
        "mode": _filtered_file_mode(member.mode),
        "path": relative_name,
        "size": size,
        "type": "file",
    }


def _is_archive_root(member: tarfile.TarInfo, relative: PurePosixPath) -> bool:
    if relative != PurePosixPath("."):
        return False
    if not member.isdir():
        raise SDLParseError("OCI bundle cannot replace the cache tree root")
    return True


def _expected_cache_tree_manifest(
    *,
    tar: tarfile.TarFile,
    members: list[tarfile.TarInfo],
    content_digest: str,
    root_file: str,
) -> dict[str, Any]:
    """Hash a verified tar into the platform-neutral cache integrity inventory."""

    nodes: dict[str, dict[str, Any]] = {
        ".": {"mode": _representable_directory_mode(), "path": ".", "type": "directory"}
    }
    entry_limit = _limits().max_bundle_members + 1
    for member in members:
        relative = PurePosixPath(member.name)
        if _is_archive_root(member, relative):
            continue
        _add_parent_directories(nodes, relative)
        _add_archive_member(nodes, tar=tar, member=member, relative=relative)
        if len(nodes) > entry_limit:
            raise SDLParseError("OCI bundle exceeds the bounded extracted-tree entry limit")
    entries = [nodes[name] for name in sorted(nodes, key=lambda name: PurePosixPath(name).parts)]
    manifest = {
        "content_digest": content_digest,
        "entries": entries,
        "root_file": root_file,
        "schema": _CACHE_TREE_SCHEMA,
        "tree_digest": sha256_digest(_canonical_json_bytes(entries)),
    }
    if len(_canonical_json_bytes(manifest)) > _limits().max_metadata_bytes:
        raise SDLParseError("OCI module cache integrity manifest exceeds the metadata limit")
    return manifest
