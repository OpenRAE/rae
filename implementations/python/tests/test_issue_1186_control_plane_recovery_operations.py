"""CP-12 recovery operations, readiness, and redaction acceptance tests."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from raes_backend_stubs.stubs import create_stub_target
from raes_cli.main import app as cli_app
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api._responses import _conflict_detail
from raes_runtime.control_plane_api_guards import RequestSizeLimitMiddleware
from raes_runtime.control_plane_health import ControlPlaneHealthStatus, control_plane_readiness
from raes_runtime.control_plane_recovery import IndeterminateResolutionDisposition
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
)
from raes_runtime.control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    InMemoryControlPlaneStore,
    TerminalCommitMode,
)
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_local_codec import encode_payload
from raes_runtime.control_plane_store_maintenance import (
    DestinationConflictPolicy,
    LocalStoreMaintenanceOperation,
    maintain_local_control_plane_store,
)
import raes_runtime.control_plane_store_maintenance as maintenance_module
from typer.testing import CliRunner


def _running_record(operation_id: str) -> ControlPlaneOperationRecord:
    submitted_at = "2026-09-19T00:00:00Z"
    context = OperationAdmissionContext(
        actor_id="operator-1186",
        authorization_scope=("role:operator",),
        target_scope="target:stub",
        run_scope="run:default",
        operation_kind=OperationKind.PROVISIONING,
        request_commitment=f"sha256:{'1' * 64}",
    )
    return ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PROVISIONING,
            submitted_at=submitted_at,
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PROVISIONING,
            state=OperationState.RUNNING,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=context,
        ),
        request_fingerprint=context.request_commitment,
        idempotency_key=f"key-{operation_id}",
    )


def _store_with_indeterminate_parent() -> tuple[InMemoryControlPlaneStore, str]:
    store = InMemoryControlPlaneStore()
    running = _running_record("indeterminate-1186")
    store.claim_record(running)
    terminal = replace(
        running,
        status=replace(
            running.status,
            state=OperationState.INDETERMINATE,
            updated_at="2026-09-19T00:00:01Z",
        ),
    )
    store.commit_terminal_operation(
        RuntimeSnapshot(),
        terminal,
        mode=TerminalCommitMode.OPERATION_ONLY,
        expected_revision=0,
    )
    return store, running.receipt.operation_id


def test_health_projection_is_closed_ready_and_value_free() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())

    health = control_plane_readiness(control_plane)

    assert health.status is ControlPlaneHealthStatus.READY
    assert health.reasons == ()
    assert health.to_payload() == {"status": "ready", "reasons": []}
    assert set(health.to_payload()) == {"status", "reasons"}


def test_unresolved_indeterminate_operation_keeps_readiness_closed_until_linked_resolution() -> None:
    store, parent_id = _store_with_indeterminate_parent()
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)

    assert control_plane_readiness(control_plane).to_payload() == {
        "status": "unready",
        "reasons": ["recovery-required"],
    }

    control_plane.resolve_indeterminate_operation(
        parent_id,
        disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
        idempotency_key="resolution-1186",
        identity=ControlPlaneIdentity(
            identity="resolver-1186",
            roles=frozenset({ControlPlaneRole.OPERATOR}),
            target_name="stub",
        ),
    )

    assert control_plane_readiness(control_plane).to_payload() == {"status": "ready", "reasons": []}


def test_health_routes_are_public_value_free_and_do_not_append_audit() -> None:
    store, _parent_id = _store_with_indeterminate_parent()
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)
    app = create_control_plane_app(control_plane)

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "live", "reasons": []}
    assert ready.status_code == 503
    assert ready.json() == {"status": "unready", "reasons": ["recovery-required"]}
    assert len(store.read_audit()) == 1


def test_readiness_fails_closed_after_local_store_lease_loss(tmp_path: Path) -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(tmp_path / "control-plane"),
    )
    app = create_control_plane_app(control_plane)

    with TestClient(app) as client:
        lease = control_plane._runtime_lease
        assert lease is not None
        lease.close()
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unready", "reasons": ["lease-unavailable"]}


def test_readiness_observes_lifecycle_and_recovery_under_one_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    import raes_runtime.control_plane_health as health_module

    control_plane = RuntimeControlPlane(create_stub_target())
    entered = Event()
    release = Event()
    close_started = Event()
    original = health_module.unresolved_indeterminate_operation_ids_from_records

    def block_recovery_projection(*args: object, **kwargs: object) -> object:
        entered.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(health_module, "unresolved_indeterminate_operation_ids_from_records", block_recovery_projection)

    def close_after_signal() -> None:
        close_started.set()
        control_plane.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        health_future = pool.submit(control_plane_readiness, control_plane)
        assert entered.wait(timeout=5)
        close_future = pool.submit(close_after_signal)
        try:
            assert close_started.wait(timeout=5)
            assert not close_future.done()
            assert not control_plane._closing
        finally:
            release.set()
        assert health_future.result(timeout=5).status is ControlPlaneHealthStatus.READY
        close_future.result(timeout=5)

    assert control_plane_readiness(control_plane).status is ControlPlaneHealthStatus.UNREADY


def _create_local_store(path: Path, *, run_scope: str = "run:ops") -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(path),
        run_scope=run_scope,
    )
    control_plane.record_audit(
        action="maintenance-fixture",
        identity="operator-1186",
        allowed=True,
        target="target:stub",
        reason="accepted",
        details={"count": 1},
    )
    control_plane.close()


def test_local_maintenance_check_backup_and_restore_preserve_scope_and_state(tmp_path: Path) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "private-backups" / "control-plane-backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)

    checked = maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.CHECK,
        store_path=source,
        target_name="stub",
        run_scope="run:ops",
    )
    backed_up = maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    backup_bytes = backup.read_bytes()
    restored_result = maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.RESTORE,
        store_path=restored,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )

    assert checked.to_payload() == {"operation": "check", "outcome": "succeeded"}
    assert backed_up.to_payload() == {"operation": "backup", "outcome": "succeeded"}
    assert restored_result.to_payload() == {"operation": "restore", "outcome": "succeeded"}
    assert backup.read_bytes() == backup_bytes
    assert not Path(f"{backup}-wal").exists()
    assert not Path(f"{backup}-shm").exists()
    reopened_store = LocalControlPlaneStore(restored)
    reopened = RuntimeControlPlane(create_stub_target(), store=reopened_store, run_scope="run:ops")
    try:
        assert control_plane_readiness(reopened).status is ControlPlaneHealthStatus.READY
        assert [event.action for event in reopened_store.read_audit()] == ["maintenance-fixture"]
    finally:
        reopened.close()


def test_maintenance_requires_exclusive_lease_and_exact_scope(tmp_path: Path) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    active = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(source),
        run_scope="run:ops",
    )
    try:
        with pytest.raises(RuntimeError, match="exactly one worker"):
            maintain_local_control_plane_store(
                operation=LocalStoreMaintenanceOperation.BACKUP,
                store_path=source,
                backup_path=backup,
                target_name="stub",
                run_scope="run:ops",
            )
    finally:
        active.close()

    with pytest.raises(RuntimeError, match="scope does not match"):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.CHECK,
            store_path=source,
            target_name="stub",
            run_scope="run:other",
        )


def test_check_does_not_initialize_an_unbound_existing_database(tmp_path: Path) -> None:
    store_path = tmp_path / "unbound-store"
    store_path.mkdir(mode=0o700)
    database = store_path / "control-plane.sqlite3"
    with sqlite3.connect(database):
        pass
    database.chmod(0o600)
    original_bytes = database.read_bytes()

    with pytest.raises((RuntimeError, ValueError, sqlite3.DatabaseError)):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.CHECK,
            store_path=store_path,
            target_name="stub",
            run_scope="run:ops",
        )

    assert database.read_bytes() == original_bytes
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


@pytest.mark.parametrize("operation", [LocalStoreMaintenanceOperation.CHECK, LocalStoreMaintenanceOperation.BACKUP])
def test_maintenance_refuses_a_source_not_in_wal_mode_without_mutating_it(
    tmp_path: Path,
    operation: LocalStoreMaintenanceOperation,
) -> None:
    source = tmp_path / "source-store"
    _create_local_store(source)
    database = source / "control-plane.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode=DELETE").fetchone() == ("delete",)

    with pytest.raises(RuntimeError, match="WAL"):
        maintain_local_control_plane_store(
            operation=operation,
            store_path=source,
            backup_path=tmp_path / "backup.sqlite3",
            target_name="stub",
            run_scope="run:ops",
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    assert not (tmp_path / "backup.sqlite3").exists()


def test_backup_and_restore_refuse_implicit_destination_replacement(tmp_path: Path) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )

    with pytest.raises(FileExistsError):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.BACKUP,
            store_path=source,
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
        )

    _create_local_store(restored)
    with pytest.raises(FileExistsError):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.RESTORE,
            store_path=restored,
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
        )

    result = maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.RESTORE,
        store_path=restored,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
        conflict_policy=DestinationConflictPolicy.REPLACE,
    )
    assert result.to_payload() == {"operation": "restore", "outcome": "succeeded"}
    assert len(list(restored.glob("pre-restore-*.sqlite3"))) == 1


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_backup_replace_rejects_existing_destination_sidecars(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    _create_local_store(source)
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    original_bytes = backup.read_bytes()
    sidecar = Path(f"{backup}{suffix}")
    sidecar.write_bytes(b"stale")
    sidecar.chmod(0o600)

    with pytest.raises(RuntimeError, match="stale SQLite sidecar"):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.BACKUP,
            store_path=source,
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
            conflict_policy=DestinationConflictPolicy.REPLACE,
        )

    assert backup.read_bytes() == original_bytes
    assert sidecar.read_bytes() == b"stale"


def test_restore_migrates_a_working_copy_without_mutating_the_supplied_backup(tmp_path: Path) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    with sqlite3.connect(backup) as connection:
        connection.execute("UPDATE metadata SET value='4' WHERE key='schema-version'")
    predecessor_bytes = backup.read_bytes()

    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.RESTORE,
        store_path=restored,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )

    assert backup.read_bytes() == predecessor_bytes
    with sqlite3.connect(restored / "control-plane.sqlite3") as connection:
        assert connection.execute("SELECT value FROM metadata WHERE key='schema-version'").fetchone() == ("5",)


def test_failed_restore_keeps_the_backup_and_destination_authoritative(tmp_path: Path) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)
    _create_local_store(restored)
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    with sqlite3.connect(backup) as connection:
        connection.execute("UPDATE metadata SET value='4' WHERE key='schema-version'")
        payload = asdict(
            AuditEvent(
                timestamp="2026-09-19T00:00:00Z",
                action="legacy",
                identity="operator-1186",
                allowed=True,
                target="target:stub",
            )
        )
        payload["details"] = {"nested": {"secret": "must-remain-source-only"}}
        content, digest = encode_payload(payload)
        connection.execute("UPDATE audit_events SET payload=?, digest=?", (content, digest))
    backup_bytes = backup.read_bytes()
    destination = restored / "control-plane.sqlite3"
    destination_bytes = destination.read_bytes()

    with pytest.raises(ValueError):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.RESTORE,
            store_path=restored,
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
            conflict_policy=DestinationConflictPolicy.REPLACE,
        )

    assert backup.read_bytes() == backup_bytes
    assert destination.read_bytes() == destination_bytes
    assert list(restored.glob("pre-restore-*.sqlite3")) == []


def test_restore_publication_failure_preserves_existing_wal_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)
    _create_local_store(restored)
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    database = restored / "control-plane.sqlite3"
    original_bytes = database.read_bytes()
    original_replace = maintenance_module.os.replace

    def fail_publication(source_path: Path, destination_path: Path) -> None:
        if source_path.name.startswith(".restore-") and destination_path == database:
            raise OSError("injected publication failure")
        original_replace(source_path, destination_path)

    monkeypatch.setattr(maintenance_module.os, "replace", fail_publication)
    with pytest.raises(OSError, match="injected publication failure"):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.RESTORE,
            store_path=restored,
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
            conflict_policy=DestinationConflictPolicy.REPLACE,
        )

    assert database.read_bytes() == original_bytes
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    assert len(list(restored.glob("pre-restore-*.sqlite3"))) == 1


def test_restore_fsync_failure_rolls_back_published_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)
    _create_local_store(restored)
    destination_owner = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(restored),
        run_scope="run:ops",
    )
    destination_owner.record_audit(
        action="maintenance-fixture",
        identity="operator-1186",
        allowed=True,
        target="target:stub",
        reason="accepted",
        details={"count": 2},
    )
    destination_owner.close()
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    database = restored / "control-plane.sqlite3"
    original_fsync = maintenance_module._fsync_regular_file
    failed = False

    def fail_once(path: Path) -> None:
        nonlocal failed
        if path == database and not failed:
            failed = True
            raise OSError("injected fsync failure")
        original_fsync(path)

    monkeypatch.setattr(maintenance_module, "_fsync_regular_file", fail_once)
    with pytest.raises(OSError, match="injected fsync failure"):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.RESTORE,
            store_path=restored,
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
            conflict_policy=DestinationConflictPolicy.REPLACE,
        )

    assert failed
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone() == (2,)
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.CHECK,
        store_path=restored,
        target_name="stub",
        run_scope="run:ops",
    )


def test_unconfirmed_restore_rollback_keeps_destination_exclusively_owned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)
    _create_local_store(restored)
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    database = restored / "control-plane.sqlite3"
    original_replace = maintenance_module.os.replace
    original_fsync = maintenance_module._fsync_regular_file
    failed = False

    def fail_rollback(source_path: Path, destination_path: Path) -> None:
        if source_path.name.startswith("pre-restore-") and destination_path == database:
            raise OSError("injected rollback failure")
        original_replace(source_path, destination_path)

    def fail_publication_fsync_once(path: Path) -> None:
        nonlocal failed
        if path == database and not failed:
            failed = True
            raise OSError("injected fsync failure")
        original_fsync(path)

    monkeypatch.setattr(maintenance_module.os, "replace", fail_rollback)
    monkeypatch.setattr(maintenance_module, "_fsync_regular_file", fail_publication_fsync_once)
    held_leases = maintenance_module._UNCERTAIN_RESTORE_LEASES
    try:
        with pytest.raises(RuntimeError, match="rollback could not be confirmed"):
            maintain_local_control_plane_store(
                operation=LocalStoreMaintenanceOperation.RESTORE,
                store_path=restored,
                backup_path=backup,
                target_name="stub",
                run_scope="run:ops",
                conflict_policy=DestinationConflictPolicy.REPLACE,
            )
        with pytest.raises(RuntimeError, match="already has a runtime owner"):
            maintain_local_control_plane_store(
                operation=LocalStoreMaintenanceOperation.CHECK,
                store_path=restored,
                target_name="stub",
                run_scope="run:ops",
            )
    finally:
        held_leases.pop().close()


def test_restore_refuses_stale_destination_sidecars_before_publication(tmp_path: Path) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    restored.mkdir(mode=0o700)
    stale_sidecar = restored / "control-plane.sqlite3-wal"
    stale_sidecar.write_bytes(b"stale")
    stale_sidecar.chmod(0o600)

    with pytest.raises(RuntimeError, match="stale SQLite sidecar"):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.RESTORE,
            store_path=restored,
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
        )

    assert not (restored / "control-plane.sqlite3").exists()
    assert stale_sidecar.read_bytes() == b"stale"


@pytest.mark.parametrize("sidecar_owner", ["backup", "destination"])
def test_restore_rejects_symlink_sidecars_before_sqlite_connect(
    tmp_path: Path,
    sidecar_owner: str,
) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.BACKUP,
        store_path=source,
        backup_path=backup,
        target_name="stub",
        run_scope="run:ops",
    )
    _create_local_store(restored)
    protected = tmp_path / "protected-file"
    protected.write_bytes(b"must-not-change")
    target = backup if sidecar_owner == "backup" else restored / "control-plane.sqlite3"
    Path(f"{target}-wal").symlink_to(protected)

    with pytest.raises(RuntimeError, match="symlink"):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.RESTORE,
            store_path=restored,
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
            conflict_policy=DestinationConflictPolicy.REPLACE,
        )

    assert protected.read_bytes() == b"must-not-change"


def test_runtime_store_cli_delegates_to_maintenance_and_emits_only_fixed_codes(tmp_path: Path) -> None:
    source = tmp_path / "source-store"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored-store"
    _create_local_store(source)
    runner = CliRunner()

    checked = runner.invoke(
        cli_app,
        ["runtime", "store", "check", str(source), "--target", "stub", "--run-scope", "run:ops"],
    )
    backed_up = runner.invoke(
        cli_app,
        [
            "runtime",
            "store",
            "backup",
            str(source),
            str(backup),
            "--target",
            "stub",
            "--run-scope",
            "run:ops",
        ],
    )
    restored_result = runner.invoke(
        cli_app,
        [
            "runtime",
            "store",
            "restore",
            str(backup),
            str(restored),
            "--target",
            "stub",
            "--run-scope",
            "run:ops",
        ],
    )

    assert (checked.exit_code, checked.stdout) == (0, "control-plane-store-check-succeeded\n")
    assert (backed_up.exit_code, backed_up.stdout) == (0, "control-plane-store-backup-succeeded\n")
    assert (restored_result.exit_code, restored_result.stdout) == (0, "control-plane-store-restore-succeeded\n")


def test_runtime_store_cli_failure_redacts_paths_and_provider_errors(tmp_path: Path) -> None:
    sentinel = "secret-store-path-1186"
    source = tmp_path / sentinel
    _create_local_store(source)

    result = CliRunner().invoke(
        cli_app,
        ["runtime", "store", "check", str(source), "--target", "stub", "--run-scope", "run:wrong"],
    )

    assert result.exit_code == 1
    assert result.stdout == "control-plane-store-check-failed\n"
    assert sentinel not in result.stdout
    assert "scope does not match" not in result.stdout


def test_audit_creation_rejects_unbounded_or_nested_details() -> None:
    base = {
        "timestamp": "2026-09-19T00:00:00Z",
        "action": "test",
        "identity": "operator-1186",
        "allowed": True,
        "target": "target:stub",
        "reason": "accepted",
    }

    with pytest.raises(ValueError, match="audit details"):
        AuditEvent(**base, details={"nested": {"secret": "value"}})
    with pytest.raises(ValueError, match="audit details"):
        AuditEvent(**base, details={f"key-{index}": index for index in range(17)})
    with pytest.raises(ValueError, match="audit action"):
        AuditEvent(**{**base, "action": "x" * 513})


def test_audit_details_reject_unknown_fields_and_values_outside_their_closed_domains() -> None:
    base = {
        "timestamp": "2026-09-19T00:00:00Z",
        "action": "provisioning_terminal",
        "identity": "operator-1186",
        "allowed": True,
        "target": "target:stub",
        "reason": "operation-succeeded",
    }
    sentinel = "secret-provider-value-1186"

    with pytest.raises(ValueError, match="audit details"):
        AuditEvent(**base, details={"request_body": sentinel})
    with pytest.raises(ValueError, match="audit details"):
        AuditEvent(**base, details={"state": sentinel})
    with pytest.raises(ValueError, match="audit details"):
        AuditEvent(**base, details={"episode_id": "episode-1"})
    with pytest.raises(ValueError, match="audit details"):
        AuditEvent(**{**base, "action": "record_participant_crossing"}, details={"episode_id": "/private/path"})
    assert AuditEvent(**base, details={"state": "succeeded"}).details == {"state": "succeeded"}


def test_composed_participant_crossing_audit_fields_remain_closed_and_value_free() -> None:
    base = {
        "timestamp": "2026-09-19T00:00:00Z",
        "identity": "operator-1186",
        "allowed": True,
        "target": "participant.red",
        "reason": "accepted",
    }
    crossing = {
        "episode_id": "episode-1",
        "crossing_decision_id": "decision-1",
        "crossing_decision_cut_ref": "participant-policy-cut:red:episode-1:8",
        "crossing_disposition": "permit",
        "flow_final_disposition": "permit",
    }

    for action in (
        "record_participant_crossing",
        "record_participant_control",
        "authorize_participant_action",
        "admit_participant_action",
    ):
        event = AuditEvent(**base, action=action, details=crossing)
        assert event.details == crossing
        with pytest.raises(ValueError, match="audit details"):
            AuditEvent(**base, action=action, details={**crossing, "crossing_disposition": "secret"})
        denied = {**crossing, "flow_sink_decision_id": "", "flow_final_disposition": "unresolved"}
        assert AuditEvent(**base, action=action, details=denied).details == denied
        with pytest.raises(ValueError, match="audit details"):
            AuditEvent(**base, action=action, details={**denied, "flow_final_disposition": "permit"})


@pytest.mark.parametrize(
    "invalid_details",
    [
        {"nested": {"secret": "must-not-be-rewritten"}},
        {"request_body": "must-not-be-rewritten"},
    ],
)
def test_schema_v4_audit_history_is_validated_before_v5_upgrade(
    tmp_path: Path,
    invalid_details: dict[str, object],
) -> None:
    store_path = tmp_path / "store"
    _create_local_store(store_path)
    database = store_path / "control-plane.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE metadata SET value='4' WHERE key='schema-version'")
        payload = asdict(
            AuditEvent(
                timestamp="2026-09-19T00:00:00Z",
                action="legacy",
                identity="operator-1186",
                allowed=True,
                target="target:stub",
            )
        )
        payload["details"] = invalid_details
        content, digest = encode_payload(payload)
        connection.execute("UPDATE audit_events SET payload=?, digest=?", (content, digest))

    with pytest.raises(ValueError):
        RuntimeControlPlane(
            create_stub_target(),
            store=LocalControlPlaneStore(store_path),
            run_scope="run:ops",
        )

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM metadata WHERE key='schema-version'").fetchone() == ("4",)
        persisted = connection.execute("SELECT payload FROM audit_events").fetchone()
        assert persisted is not None and "must-not-be-rewritten" in persisted[0]


def test_valid_schema_v4_audit_history_advances_to_v5(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    _create_local_store(store_path)
    database = store_path / "control-plane.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE metadata SET value='4' WHERE key='schema-version'")

    reopened = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(store_path),
        run_scope="run:ops",
    )
    reopened.close()

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM metadata WHERE key='schema-version'").fetchone() == ("5",)


def test_api_audits_use_immutable_target_scope_instead_of_request_paths() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    security = ControlPlaneSecurityConfig(
        bearer_tokens={
            "auditor-token-1186": ControlPlaneIdentity(
                identity="auditor-1186",
                roles=frozenset({ControlPlaneRole.AUDITOR}),
                target_name="stub",
            )
        }
    )
    app = create_control_plane_app(control_plane, security=security)

    with TestClient(app) as client:
        response = client.get("/snapshot", headers={"authorization": "Bearer auditor-token-1186"})
        audit_targets = {event.target for event in control_plane.audit_log()}

    assert response.status_code == 200
    assert audit_targets == {"target:stub"}


def test_conflict_details_never_return_provider_text() -> None:
    sentinel = "provider-secret-sql-path-1186"
    assert _conflict_detail(ValueError(sentinel)) == "operation conflict"


def test_rejection_audit_failure_log_omits_exception_and_request_path(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "provider-secret-1186"
    control_plane = RuntimeControlPlane(create_stub_target())

    def fail_audit(**_kwargs: object) -> None:
        raise OSError(sentinel)

    control_plane.record_audit = fail_audit  # type: ignore[method-assign]

    async def accepted(_scope: object, _receive: object, _send: object) -> None:
        raise AssertionError("oversized request must not be dispatched")

    middleware = RequestSizeLimitMiddleware(
        accepted,  # type: ignore[arg-type]
        control_plane=control_plane,
        max_request_bytes=1,
    )

    client = TestClient(middleware, raise_server_exceptions=False)
    response = client.post("/secret/request/path", content=b"xx")

    assert response.status_code == 413
    assert "control-plane-rejection-audit-failed" in caplog.text
    assert sentinel not in caplog.text
    assert "/secret/request/path" not in caplog.text


def test_oversized_http_method_cannot_suppress_rejection_audit() -> None:
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)

    async def accepted(_scope: object, _receive: object, _send: object) -> None:
        raise AssertionError("oversized request must not be dispatched")

    middleware = RequestSizeLimitMiddleware(
        accepted,  # type: ignore[arg-type]
        control_plane=control_plane,
        max_request_bytes=1,
    )
    response = TestClient(middleware).request("M" * 600, "/rejected", content=b"xx")

    assert response.status_code == 413
    assert [(item.action, item.reason) for item in store.read_audit()] == [
        ("http-request-rejected", "request too large")
    ]


def test_validation_secondary_audit_failure_preserves_coarse_response_and_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "secret-validation-audit-provider-1186"
    control_plane = RuntimeControlPlane(create_stub_target())
    security = ControlPlaneSecurityConfig(
        bearer_tokens={
            "backend-token-1186": ControlPlaneIdentity(
                identity="backend-1186",
                roles=frozenset({ControlPlaneRole.BACKEND}),
                target_name="stub",
            )
        }
    )
    app = create_control_plane_app(control_plane, security=security)

    def fail_audit(**_kwargs: object) -> None:
        raise OSError(sentinel)

    control_plane.record_audit = fail_audit  # type: ignore[method-assign]
    raw_request_value = "secret-request-value-1186"
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/operations/orchestration",
            content=f'{{"operations":"{raw_request_value}"}}',
            headers={
                "authorization": "Bearer backend-token-1186",
                "content-type": "application/json",
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "request validation failed"}
    assert "control-plane-validation-audit-failed" in caplog.text
    assert sentinel not in caplog.text
    assert raw_request_value not in caplog.text
