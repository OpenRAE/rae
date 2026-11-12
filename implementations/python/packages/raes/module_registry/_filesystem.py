"""Gapless filesystem publication helpers for OCI layouts and cache trees."""

from __future__ import annotations

import contextlib
import errno
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

from raes_contracts.errors import OperationalError
from raes_contracts.operational_logging import get_logger

_LOGGER = get_logger(__name__)
_CURRENT_POINTER_NAME = ".raes-current"
_POINTER_STAGE_PREFIX = f"{_CURRENT_POINTER_NAME}.staged-"
_VERSION_STAGE_PREFIX = ".staged-"
_VERSIONS_DIRECTORY_NAME = "versions"
_MAX_POINTER_BYTES = 256
_MAX_RETAINED_VERSIONS = 8
_VERSION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
_INVALID_VERSION_NAME = "version name must be a bounded portable directory name"
_VERSION_DIGEST_PREFIX_HEX = 20
_VERSION_NONCE_HEX = 20
_DIRECTORY_FSYNC_SUPPORTED = os.name != "nt"
_O_BINARY = getattr(os, "O_BINARY", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
# Windows implements os.fsync with MSVCRT _commit, which rejects a read-only
# descriptor. Transaction stages are writable; POSIX retains its read-only open.
_REGULAR_FILE_FSYNC_ACCESS_MODE = os.O_RDWR if os.name == "nt" else os.O_RDONLY


def _version_digest_prefix(digest: str) -> str:
    """Return the bounded content prefix used to find immutable versions."""

    return digest.removeprefix("sha256:")[:_VERSION_DIGEST_PREFIX_HEX]


def _new_digest_version_name(digest: str) -> str:
    """Return a version lookup discriminator with bounded path growth.

    The full digest remains authoritative in each domain's validated contents;
    this prefix and nonce only name an immutable filesystem version.
    """

    nonce = uuid4().hex[:_VERSION_NONCE_HEX]
    return f"{_version_digest_prefix(digest)}-{nonce}"


def _remove_path(path: Path) -> None:
    """Remove one explicitly resolved transaction path without following links."""

    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _fsync_directory(path: Path, *, error_message: str) -> None:
    """Persist directory-entry changes where the host exposes directory fsync."""

    if not _DIRECTORY_FSYNC_SUPPORTED:
        return
    flags = os.O_RDONLY | _O_DIRECTORY | _O_CLOEXEC
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        os.fsync(descriptor)
    except OSError as exc:
        unsupported = {
            errno.EINVAL,
            getattr(errno, "ENOTSUP", errno.EINVAL),
            getattr(errno, "EOPNOTSUPP", errno.EINVAL),
        }
        if exc.errno in unsupported:
            return
        raise OperationalError(error_message) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    if left.st_dev and right.st_dev and left.st_dev != right.st_dev:
        return False
    return not (left.st_ino and right.st_ino and left.st_ino != right.st_ino)


def _fsync_tree(root: Path, *, error_message: str) -> None:
    """Persist a validated regular-file/directory tree before publishing it."""

    pending = [root]
    directories: list[Path] = []
    try:
        while pending:
            path = pending.pop()
            expected = path.lstat()
            if stat.S_ISLNK(expected.st_mode):
                raise OperationalError(error_message)
            if stat.S_ISDIR(expected.st_mode):
                directories.append(path)
                with os.scandir(path) as iterator:
                    pending.extend(Path(entry.path) for entry in iterator)
                continue
            if not stat.S_ISREG(expected.st_mode):
                raise OperationalError(error_message)
            flags = _REGULAR_FILE_FSYNC_ACCESS_MODE | _O_BINARY | _O_NOFOLLOW
            descriptor = os.open(path, flags)
            try:
                actual = os.fstat(descriptor)
                if not stat.S_ISREG(actual.st_mode) or not _same_file_identity(expected, actual):
                    raise OperationalError(error_message)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            _fsync_directory(directory, error_message=error_message)
    except OSError as exc:
        raise OperationalError(error_message) from exc


def _require_directory(path: Path, *, error_message: str) -> None:
    """Create one directory while rejecting a file or symlink at its name."""

    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise OperationalError(error_message)
    existed = path.exists()
    try:
        path.mkdir(parents=False, exist_ok=True)
    except OSError as exc:
        raise OperationalError(error_message) from exc
    # Recheck after mkdir so a concurrent replacement cannot turn the slot into a
    # link between the preflight and use. Domain writers serialize access to a
    # logical slot, while this check also fails closed on external interference.
    if path.is_symlink() or not path.is_dir():
        raise OperationalError(error_message)
    if not existed:
        _fsync_directory(path.parent, error_message=error_message)


def _prepare_versioned_slot(*, slot: Path, error_message: str) -> Path:
    """Return a safe versions directory and remove crash-only temporary names.

    Complete versions are never removed here: one may be held by a reader or may
    be the only recoverable version after a process died between installing it
    and replacing the pointer. Only names that can never be published are
    cleaned.
    """

    _require_directory(slot, error_message=error_message)
    versions = slot / _VERSIONS_DIRECTORY_NAME
    _require_directory(versions, error_message=error_message)
    try:
        for child in versions.iterdir():
            if child.name.startswith(_VERSION_STAGE_PREFIX):
                _remove_path(child)
        for child in slot.iterdir():
            if child.name.startswith(_POINTER_STAGE_PREFIX):
                _remove_path(child)
    except OSError as exc:
        raise OperationalError(error_message) from exc
    return versions


def _valid_version_name(name: str) -> bool:
    return bool(_VERSION_NAME.fullmatch(name)) and name not in {".", ".."}


def _iter_version_directories(
    versions: Path,
    *,
    error_message: str = "Unable to inspect immutable version directories",
) -> Iterator[Path]:
    """Yield immutable versions in a deterministic order, never following links."""

    try:
        children = sorted(versions.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise OperationalError(error_message) from exc
    for child in children:
        if _valid_version_name(child.name) and not child.is_symlink() and child.is_dir():
            yield child


def _prune_version_directories(
    *,
    versions: Path,
    retain_names: set[str],
    error_message: str,
    max_versions: int = _MAX_RETAINED_VERSIONS,
) -> None:
    """Bound retained immutable versions while preserving current/prior readers.

    Domain writers call this under the logical-slot lock after publishing. The
    selected version and the pointer value observed before publication are
    explicit retains; the newest remaining versions fill the bounded support
    window. Content is never modified in place.
    """

    if max_versions < 2 or len(retain_names) > max_versions:
        raise ValueError("version retention requires at least two slots and no more retained names than slots")
    try:
        ranked = sorted(
            _iter_version_directories(versions, error_message=error_message),
            key=lambda version: (version.stat().st_mtime_ns, version.name),
            reverse=True,
        )
        keep = {name for name in retain_names if _valid_version_name(name)}
        for version in ranked:
            if len(keep) >= max_versions:
                break
            keep.add(version.name)
        for version in ranked:
            if version.name not in keep:
                _remove_path(version)
        _fsync_directory(versions, error_message=error_message)
    except OSError as exc:
        raise OperationalError(error_message) from exc


def _read_version_pointer(*, slot: Path) -> str | None:
    """Read the current-version pointer, returning ``None`` when it is invalid."""

    pointer = slot / _CURRENT_POINTER_NAME
    payload = _read_version_pointer_payload(pointer)
    name = _decode_version_pointer(payload)
    if name is None:
        return None
    version = slot / _VERSIONS_DIRECTORY_NAME / name
    return name if not version.is_symlink() and version.is_dir() else None


def _read_version_pointer_payload(pointer: Path) -> bytes | None:
    """Read a bounded pointer payload through a stable regular-file descriptor."""

    descriptor = -1
    payload: bytes | None = None
    try:
        expected = pointer.lstat()
        if stat.S_ISREG(expected.st_mode):
            flags = os.O_RDONLY | _O_BINARY | _O_NOFOLLOW
            descriptor = os.open(pointer, flags)
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                actual = os.fstat(handle.fileno())
                if stat.S_ISREG(actual.st_mode) and _same_file_identity(expected, actual):
                    payload = handle.read(_MAX_POINTER_BYTES + 1)
    except FileNotFoundError:
        pass
    except OSError:
        # Callers recover from the immutable versions; the record shows the degraded read (rule H3).
        _LOGGER.warning("version pointer could not be read; recovery treats it as absent", exc_info=True)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return payload


def _decode_version_pointer(payload: bytes | None) -> str | None:
    """Decode the exact canonical pointer representation, if valid."""

    name: str | None = None
    if payload is not None and len(payload) <= _MAX_POINTER_BYTES:
        try:
            candidate = payload.decode("ascii").removesuffix("\n")
        except UnicodeDecodeError:
            pass
        else:
            if payload == f"{candidate}\n".encode("ascii") and _valid_version_name(candidate):
                name = candidate
    return name


def _install_version_directory(
    *,
    staged: Path,
    versions: Path,
    version_name: str,
    error_message: str,
) -> Path:
    """Install a complete new immutable version with one directory rename."""

    if not _valid_version_name(version_name):
        _remove_path(staged)
        raise ValueError(_INVALID_VERSION_NAME)
    target = versions / version_name
    if target.exists() or target.is_symlink():
        _remove_path(staged)
        raise OperationalError(error_message)
    try:
        _fsync_tree(staged, error_message=error_message)
        os.replace(staged, target)
        _fsync_directory(versions, error_message=error_message)
    except OSError as exc:
        _remove_path(staged)
        raise OperationalError(error_message) from exc
    except BaseException:
        _remove_path(staged)
        raise
    return target


def _write_version_pointer(
    *,
    slot: Path,
    version_name: str,
    error_message: str,
) -> None:
    """Publish a version by atomically replacing one small pointer file.

    The old pointer is never removed first. A crash before ``os.replace`` leaves
    it untouched; a crash after ``os.replace`` leaves the complete new version
    selected. The temporary pointer is safe startup residue and is removed by
    :func:`_prepare_versioned_slot`.
    """

    if not _valid_version_name(version_name):
        raise ValueError(_INVALID_VERSION_NAME)
    version = slot / _VERSIONS_DIRECTORY_NAME / version_name
    if version.is_symlink() or not version.is_dir():
        raise OperationalError(error_message)
    pointer = slot / _CURRENT_POINTER_NAME
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(prefix=_POINTER_STAGE_PREFIX, dir=slot)
        temporary = Path(raw_path)
        payload = f"{version_name}\n".encode("ascii")
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, pointer)
        _fsync_directory(slot, error_message=error_message)
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            with contextlib.suppress(OSError):
                _remove_path(temporary)
        raise OperationalError(error_message) from exc


def _new_version_stage(*, versions: Path, error_message: str) -> Path:
    """Create a private sibling stage inside a version store."""

    try:
        return Path(tempfile.mkdtemp(prefix=_VERSION_STAGE_PREFIX, dir=versions))
    except OSError as exc:
        raise OperationalError(error_message) from exc
