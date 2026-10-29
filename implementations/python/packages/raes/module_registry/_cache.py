"""Bounded OCI cache admission, locking, inventory, and recovery helpers."""

from __future__ import annotations

import contextlib
import gzip
import io
import os
import stat
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, BinaryIO

from .._errors import SDLParseError
from ._cache_integrity import _DECOMPRESSION_CHUNK_BYTES, _validated_cache_root
from ._filesystem import (
    _O_BINARY,
    _O_DIRECTORY,
    _O_NOFOLLOW,
    _iter_version_directories,
    _prune_version_directories,
    _read_version_pointer,
    _require_directory,
    _same_file_identity,
    _version_digest_prefix,
    _write_version_pointer,
)

if TYPE_CHECKING:
    from . import _OCIResourceLimits

_CACHE_THREAD_LOCKS: dict[str, threading.Lock] = {}
_CACHE_THREAD_LOCKS_GUARD = threading.Lock()
_SPOOL_MEMORY_BYTES = 8 * 1024 * 1024
_WINDOWS_LOCKING = os.name == "nt"
_LOCK_DIR_FD_SUPPORTED = os.open in os.supports_dir_fd


def _limits() -> _OCIResourceLimits:
    # Keep the historical package-facade test/operator seam authoritative.
    from . import _OCI_LIMITS

    return _OCI_LIMITS


def _acquire_file_lock(handle: BinaryIO) -> None:
    """Acquire an OS-backed exclusive lock within the configured OCI timeout."""

    deadline = time.monotonic() + _limits().timeout_seconds
    while True:
        try:
            if _WINDOWS_LOCKING:
                import msvcrt

                handle.seek(0)
                if handle.read(1) == b"":
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if time.monotonic() >= deadline:
                raise SDLParseError("Timed out waiting for the OCI module cache lock") from exc
            time.sleep(0.01)


def _release_file_lock(handle: BinaryIO) -> None:
    if _WINDOWS_LOCKING:
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _anchored_lock_parent(
    lock_path: Path,
    *,
    error_message: str,
) -> tuple[int, os.stat_result, str | Path, dict[str, int]]:
    parent_expected = lock_path.parent.lstat()
    if not stat.S_ISDIR(parent_expected.st_mode):
        raise SDLParseError(error_message)
    if not _LOCK_DIR_FD_SUPPORTED:
        return -1, parent_expected, lock_path, {}

    parent_flags = os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW
    parent_descriptor = os.open(lock_path.parent, parent_flags)
    try:
        parent_actual = os.fstat(parent_descriptor)
        if not stat.S_ISDIR(parent_actual.st_mode) or not _same_file_identity(parent_expected, parent_actual):
            raise SDLParseError(error_message)
    except OSError, SDLParseError:
        os.close(parent_descriptor)
        raise
    return parent_descriptor, parent_actual, lock_path.name, {"dir_fd": parent_descriptor}


def _lock_file_stat(lock_path: Path, parent_descriptor: int) -> os.stat_result:
    if parent_descriptor >= 0:
        return os.stat(lock_path.name, dir_fd=parent_descriptor, follow_symlinks=False)
    return lock_path.lstat()


def _open_existing_lock_file(
    open_path: str | Path,
    *,
    expected: os.stat_result,
    common_flags: int,
    open_options: dict[str, int],
    error_message: str,
) -> int:
    if not stat.S_ISREG(expected.st_mode):
        raise SDLParseError(error_message)
    return os.open(open_path, common_flags, **open_options)


def _open_lock_file(
    lock_path: Path,
    *,
    parent_descriptor: int,
    open_path: str | Path,
    common_flags: int,
    open_options: dict[str, int],
    error_message: str,
) -> tuple[int, os.stat_result | None]:
    try:
        expected = _lock_file_stat(lock_path, parent_descriptor)
    except FileNotFoundError:
        try:
            descriptor = os.open(open_path, common_flags | os.O_CREAT | os.O_EXCL, 0o600, **open_options)
        except FileExistsError:
            # A concurrent first user may create the shared lock after our
            # missing-path check. Re-enter the same no-follow admission path.
            expected = _lock_file_stat(lock_path, parent_descriptor)
            descriptor = _open_existing_lock_file(
                open_path,
                expected=expected,
                common_flags=common_flags,
                open_options=open_options,
                error_message=error_message,
            )
        else:
            expected = None
    else:
        descriptor = _open_existing_lock_file(
            open_path,
            expected=expected,
            common_flags=common_flags,
            open_options=open_options,
            error_message=error_message,
        )
    return descriptor, expected


def _validate_open_lock(
    lock_path: Path,
    *,
    descriptor: int,
    expected: os.stat_result | None,
    parent_actual: os.stat_result,
    error_message: str,
) -> None:
    actual = os.fstat(descriptor)
    if not stat.S_ISREG(actual.st_mode) or (expected is not None and not _same_file_identity(expected, actual)):
        raise SDLParseError(error_message)
    parent_after = lock_path.parent.lstat()
    if not stat.S_ISDIR(parent_after.st_mode) or not _same_file_identity(parent_actual, parent_after):
        raise SDLParseError(error_message)


def _open_cache_lock(lock_path: Path) -> BinaryIO:
    """Open one regular lock file, anchored to a validated parent directory."""

    error_message = "Unable to open the OCI module cache lock"
    _require_directory(lock_path.parent, error_message=error_message)
    common_flags = os.O_RDWR | _O_BINARY | _O_NOFOLLOW
    descriptor = -1
    parent_descriptor = -1
    try:
        parent_descriptor, parent_actual, open_path, open_options = _anchored_lock_parent(
            lock_path,
            error_message=error_message,
        )
        descriptor, expected = _open_lock_file(
            lock_path,
            parent_descriptor=parent_descriptor,
            open_path=open_path,
            common_flags=common_flags,
            open_options=open_options,
            error_message=error_message,
        )
        _validate_open_lock(
            lock_path,
            descriptor=descriptor,
            expected=expected,
            parent_actual=parent_actual,
            error_message=error_message,
        )
        handle = os.fdopen(descriptor, "r+b")
        descriptor = -1
        return handle
    except SDLParseError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise SDLParseError(error_message) from exc
    finally:
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


@contextlib.contextmanager
def _cache_entry_lock(lock_path: Path) -> Iterator[None]:
    from . import _acquire_file_lock, _open_cache_lock, _release_file_lock

    lock_key = str(lock_path.absolute())
    with _CACHE_THREAD_LOCKS_GUARD:
        thread_lock = _CACHE_THREAD_LOCKS.setdefault(lock_key, threading.Lock())
    with thread_lock:
        handle = _open_cache_lock(lock_path)
        acquired = False
        try:
            _acquire_file_lock(handle)
            acquired = True
            yield
        finally:
            if acquired:
                _release_file_lock(handle)
            handle.close()


@contextlib.contextmanager
def _bounded_gzip_tar_stream(bundle_bytes: bytes) -> Iterator[BinaryIO]:
    """Decode a complete gzip stream behind absolute and ratio bounds."""

    limits = _limits()
    absolute_limit = limits.max_tar_stream_bytes
    ratio_limit = len(bundle_bytes) * limits.max_gzip_expansion_ratio
    if absolute_limit < 0 or limits.max_gzip_expansion_ratio < 0:
        raise SDLParseError("OCI gzip expansion limits must be non-negative")
    total = 0
    with (
        tempfile.SpooledTemporaryFile(max_size=_SPOOL_MEMORY_BYTES, mode="w+b") as stream,
        gzip.GzipFile(fileobj=io.BytesIO(bundle_bytes), mode="rb") as decoded,
    ):
        while True:
            remaining = min(absolute_limit - total, ratio_limit - total)
            read_size = min(_DECOMPRESSION_CHUNK_BYTES, max(1, remaining + 1))
            chunk = decoded.read(read_size)
            if not chunk:
                break
            total += len(chunk)
            if total > absolute_limit:
                raise SDLParseError(f"OCI bundle uncompressed tar stream exceeds the {absolute_limit}-byte limit")
            if total > ratio_limit:
                raise SDLParseError("OCI bundle gzip expansion exceeds the configured compressed-to-uncompressed ratio")
            stream.write(chunk)
        stream.seek(0)
        yield stream


def _recover_cache_root(
    *,
    slot: Path,
    versions: Path,
    expected_content_digest: str,
    expected_manifest: dict[str, Any],
    root_relative: PurePosixPath,
) -> Path | None:
    """Find a valid current/orphan version and repair its pointer when needed."""

    current = _read_version_pointer(slot=slot)
    candidates: list[Path] = []
    if current is not None:
        candidates.append(versions / current)
    digest_prefix = _version_digest_prefix(expected_content_digest)
    for version in _iter_version_directories(
        versions,
        error_message="Unable to inspect OCI module cache versions",
    ):
        if version.name.startswith(digest_prefix) and version not in candidates:
            candidates.append(version)
    for version in candidates[:64]:
        root = _validated_cache_root(
            version=version,
            expected_manifest=expected_manifest,
            root_relative=root_relative,
        )
        if root is None:
            continue
        _prune_version_directories(
            versions=versions,
            retain_names={version.name, *(() if current is None else (current,))},
            error_message="Unable to prune stale OCI module cache versions",
        )
        if current != version.name:
            _write_version_pointer(
                slot=slot,
                version_name=version.name,
                error_message="Unable to commit the OCI module cache pointer atomically",
            )
        return root
    return None
