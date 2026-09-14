"""Descriptor-bound immutable SDL sources for verified OCI cache trees."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, BinaryIO

from pydantic import ValidationError

from .._errors import SDLParseError
from .._source_profile import SDLSourceParseOptions
from ..scenario import ImportDecl
from ._filesystem import _O_BINARY, _O_NOFOLLOW, _same_file_identity

if TYPE_CHECKING:
    from ..parser import SDLSourceDocument

_CACHE_INTEGRITY_ERROR = "OCI module cache tree failed integrity validation"


@dataclass(frozen=True)
class _VerifiedSourceBundle:
    """One immutable in-memory view of a verified OCI SDL import graph."""

    cache_root: Path
    documents: Mapping[str, SDLSourceDocument]

    def resolve_local(self, *, base_dir: Path, relative: str) -> tuple[Path, SDLSourceDocument]:
        base_relative = _cache_relative_path(self.cache_root, base_dir)
        target = _normalize_bundle_path(base_relative, relative)
        document = self.documents.get(target)
        if document is None:
            raise SDLParseError(f"Imported SDL file not found: {relative}")
        return self.cache_root.joinpath(*PurePosixPath(target).parts), document

    def identity_path(self, path: Path) -> Path:
        """Return a lexical cache identity without consulting mutable paths."""

        relative = _cache_relative_path(self.cache_root, path)
        return self.cache_root.joinpath(*PurePosixPath(relative).parts)


def _cache_relative_path(cache_root: Path, path: Path) -> str:
    root = cache_root.absolute()
    candidate = path.absolute()
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise SDLParseError("Local import path escapes the verified OCI module cache") from exc
    return relative.as_posix() or "."


def _local_resolved_source(import_path: Path, base_dir: Path, *, lexical: bool = False) -> str:
    """Return one portable lock identity, without resolving admitted cache paths.

    Local lock identities are checkout-independent POSIX paths. Ordinary local
    files retain canonical filesystem resolution, while a descriptor-bound OCI
    source uses only its already-confined lexical identity.
    """

    anchor = base_dir.absolute() if lexical else base_dir.resolve()
    return Path(os.path.relpath(import_path, anchor)).as_posix()


def _normalize_bundle_path(base_relative: str, relative: str) -> str:
    normalized = relative.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    invalid_reference = (
        not normalized
        or "\x00" in normalized
        or candidate.is_absolute()
        or (candidate.parts and len(candidate.parts[0]) == 2 and candidate.parts[0][1] == ":")
    )
    if invalid_reference:
        raise SDLParseError(f"Local import path escapes base directory: {relative!r}")
    parts = [] if base_relative == "." else list(PurePosixPath(base_relative).parts)
    _apply_bundle_path_parts(parts, candidate.parts, relative=relative)
    if not parts:
        raise SDLParseError(f"Local import path escapes base directory: {relative!r}")
    return PurePosixPath(*parts).as_posix()


def _apply_bundle_path_parts(parts: list[str], candidate_parts: tuple[str, ...], *, relative: str) -> None:
    """Apply normalized path components without permitting an escape."""

    for part in candidate_parts:
        if part == "..":
            if not parts:
                raise SDLParseError(f"Local import path escapes base directory: {relative!r}")
            parts.pop()
        else:
            parts.append(part)


def _cache_file_fingerprint(metadata: os.stat_result) -> tuple[bool, int, int]:
    return stat.S_ISREG(metadata.st_mode), metadata.st_size, stat.S_IMODE(metadata.st_mode)


def _require_expected_cache_file(
    metadata: os.stat_result,
    *,
    expected_size: int,
    expected_mode: int,
    identity: os.stat_result | None = None,
) -> None:
    expected_fingerprint = (True, expected_size, expected_mode)
    if _cache_file_fingerprint(metadata) != expected_fingerprint:
        raise SDLParseError(_CACHE_INTEGRITY_ERROR)
    if identity is not None and not _same_file_identity(identity, metadata):
        raise SDLParseError(_CACHE_INTEGRITY_ERROR)


def _capture_source_bytes(source: BinaryIO, *, capture_limit: int) -> tuple[bytes, int, str]:
    """Hash an entire admitted source while retaining only the parser limit."""

    digest = hashlib.sha256()
    captured = bytearray()
    byte_count = 0
    while chunk := source.read(1024 * 1024):
        byte_count += len(chunk)
        digest.update(chunk)
        remaining = max(capture_limit - len(captured), 0)
        captured.extend(chunk[:remaining])
    return bytes(captured), byte_count, digest.hexdigest()


def _read_verified_cache_source(
    path: Path,
    *,
    expected_entry: dict[str, Any],
    source_options: SDLSourceParseOptions,
) -> SDLSourceDocument:
    """Read and authenticate exact source bytes through one no-follow descriptor."""

    expected_size = expected_entry["size"]
    expected_mode = expected_entry["mode"]
    descriptor = -1
    try:
        before = path.lstat()
        _require_expected_cache_file(before, expected_size=expected_size, expected_mode=expected_mode)
        flags = os.O_RDONLY | _O_BINARY | _O_NOFOLLOW
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            opened = os.fstat(source.fileno())
            _require_expected_cache_file(
                opened,
                expected_size=expected_size,
                expected_mode=expected_mode,
                identity=before,
            )
            captured, byte_count, digest = _capture_source_bytes(
                source,
                capture_limit=source_options.limits.max_input_bytes + 1,
            )
            after = os.fstat(source.fileno())
        _require_expected_cache_file(
            after,
            expected_size=expected_size,
            expected_mode=expected_mode,
            identity=opened,
        )
    except SDLParseError:
        raise
    except OSError as exc:
        raise SDLParseError(_CACHE_INTEGRITY_ERROR) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if byte_count != expected_size or f"sha256:{digest}" != expected_entry["digest"]:
        raise SDLParseError(_CACHE_INTEGRITY_ERROR)

    from ..parser import _source_document_from_bytes

    return _source_document_from_bytes(captured, path=path, limits=source_options.limits)


def _local_import_targets(
    document: SDLSourceDocument,
    *,
    path: Path,
    relative: str,
    source_options: SDLSourceParseOptions,
) -> list[str]:
    """Return normalized local targets declared by one verified source."""

    from ..parser import _load_normalized_data

    payload = _load_normalized_data(
        document.text,
        path=path,
        source_format=source_options.source_format,
        required_semantic_revision=source_options.required_semantic_revision,
        migration_policy=source_options.migration_policy,
        limits=source_options.limits,
    )
    raw_imports = payload.get("imports", [])
    if not isinstance(raw_imports, list):
        raise SDLParseError("Imported SDL unit is structurally invalid", path=path)
    parent = PurePosixPath(relative).parent.as_posix()
    targets: list[str] = []
    for raw_import in raw_imports:
        try:
            import_decl = ImportDecl.model_validate(raw_import)
        except ValidationError as exc:
            raise SDLParseError("Imported SDL unit is structurally invalid", path=path) from exc
        source = import_decl.normalized_source
        if source.startswith("local:"):
            targets.append(_normalize_bundle_path(parent, source.removeprefix("local:")))
    return targets


def _read_verified_source_bundle(
    *,
    cache_root: Path,
    expected_manifest: dict[str, Any],
    root_relative: PurePosixPath,
    source_options: SDLSourceParseOptions,
) -> _VerifiedSourceBundle:
    """Capture the complete reachable local SDL graph before releasing its lock."""

    entries = {
        entry["path"]: entry
        for entry in expected_manifest["entries"]
        if isinstance(entry, dict) and entry.get("type") == "file"
    }
    pending = [root_relative.as_posix()]
    documents: dict[str, SDLSourceDocument] = {}
    while pending:
        relative = pending.pop()
        if relative in documents:
            continue
        entry = entries.get(relative)
        if entry is None:
            raise SDLParseError(f"Imported SDL file not found: {relative}")
        path = cache_root.joinpath(*PurePosixPath(relative).parts)
        document = _read_verified_cache_source(
            path,
            expected_entry=entry,
            source_options=source_options,
        )
        documents[relative] = document
        pending.extend(
            _local_import_targets(
                document,
                path=path,
                relative=relative,
                source_options=source_options,
            )
        )
    return _VerifiedSourceBundle(
        cache_root=cache_root.absolute(),
        documents=MappingProxyType(dict(sorted(documents.items()))),
    )


def _cache_source_result(
    root: Path,
    *,
    expected_manifest: dict[str, Any],
    root_relative: PurePosixPath,
    source_options: SDLSourceParseOptions | None,
) -> Path | _VerifiedSourceBundle:
    if source_options is None:
        return root
    cache_root = root
    for _part in root_relative.parts:
        cache_root = cache_root.parent
    return _read_verified_source_bundle(
        cache_root=cache_root,
        expected_manifest=expected_manifest,
        root_relative=root_relative,
        source_options=source_options,
    )


__all__ = ["_VerifiedSourceBundle"]
