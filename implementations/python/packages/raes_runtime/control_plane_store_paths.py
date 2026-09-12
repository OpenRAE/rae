"""Private filesystem boundary for the local control-plane store."""

from __future__ import annotations

import errno
import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from raes_contracts.runtime_state import RuntimeSnapshot

_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_DATABASE_FILE_KIND = "database file"
_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_DIRECTORY_FSYNC_SUPPORTED = os.name != "nt"
_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = frozenset(
    {
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
)


def _store_path_is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _require_safe_link_count(metadata: os.stat_result, path: Path, *, kind: str) -> None:
    link_count = getattr(metadata, "st_nlink", 1)
    unsafe = (kind == _DATABASE_FILE_KIND and link_count != 1) or (kind == "SQLite sidecar" and link_count > 1)
    if unsafe:
        raise RuntimeError(f"local control-plane {kind} must not have hard links: {path}")


def _require_safe_store_path_metadata(
    metadata: os.stat_result,
    path: Path,
    *,
    kind: str,
) -> None:
    if stat.S_ISLNK(metadata.st_mode) or _store_path_is_reparse_point(metadata):
        raise RuntimeError(f"local control-plane {kind} must not be a symlink or reparse point: {path}")
    expected = stat.S_ISDIR(metadata.st_mode) if kind == "directory" else stat.S_ISREG(metadata.st_mode)
    if not expected:
        raise RuntimeError(f"local control-plane {kind} has the wrong filesystem type: {path}")
    get_effective_uid = getattr(os, "geteuid", None)
    if callable(get_effective_uid) and metadata.st_uid != get_effective_uid():
        raise RuntimeError(f"local control-plane {kind} must be owned by the current user: {path}")
    _require_safe_link_count(metadata, path, kind=kind)


def _secure_store_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        path.mkdir(mode=_PRIVATE_DIRECTORY_MODE, parents=True, exist_ok=True)
        metadata = path.lstat()
    _require_safe_store_path_metadata(metadata, path, kind="directory")
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened_metadata = os.fstat(descriptor)
        _require_safe_store_path_metadata(opened_metadata, path, kind="directory")
        current_metadata = path.lstat()
        _require_safe_store_path_metadata(current_metadata, path, kind="directory")
        if not os.path.samestat(opened_metadata, current_metadata):
            raise RuntimeError(f"local control-plane directory changed while it was opened: {path}")
        os.fchmod(descriptor, _PRIVATE_DIRECTORY_MODE)
    finally:
        os.close(descriptor)


def _secure_database_file(path: Path, *, allow_missing: bool) -> os.stat_result | None:
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        if allow_missing:
            return None
        raise RuntimeError(f"local control-plane database file is missing: {path}") from exc
    _require_safe_store_path_metadata(before, path, kind=_DATABASE_FILE_KIND)
    if os.name != "nt" and stat.S_IMODE(before.st_mode) != _PRIVATE_FILE_MODE:
        try:
            os.chmod(path, _PRIVATE_FILE_MODE, follow_symlinks=False)
        except (NotImplementedError, OSError) as exc:
            raise RuntimeError(f"could not secure local control-plane database file: {path}") from exc
    try:
        after = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"local control-plane database file disappeared while it was secured: {path}") from exc
    _require_safe_store_path_metadata(after, path, kind=_DATABASE_FILE_KIND)
    if not os.path.samestat(before, after):
        raise RuntimeError(f"local control-plane database file changed while it was secured: {path}")
    if os.name != "nt" and stat.S_IMODE(after.st_mode) != _PRIVATE_FILE_MODE:
        raise RuntimeError(f"local control-plane database file must use private permissions 0600: {path}")
    return after


def _require_same_file(
    before: os.stat_result,
    after: os.stat_result,
    path: Path,
    activity: str,
) -> None:
    if not os.path.samestat(before, after):
        raise RuntimeError(f"local control-plane database file changed while {activity}: {path}")


def _validate_sqlite_sidecar(path: Path) -> bool:
    """Validate an ephemeral SQLite file without disturbing its POSIX locks."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    _require_safe_store_path_metadata(metadata, path, kind="SQLite sidecar")
    if getattr(metadata, "st_nlink", 1) == 0:
        return False
    if os.name != "nt" and stat.S_IMODE(metadata.st_mode) != _PRIVATE_FILE_MODE:
        raise RuntimeError(f"local control-plane SQLite sidecar must use private permissions 0600: {path}")
    return True


def _validate_sqlite_sidecars(database_path: Path) -> None:
    for suffix in _SQLITE_SIDECAR_SUFFIXES:
        _validate_sqlite_sidecar(Path(f"{database_path}{suffix}"))


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"legacy control-plane file must contain an object: {path.name}")
    return payload


def _fsync_directory(path: Path) -> None:
    """Persist directory entries, failing closed on real I/O failures."""

    if not _DIRECTORY_FSYNC_SUPPORTED:
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            return
        raise RuntimeError(f"could not durably synchronize local control-plane directory: {path}") from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            return
        raise RuntimeError(f"could not durably synchronize local control-plane directory: {path}") from exc
    finally:
        os.close(descriptor)


def _fsync_regular_file(path: Path) -> None:
    """Persist a newly copied regular file before publishing its directory entry."""

    try:
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
    except OSError as exc:
        raise RuntimeError(f"could not durably synchronize local control-plane file: {path}") from exc


def _copy_regular_file_durably(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)
    _fsync_regular_file(destination)


def _participant_transition_count(snapshot: RuntimeSnapshot) -> int:
    return sum(
        len(events)
        for history in (
            snapshot.participant_control_history,
            snapshot.participant_crossing_history,
            snapshot.information_state_history,
        )
        for events in history.values()
    )


__all__ = ()
