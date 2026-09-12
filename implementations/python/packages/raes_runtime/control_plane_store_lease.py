"""Secure, exclusive runtime ownership for the local control-plane store."""

from __future__ import annotations

import os
import stat
from contextlib import suppress
from pathlib import Path

_WORKER_COUNT_ENVIRONMENTS = ("WEB_CONCURRENCY", "UVICORN_WORKERS")


def _is_windows() -> bool:
    return os.name == "nt"


def _runtime_owner_is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _require_safe_runtime_owner_metadata(metadata: os.stat_result, path: Path) -> None:
    if stat.S_ISLNK(metadata.st_mode) or _runtime_owner_is_reparse_point(metadata):
        raise RuntimeError(f"runtime-owner lock path must not be a symlink or reparse point: {path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"runtime-owner lock path must be a regular file: {path}")
    get_effective_uid = getattr(os, "geteuid", None)
    if callable(get_effective_uid) and metadata.st_uid != get_effective_uid():
        raise RuntimeError(f"runtime-owner lock path must be owned by the current user: {path}")
    if getattr(metadata, "st_nlink", 1) != 1:
        raise RuntimeError(f"runtime-owner lock path must not have hard links: {path}")


def _existing_runtime_owner_metadata(path: Path) -> os.stat_result | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    _require_safe_runtime_owner_metadata(metadata, path)
    return metadata


def require_single_worker_configuration() -> None:
    for variable in _WORKER_COUNT_ENVIRONMENTS:
        configured = os.environ.get(variable)
        if configured is None or not configured.strip():
            continue
        try:
            worker_count = int(configured)
        except ValueError as exc:
            raise RuntimeError(f"{variable} must be 1 for a local control-plane store") from exc
        if worker_count != 1:
            raise RuntimeError(
                f"{variable}={worker_count} is unsupported for a local control-plane store; "
                "use exactly one worker with reload disabled"
            )


def _lock_runtime_owner(descriptor: int) -> None:
    if _is_windows():
        import msvcrt

        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_runtime_owner(descriptor: int) -> None:
    if _is_windows():
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_UN)


def _acquire_store_directory_guard(path: Path) -> int | None:
    """Hold a POSIX lock that survives lock-file unlink or replacement."""

    if _is_windows():
        return None
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path.parent, flags)
    except OSError as exc:
        raise RuntimeError(f"could not securely open runtime-owner store directory: {path.parent}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError(f"runtime-owner store path must be a directory: {path.parent}")
        _lock_runtime_owner(descriptor)
    except OSError as exc:
        os.close(descriptor)
        raise RuntimeError(
            "local control-plane store already has a runtime owner; use exactly one worker with reload disabled"
        ) from exc
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _release_store_directory_guard(descriptor: int | None, *, owner_process: bool) -> None:
    if descriptor is None:
        return
    try:
        if owner_process:
            _unlock_runtime_owner(descriptor)
    finally:
        os.close(descriptor)


def _open_runtime_owner_file(path: Path) -> tuple[int, os.stat_result]:
    _existing_runtime_owner_metadata(path)
    flags = os.O_CREAT | os.O_RDWR
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"could not securely open runtime-owner lock path: {path}") from exc
    try:
        opened_metadata = _validate_open_runtime_owner_file(descriptor, path)
        _claim_runtime_owner_file(descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, opened_metadata


def _validate_open_runtime_owner_file(descriptor: int, path: Path) -> os.stat_result:
    opened_metadata = os.fstat(descriptor)
    _require_safe_runtime_owner_metadata(opened_metadata, path)
    current_metadata = path.lstat()
    _require_safe_runtime_owner_metadata(current_metadata, path)
    if not os.path.samestat(opened_metadata, current_metadata):
        raise RuntimeError(f"runtime-owner lock path changed while it was opened: {path}")
    return opened_metadata


def _claim_runtime_owner_file(descriptor: int) -> None:
    if not _is_windows():
        os.fchmod(descriptor, 0o600)
    try:
        _lock_runtime_owner(descriptor)
    except OSError as exc:
        raise RuntimeError(
            "local control-plane store already has a runtime owner; use exactly one worker with reload disabled"
        ) from exc
    owner = f"{os.getpid()}\n".encode("ascii")
    os.ftruncate(descriptor, 0)
    os.write(descriptor, owner)
    os.fsync(descriptor)


class RuntimeOwnerLease:
    """Exclusive, process-bound authority to drive one local runtime target."""

    def __init__(
        self,
        descriptor: int,
        *,
        path: Path | None = None,
        identity: os.stat_result | None = None,
        directory_descriptor: int | None = None,
    ) -> None:
        self._descriptor = descriptor
        self._path = path
        self._identity = identity
        self._directory_descriptor = directory_descriptor
        self._owner_pid = os.getpid()
        self._closed = False

    @classmethod
    def acquire(cls, path: Path) -> RuntimeOwnerLease:
        directory_descriptor = _acquire_store_directory_guard(path)
        try:
            descriptor, opened_metadata = _open_runtime_owner_file(path)
        except BaseException:
            _release_store_directory_guard(directory_descriptor, owner_process=True)
            raise
        return cls(
            descriptor,
            path=path,
            identity=opened_metadata,
            directory_descriptor=directory_descriptor,
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def assert_owner(self) -> None:
        if self._closed:
            raise RuntimeError("local control-plane runtime-owner lease is closed")
        if os.getpid() != self._owner_pid:
            raise RuntimeError(
                "local control-plane runtime-owner lease cannot be used after fork; "
                "construct one runtime in a single worker with reload disabled"
            )
        if self._path is None or self._identity is None:
            return
        current_metadata = _existing_runtime_owner_metadata(self._path)
        if current_metadata is None or not os.path.samestat(self._identity, current_metadata):
            raise RuntimeError(f"runtime-owner lock path changed while the lease was active: {self._path}")

    def close(self) -> None:
        if self._closed:
            return
        descriptor = self._descriptor
        directory_descriptor = self._directory_descriptor
        self._closed = True
        owner_process = os.getpid() == self._owner_pid
        try:
            if owner_process:
                _unlock_runtime_owner(descriptor)
        finally:
            try:
                os.close(descriptor)
            finally:
                _release_store_directory_guard(directory_descriptor, owner_process=owner_process)

    def __del__(self) -> None:
        with suppress(OSError):
            self.close()


__all__ = ("RuntimeOwnerLease", "require_single_worker_configuration")
