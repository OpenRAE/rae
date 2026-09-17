"""Verified, concurrent-safe installation of a complete reviewed archive tree.

The generic-tool installer in :mod:`tools.verified_tool_installation` admits
small in-memory carriers. A large prover distribution is a multi-gigabyte tree
with thousands of files and in-tree relative symbolic links, so it is streamed
into private staging instead. It still uses the same transaction rules: the
private-root guard, qualified filesystems, one native lock per identity,
exclusive staging, fsync, atomic rename, quarantine, and durable checkpoints.

The reviewed lock binds the raw archive digest and the SHA-256 of the canonical
installed-tree manifest. The manifest is reconstructed from the admitted
archive at installation. It is retained next to the immutable tree, and every
use checks the manifest against the reviewed digest and the whole tree against
the manifest. Neither a marker nor the presence of a file is ever treated as
trust.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import platform
import shutil
import stat
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from tools import verified_tool_installation as installation
from tools import verified_tree_archive as archive
from tools import verified_tree_validation as validation
from tools.verified_tree_archive import TreeEntry, manifest_bytes
from tools.verified_tree_validation import (
    TREE_CONTENT_NAME,
    TREE_MANIFEST_NAME,
    ManifestEntry,
    TreeSelection,
)

INSTALLATION_TREE_POLICY_ID = "install-tree-v1"
RAW_OBJECT_NAME = "raw-object"
LEGACY_CARRIER_PREFIX = ".legacy-carrier-"
TREE_LOCK_TIMEOUT_SECONDS = 5400
_failure = archive.failure


@dataclass(frozen=True)
class LegacyTreeInputs:
    """Version-keyed legacy content that is migrated but never trusted."""

    raw_carrier: Path | None = None
    derived_paths: tuple[Path, ...] = ()


def _policy_identity(selection: TreeSelection) -> str:
    encoded = json.dumps(
        {
            "installation_policy": INSTALLATION_TREE_POLICY_ID,
            "policy_refs": list(selection.policy_refs),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _raw_parent(installation_root: Path, selection: TreeSelection) -> Path:
    return (
        installation_root
        / installation._safe_component(selection.artifact_id)
        / installation._safe_component(selection.platform_id)
        / selection.raw_manifest[0].sha256
    )


def tree_installation_path(installation_root: Path, selection: TreeSelection) -> Path:
    """Return the content-addressed installation path for a validated tree selection."""

    descriptor = validation.validated_descriptor(selection)
    return (
        _raw_parent(installation_root, selection)
        / INSTALLATION_TREE_POLICY_ID
        / _policy_identity(selection)
        / descriptor.manifest_sha256
    )


def describe_archive_tree(archive_path: Path, raw_entry: ManifestEntry) -> dict[str, object]:
    """Return the reviewable installed-tree descriptor of one lock-verified archive."""

    try:
        with validation.opened_verified_raw(archive_path, raw_entry, mode="input") as stream:
            entries = archive.admit_archive_stream(stream, archive.CEILING_LIMITS, None)
    except RuntimeError:
        raise
    except OSError:
        raise _failure("raw-manifest-mismatch") from None
    archive.bounded_manifest_bytes(entries)
    return archive.tree_descriptor(entries)


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _make_stage_durable(stage: Path, entries: list[TreeEntry]) -> None:
    """Make every sealed staged file, mode, and directory entry durable.

    Linux ``sync(2)`` waits for I/O completion and gives the same guarantee as
    calling fsync on every file in the system (sync(2) manual page), so one call
    replaces tens of thousands of per-file fsyncs for a proof distribution.
    Other platforms keep explicit per-entry synchronization.
    """

    content = stage / TREE_CONTENT_NAME
    if platform.system() == "Linux":
        os.sync()
    else:
        for entry in entries:
            if entry.kind == "file":
                _fsync_file(content.joinpath(*PurePosixPath(entry.path).parts))
        for entry in entries:
            if entry.kind == "directory":
                installation._fsync_directory(content.joinpath(*PurePosixPath(entry.path).parts))
        _fsync_file(stage / TREE_MANIFEST_NAME)
    installation._fsync_directory(content)
    installation._fsync_directory(stage)


def _seal_stage(stage: Path, entries: list[TreeEntry]) -> None:
    content = stage / TREE_CONTENT_NAME
    for entry in entries:
        if entry.kind == "file":
            content.joinpath(*PurePosixPath(entry.path).parts).chmod(0o500 if entry.executable else 0o400)
    directories = [entry for entry in entries if entry.kind == "directory"]
    for entry in sorted(directories, key=lambda item: len(PurePosixPath(item.path).parts), reverse=True):
        content.joinpath(*PurePosixPath(entry.path).parts).chmod(0o500)
    content.chmod(0o500)
    (stage / TREE_MANIFEST_NAME).chmod(0o400)
    _make_stage_durable(stage, entries)


def _discard(path: Path) -> None:
    if installation._tree_present(path):
        installation._make_quarantine_non_executable(path)
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def _install_from_raw(target: Path, raw_object: Path, selection: TreeSelection) -> Path:
    descriptor = validation.validated_descriptor(selection)
    limits = archive.TreeLimits(
        file_count=descriptor.file_count,
        directory_count=descriptor.directory_count,
        symlink_count=descriptor.symlink_count,
        expanded_bytes=descriptor.expanded_bytes,
        exact=True,
    )
    stage = Path(tempfile.mkdtemp(prefix=f".stage-{target.name}-", dir=target.parent))
    try:
        stage.chmod(0o700)
        content = stage / TREE_CONTENT_NAME
        content.mkdir(mode=0o700)
        with validation.opened_verified_raw(raw_object, selection.raw_manifest[0], mode="installed") as stream:
            entries = archive.admit_archive_stream(stream, limits, archive.StageSink(content))
        payload = archive.bounded_manifest_bytes(entries)
        if hashlib.sha256(payload).hexdigest() != descriptor.manifest_sha256:
            raise _failure("installed-manifest-mismatch")
        validation.require_installed_manifest(selection, {entry.path: entry for entry in entries})
        installation._write_file(stage / TREE_MANIFEST_NAME, payload)
        installation._publication_checkpoint("staged-written", stage)
        _seal_stage(stage, entries)
        installation._seal_staged_root(stage)
        installation._publication_checkpoint("staged-durable", stage)
        installation._publish_staged_root(stage, target)
        installation._publication_checkpoint("published", target)
        installation._fsync_directory(target.parent)
        installation._publication_checkpoint("parent-durable", target)
    finally:
        _discard(stage)
    return validation.validated_installation(target, selection)


def _publish_raw(source: Path, raw_object: Path) -> None:
    source.chmod(0o400)
    _fsync_file(source)
    installation._publication_checkpoint("raw-staged-durable", source)
    os.rename(source, raw_object)
    installation._fsync_directory(raw_object.parent)
    installation._publication_checkpoint("raw-published", raw_object)


def _admit_raw_object(
    raw_parent: Path,
    selection: TreeSelection,
    acquire_raw: Callable[[Path], None],
    quarantine_root: Path,
) -> Path:
    entry = selection.raw_manifest[0]
    raw_object = raw_parent / RAW_OBJECT_NAME
    carriers = sorted(raw_parent.glob(f"{LEGACY_CARRIER_PREFIX}*"))
    if installation._tree_present(raw_object):
        for carrier in carriers:
            installation._quarantine(carrier, quarantine_root, prefix="legacy")
        try:
            validation.verify_raw_file(raw_object, entry, mode="installed")
        except (OSError, RuntimeError):
            installation._quarantine(raw_object, quarantine_root, prefix="raw")
            raise _failure("raw-integrity-failure") from None
        return raw_object
    if carriers:
        for extra in carriers[1:]:
            installation._quarantine(extra, quarantine_root, prefix="legacy")
        try:
            validation.verify_raw_file(carriers[0], entry, mode="carrier")
        except (OSError, RuntimeError):
            installation._quarantine(carriers[0], quarantine_root, prefix="legacy")
            raise _failure("legacy-integrity-failure") from None
        _publish_raw(carriers[0], raw_object)
        return raw_object
    descriptor, staged_name = tempfile.mkstemp(prefix=".stage-raw-", dir=raw_parent)
    os.close(descriptor)
    staged = Path(staged_name)
    try:
        acquire_raw(staged)
        try:
            validation.verify_raw_file(staged, entry, mode="staged")
        except (OSError, RuntimeError):
            raise _failure("raw-manifest-mismatch") from None
        _publish_raw(staged, raw_object)
    finally:
        staged.unlink(missing_ok=True)
    return raw_object


def _migrate_legacy(legacy: LegacyTreeInputs, raw_parent: Path, quarantine_root: Path) -> None:
    carrier = legacy.raw_carrier
    if carrier is not None and installation._tree_present(carrier):
        state = carrier.lstat()
        if not stat.S_ISREG(state.st_mode) or state.st_uid != os.geteuid():
            installation._quarantine(carrier, quarantine_root, prefix="legacy")
            raise _failure("legacy-integrity-failure")
        destination = raw_parent / f"{LEGACY_CARRIER_PREFIX}{uuid.uuid4().hex}"
        os.replace(carrier, destination)
        destination.chmod(0o600)
        installation._fsync_directory(carrier.parent)
        installation._fsync_directory(raw_parent)
    for derived in legacy.derived_paths:
        if installation._tree_present(derived):
            installation._quarantine(derived, quarantine_root, prefix="legacy")


def _validated_or_quarantined(target: Path, selection: TreeSelection, quarantine_root: Path) -> Path:
    try:
        installation._complete_interrupted_seal(target)
        return validation.validated_installation(target, selection)
    except (OSError, RuntimeError):
        installation._quarantine(target, quarantine_root, prefix="cache")
        raise _failure("cache-integrity-failure") from None


def _validated_or_repaired_existing(
    target: Path,
    selection: TreeSelection,
    identity_lock: Path,
    quarantine_root: Path,
) -> Path | None:
    """Return a valid existing tree, or ``None`` when no installation exists yet."""

    if not installation._tree_present(target):
        return None
    try:
        return validation.validated_installation(target, selection)
    except (OSError, RuntimeError):
        with installation._portable_lock(identity_lock, timeout=TREE_LOCK_TIMEOUT_SECONDS):
            if installation._tree_present(target):  # NOSONAR -- recheck under the lock closes the race.
                return _validated_or_quarantined(target, selection, quarantine_root)
        raise _failure("cache-integrity-failure") from None


def _ensure_tree(
    install_root: Path,
    selection: TreeSelection,
    *,
    acquire_raw: Callable[[Path], None],
    legacy: LegacyTreeInputs | None,
) -> Path:
    target = tree_installation_path(install_root, selection)
    raw_parent = _raw_parent(install_root, selection)
    artifact_root = install_root / selection.artifact_id
    lock_root = artifact_root / ".locks"
    quarantine_root = artifact_root / ".quarantine"
    for directory in (target.parent, lock_root, quarantine_root):
        installation._ensure_private_subdirectory(directory, install_root)
    identity_lock = lock_root / f"install-tree-{selection.raw_manifest[0].sha256}.lock"
    migration_lock = lock_root / f"migration-tree-{selection.platform_id}.lock"

    installed = _validated_or_repaired_existing(target, selection, identity_lock, quarantine_root)
    if installed is not None:
        return installed

    if legacy is not None:
        with installation._portable_lock(migration_lock, timeout=TREE_LOCK_TIMEOUT_SECONDS):
            _migrate_legacy(legacy, raw_parent, quarantine_root)

    with installation._portable_lock(identity_lock, timeout=TREE_LOCK_TIMEOUT_SECONDS):
        installation._clean_staging(target.parent, target.name)
        for staged_raw in raw_parent.glob(".stage-raw-*"):
            _discard(staged_raw)
        if installation._tree_present(target):
            return _validated_or_quarantined(target, selection, quarantine_root)
        raw_object = _admit_raw_object(raw_parent, selection, acquire_raw, quarantine_root)
        return _install_from_raw(target, raw_object, selection)


def _storage_failure(exc: OSError) -> RuntimeError:
    reason = "storage-exhausted" if exc.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)} else "filesystem-failure"
    return _failure(reason)


def ensure_verified_tree_installation(
    repo_root: Path,
    selection: TreeSelection,
    *,
    acquire_raw: Callable[[Path], None],
    legacy: LegacyTreeInputs | None = None,
    installation_root: Path | None = None,
) -> Path:
    """Return the root of one fully admitted, immutable installed tree."""

    try:
        install_root = installation_root or installation.default_installation_root(repo_root)
        with installation._private_root_guard(repo_root, install_root):
            return _ensure_tree(install_root, selection, acquire_raw=acquire_raw, legacy=legacy)
    except RuntimeError:
        raise
    except OSError as exc:
        raise _storage_failure(exc) from None


def require_verified_tree_installation(
    repo_root: Path,
    selection: TreeSelection,
    *,
    installation_root: Path | None = None,
) -> Path:
    """Verify an existing installed tree completely without acquiring or installing."""

    try:
        install_root = installation_root or installation.default_installation_root(repo_root)
        with installation._private_root_guard(repo_root, install_root):
            target = tree_installation_path(install_root, selection)
            if not installation._tree_present(target):
                raise _failure("installation-missing")
            try:
                return validation.validated_installation(target, selection)
            except (OSError, RuntimeError):
                raise _failure("cache-integrity-failure") from None
    except RuntimeError:
        raise
    except OSError as exc:
        raise _storage_failure(exc) from None


__all__ = [
    "INSTALLATION_TREE_POLICY_ID",
    "LegacyTreeInputs",
    "TreeEntry",
    "describe_archive_tree",
    "ensure_verified_tree_installation",
    "manifest_bytes",
    "require_verified_tree_installation",
    "tree_installation_path",
]
