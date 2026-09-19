"""Lease-admitted maintenance for the local control-plane store."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .control_plane_configuration import ControlPlaneConfiguration
from .control_plane_execution import _utc_now
from .control_plane_operation_context import runtime_target_scope
from .control_plane_store_lease import RuntimeOwnerLease, require_single_worker_configuration
from .control_plane_store_local import LocalControlPlaneStore
from .control_plane_store_local_codec import decode_payload, encode_payload, transaction
from .control_plane_store_paths import (
    _fsync_directory,
    _fsync_regular_file,
    _require_same_file,
    _secure_database_file,
    _secure_store_directory,
    _validate_sqlite_sidecars,
)
from .control_plane_store_record_migration import migrate_sqlite_schema

_DATABASE_NAME = "control-plane.sqlite3"
_OWNER_NAME = "runtime-owner.lock"
_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
_UNCERTAIN_RESTORE_LEASES: list[RuntimeOwnerLease] = []


class LocalStoreMaintenanceOperation(str, Enum):
    """Closed local-provider maintenance operations."""

    CHECK = "check"
    BACKUP = "backup"
    RESTORE = "restore"


class DestinationConflictPolicy(str, Enum):
    """Explicit publication policy for an existing destination."""

    REFUSE = "refuse"
    REPLACE = "replace"


@dataclass(frozen=True)
class LocalStoreMaintenanceResult:
    """Value-free maintenance result safe for machine-readable output."""

    operation: LocalStoreMaintenanceOperation

    def to_payload(self) -> dict[str, str]:
        return {"operation": self.operation.value, "outcome": "succeeded"}


def maintain_local_control_plane_store(
    *,
    operation: LocalStoreMaintenanceOperation,
    store_path: Path,
    target_name: str,
    run_scope: str,
    backup_path: Path | None = None,
    conflict_policy: DestinationConflictPolicy = DestinationConflictPolicy.REFUSE,
) -> LocalStoreMaintenanceResult:
    """Run one closed maintenance operation under runtime-exclusive authority."""

    if not isinstance(operation, LocalStoreMaintenanceOperation):
        raise TypeError("operation must be a LocalStoreMaintenanceOperation")
    if not isinstance(conflict_policy, DestinationConflictPolicy):
        raise TypeError("conflict_policy must be a DestinationConflictPolicy")
    target_scope, normalized_run_scope = _normalized_scopes(target_name, run_scope)
    if operation is LocalStoreMaintenanceOperation.CHECK:
        _check_store(store_path, target_scope=target_scope, run_scope=normalized_run_scope)
    elif operation is LocalStoreMaintenanceOperation.BACKUP:
        if backup_path is None:
            raise ValueError("backup operation requires a backup path")
        _backup_store(
            store_path,
            backup_path,
            target_scope=target_scope,
            run_scope=normalized_run_scope,
            conflict_policy=conflict_policy,
        )
    else:
        if backup_path is None:
            raise ValueError("restore operation requires a backup path")
        _restore_store(
            store_path,
            backup_path,
            target_scope=target_scope,
            run_scope=normalized_run_scope,
            conflict_policy=conflict_policy,
        )
    return LocalStoreMaintenanceResult(operation)


def _normalized_scopes(target_name: str, run_scope: str) -> tuple[str, str]:
    target_scope = runtime_target_scope(target_name)
    config = ControlPlaneConfiguration(run_scope=run_scope)
    return target_scope, config.run_scope


@contextmanager
def _admitted_store(
    store_path: Path,
    *,
    target_scope: str,
    run_scope: str,
) -> Iterator[LocalControlPlaneStore]:
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_maintenance(target_scope=target_scope, run_scope=run_scope)
    try:
        yield store
    finally:
        store.close()
        lease.close()


def _check_store(store_path: Path, *, target_scope: str, run_scope: str) -> None:
    with _admitted_store(store_path, target_scope=target_scope, run_scope=run_scope) as store:
        store.load_snapshot_state()
        store.load_records()
        store.read_audit()


def _backup_store(
    store_path: Path,
    backup_path: Path,
    *,
    target_scope: str,
    run_scope: str,
    conflict_policy: DestinationConflictPolicy,
) -> None:
    with _admitted_store(store_path, target_scope=target_scope, run_scope=run_scope) as store:
        _prepare_destination(backup_path, conflict_policy=conflict_policy)
        existing = _secure_database_file(backup_path, allow_missing=True)
        if existing is not None and os.path.samestat(existing, store._database_path.lstat()):
            raise ValueError("backup destination must differ from the admitted store")
        with store._connection() as source:
            _publish_backup(
                source,
                backup_path,
                target_scope=target_scope,
                run_scope=run_scope,
                conflict_policy=conflict_policy,
            )


def _restore_store(
    store_path: Path,
    backup_path: Path,
    *,
    target_scope: str,
    run_scope: str,
    conflict_policy: DestinationConflictPolicy,
) -> None:
    require_single_worker_configuration()
    _secure_store_directory(store_path, reject_insecure_existing=True)
    lease = RuntimeOwnerLease.acquire(store_path / _OWNER_NAME)
    release_lease = True
    try:
        database_path = store_path / _DATABASE_NAME
        existing = _secure_database_file(database_path, allow_missing=True)
        if existing is not None and conflict_policy is DestinationConflictPolicy.REFUSE:
            raise FileExistsError("restore destination already exists")
        backup_metadata = _secure_database_file(backup_path, allow_missing=False)
        assert backup_metadata is not None
        if existing is not None and os.path.samestat(existing, backup_metadata):
            raise ValueError("restore source must differ from the destination store")
        working_path = _working_path(store_path, prefix=".restore-")
        previous_copy: Path | None = None
        published = False
        try:
            _copy_backup_to_working_database(
                backup_path,
                working_path,
                target_scope=target_scope,
                run_scope=run_scope,
            )
            if existing is not None:
                previous_copy = _retain_pre_restore_copy(
                    database_path,
                    store_path,
                    target_scope=target_scope,
                    run_scope=run_scope,
                )
            _require_no_sidecars(database_path)
            os.replace(working_path, database_path)
            published = True
            _fsync_regular_file(database_path)
            _fsync_directory(store_path)
        except BaseException:
            if published:
                try:
                    _rollback_restored_destination(
                        database_path,
                        previous_copy=previous_copy,
                        working_path=working_path,
                        directory=store_path,
                    )
                except BaseException:
                    release_lease = False
                    _UNCERTAIN_RESTORE_LEASES.append(lease)
                    raise RuntimeError("local control-plane restore rollback could not be confirmed") from None
            raise
        finally:
            working_path.unlink(missing_ok=True)
    finally:
        if release_lease:
            lease.close()


def _rollback_restored_destination(
    database_path: Path,
    *,
    previous_copy: Path | None,
    working_path: Path,
    directory: Path,
) -> None:
    _require_no_sidecars(database_path)
    if previous_copy is None:
        os.replace(database_path, working_path)
    else:
        os.replace(previous_copy, database_path)
        _fsync_regular_file(database_path)
    _fsync_directory(directory)


def _prepare_destination(path: Path, *, conflict_policy: DestinationConflictPolicy) -> None:
    _secure_store_directory(path.parent, reject_insecure_existing=True)
    existing = _secure_database_file(path, allow_missing=True)
    if existing is not None and conflict_policy is DestinationConflictPolicy.REFUSE:
        raise FileExistsError("backup destination already exists")
    _require_no_sidecars(path)


def _publish_backup(
    source: sqlite3.Connection,
    destination: Path,
    *,
    target_scope: str,
    run_scope: str,
    conflict_policy: DestinationConflictPolicy,
) -> None:
    _prepare_destination(destination, conflict_policy=conflict_policy)
    working_path = _working_path(destination.parent, prefix=".backup-")
    try:
        _backup_connection(source, working_path)
        _validate_working_database(
            working_path,
            target_scope=target_scope,
            run_scope=run_scope,
            migrate=False,
        )
        os.replace(working_path, destination)
        _fsync_regular_file(destination)
        _fsync_directory(destination.parent)
    finally:
        working_path.unlink(missing_ok=True)


def _copy_backup_to_working_database(
    backup_path: Path,
    working_path: Path,
    *,
    target_scope: str,
    run_scope: str,
) -> None:
    _secure_database_file(backup_path, allow_missing=False)
    with _database_connection(backup_path, mode="ro", standalone=True) as source:
        _backup_connection(source, working_path)
    _validate_working_database(
        working_path,
        target_scope=target_scope,
        run_scope=run_scope,
        migrate=True,
    )


def _retain_pre_restore_copy(
    database_path: Path,
    store_path: Path,
    *,
    target_scope: str,
    run_scope: str,
) -> Path:
    stamp = "".join(character for character in _utc_now() if character.isdigit())
    destination = store_path / f"pre-restore-{stamp}.sqlite3"
    with _database_connection(database_path, mode="rw") as source:
        LocalControlPlaneStore._validate_persisted_state(
            source,
            target_scope=target_scope,
            run_scope=run_scope,
        )
        _publish_backup(
            source,
            destination,
            target_scope=target_scope,
            run_scope=run_scope,
            conflict_policy=DestinationConflictPolicy.REFUSE,
        )
    with _database_connection(destination, mode="rw", standalone=True) as retained:
        if retained.execute("PRAGMA journal_mode=WAL").fetchone() != ("wal",):
            raise RuntimeError("pre-restore copy could not retain WAL mode")
    _fsync_regular_file(destination)
    _fsync_directory(store_path)
    return destination


def _validate_working_database(
    path: Path,
    *,
    target_scope: str,
    run_scope: str,
    migrate: bool,
) -> None:
    with _database_connection(path, mode="rw", standalone=True) as connection:
        stored_target, stored_run = LocalControlPlaneStore._scope_metadata(connection)
        if (stored_target, stored_run) != (target_scope, run_scope):
            raise RuntimeError("local control-plane store scope does not match runtime admission")
        if migrate:
            with transaction(connection):
                migrate_sqlite_schema(connection, decode_payload, encode_payload)
        LocalControlPlaneStore._validate_persisted_state(
            connection,
            target_scope=target_scope,
            run_scope=run_scope,
        )
        journal_mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()
        if journal_mode != ("delete",):
            raise RuntimeError("maintenance copy could not enter standalone journal mode")
    _secure_database_file(path, allow_missing=False)
    _fsync_regular_file(path)


def _backup_connection(source: sqlite3.Connection, destination: Path) -> None:
    with sqlite3.connect(destination) as target:
        target.execute("PRAGMA synchronous=FULL")
        source.backup(target)
        target.commit()
    if os.name != "nt":
        os.chmod(destination, 0o600, follow_symlinks=False)


@contextmanager
def _database_connection(
    path: Path,
    *,
    mode: str,
    standalone: bool = False,
) -> Iterator[sqlite3.Connection]:
    _secure_store_directory(path.parent, reject_insecure_existing=True)
    directory_identity = path.parent.lstat()
    before = _secure_database_file(path, allow_missing=False)
    assert before is not None
    _validate_sqlite_sidecars(path)
    if standalone:
        _require_no_sidecars(path)
    sidecar_identities = _sidecar_identities(path)
    uri = f"{path.absolute().as_uri()}?mode={mode}"
    connection = sqlite3.connect(uri, isolation_level=None, uri=True)
    try:
        opened = _secure_database_file(path, allow_missing=False)
        assert opened is not None
        _require_same_file(before, opened, path, "SQLite opened it")
        _validate_sqlite_sidecars(path)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        yield connection
    finally:
        connection.close()
        after = _secure_database_file(path, allow_missing=False)
        assert after is not None
        _require_same_file(before, after, path, "SQLite was connected")
        if not os.path.samestat(directory_identity, path.parent.lstat()):
            raise RuntimeError("local control-plane maintenance directory changed during SQLite access")
        _validate_sqlite_sidecars(path)
        for suffix, original in sidecar_identities.items():
            current = Path(f"{path}{suffix}")
            if current.exists():
                _require_same_file(original, current.lstat(), current, "SQLite was connected")
        if not standalone:
            for suffix in _SIDECAR_SUFFIXES:
                if suffix not in sidecar_identities and Path(f"{path}{suffix}").exists():
                    raise RuntimeError("local control-plane maintenance sidecar appeared during SQLite access")
        if standalone:
            _require_no_sidecars(path)


def _working_path(directory: Path, *, prefix: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix=prefix, suffix=".sqlite3", dir=directory)
    os.close(descriptor)
    path = Path(raw_path)
    if os.name != "nt":
        os.chmod(path, 0o600, follow_symlinks=False)
    return path


def _require_no_sidecars(database_path: Path) -> None:
    _validate_sqlite_sidecars(database_path)
    if any(Path(f"{database_path}{suffix}").exists() for suffix in _SIDECAR_SUFFIXES):
        raise RuntimeError("stale SQLite sidecar prevents restore publication")


def _sidecar_identities(database_path: Path) -> dict[str, os.stat_result]:
    return {
        suffix: Path(f"{database_path}{suffix}").lstat()
        for suffix in _SIDECAR_SUFFIXES
        if Path(f"{database_path}{suffix}").exists()
    }


__all__ = (
    "DestinationConflictPolicy",
    "LocalStoreMaintenanceOperation",
    "LocalStoreMaintenanceResult",
    "maintain_local_control_plane_store",
)
