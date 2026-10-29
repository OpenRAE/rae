"""OCI-layout publishing for local SDL module graphs."""

from __future__ import annotations

import base64
import gzip
import io
import json
import stat
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from raes_contracts.errors import ConflictError, InvalidInputError, OperationalError

from .._errors import SDLParseError
from ..scenario import ImportDecl, ModuleDescriptor
from ._constants import (
    OCI_BUNDLE_MEDIA_TYPE,
    OCI_CONFIG_MEDIA_TYPE,
    OCI_LAYOUT_MEDIA_TYPE,
    OCI_LAYOUT_SCHEMA_VERSION,
)
from ._digests import _SHA256_PREFIX, _descriptor_digest
from ._filesystem import (
    _install_version_directory,
    _iter_version_directories,
    _new_digest_version_name,
    _new_version_stage,
    _prepare_versioned_slot,
    _prune_version_directories,
    _read_version_pointer,
    _remove_path,
    _version_digest_prefix,
    _write_version_pointer,
)
from .models import _scenario_module_descriptor

# ``_sha256_digest`` / ``_signable_payload`` are resolved through the package
# facade with function-local ``from . import`` so a test that patches
# ``raes.module_registry.<seam>`` replaces the binding these production calls use,
# exactly as the pre-split single-file module did.


def _collect_local_bundle_files(
    root_path: Path,
    *,
    bundle_root: Path | None = None,
    seen: set[Path] | None = None,
) -> dict[Path, bytes]:
    from ..parser import _load_normalized_data, read_sdl_source

    seen = set() if seen is None else set(seen)
    try:
        resolved = root_path.resolve(strict=True)
    except OSError as exc:
        raise SDLParseError("Unable to resolve the module publishing entrypoint") from exc
    if not resolved.is_file():
        raise SDLParseError("The module publishing entrypoint must be a regular file")
    bundle_root = resolved.parent if bundle_root is None else bundle_root
    if not resolved.is_relative_to(bundle_root):
        raise SDLParseError("Local import path escapes the canonical publishing root")
    if resolved in seen:
        raise SDLParseError(f"Import cycle detected at {resolved}")
    seen.add(resolved)
    root_source = read_sdl_source(resolved)
    payload = _load_normalized_data(root_source.text, path=resolved)
    files = {resolved: root_source.raw_bytes}
    for raw_import in payload.get("imports", []):
        import_decl = ImportDecl.model_validate(raw_import)
        source = import_decl.normalized_source
        if not source.startswith("local:"):
            raise SDLParseError(
                "Publishing modules with remote OCI imports is not supported; "
                "publish a self-contained local module graph"
            )
        child_path = (resolved.parent / source.removeprefix("local:")).resolve()
        if not child_path.is_relative_to(bundle_root):
            raise SDLParseError(f"Local import path escapes base directory: {source!r}")
        files.update(_collect_local_bundle_files(child_path, bundle_root=bundle_root, seen=seen))
    return files


def _build_module_bundle(root_path: Path) -> bytes:
    canonical_root = root_path.resolve(strict=True)
    bundle_root = canonical_root.parent
    files = _collect_local_bundle_files(canonical_root, bundle_root=bundle_root)
    relative_files = {path.relative_to(bundle_root).as_posix(): content for path, content in files.items()}
    bundle_buffer = io.BytesIO()
    # Issue #1096 / GOV-913: both the tar headers and the gzip envelope are
    # normalized. Identical canonical module bytes therefore produce identical
    # content digests regardless of wall clock, checkout ownership, or file mode.
    with (
        gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=bundle_buffer, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for relative_name, content in sorted(relative_files.items()):
            info = tarfile.TarInfo(name=relative_name)
            info.size = len(content)
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            tar.addfile(info, io.BytesIO(content))
    return bundle_buffer.getvalue()


def _build_signatures(
    descriptor: ModuleDescriptor,
    *,
    content_digest: str,
    root_file: str,
    signer_id: str,
    private_key_path: Path | None,
) -> list[dict[str, str]]:
    from . import _signable_payload

    signer_configured = signer_id != ""
    key_configured = private_key_path is not None
    if signer_configured != key_configured:
        raise SDLParseError("Publishing signing requires both signer_id and private_key_path")
    if not signer_configured:
        return []
    if signer_id != signer_id.strip():
        raise SDLParseError("Publishing signer_id must not contain leading or trailing whitespace")
    assert private_key_path is not None
    try:
        private_key_bytes = private_key_path.read_bytes()
    except OSError as exc:
        raise SDLParseError("Unable to read the publishing private key") from exc
    try:
        private_key = serialization.load_pem_private_key(private_key_bytes, password=None)
    except (TypeError, ValueError, UnsupportedAlgorithm) as exc:
        raise SDLParseError("Publishing private key is not a valid PEM private key") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise SDLParseError("Publishing key must be an Ed25519 private key")
    signature = private_key.sign(_signable_payload(descriptor, content_digest=content_digest, root_file=root_file))
    return [
        {
            "signer_id": signer_id,
            "signature": base64.b64encode(signature).decode("utf-8"),
        }
    ]


@dataclass(frozen=True)
class _LayoutPublication:
    """Immutable inputs shared by layout validation and publication."""

    slot: Path
    expected_files: Mapping[str, bytes]
    manifest_digest: str


class _InvalidLayoutError(InvalidInputError):
    """Internal marker for a filesystem object that is not an OCI layout."""


def _build_layout_index(
    *,
    descriptor: ModuleDescriptor,
    blobs: dict[str, bytes],
    manifest_digest: str,
) -> bytes:
    return (
        json.dumps(
            {
                "schemaVersion": 2,
                "manifests": [
                    {
                        "mediaType": OCI_LAYOUT_MEDIA_TYPE,
                        "digest": manifest_digest,
                        "size": len(blobs[manifest_digest]),
                        "annotations": {
                            "org.opencontainers.image.ref.name": descriptor.version,
                            "io.raes.module.id": descriptor.id,
                        },
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _layout_expected_files(
    *,
    descriptor: ModuleDescriptor,
    blobs: dict[str, bytes],
    manifest_digest: str,
) -> dict[str, bytes]:
    # ``blobs`` maps each blob's ``sha256:`` digest to its bytes (config, bundle,
    # manifest); ``manifest_digest`` selects which one the index references.
    return {
        "oci-layout": b'{"imageLayoutVersion":"1.0.0"}\n',
        "index.json": _build_layout_index(
            descriptor=descriptor,
            blobs=blobs,
            manifest_digest=manifest_digest,
        ),
        **{f"blobs/sha256/{digest.removeprefix(_SHA256_PREFIX)}": payload for digest, payload in blobs.items()},
    }


def _layout_inventory(version: Path) -> tuple[set[str], set[str]]:
    actual_files: set[str] = set()
    actual_directories: set[str] = {"."}
    for path in version.rglob("*"):
        relative = path.relative_to(version).as_posix()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise _InvalidLayoutError
        if stat.S_ISDIR(metadata.st_mode):
            actual_directories.add(relative)
        elif stat.S_ISREG(metadata.st_mode):
            actual_files.add(relative)
        else:
            raise _InvalidLayoutError
    return actual_files, actual_directories


def _layout_file_bytes_match(version: Path, expected_files: Mapping[str, bytes]) -> bool:
    matches = True
    for relative, expected in expected_files.items():
        path = version.joinpath(*relative.split("/"))
        if path.is_symlink() or path.stat().st_size != len(expected) or path.read_bytes() != expected:
            matches = False
            break
    return matches


def _valid_oci_layout(version: Path, expected_files: Mapping[str, bytes]) -> bool:
    try:
        actual_files, actual_directories = _layout_inventory(version)
        expected_directories = {".", "blobs", "blobs/sha256"}
        valid_inventory = actual_directories == expected_directories and actual_files == set(expected_files)
        return valid_inventory and _layout_file_bytes_match(version, expected_files)
    except OSError, _InvalidLayoutError:
        return False


def _layout_candidates(
    publication: _LayoutPublication,
    *,
    versions: Path,
    current: str | None,
) -> list[Path]:
    candidates = [] if current is None else [versions / current]
    digest_prefix = _version_digest_prefix(publication.manifest_digest)
    for version in _iter_version_directories(
        versions,
        error_message="Unable to inspect OCI layout versions",
    ):
        if version.name.startswith(digest_prefix) and version not in candidates:
            candidates.append(version)
    return candidates[:64]


def _recover_oci_layout(
    publication: _LayoutPublication,
    *,
    versions: Path,
    current: str | None,
) -> Path | None:
    for version in _layout_candidates(publication, versions=versions, current=current):
        if not _valid_oci_layout(version, publication.expected_files):
            continue
        _prune_version_directories(
            versions=versions,
            retain_names={version.name, *(() if current is None else (current,))},
            error_message="Unable to prune stale OCI layout versions",
        )
        if current != version.name:
            _write_version_pointer(
                slot=publication.slot,
                version_name=version.name,
                error_message="Unable to publish the OCI layout pointer atomically",
            )
        return version
    return None


def _reject_legacy_layout(layout_slot: Path) -> None:
    if layout_slot.is_symlink() or not layout_slot.is_dir():
        return
    legacy_paths = (layout_slot / "oci-layout", layout_slot / "index.json", layout_slot / "blobs")
    if any(child.exists() or child.is_symlink() for child in legacy_paths):
        raise ConflictError(
            "Existing OCI output uses the legacy root-layout format; move or remove "
            f"'{layout_slot}' before publishing into its versioned layout slot"
        )


def _populate_layout_stage(staging: Path, expected_files: Mapping[str, bytes]) -> None:
    (staging / "blobs" / "sha256").mkdir(parents=True)
    for relative, payload in sorted(expected_files.items()):
        staging.joinpath(*relative.split("/")).write_bytes(payload)
    if not _valid_oci_layout(staging, expected_files):
        raise OperationalError("Staged OCI layout failed validation")


def _commit_layout_stage(
    publication: _LayoutPublication,
    *,
    staging: Path,
    versions: Path,
    prior_version: str | None,
) -> Path:
    version_name = _new_digest_version_name(publication.manifest_digest)
    installed = _install_version_directory(
        staged=staging,
        versions=versions,
        version_name=version_name,
        error_message="Unable to publish the OCI layout atomically",
    )
    if not _valid_oci_layout(installed, publication.expected_files):
        raise OperationalError("Published OCI layout failed validation")
    _prune_version_directories(
        versions=versions,
        retain_names={version_name, *(() if prior_version is None else (prior_version,))},
        error_message="Unable to prune stale OCI layout versions",
    )
    _write_version_pointer(
        slot=publication.slot,
        version_name=version_name,
        error_message="Unable to publish the OCI layout pointer atomically",
    )
    return installed


def _publish_new_layout(
    publication: _LayoutPublication,
    *,
    versions: Path,
    prior_version: str | None,
) -> Path:
    staging = _new_version_stage(
        versions=versions,
        error_message="Unable to stage the OCI layout",
    )
    try:
        _populate_layout_stage(staging, publication.expected_files)
        return _commit_layout_stage(
            publication,
            staging=staging,
            versions=versions,
            prior_version=prior_version,
        )
    finally:
        _remove_path(staging)


def _write_oci_layout(
    *,
    output_dir: Path,
    descriptor: ModuleDescriptor,
    blobs: dict[str, bytes],
    manifest_digest: str,
) -> Path:
    layout_slot = output_dir / f"{descriptor.id.replace('/', '_')}-{descriptor.version}.oci"
    publication = _LayoutPublication(
        slot=layout_slot,
        expected_files=_layout_expected_files(
            descriptor=descriptor,
            blobs=blobs,
            manifest_digest=manifest_digest,
        ),
        manifest_digest=manifest_digest,
    )

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        lock_path = output_dir / ".raes-layout-locks" / f"{layout_slot.name}.lock"
        from . import _cache_entry_lock

        with _cache_entry_lock(lock_path):
            _reject_legacy_layout(layout_slot)
            versions = _prepare_versioned_slot(
                slot=layout_slot,
                error_message="Unable to publish the OCI layout atomically",
            )
            prior_version = _read_version_pointer(slot=layout_slot)
            recovered = _recover_oci_layout(publication, versions=versions, current=prior_version)
            if recovered is not None:
                return recovered
            return _publish_new_layout(
                publication,
                versions=versions,
                prior_version=prior_version,
            )
    except OSError as exc:
        raise OperationalError("Unable to build the OCI layout") from exc


def publish_module_to_oci_layout(
    root_path: Path,
    *,
    output_dir: Path,
    signer_id: str = "",
    private_key_path: Path | None = None,
) -> dict[str, Any]:
    from ..parser import parse_sdl_file
    from . import _sha256_digest

    try:
        canonical_root = root_path.resolve(strict=True)
    except OSError as exc:
        raise SDLParseError("Unable to resolve the module publishing entrypoint") from exc
    scenario = parse_sdl_file(canonical_root, skip_semantic_validation=True)
    descriptor = _scenario_module_descriptor(
        scenario,
        source_id=canonical_root.name,
    )
    bundle_bytes = _build_module_bundle(canonical_root)
    content_digest = f"{_SHA256_PREFIX}{_sha256_digest(bundle_bytes)}"
    signatures = _build_signatures(
        descriptor,
        content_digest=content_digest,
        root_file=canonical_root.name,
        signer_id=signer_id,
        private_key_path=private_key_path,
    )
    config_payload = {
        "schema_version": OCI_LAYOUT_SCHEMA_VERSION,
        "root_file": canonical_root.name,
        "module": descriptor.model_dump(mode="python", by_alias=True),
        "signatures": signatures,
    }
    config_bytes = json.dumps(config_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    config_digest = f"{_SHA256_PREFIX}{_sha256_digest(config_bytes)}"
    manifest_payload = {
        "schemaVersion": 2,
        "mediaType": OCI_LAYOUT_MEDIA_TYPE,
        "config": {
            "mediaType": OCI_CONFIG_MEDIA_TYPE,
            "digest": config_digest,
            "size": len(config_bytes),
        },
        "layers": [
            {
                "mediaType": OCI_BUNDLE_MEDIA_TYPE,
                "digest": content_digest,
                "size": len(bundle_bytes),
            }
        ],
        "annotations": {
            "org.opencontainers.image.ref.name": descriptor.version,
            "io.raes.module.id": descriptor.id,
        },
    }
    manifest_bytes = json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_digest = f"{_SHA256_PREFIX}{_sha256_digest(manifest_bytes)}"
    layout_dir = _write_oci_layout(
        output_dir=output_dir,
        descriptor=descriptor,
        blobs={config_digest: config_bytes, content_digest: bundle_bytes, manifest_digest: manifest_bytes},
        manifest_digest=manifest_digest,
    )
    return {
        "layout_dir": str(layout_dir),
        "module_id": descriptor.id,
        "module_version": descriptor.version,
        "manifest_digest": manifest_digest,
        "content_digest": content_digest,
        "export_hash": _descriptor_digest(descriptor.exports),
        "signer_id": signer_id,
    }
