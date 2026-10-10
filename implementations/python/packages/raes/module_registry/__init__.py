"""Registry-aware SDL module resolution and publishing.

This package is a thin facade over cohesive cache, extraction, filesystem,
model, resolution, signing, and publishing subdomains.

The package facade remains the compatibility and injection surface for OCI
transport and archive limits. The cache/extraction helpers dynamically use the
facade's patchable seams, preserving historical test behavior while keeping each
source module below the repository size cap.
"""

from __future__ import annotations

import json
import os
import tarfile
import time
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

# Registry requests resolve ``urlopen`` through this facade, the transport patch seam.
from urllib.request import urlopen

# The submodule imports below retain the package's documented domain re-exports
# plus the private ``_sha256_digest`` / ``_signable_payload`` /
# ``_verify_signatures`` seams used by existing tests. Incidental implementation
# imports are not an API; F401 is ignored for this facade because these deliberate
# domain re-exports otherwise look unused inside this file.
from .._errors import SDLParseError
from .._source_profile import SDLSourceParseOptions
from ..scenario import ImportDecl, ModuleDescriptor, Scenario
from ._archive import _expected_cache_tree_manifest
from ._cache import (
    _CACHE_THREAD_LOCKS,
    _CACHE_THREAD_LOCKS_GUARD,
    _SPOOL_MEMORY_BYTES,
    _acquire_file_lock,
    _bounded_gzip_tar_stream,
    _cache_entry_lock,
    _open_cache_lock,
    _recover_cache_root,
    _release_file_lock,
)
from ._cache_integrity import (
    _CACHE_TREE_SCHEMA,
    _DECOMPRESSION_CHUNK_BYTES,
    _cache_tree_entries,
    _cache_tree_manifest,
    _canonical_json_bytes,
    _hash_cache_file,
    _read_cache_manifest_bytes,
    _trusted_entry_projection,
    _validated_cache_root,
    _write_cache_tree_manifest,
)
from ._constants import (
    LOCKFILE_NAME,
    LOCKFILE_SCHEMA_VERSION,
    OCI_BUNDLE_MEDIA_TYPE,
    OCI_CONFIG_MEDIA_TYPE,
    OCI_LAYOUT_MEDIA_TYPE,
    OCI_LAYOUT_SCHEMA_VERSION,
    TRUST_POLICY_NAME,
    TRUST_POLICY_SCHEMA_VERSION,
)
from ._digests import _sha256_digest
from ._extraction import (
    _HTTP_TIMEOUT_SECONDS,
    _extract_tar_to_stage,
    _OCIResourceLimits,
    _safe_tar_members_with_limits,
    _validate_tar_member_shape,
)
from ._filesystem import (
    _install_version_directory,
    _iter_version_directories,
    _new_digest_version_name,
    _new_version_stage,
    _prepare_versioned_slot,
    _prune_version_directories,
    _read_version_pointer,
    _remove_path,
    _require_directory,
    _same_file_identity,
    _write_version_pointer,
)
from ._registry_auth import _registry_get, _RegistryTokens
from ._verified_sources import _cache_source_result, _VerifiedSourceBundle
from .models import (
    Lockfile,
    LockRecord,
    RegistryTrustPolicy,
    ResolvedModule,
    TrustPolicy,
    load_lockfile,
    load_trust_policy,
    write_lockfile,
)
from .publishing import publish_module_to_oci_layout
from .resolution import resolve_import, resolve_lock_records
from .signing import _signable_payload, _verify_signatures

_OCI_LIMITS = _OCIResourceLimits()


class _CappableResponse(Protocol):
    """Minimal HTTP-response surface the bounded reader depends on.

    Structural view of ``http.client.HTTPResponse`` (the ``urlopen`` return) so the
    reader is typed without a bare ``Any``: it only needs a size-capped ``read`` and,
    optionally, response headers for the advisory Content-Length pre-check.
    """

    def read(self, amt: int = ..., /) -> bytes: ...


def _declared_content_length(response: _CappableResponse) -> int | None:
    """Return a validated Content-Length, or ``None`` when the header is absent.

    Content-Length is advisory and attacker-controlled, so it is only ever used to
    reject early - never to size a buffer or to substitute for counting the bytes
    actually read.
    """
    headers = getattr(response, "headers", None)
    raw = headers.get("Content-Length") if headers is not None else None
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise SDLParseError(f"OCI response declares an invalid Content-Length: {raw!r}") from exc
    if value < 0:
        raise SDLParseError(f"OCI response declares a negative Content-Length: {value}")
    return value


def _read_capped(response: _CappableResponse, *, url: str, max_bytes: int) -> bytes:
    """Read at most ``max_bytes`` from ``response``, failing closed if exceeded.

    Rejecting an oversized advisory ``Content-Length`` avoids even starting the
    read; the authoritative check reads ``max_bytes + 1`` so the in-memory buffer
    stays bounded and a registry cannot force the resolver to buffer an unbounded
    blob. Messages name the limit and the safe URL only - never the body.
    """
    declared = _declared_content_length(response)
    if declared is not None and declared > max_bytes:
        raise SDLParseError(
            f"OCI response from {url} declares Content-Length {declared} bytes, exceeding the {max_bytes}-byte limit"
        )
    data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise SDLParseError(f"OCI response from {url} exceeds the {max_bytes}-byte limit")
    return data


def _json_request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_bytes: int | None = None,
    tokens: _RegistryTokens | None = None,
) -> dict[str, Any]:
    limit = _OCI_LIMITS.max_metadata_bytes if max_bytes is None else max_bytes
    failure = f"Failed to fetch OCI metadata from {url}"
    payload = _registry_get(url, headers=headers, max_bytes=limit, tokens=tokens, failure=failure)
    return _decode_json_object(payload, context=f"OCI metadata from {url}")


def _decode_json_object(payload: bytes, *, context: str) -> dict[str, Any]:
    """Decode attacker-controlled JSON behind one stable, bounded error surface."""

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (RecursionError, ValueError) as exc:
        raise SDLParseError(f"{context} is not valid UTF-8 JSON") from exc
    if not isinstance(decoded, dict):
        raise SDLParseError(f"{context} must be a JSON object")
    return decoded


def _bytes_request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_bytes: int | None = None,
    tokens: _RegistryTokens | None = None,
) -> bytes:
    limit = _OCI_LIMITS.max_metadata_bytes if max_bytes is None else max_bytes
    failure = f"Failed to fetch OCI blob from {url}"
    return _registry_get(url, headers=headers, max_bytes=limit, tokens=tokens, failure=failure)


def _oci_cache_dir(base_dir: Path) -> Path:
    return base_dir / ".raes" / "module-cache"


def _safe_tar_members(
    tar: tarfile.TarFile,
    dest: Path,
) -> list[tarfile.TarInfo]:
    """Validate every tar member under the facade's patchable limits seam."""

    return _safe_tar_members_with_limits(tar, dest, limits=_OCI_LIMITS)


@dataclass(frozen=True)
class _CacheExtraction:
    """Validated immutable inputs for one cache transaction."""

    bundle_bytes: bytes
    content_digest: str
    root_file: str
    root_relative: PurePosixPath
    cache_slot: Path
    lock_path: Path
    source_options: SDLSourceParseOptions | None


def _validated_cache_key(manifest_digest: str) -> str:
    invalid = any(
        (
            not manifest_digest,
            manifest_digest in {".", ".."},
            "/" in manifest_digest,
            "\\" in manifest_digest,
            "\x00" in manifest_digest,
        )
    )
    if invalid:
        raise SDLParseError("Invalid OCI manifest digest cache key")
    return manifest_digest


def _is_windows_absolute_path(path: PurePosixPath) -> bool:
    return bool(path.parts) and len(path.parts[0]) == 2 and path.parts[0][1] == ":"


def _validated_root_file(root_file: str) -> PurePosixPath:
    root_relative = PurePosixPath(root_file)
    invalid = any(
        (
            not root_file,
            "\\" in root_file,
            "\x00" in root_file,
            ".." in root_relative.parts,
            root_relative.is_absolute(),
            root_relative == PurePosixPath("."),
            root_file != root_relative.as_posix(),
            _is_windows_absolute_path(root_relative),
        )
    )
    if invalid:
        raise SDLParseError(f"Invalid OCI root_file path: {root_file!r}")
    return root_relative


def _validated_content_digest(bundle_bytes: bytes, expected: str | None) -> str:
    actual = f"sha256:{_sha256_digest(bundle_bytes)}"
    expected_digest = expected or actual
    if expected_digest != actual:
        raise SDLParseError("OCI module bundle does not match its expected content digest")
    return expected_digest


def _cache_extraction(
    *,
    bundle_bytes: bytes,
    manifest_digest: str,
    content_digest: str | None = None,
    root_file: str,
    base_dir: Path,
    source_options: SDLSourceParseOptions | None = None,
) -> _CacheExtraction:
    cache_key = _validated_cache_key(manifest_digest)
    root_relative = _validated_root_file(root_file)
    expected_content_digest = _validated_content_digest(bundle_bytes, content_digest)
    cache_root = _oci_cache_dir(base_dir)
    cache_error = "Unable to create the OCI module cache"
    _require_directory(cache_root.parent, error_message=cache_error)
    _require_directory(cache_root, error_message=cache_error)
    return _CacheExtraction(
        bundle_bytes=bundle_bytes,
        content_digest=expected_content_digest,
        root_file=root_file,
        root_relative=root_relative,
        cache_slot=cache_root / cache_key,
        lock_path=cache_root / ".locks" / f"{cache_key}.lock",
        source_options=source_options,
    )


def _expected_extraction_manifest(
    extraction: _CacheExtraction,
    *,
    tar: tarfile.TarFile,
    safe_members: list[tarfile.TarInfo],
) -> dict[str, Any]:
    expected_manifest = _expected_cache_tree_manifest(
        tar=tar,
        members=safe_members,
        content_digest=extraction.content_digest,
        root_file=extraction.root_file,
    )
    expected_root = next(
        (entry for entry in expected_manifest["entries"] if entry["path"] == extraction.root_relative.as_posix()),
        None,
    )
    if expected_root is None or expected_root["type"] != "file":
        raise SDLParseError(f"Resolved OCI module bundle is missing declared root file '{extraction.root_file}'")
    return expected_manifest


def _source_result(
    extraction: _CacheExtraction,
    root: Path,
    expected_manifest: dict[str, Any],
) -> Path | _VerifiedSourceBundle:
    return _cache_source_result(
        root,
        expected_manifest=expected_manifest,
        root_relative=extraction.root_relative,
        source_options=extraction.source_options,
    )


def _recover_extracted_source(
    extraction: _CacheExtraction,
    *,
    versions: Path,
    expected_manifest: dict[str, Any],
) -> Path | _VerifiedSourceBundle | None:
    hit = _recover_cache_root(
        slot=extraction.cache_slot,
        versions=versions,
        expected_content_digest=extraction.content_digest,
        expected_manifest=expected_manifest,
        root_relative=extraction.root_relative,
    )
    if hit is None:
        return None
    return _source_result(extraction, hit, expected_manifest)


def _valid_staged_root(staged_root: Path, *, staging: Path) -> bool:
    if staged_root.is_symlink() or not staged_root.is_file():
        return False
    return staged_root.resolve(strict=True).is_relative_to(staging.resolve(strict=True))


def _commit_extracted_stage(
    extraction: _CacheExtraction,
    *,
    staging: Path,
    versions: Path,
    prior_version: str | None,
    expected_manifest: dict[str, Any],
) -> Path | _VerifiedSourceBundle:
    staged_validation = _validated_cache_root(
        version=staging,
        expected_manifest=expected_manifest,
        root_relative=extraction.root_relative,
    )
    if staged_validation is None:
        raise SDLParseError("Staged OCI module cache entry failed validation")
    version_name = _new_digest_version_name(extraction.content_digest)
    installed = _install_version_directory(
        staged=staging,
        versions=versions,
        version_name=version_name,
        error_message="Unable to commit the OCI module cache entry atomically",
    )
    committed = _validated_cache_root(
        version=installed,
        expected_manifest=expected_manifest,
        root_relative=extraction.root_relative,
    )
    if committed is None:
        raise SDLParseError("Committed OCI module cache entry failed validation")
    _prune_version_directories(
        versions=versions,
        retain_names={version_name, *(() if prior_version is None else (prior_version,))},
        error_message="Unable to prune stale OCI module cache versions",
    )
    _write_version_pointer(
        slot=extraction.cache_slot,
        version_name=version_name,
        error_message="Unable to commit the OCI module cache pointer atomically",
    )
    return _source_result(extraction, committed, expected_manifest)


def _install_extracted_source(
    extraction: _CacheExtraction,
    *,
    tar: tarfile.TarFile,
    safe_members: list[tarfile.TarInfo],
    versions: Path,
    expected_manifest: dict[str, Any],
) -> Path | _VerifiedSourceBundle:
    staging = _new_version_stage(
        versions=versions,
        error_message="Unable to stage the OCI module cache entry",
    )
    try:
        _extract_tar_to_stage(
            tar=tar,
            members=safe_members,
            staging=staging,
            expected_entries=expected_manifest["entries"],
        )
        staged_root = staging.joinpath(*extraction.root_relative.parts)
        if not _valid_staged_root(staged_root, staging=staging):
            raise SDLParseError(f"Resolved OCI module bundle is missing declared root file '{extraction.root_file}'")
        prior_version = _read_version_pointer(slot=extraction.cache_slot)
        _write_cache_tree_manifest(
            root=staging,
            content_digest=extraction.content_digest,
            root_file=extraction.root_file,
        )
        return _commit_extracted_stage(
            extraction,
            staging=staging,
            versions=versions,
            prior_version=prior_version,
            expected_manifest=expected_manifest,
        )
    finally:
        _remove_path(staging)


def _read_or_install_extracted_source(
    extraction: _CacheExtraction,
    *,
    tar: tarfile.TarFile,
    versions: Path,
) -> Path | _VerifiedSourceBundle:
    # The complete uncompressed stream is admitted before ``tarfile`` parses its
    # first header. Member validation and the standard data filter then provide
    # independent filesystem-write defenses.
    safe_members = _safe_tar_members(tar, versions / ".inventory")
    expected_manifest = _expected_extraction_manifest(
        extraction,
        tar=tar,
        safe_members=safe_members,
    )
    recovered = _recover_extracted_source(
        extraction,
        versions=versions,
        expected_manifest=expected_manifest,
    )
    if recovered is not None:
        return recovered
    return _install_extracted_source(
        extraction,
        tar=tar,
        safe_members=safe_members,
        versions=versions,
        expected_manifest=expected_manifest,
    )


def _extract_bundle_to_cache(
    *,
    bundle_bytes: bytes,
    manifest_digest: str,
    content_digest: str | None = None,
    root_file: str,
    base_dir: Path,
    source_options: SDLSourceParseOptions | None = None,
) -> Path | _VerifiedSourceBundle:
    extraction = _cache_extraction(
        bundle_bytes=bundle_bytes,
        manifest_digest=manifest_digest,
        content_digest=content_digest,
        root_file=root_file,
        base_dir=base_dir,
        source_options=source_options,
    )

    with _cache_entry_lock(extraction.lock_path):
        versions = _prepare_versioned_slot(
            slot=extraction.cache_slot,
            error_message="Unable to prepare the OCI module cache entry",
        )
        try:
            with (
                _bounded_gzip_tar_stream(extraction.bundle_bytes) as tar_stream,
                tarfile.open(fileobj=tar_stream, mode="r:") as tar,
            ):
                return _read_or_install_extracted_source(extraction, tar=tar, versions=versions)
        except (EOFError, OSError, tarfile.TarError, zlib.error) as exc:
            raise SDLParseError("OCI module bundle is not a valid gzip-compressed tar archive") from exc
