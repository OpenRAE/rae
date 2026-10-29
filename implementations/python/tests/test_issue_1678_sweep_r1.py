"""Issue 1678 sweep regressions for area R1: local store maintenance and durable state (ADR-116).

A malformed store file, backup file, operator path, operator value or stored
record keeps its refusal outcome. The store command prints its fixed failure
label and exits with status 1, the store raises a category, and an HTTP route
keeps its 409 response. A programming error still reaches the application
boundary and is not reported as a refusal.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_cli.main import app as cli_app
from raes_contracts.errors import ConflictError, EvidenceIntegrityError, InvalidInputError, OperationalError
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime import control_plane_store_maintenance as maintenance_module
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_local_codec import (
    DURABLE_MAX_NESTING,
    decode_contract,
    decode_payload,
    encode_payload,
    exceeds_durable_nesting,
    refuse_invalid_database,
)
from raes_runtime.control_plane_store_maintenance import (
    DestinationConflictPolicy,
    LocalStoreMaintenanceOperation,
    maintain_local_control_plane_store,
)
from starlette.testclient import TestClient
from typer.testing import CliRunner

SENTINEL = "value-sentinel-r1-1678"
_DATABASE = "control-plane.sqlite3"
_OPTIONS = ("--target", "stub", "--run-scope", "run:ops")
_HEADERS = {"x-raes-client-verified": "true", "x-raes-client-identity": "backend-service"}
_PROVISIONING = {"operations": [], "diagnostics": [], "realization_authority": []}


def _create_store(path: Path) -> Path:
    control_plane = RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(path), run_scope="run:ops")
    control_plane.record_audit(
        action="maintenance-fixture",
        identity="operator-r1",
        allowed=True,
        target="target:stub",
        reason="accepted",
        details={"count": 1},
    )
    control_plane.close()
    return path / _DATABASE


def _private_file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o600)
    return path


def _store_command(*arguments: str):
    return CliRunner().invoke(cli_app, ["runtime", "store", *arguments])


def _assert_refused(result, operation: str) -> None:
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert (result.stdout, result.stderr) == ("", f"control-plane-store-{operation}-failed\n")
    assert SENTINEL not in result.output


def _check(store_path: Path) -> None:
    maintain_local_control_plane_store(
        operation=LocalStoreMaintenanceOperation.CHECK,
        store_path=store_path,
        target_name="stub",
        run_scope="run:ops",
    )


def _replace_audit_payload(database: Path, payload: object, digest: object | None = None) -> None:
    if digest is None:
        assert isinstance(payload, str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE audit_events SET payload=?, digest=?", (payload, digest))


def test_store_command_refuses_a_store_file_that_is_not_a_database(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store_path = tmp_path / SENTINEL
    _private_file(store_path / _DATABASE, b"not a database at all" * 100)
    store_path.chmod(0o700)

    with caplog.at_level(logging.DEBUG):
        result = _store_command("check", str(store_path), *_OPTIONS)

    _assert_refused(result, "check")
    assert SENTINEL not in caplog.text
    with pytest.raises(EvidenceIntegrityError, match="not a valid SQLite database"):
        _check(store_path)


def test_store_command_refuses_a_backup_file_that_is_not_a_database(tmp_path: Path) -> None:
    backup = _private_file(tmp_path / "backups" / f"{SENTINEL}.sqlite3", b"x" * 4096)

    result = _store_command("restore", str(backup), str(tmp_path / "restored"), *_OPTIONS)

    _assert_refused(result, "restore")
    with pytest.raises(EvidenceIntegrityError, match="not a valid SQLite database"):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.RESTORE,
            store_path=tmp_path / "restored-again",
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
        )


def test_store_command_refuses_a_store_with_a_damaged_page(tmp_path: Path) -> None:
    store_path = tmp_path / "damaged"
    database = _create_store(store_path)
    with sqlite3.connect(database) as connection:
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        root = connection.execute("SELECT rootpage FROM sqlite_master WHERE name='audit_events'").fetchone()[0]
    content = bytearray(database.read_bytes())
    content[(root - 1) * page_size : root * page_size] = b"\xff" * page_size
    database.write_bytes(bytes(content))

    _assert_refused(_store_command("check", str(store_path), *_OPTIONS), "check")
    with pytest.raises(EvidenceIntegrityError, match="not a valid SQLite database"):
        _check(store_path)


@pytest.mark.parametrize("operation", ["check", "backup"])
@pytest.mark.parametrize("path_kind", ["below-a-file", "name-too-long"])
def test_store_command_refuses_operator_paths_that_the_host_cannot_use(
    tmp_path: Path, operation: str, path_kind: str
) -> None:
    source = tmp_path / "source"
    _create_store(source)
    regular_file = _private_file(tmp_path / f"{SENTINEL}-file", b"x")
    unusable = regular_file / "nested" / "target" if path_kind == "below-a-file" else tmp_path / (SENTINEL * 20)
    arguments = (str(unusable),) if operation == "check" else (str(source), str(unusable / "backup.sqlite3"))

    _assert_refused(_store_command(operation, *arguments, *_OPTIONS), operation)


def test_maintenance_refuses_an_operator_path_with_an_operational_error(tmp_path: Path) -> None:
    regular_file = _private_file(tmp_path / "file", b"x")

    with pytest.raises(OperationalError, match="filesystem operation failed") as caught:
        _check(regular_file / "nested" / "store")

    assert isinstance(caught.value.__cause__, NotADirectoryError)


@pytest.mark.parametrize(
    ("target", "run_scope", "message"),
    [
        ("", "run:ops", "target is invalid"),
        ("t" * 600, "run:ops", "target is invalid"),
        ("stub", "not-a-run-scope", "run scope is invalid"),
        ("stub", "run:", "run scope is invalid"),
    ],
)
def test_maintenance_refuses_invalid_operator_scopes_as_invalid_input(
    tmp_path: Path, target: str, run_scope: str, message: str
) -> None:
    with pytest.raises(InvalidInputError, match=message):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.CHECK,
            store_path=tmp_path / "store",
            target_name=target,
            run_scope=run_scope,
        )
    assert not (tmp_path / "store").exists()


def test_maintenance_refuses_same_file_backup_and_restore_as_invalid_input(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    database = _create_store(store_path)

    with pytest.raises(InvalidInputError, match="backup destination must differ"):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.BACKUP,
            store_path=store_path,
            backup_path=database,
            target_name="stub",
            run_scope="run:ops",
            conflict_policy=DestinationConflictPolicy.REPLACE,
        )
    with pytest.raises(InvalidInputError, match="restore source must differ"):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.RESTORE,
            store_path=store_path,
            backup_path=database,
            target_name="stub",
            run_scope="run:ops",
            conflict_policy=DestinationConflictPolicy.REPLACE,
        )
    _check(store_path)


@pytest.mark.parametrize(
    ("payload", "digest", "message"),
    [
        ("{}", "0" * 64, "audit event failed its durable integrity check"),
        # Deeper than the durable limit, yet decodable on every host: the explicit limit refuses it.
        ('{"a":' + "[" * 200 + "]" * 200 + "}", None, "audit event exceeds the durable nesting limit"),
        ('{"a":' + "7" * 5000 + "}", None, "audit event failed its durable integrity check"),
        ("not json", None, "audit event failed its durable integrity check"),
        (b"\x00\x01", "0" * 64, "audit event failed its durable integrity check"),
        ("[1]", None, "audit event payload must be an object"),
        ('{"action":"' + SENTINEL + '"}', None, "audit event failed its durable contract check"),
    ],
    ids=["digest", "nesting", "digit-limit", "not-json", "blob", "not-object", "contract"],
)
def test_damaged_durable_records_are_refused_as_integrity_failures(
    tmp_path: Path, payload: object, digest: str | None, message: str
) -> None:
    store_path = tmp_path / "store"
    _replace_audit_payload(_create_store(store_path), payload, digest)

    with pytest.raises(EvidenceIntegrityError, match=message) as caught:
        _check(store_path)

    assert SENTINEL not in str(caught.value)
    _assert_refused(_store_command("check", str(store_path), *_OPTIONS), "check")


def test_damaged_generation_metadata_is_an_integrity_failure(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    database = _create_store(store_path)
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:ops")
    try:
        store.save_snapshot(RuntimeSnapshot(), expected_revision=0)
    finally:
        store.close()
        lease.close()
    with sqlite3.connect(database) as connection:
        # An integer beyond the interpreter digit limit must not reach int() as an unexpected failure.
        connection.execute("UPDATE metadata SET value=? WHERE key='snapshot-history-generation'", ("9" * 5000,))

    with pytest.raises(EvidenceIntegrityError, match="execution generation metadata is invalid"):
        _check(store_path)
    _assert_refused(_store_command("check", str(store_path), *_OPTIONS), "check")


def test_an_unsupported_store_schema_is_a_conflict(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    with sqlite3.connect(_create_store(store_path)) as connection:
        connection.execute("UPDATE metadata SET value='999' WHERE key='schema-version'")

    with pytest.raises(ConflictError, match="unsupported local control-plane database schema"):
        _check(store_path)
    _assert_refused(_store_command("check", str(store_path), *_OPTIONS), "check")


def test_http_submission_keeps_its_conflict_response_for_a_damaged_stored_record(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    control_plane = RuntimeControlPlane(
        create_stub_target(), store=LocalControlPlaneStore(store_path), run_scope="run:ops"
    )
    security = ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=True,
        trusted_identities={
            "backend-service": ControlPlaneIdentity(
                identity="backend-service",
                roles=frozenset({ControlPlaneRole.BACKEND}),
                target_name=control_plane.target_name,
            )
        },
    )
    app = create_control_plane_app(control_plane, security=security)
    with TestClient(app, raise_server_exceptions=False) as client:
        accepted = client.post(
            "/operations/provisioning", json=_PROVISIONING, headers={**_HEADERS, "idempotency-key": "a"}
        )
        with sqlite3.connect(store_path / _DATABASE) as connection:
            connection.execute("UPDATE operations SET digest=?", ("0" * 64,))
        refused = client.post(
            "/operations/provisioning", json=_PROVISIONING, headers={**_HEADERS, "idempotency-key": "b"}
        )

    assert accepted.status_code == 200
    assert (refused.status_code, refused.json()) == (409, {"detail": "operation conflict"})


@pytest.mark.parametrize("defect", [ValueError, KeyError, TypeError])
def test_maintenance_boundary_lets_programming_errors_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: type[Exception]
) -> None:
    store_path = tmp_path / "store"
    _create_store(store_path)

    def _defect(*_args: object, **_kwargs: object) -> None:
        raise defect(SENTINEL)

    monkeypatch.setattr(maintenance_module, "_check_store", _defect)
    with pytest.raises(defect):
        _check(store_path)

    result = _store_command("check", str(store_path), *_OPTIONS)
    assert type(result.exception) is defect
    assert "control-plane-store-check-failed" not in result.output
    assert SENTINEL not in result.output


@pytest.mark.parametrize(
    "error",
    [sqlite3.ProgrammingError("Cannot operate on a closed database."), sqlite3.InterfaceError(SENTINEL)],
)
def test_invalid_database_refusal_keeps_other_sqlite_errors(error: sqlite3.Error) -> None:
    with pytest.raises(type(error)), refuse_invalid_database():
        raise error


def test_invalid_database_refusal_keeps_a_statement_error() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(sqlite3.OperationalError), refuse_invalid_database():
            connection.execute("SELECT * FROM missing_table")
    finally:
        connection.close()


@pytest.mark.parametrize("activity", ["_invoke", "_observe"])
def test_activity_settles_after_its_handler_so_no_provider_failure_is_chained(activity: str) -> None:
    from raes_runtime.operation_temporal import EngineOperationReference
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities

    foreign = type("ProviderSecretTypeR1", (RuntimeError,), {})
    settlement = OperationalError("worker authority response could not be established")

    class Authority:
        def get_request(self, _reference: object) -> object:
            raise foreign(SENTINEL)

        def indeterminate(self, _reference: object) -> str:
            raise settlement

    reference = EngineOperationReference(
        operation_id="operation-1",
        invocation_id="invocation-1",
        deployment_id="deployment-1",
        owner_generation=1,
        execution_generation=1,
        worker_id="worker-1",
        request_digest="sha256:" + "a" * 64,
        effect_queue="effects",
        control_queue="controls",
        execution_budget_ms=1000,
        control_budget_ms=1000,
    )
    activities = TemporalOperationActivities(
        provider=object(), effect_authority=Authority(), control_authority=Authority(), worker_identity="worker-1"
    )
    try:
        run_activity = getattr(activities, activity)
        with pytest.raises(OperationalError) as raised:
            run_activity(reference)
    finally:
        assert activities.close()

    # A settlement failure inside the handler would carry the provider exception as its context.
    assert raised.value is settlement
    assert raised.value.__context__ is None


def test_migration_refuses_stored_rows_that_repeat_one_idempotency_claim() -> None:
    from raes_runtime.control_plane_store_record_migration import _ensure_idempotency_claim_index

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE operations (actor_id TEXT, operation_kind TEXT, idempotency_key TEXT)")
        connection.executemany("INSERT INTO operations VALUES (?, ?, ?)", [("actor", "provisioning", SENTINEL)] * 2)
        with pytest.raises(EvidenceIntegrityError, match="repeat an idempotency claim") as caught:
            _ensure_idempotency_claim_index(connection)
    finally:
        connection.close()

    assert isinstance(caught.value.__cause__, sqlite3.IntegrityError)
    assert SENTINEL not in str(caught.value)


def test_contract_decoder_lets_programming_errors_propagate() -> None:
    def _defect(_payload: dict[str, object]) -> None:
        raise KeyError(SENTINEL)

    digest = hashlib.sha256(b"{}").hexdigest()
    with pytest.raises(KeyError):
        decode_contract("{}", digest, kind="audit event", rebuild=_defect)


# HTTP routes: request content that the pre-branch handlers refused keeps its refusal status.

_LONE_SURROGATE = "\ud800"
_OPERATOR_TOKEN = "operator-token-r1"
_OPERATOR = {"authorization": f"Bearer {_OPERATOR_TOKEN}"}
_WORKER = {"x-raes-client-verified": "true", "x-raes-client-identity": "worker-1362"}


def _json_body(payload: object) -> bytes:
    # json.dumps escapes a lone surrogate as \ud800, which the server decodes back into a lone surrogate.
    return json.dumps(payload).encode("ascii")


def _stub_client() -> TestClient:
    control_plane = RuntimeControlPlane(create_stub_target())
    security = ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=True,
        trusted_identities={
            "backend-service": ControlPlaneIdentity(
                identity="backend-service",
                roles=frozenset({ControlPlaneRole.BACKEND}),
                target_name=control_plane.target_name,
            )
        },
    )
    return TestClient(create_control_plane_app(control_plane, security=security), raise_server_exceptions=False)


def _supervised_client(*, distributed: bool) -> tuple[RuntimeControlPlane, object, object, TestClient]:
    from test_issue_1362_distributed_authority import Dispatcher
    from test_issue_1362_provider_execution import Evidence, Provider, target

    provider = Provider()
    options: dict[str, object] = {"operation_evidence": Evidence()}
    dispatcher = Dispatcher() if distributed else None
    if distributed:
        options["distributed_execution"] = dispatcher
    else:
        provider.bad_digest = True
    control_plane = RuntimeControlPlane(target(provider), **options)
    receipt = control_plane.submit_provisioning(ProvisioningPlan(), idempotency_key="parent")
    request = dispatcher.commands[0] if dispatcher is not None else None
    security = ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=True,
        trusted_identities={
            "worker-1362": ControlPlaneIdentity(
                identity="worker-1362", roles=frozenset({ControlPlaneRole.BACKEND}), target_name="stub"
            )
        },
        bearer_tokens={
            _OPERATOR_TOKEN: ControlPlaneIdentity(
                identity="operator", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name="stub"
            )
        },
    )
    client = TestClient(create_control_plane_app(control_plane, security=security), raise_server_exceptions=False)
    return control_plane, receipt, request, client


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/operations/orchestration", {"diagnostics": [{"message": _LONE_SURROGATE}]}),
        ("/operations/evaluation", {"diagnostics": [{"message": _LONE_SURROGATE}]}),
        ("/workflows/orchestration.workflow.a/cancel", {"reason": _LONE_SURROGATE}),
    ],
    ids=["orchestration", "evaluation", "workflow-cancel"],
)
def test_routes_refuse_request_text_without_a_canonical_form(path: str, body: dict[str, object]) -> None:
    with _stub_client() as client:
        response = client.post(path, content=_json_body(body), headers={**_HEADERS, "content-type": "application/json"})

    assert (response.status_code, response.json()) == (409, {"detail": "operation conflict"})


def test_workflow_cancel_refuses_an_address_beyond_the_portable_diagnostic_bound() -> None:
    with _stub_client() as client:
        response = client.post(f"/workflows/{'a' * 5000}/cancel", json={}, headers=_HEADERS)

    assert (response.status_code, response.json()) == (409, {"detail": "operation conflict"})


def test_admission_context_refuses_a_request_integer_outside_the_canonical_range() -> None:
    from raes_contracts.operation_lifecycle import OperationKind
    from raes_runtime.control_plane_operation_context import operation_admission_context

    control_plane = RuntimeControlPlane(create_stub_target())
    try:
        with pytest.raises(InvalidInputError, match="canonical JSON value domain") as caught:
            operation_admission_context(
                control_plane, kind=OperationKind.ORCHESTRATION, request={"expected_snapshot_revision": 2**60}
            )
    finally:
        control_plane.close()

    assert str(2**60) not in str(caught.value)


@pytest.mark.parametrize("started_at", ["2016-12-31T23:59:60Z", "lower-z"], ids=["leap-second", "lowercase-z"])
def test_supervision_control_refuses_a_start_time_that_the_clock_cannot_read(started_at: str) -> None:
    from raes_contracts.contracts import backend_operation_request_digest

    if started_at == "lower-z":
        started_at = datetime.now(UTC).isoformat().replace("+00:00", "z")
    control_plane, receipt, request, client = _supervised_client(distributed=True)
    control = {
        "binding": request.binding.model_dump(mode="json"),
        "request_digest": backend_operation_request_digest(request),
        "control_id": "c1",
        "actor_id": "operator",
        "authorization_scope": ["role:operator"],
        "action": "observe",
        "budget": {"origin_id": "o1", "started_at": started_at, "limit_ms": 1500, "remaining_ms": 1500},
    }
    try:
        with client:
            response = client.post(f"/operations/{receipt.operation_id}/controls", json=control, headers=_OPERATOR)
    finally:
        control_plane.close()

    assert (response.status_code, response.json()) == (409, {"detail": "operation supervision conflict"})


def test_absence_resolution_refuses_evidence_that_does_not_establish_absence() -> None:
    operator = ControlPlaneIdentity(
        identity="operator", roles=frozenset({ControlPlaneRole.OPERATOR}), target_name="stub"
    )
    control_plane, receipt, _request, client = _supervised_client(distributed=False)
    control_plane.supervise_operation(receipt.operation_id, action="reconcile", control_id="unknown", identity=operator)
    try:
        with client:
            response = client.post(
                f"/operations/{receipt.operation_id}/absence-resolution",
                json={"control_id": "unknown"},
                headers={**_OPERATOR, "idempotency-key": "unknown-proof"},
            )
    finally:
        control_plane.close()

    assert (response.status_code, response.json()) == (409, {"detail": "operation supervision conflict"})


def test_worker_response_out_of_transcript_order_is_a_conflict() -> None:
    from raes_contracts.contracts import backend_operation_request_digest
    from test_issue_1362_distributed_authority import worker
    from test_issue_1362_provider_execution import Provider

    control_plane, receipt, request, client = _supervised_client(distributed=True)
    provider = Provider()
    control_plane.claim_backend_invocation(
        request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
    )

    def _response(sequence: int, message: dict[str, str]) -> dict[str, object]:
        return {
            "binding": request.binding.model_dump(mode="json"),
            "request_digest": backend_operation_request_digest(request),
            "sequence": sequence,
            "message": message,
        }

    url = f"/operations/{receipt.operation_id}/invocation/responses"
    try:
        with client:
            accepted = client.post(
                url, json=_response(5, {"kind": "acknowledgement", "disposition": "accepted"}), headers=_WORKER
            )
            stale = client.post(url, json=_response(3, {"kind": "progress", "phase": "executing"}), headers=_WORKER)
    finally:
        control_plane.close()

    assert accepted.status_code == 200
    assert (stale.status_code, stale.json()) == (409, {"detail": "operation supervision conflict"})


def test_temporal_connection_failure_is_an_operational_error() -> None:
    from raes_runtime.operation_temporal import TemporalExecutionAdapter, TemporalExecutionConfiguration

    async def _unreachable() -> object:
        raise RuntimeError(f"Failed client connect: {SENTINEL}")

    adapter = TemporalExecutionAdapter(TemporalExecutionConfiguration(), client_factory=_unreachable)
    try:
        with pytest.raises(OperationalError, match="^Temporal client connection failed$"):
            adapter._portal.call(adapter._connected)
    finally:
        adapter.close()


def test_request_digest_lets_a_programming_error_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_contracts.operation_lifecycle import OperationKind
    from raes_runtime import control_plane_operation_context as context_module

    def _defect(_payload: object) -> str:
        raise ValueError(SENTINEL)

    monkeypatch.setattr(context_module, "canonical_json_digest", _defect)
    control_plane = RuntimeControlPlane(create_stub_target())
    try:
        with pytest.raises(ValueError, match=SENTINEL):
            context_module.operation_admission_context(control_plane, kind=OperationKind.ORCHESTRATION, request={})
    finally:
        control_plane.close()


# Built-in handlers: backend refusals keep their outcome, and defects are not reported as refusals.


def test_credential_sanitizer_refuses_backend_output_as_invalid_input() -> None:
    from raes_contracts.runtime_state import ApplyResult
    from raes_runtime.backend_account_credentials import sanitize_account_credential_result
    from test_issue_673_account_credential_bindings import _credential_plan

    result = ApplyResult(True, RuntimeSnapshot(), details={"leak": SENTINEL})
    plan = _credential_plan()
    snapshot = RuntimeSnapshot()
    with pytest.raises(InvalidInputError, match="must not publish arbitrary details") as caught:
        sanitize_account_credential_result(result, plan, snapshot)

    assert SENTINEL not in str(caught.value)


def test_credential_sanitizer_boundary_lets_a_planner_defect_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import ApplyResult, SnapshotEntry
    from raes_runtime import backend_account_credentials
    from raes_runtime.backend_apply_results import _sanitize_backend_realization
    from raes_runtime.backend_realization_authority import _RealizationApplyContext
    from test_issue_673_account_credential_bindings import _credential_plan

    plan = _credential_plan()
    operation = plan.operations[0]
    entry = SnapshotEntry(
        operation.address,
        RuntimeDomain.PROVISIONING,
        operation.resource_type,
        dict(operation.payload),
        status="applied",
    )
    result = ApplyResult(True, RuntimeSnapshot().with_entries({operation.address: entry}))

    def _defect(_plan: object) -> tuple[object, ...]:
        raise ValueError(SENTINEL)

    monkeypatch.setattr(backend_account_credentials, "plan_realization_requirements", _defect)
    baseline_snapshot = RuntimeSnapshot()
    realization = _RealizationApplyContext(plan=plan)
    with pytest.raises(ValueError, match=SENTINEL):
        _sanitize_backend_realization(
            result,
            address="runtime.sweep-r1",
            baseline_snapshot=baseline_snapshot,
            realization=realization,
        )


@pytest.mark.parametrize("raw", ["0001-01-01T00:00:00+23:59", "9999-12-31T23:59:59-23:59"])
def test_timestamps_without_a_utc_form_are_invalid_timestamps(raw: str) -> None:
    from raes_runtime.control_plane_timeouts import _reconciliation_clock
    from raes_runtime.control_plane_workflows import parse_timestamp

    with pytest.raises(ValueError, match="explicit UTC offset"):
        parse_timestamp(raw)
    with pytest.raises(InvalidInputError, match="reconciliation clock is invalid"):
        _reconciliation_clock(raw)


@pytest.mark.parametrize(("error", "refused"), [(ValueError(SENTINEL), True), (TypeError(SENTINEL), False)])
def test_materialization_precondition_refuses_only_an_invalid_source(
    monkeypatch: pytest.MonkeyPatch, error: Exception, refused: bool
) -> None:
    from types import SimpleNamespace

    from raes_runtime import backend_materialization

    def _bound_scope(_request: object) -> tuple[object, bool]:
        raise error

    monkeypatch.setattr(backend_materialization, "_bound_scope_requirement", _bound_scope)
    context = SimpleNamespace(operation_plan=ProvisioningPlan(), manifest=None)
    if refused:
        assert backend_materialization.materialization_precondition(context, None) == (
            "Materialization reporting requires valid bound source context."
        )
    else:
        with pytest.raises(TypeError, match=SENTINEL):
            backend_materialization.materialization_precondition(context, None)


@pytest.mark.parametrize(("error", "refused"), [(ValueError(SENTINEL), True), (TypeError(SENTINEL), False)])
def test_submitted_authority_match_refuses_only_an_invalid_plan(
    monkeypatch: pytest.MonkeyPatch, error: Exception, refused: bool
) -> None:
    from types import SimpleNamespace

    from raes_runtime import backend_realization_authority

    def _digest(_plan: object) -> str:
        raise error

    monkeypatch.setattr(backend_realization_authority, "runtime_plan_digest", _digest)
    context = SimpleNamespace(plan=ProvisioningPlan(), operation_plan=ProvisioningPlan())
    if refused:
        assert backend_realization_authority._submitted_authority_matches(context) is False
    else:
        with pytest.raises(TypeError, match=SENTINEL):
            backend_realization_authority._submitted_authority_matches(context)


def test_participant_control_route_refuses_a_revision_outside_the_canonical_range() -> None:
    from test_run_310_supervisory_lifecycle import (
        _PARTICIPANT,
        _SPEC_ADDRESS,
        _api_security,
        _compiled_specification,
        _proposal_body,
    )

    control_plane = RuntimeControlPlane(
        create_stub_target(), behavior_specifications={_SPEC_ADDRESS: _compiled_specification()}
    )
    # A v1 intent has an unbounded revision, so 2**53 + 1 passes the model but has no RFC 8785 form.
    body = {**_proposal_body(), "expected_state_revision": 2**53 + 1}
    app = create_control_plane_app(control_plane, security=_api_security())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/participants/{_PARTICIPANT}/control-occurrences",
            json=body,
            headers={"authorization": "Bearer operator-token", "idempotency-key": "key-1"},
        )

    assert (response.status_code, response.json()) == (409, {"detail": "control intent conflicts with runtime state"})


@pytest.mark.parametrize("participant", ["alice", "p%20a"])
def test_episode_route_refuses_a_participant_address_that_is_not_compiled(participant: str) -> None:
    with _stub_client() as client:
        response = client.post(
            f"/participants/{participant}/episodes/initialize", json={"episode_id": "ep-1"}, headers=_HEADERS
        )

    assert (response.status_code, response.json()) == (409, {"detail": "operation conflict"})


def test_execution_control_route_refuses_a_scope_beyond_the_portable_diagnostic_bound() -> None:
    from dataclasses import replace

    from test_dsl_437_benign_participant_execution import (
        _autonomous_manifest,
        _compiled,
        _NativeParticipantRuntime,
    )
    from test_issue_898_participant_execution_control import _service_state

    scope = "participant.autonomous-execution.green-activity"
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(_compiled()[0]),
        participant_runtime=_NativeParticipantRuntime(),
    )
    control_plane = RuntimeControlPlane(
        target,
        initial_snapshot=RuntimeSnapshot(
            participant_execution_services={scope: _service_state().model_dump(mode="json")}
        ),
    )
    security = ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=True,
        trusted_identities={
            "backend-service": ControlPlaneIdentity(
                identity="backend-service",
                roles=frozenset({ControlPlaneRole.BACKEND}),
                target_name=control_plane.target_name,
            )
        },
    )
    app = create_control_plane_app(control_plane, security=security)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/participant-executions/{'s' * 5000}/control",
            json={"action": "start", "expected_generation": 0},
            headers={**_HEADERS, "idempotency-key": "key-1"},
        )

    assert (response.status_code, response.json()) == (409, {"detail": "operation conflict"})


def test_governed_view_leaves_a_budget_exhaustion_to_the_offload_deadline_response() -> None:
    from raes_runtime.control_plane_api_participant_retrieval import _governed_view
    from raes_runtime.errors import RuntimeBudgetExhaustedError

    def _exhausted() -> object:
        raise RuntimeBudgetExhaustedError("state admission budget exhausted")

    with pytest.raises(RuntimeBudgetExhaustedError):
        _governed_view(_exhausted)


# Isolation handlers settle after the handler, so a later failure carries no foreign exception as context.

_FOREIGN = type("ProviderSecretTypeR1", (RuntimeError,), {})


def test_native_work_settles_after_its_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_runtime import control_plane_supervised_execution as supervised

    settlement = OperationalError("store commit failed")

    def _foreign_failure(*_args: object, **_kwargs: object) -> None:
        raise _FOREIGN(SENTINEL)

    def _failed_settlement(*_args: object, **_kwargs: object) -> None:
        raise settlement

    monkeypatch.setattr(supervised, "_validate_native_invocation", _foreign_failure)
    monkeypatch.setattr(supervised, "settle", _failed_settlement)
    control_plane = RuntimeControlPlane(create_stub_target())
    try:
        plan = ProvisioningPlan()
        with pytest.raises(OperationalError) as raised:
            control_plane.submit_provisioning(plan, idempotency_key="native")
    finally:
        control_plane.close()

    assert raised.value is settlement
    assert raised.value.__context__ is None


def test_worker_outcome_settles_after_its_evidence_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_runtime import operation_provider_execution, operation_worker_authority
    from test_issue_1362_distributed_authority import Dispatcher, worker
    from test_issue_1362_provider_execution import Evidence, Provider, target

    provider, dispatcher = Provider(), Dispatcher()
    control_plane = RuntimeControlPlane(
        target(provider), operation_evidence=Evidence(), distributed_execution=dispatcher
    )
    settlement = OperationalError("store commit failed")

    def _foreign_failure(*_args: object, **_kwargs: object) -> None:
        raise _FOREIGN(SENTINEL)

    def _failed_settlement(*_args: object, **_kwargs: object) -> None:
        raise settlement

    try:
        control_plane.submit_provisioning(ProvisioningPlan())
        request = dispatcher.commands[0]
        control_plane.claim_backend_invocation(
            request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
        )
        control_plane.publish_backend_response(provider.start_operation(request), identity=worker())
        outcome = provider.observe_operation(None)
        monkeypatch.setattr(operation_provider_execution, "validate_outcome", _foreign_failure)
        monkeypatch.setattr(operation_worker_authority, "settle", _failed_settlement)
        identity = worker()
        with pytest.raises(OperationalError) as raised:
            control_plane.publish_backend_response(outcome, identity=identity)
    finally:
        monkeypatch.undo()
        control_plane.close()

    assert raised.value is settlement
    assert raised.value.__context__ is None


def test_inject_admission_refuses_after_its_resolver_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from raes_runtime import control_plane_injects

    settlement = OperationalError("refusal audit failed")

    def _foreign_failure(_request: object, _context: object) -> None:
        raise _FOREIGN(SENTINEL)

    def _failed_refusal(**_kwargs: object) -> None:
        raise settlement

    monkeypatch.setattr(
        control_plane_injects, "operation_admission_context", lambda *_args, **_kwargs: SimpleNamespace()
    )
    plane = SimpleNamespace(
        _target_scope="target:stub",
        _run_scope="run:default",
        _store=SimpleNamespace(find_by_idempotency=lambda *_args, **_kwargs: None),
        _admit_inject=_foreign_failure,
        _reject_diagnostics=_failed_refusal,
    )
    request = SimpleNamespace(target_scope="target:stub", run_scope="run:default", request_key="key-1")
    with pytest.raises(OperationalError) as raised:
        control_plane_injects.RuntimeInjectMixin._submit_inject(plane, request, identity=None)

    assert raised.value is settlement
    assert raised.value.__context__ is None


@pytest.mark.parametrize("typed", [True, False], ids=["claim-conflict", "same-text-conflict"])
def test_effect_claim_detects_the_idempotency_claim_conflict_by_type(
    monkeypatch: pytest.MonkeyPatch, typed: bool
) -> None:
    from types import SimpleNamespace

    from raes_contracts.operation_lifecycle import OperationAdmissionContext, OperationKind
    from raes_runtime import participant_control_receipts as receipts
    from raes_runtime.control_plane_store import IDEMPOTENCY_CLAIM_CONFLICT
    from raes_runtime.errors import IdempotencyClaimConflictError

    context = OperationAdmissionContext(
        actor_id="operator-r1",
        authorization_scope=("role:operator",),
        target_scope="target:stub",
        run_scope="run:default",
        operation_kind=OperationKind.PARTICIPANT_CONTROL,
        request_commitment=f"sha256:{'1' * 64}",
        parent_operation_id="origin-1",
    )
    conflict = IdempotencyClaimConflictError if typed else ConflictError
    monkeypatch.setattr(receipts, "_effect_claim_context", lambda _origin, _request: context)
    monkeypatch.setattr(receipts, "effect_idempotency_key", lambda _request: "control-effect:key")

    def _claim(_record: object) -> object:
        raise conflict(IDEMPOTENCY_CLAIM_CONFLICT)

    plane = SimpleNamespace(_claim_record=_claim)
    # A v1 effect request, which has no retained v2 claim to look up.
    request = SimpleNamespace()
    if typed:
        assert receipts.claim_effect(plane, None, request) is None
    else:
        # Exception text never selects a handler (E7): only the typed claim conflict is the claim refusal.
        with pytest.raises(ConflictError, match=IDEMPOTENCY_CLAIM_CONFLICT) as raised:
            receipts.claim_effect(plane, None, request)
        assert type(raised.value) is ConflictError


def test_stores_raise_the_typed_idempotency_claim_conflict(tmp_path: Path) -> None:
    from raes_contracts.operation_lifecycle import OperationAdmissionContext, OperationKind
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import OperationReceipt, OperationState, OperationStatus
    from raes_runtime.control_plane_store import IDEMPOTENCY_CLAIM_CONFLICT, ControlPlaneOperationRecord
    from raes_runtime.control_plane_store_memory import InMemoryControlPlaneStore
    from raes_runtime.errors import IdempotencyClaimConflictError

    def _record(operation_id: str, commitment: str) -> ControlPlaneOperationRecord:
        context = OperationAdmissionContext(
            actor_id="operator-r1",
            authorization_scope=("role:operator",),
            target_scope="target:stub",
            run_scope="run:ops",
            operation_kind=OperationKind.PROVISIONING,
            request_commitment=commitment,
        )
        submitted_at = "2026-10-28T00:00:00Z"
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
            request_fingerprint=commitment,
            idempotency_key="shared-key",
        )

    local = LocalControlPlaneStore(tmp_path / "store")
    lease = local.admit_runtime(target_scope="target:stub", run_scope="run:ops")
    try:
        for store in (InMemoryControlPlaneStore(), local):
            store.claim_record(_record("first", f"sha256:{'1' * 64}"))
            second = _record("second", f"sha256:{'2' * 64}")
            with pytest.raises(IdempotencyClaimConflictError, match=IDEMPOTENCY_CLAIM_CONFLICT):
                store.claim_record(second)
    finally:
        local.close()
        lease.close()


# Tampered stores keep the refusal outcome of other damage: the store raises EvidenceIntegrityError,
# the store command prints its label with exit status 1, and an HTTP route keeps its 409 response.

_LOST_TABLE = "missing a required table or column"
_SNAPSHOT_REFUSAL = "runtime snapshot failed its durable contract check"
_ENTRY = "provision.node.web"


def _bound_store(path: Path) -> Path:
    """Create a bound store with snapshot, history and audit rows."""

    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import SnapshotEntry

    database = _create_store(path)
    entry = SnapshotEntry(address=_ENTRY, domain=RuntimeDomain.PROVISIONING, resource_type="node", payload={"a": 1})
    store = LocalControlPlaneStore(path)
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:ops")
    try:
        store.save_snapshot(
            RuntimeSnapshot(entries={_ENTRY: entry}, evaluation_history={"run": [{"n": 1}]}), expected_revision=0
        )
    finally:
        store.close()
        lease.close()
    return database


def _has_table(database: Path, table: str) -> bool:
    with sqlite3.connect(database) as connection:
        found = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
        return found.fetchone() is not None


def _assert_store_refused(store_path: Path, message: str) -> None:
    store = LocalControlPlaneStore(store_path)
    with pytest.raises(EvidenceIntegrityError, match=message):
        store.admit_runtime(target_scope="target:stub", run_scope="run:ops")
    with pytest.raises(EvidenceIntegrityError, match=message):
        _check(store_path)
    _assert_refused(_store_command("check", str(store_path), *_OPTIONS), "check")


@pytest.mark.parametrize(
    "table",
    [
        "metadata",
        "state",
        "operations",
        "audit_events",
        "operation_changes",
        "snapshot_history_streams",
        "snapshot_history",
    ],
)
def test_admission_refuses_a_store_that_lost_a_table(tmp_path: Path, table: str) -> None:
    store_path = tmp_path / "store"
    database = _bound_store(store_path)
    with sqlite3.connect(database) as connection:
        connection.execute(f"DROP TABLE {table}")

    _assert_store_refused(store_path, _LOST_TABLE)
    # Admission refuses the store before its schema script can create an empty table in place of the lost one.
    assert not _has_table(database, table)


@pytest.mark.parametrize(
    "statement",
    [
        "ALTER TABLE audit_events RENAME COLUMN digest TO checksum",
        "ALTER TABLE state DROP COLUMN revision",
        "ALTER TABLE metadata RENAME COLUMN value TO content",
    ],
    ids=["audit-digest", "snapshot-revision", "metadata-value"],
)
def test_admission_refuses_a_store_that_lost_a_column(tmp_path: Path, statement: str) -> None:
    store_path = tmp_path / "store"
    with sqlite3.connect(_bound_store(store_path)) as connection:
        connection.execute(statement)

    _assert_store_refused(store_path, _LOST_TABLE)


@pytest.mark.parametrize("tables", [(), ("metadata",)], ids=["empty-file", "metadata-only"])
def test_admission_completes_a_store_whose_first_initialization_stopped(
    tmp_path: Path, tables: tuple[str, ...]
) -> None:
    store_path = tmp_path / "store"
    store_path.mkdir(mode=0o700)
    database = store_path / _DATABASE
    with sqlite3.connect(database) as connection:
        for table in tables:
            connection.execute(f"CREATE TABLE {table} (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    database.chmod(0o600)

    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:ops")
    try:
        assert store.load_snapshot_state().revision == 0
    finally:
        store.close()
        lease.close()
    _check(store_path)


def test_restore_refuses_a_backup_that_lost_a_table(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _bound_store(source)
    backup = tmp_path / "backups" / "store.sqlite3"
    assert _store_command("backup", str(source), str(backup), *_OPTIONS).exit_code == 0
    with sqlite3.connect(backup) as connection:
        connection.execute("DROP TABLE audit_events")

    _assert_refused(_store_command("restore", str(backup), str(tmp_path / "restored"), *_OPTIONS), "restore")
    with pytest.raises(EvidenceIntegrityError, match=_LOST_TABLE):
        maintain_local_control_plane_store(
            operation=LocalStoreMaintenanceOperation.RESTORE,
            store_path=tmp_path / "restored-again",
            backup_path=backup,
            target_name="stub",
            run_scope="run:ops",
        )


class _Ledger:
    """A PostgreSQL connection double that answers the table and column lookups of runtime admission."""

    def __init__(self, missing: set[str]) -> None:
        self.missing = missing

    def execute(self, statement: str, parameters: tuple[str]) -> object:
        from types import SimpleNamespace

        from raes_runtime.control_plane_store_postgresql_schema import LEDGER_COLUMNS, PROJECTION_COLUMNS

        if statement.startswith("SELECT attname FROM pg_attribute"):
            # The tables that this ledger has keep all of their columns.
            columns = {**LEDGER_COLUMNS, **PROJECTION_COLUMNS}[parameters[0]]
            return SimpleNamespace(fetchall=lambda: [(name,) for name in columns])
        assert statement == "SELECT to_regclass(%s)"
        found = (None,) if parameters[0] in self.missing else parameters
        return SimpleNamespace(fetchone=lambda: found)


_CORE_LEDGER = {"raes_ledger_metadata", "raes_ledger_state", "raes_ledger_operations", "raes_ledger_audit"}


@pytest.mark.parametrize(
    ("missing", "projection", "refusal"),
    [
        (set(), True, None),
        ({"raes_ledger_history"}, False, None),
        (_CORE_LEDGER, False, ConflictError),
        ({"raes_ledger_metadata"}, False, EvidenceIntegrityError),
        ({"raes_ledger_audit"}, False, EvidenceIntegrityError),
        ({"raes_ledger_history"}, True, EvidenceIntegrityError),
    ],
    ids=["complete", "unprojected", "not-bootstrapped", "lost-metadata", "lost-audit", "lost-history"],
)
def test_postgresql_admission_refuses_a_ledger_that_lost_a_table(
    missing: set[str], projection: bool, refusal: type[Exception] | None
) -> None:
    from raes_runtime.control_plane_store_postgresql_schema import require_ledger_tables

    if refusal is None:
        require_ledger_tables(_Ledger(missing), projection=projection)
        return
    ledger = _Ledger(missing)
    with pytest.raises(refusal) as caught:
        require_ledger_tables(ledger, projection=projection)
    assert type(caught.value) is refusal


def _rewrite_snapshot_header(database: Path, change: object) -> None:
    with sqlite3.connect(database) as connection:
        (content,) = connection.execute("SELECT payload FROM state WHERE key='runtime-snapshot'").fetchone()
        header = json.loads(content)
        change(header)
        text = json.dumps(header, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        connection.execute("UPDATE state SET payload=?, digest=? WHERE key='runtime-snapshot'", (text, digest))


def _set(*path: str, value: object) -> object:
    def change(header: dict[str, object]) -> None:
        node = header
        for step in path[:-1]:
            node = node[step]
        node[path[-1]] = value

    return change


@pytest.mark.parametrize(
    "change",
    [
        _set("metadata", value=SENTINEL),
        _set("entries", value=[]),
        _set("orchestration_results", value={"run": SENTINEL}),
        _set("realization_provenance", value=5),
        _set("materialization_attestations", value={}),
        _set("evaluation_history", value={"run": 5}),
        _set("entries", _ENTRY, "payload", value=[1]),
        _set("entries", _ENTRY, "ordering_dependencies", value=5),
        _set("entries", _ENTRY, "profile_bindings", value={}),
    ],
    ids=[
        "metadata",
        "entries",
        "results",
        "provenance",
        "attestations",
        "history",
        "entry-payload",
        "entry-dependencies",
        "entry-bindings",
    ],
)
def test_a_stored_snapshot_with_a_malformed_shape_is_an_integrity_failure(tmp_path: Path, change: object) -> None:
    store_path = tmp_path / "store"
    database = _bound_store(store_path)
    with sqlite3.connect(database) as connection:
        # Without the history format marker, the header carries the histories itself.
        connection.execute("DELETE FROM metadata WHERE key='snapshot-history-format'")
        connection.execute("DELETE FROM snapshot_history")
        connection.execute("DELETE FROM snapshot_history_streams")
    _rewrite_snapshot_header(database, change)

    with pytest.raises(EvidenceIntegrityError, match=_SNAPSHOT_REFUSAL) as caught:
        _check(store_path)
    assert SENTINEL not in f"{caught.value} {caught.value.__cause__}"
    _assert_refused(_store_command("check", str(store_path), *_OPTIONS), "check")


def test_the_snapshot_codec_lets_a_defect_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_runtime import control_plane_store_snapshots as snapshots

    def _defect(_payload: object) -> None:
        raise KeyError(SENTINEL)

    monkeypatch.setattr(snapshots, "_snapshot_entries_from_payload", _defect)
    with pytest.raises(KeyError):
        snapshots.durable_snapshot_state({}, 0)


def _backend_client(control_plane: RuntimeControlPlane) -> TestClient:
    security = ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=True,
        trusted_identities={
            "backend-service": ControlPlaneIdentity(
                identity="backend-service",
                roles=frozenset({ControlPlaneRole.BACKEND}),
                target_name=control_plane.target_name,
            )
        },
    )
    return TestClient(create_control_plane_app(control_plane, security=security), raise_server_exceptions=False)


def test_http_submission_keeps_its_conflict_response_for_a_malformed_stored_snapshot(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    control_plane = RuntimeControlPlane(
        create_stub_target(), store=LocalControlPlaneStore(store_path), run_scope="run:ops"
    )
    with _backend_client(control_plane) as client:
        accepted = client.post(
            "/operations/provisioning", json=_PROVISIONING, headers={**_HEADERS, "idempotency-key": "a"}
        )
        _rewrite_snapshot_header(store_path / _DATABASE, _set("metadata", value=5))
        refused = client.post(
            "/operations/provisioning", json=_PROVISIONING, headers={**_HEADERS, "idempotency-key": "b"}
        )

    assert accepted.status_code == 200
    assert (refused.status_code, refused.json()) == (409, {"detail": "operation conflict"})


def test_stored_text_that_is_not_utf8_is_an_integrity_failure(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    with sqlite3.connect(_create_store(store_path)) as connection:
        # The bytes of {"\xff":1}: SQLite keeps them as text that has no UTF-8 decoding.
        connection.execute("UPDATE audit_events SET payload=CAST(X'7b22ff223a317d' AS TEXT)")

    with pytest.raises(EvidenceIntegrityError, match="audit event failed its durable integrity check"):
        _check(store_path)
    _assert_refused(_store_command("check", str(store_path), *_OPTIONS), "check")


def test_stored_utf8_text_reads_back_unchanged(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    reason = "accepted é – 日本 \U0001f642"
    control_plane = RuntimeControlPlane(
        create_stub_target(), store=LocalControlPlaneStore(store_path), run_scope="run:ops"
    )
    control_plane.record_audit(
        action="maintenance-fixture", identity="operator-r1", allowed=True, target="target:stub", reason=reason
    )
    control_plane.close()

    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:ops")
    try:
        [event] = [event for event in store.read_audit() if event.action == "maintenance-fixture"]
    finally:
        store.close()
        lease.close()
    assert (type(event.reason), event.reason) == (str, reason)


def _nested(depth: int) -> str:
    return "[" * depth + "]" * depth


@pytest.mark.parametrize(("depth", "exceeds"), [(DURABLE_MAX_NESTING, False), (DURABLE_MAX_NESTING + 1, True)])
def test_the_durable_nesting_limit_is_exact(depth: int, exceeds: bool) -> None:
    text = _nested(depth)
    assert exceeds_durable_nesting(text, json.loads(text)) is exceeds


def test_brackets_inside_stored_text_are_not_nesting() -> None:
    value = {"text": "[{" * DURABLE_MAX_NESTING}
    assert exceeds_durable_nesting(json.dumps(value), value) is False


def test_the_store_does_not_write_a_value_that_it_refuses_to_read() -> None:
    deepest = {"a": json.loads(_nested(DURABLE_MAX_NESTING - 1))}
    content, digest = encode_payload(deepest)
    assert decode_payload(content, digest, kind="audit event") == deepest

    too_deep = {"a": json.loads(_nested(DURABLE_MAX_NESTING))}
    with pytest.raises(ValueError, match="durable nesting limit"):
        encode_payload(too_deep)


def test_a_stored_history_record_nested_beyond_the_durable_limit_is_an_integrity_failure(tmp_path: Path) -> None:
    store_path = tmp_path / "store"
    record = '{"n":' + _nested(400) + "}"
    with sqlite3.connect(_bound_store(store_path)) as connection:
        digest = hashlib.sha256(record.encode("utf-8")).hexdigest()
        connection.execute("UPDATE snapshot_history SET payload=?, digest=?", (record, digest))

    with pytest.raises(EvidenceIntegrityError, match="snapshot history record exceeds the durable nesting limit"):
        _check(store_path)
    _assert_refused(_store_command("check", str(store_path), *_OPTIONS), "check")


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("control-transition-state.json", '{"snapshot": 5}'),
        ("control-transition-state.json", '{"snapshot": [["metadata", 5]]}'),
        ("control-transition-state.json", '{"records": [1]}'),
        ("control-transition-state.json", '{"audit": 5}'),
        ("snapshot.json", '{"metadata": {"a": ' + _nested(1000) + "}}"),
        ("operations.json", '{"operation-1": {"a": ' + _nested(1000) + "}}"),
    ],
    ids=["snapshot", "snapshot-pairs", "records", "audit", "deep-snapshot", "deep-operations"],
)
def test_malformed_legacy_state_is_an_integrity_failure(tmp_path: Path, name: str, content: str) -> None:
    store_path = tmp_path / "store"
    store_path.mkdir(mode=0o700)
    (store_path / name).write_text(content, encoding="utf-8")

    store = LocalControlPlaneStore(store_path)
    with pytest.raises(EvidenceIntegrityError):
        store.admit_runtime(target_scope="target:stub", run_scope="run:ops")


# A runtime that requires restart refuses the work with its restart category. The handler logs the foreign
# record one time, and the refusal is raised after the handler, so no record can render the foreign exception.

_RESTART = "requires restart after a durability reconciliation failure"


def _poisoning_failure(plane: RuntimeControlPlane, *_args: object, **_kwargs: object) -> None:
    plane._poison_runtime_durability()
    raise _FOREIGN(SENTINEL)


def _assert_restart_refusal(error: OperationalError, caplog: pytest.LogCaptureFixture, logger: str) -> None:
    assert (error.__cause__, error.__context__) == (None, None)
    [record] = [record for record in caplog.records if record.name == logger]
    assert "raes_contracts.operational_logging.ForeignCodeFailure" in (record.exc_text or "")
    assert SENTINEL not in caplog.text
    assert _FOREIGN.__name__ not in caplog.text


def test_poisoned_native_work_refuses_with_the_restart_category(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from raes_runtime import control_plane_supervised_execution as supervised

    monkeypatch.setattr(supervised, "_validate_native_invocation", _poisoning_failure)
    control_plane = RuntimeControlPlane(create_stub_target())
    try:
        plan = ProvisioningPlan()
        with caplog.at_level(logging.ERROR), pytest.raises(OperationalError, match=_RESTART) as raised:
            control_plane.submit_provisioning(plan, idempotency_key="poisoned")
        with pytest.raises(OperationalError, match=_RESTART):
            control_plane.get_snapshot()
    finally:
        control_plane.close()

    _assert_restart_refusal(raised.value, caplog, "raes_runtime.control_plane_supervised_execution")


def test_http_submission_answers_503_when_the_runtime_requires_restart(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from raes_runtime import control_plane_supervised_execution as supervised

    monkeypatch.setattr(supervised, "_validate_native_invocation", _poisoning_failure)
    with _backend_client(RuntimeControlPlane(create_stub_target())) as client, caplog.at_level(logging.ERROR):
        responses = [
            client.post("/operations/provisioning", json=_PROVISIONING, headers={**_HEADERS, "idempotency-key": key})
            for key in ("poisoned", "after")
        ]

    # Before the fix, the first response was the redacted 500 of the re-raised foreign exception.
    assert [(response.status_code, response.json()) for response in responses] == [
        (503, {"detail": "control-plane unavailable"})
    ] * 2
    assert SENTINEL not in caplog.text
    assert _FOREIGN.__name__ not in caplog.text


def test_http_admission_answers_503_for_a_closed_runtime() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    with _backend_client(control_plane) as client:
        control_plane.close()
        response = client.post("/operations/provisioning", json=_PROVISIONING, headers=_HEADERS)

    # Before the fix, the admission dependency let the closed-runtime category reach the redacted 500 handler.
    assert (response.status_code, response.json()) == (503, {"detail": "control-plane unavailable"})


def test_poisoned_provider_execution_refuses_with_the_restart_category(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from raes_runtime import operation_provider_execution
    from test_issue_1362_provider_execution import Evidence, Provider, target

    monkeypatch.setattr(operation_provider_execution, "_start_local_provider", _poisoning_failure)
    control_plane = RuntimeControlPlane(target(Provider()), operation_evidence=Evidence())
    try:
        plan = ProvisioningPlan()
        with caplog.at_level(logging.ERROR), pytest.raises(OperationalError, match=_RESTART) as raised:
            control_plane.submit_provisioning(plan)
    finally:
        control_plane.close()

    _assert_restart_refusal(raised.value, caplog, "raes_runtime.operation_provider_execution")


def test_poisoned_control_delivery_refuses_with_the_restart_category(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from raes_runtime import operation_provider_control
    from test_issue_1362_provider_execution import Evidence, Provider, target
    from test_issue_1362_runtime_supervision import supervisor

    provider = Provider()
    provider.release.clear()
    control_plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence())
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            submission = executor.submit(control_plane.submit_provisioning, ProvisioningPlan())
            try:
                assert provider.started.wait(5)
                parent_id = next(iter(control_plane._store.load_records()))
                monkeypatch.setattr(operation_provider_control, "provider_call", _poisoning_failure)
                identity = supervisor()
                with caplog.at_level(logging.ERROR), pytest.raises(OperationalError, match=_RESTART) as raised:
                    control_plane.cancel_operation(parent_id, control_id="poisoned-cancel", identity=identity)
            finally:
                provider.release.set()
            # The work of the poisoned runtime ends with the same refusal.
            assert isinstance(submission.exception(timeout=10), OperationalError)
    finally:
        control_plane.close()

    _assert_restart_refusal(raised.value, caplog, "raes_runtime.operation_provider_control")


def test_provider_failure_settles_after_its_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    from raes_runtime import operation_provider_execution
    from test_issue_1362_provider_execution import Evidence, Provider, target

    settlement = OperationalError("store commit failed")

    def _foreign_failure(*_args: object, **_kwargs: object) -> None:
        raise _FOREIGN(SENTINEL)

    def _failed_settlement(*_args: object, **_kwargs: object) -> None:
        raise settlement

    monkeypatch.setattr(operation_provider_execution, "_start_local_provider", _foreign_failure)
    monkeypatch.setattr(operation_provider_execution, "settle", _failed_settlement)
    control_plane = RuntimeControlPlane(target(Provider()), operation_evidence=Evidence())
    try:
        plan = ProvisioningPlan()
        with pytest.raises(OperationalError) as raised:
            control_plane.submit_provisioning(plan)
    finally:
        control_plane.close()

    # A settlement failure inside the handler would carry the provider exception as its context.
    assert raised.value is settlement
    assert raised.value.__context__ is None


# A change to a value that a durable claim fixes keeps its own error. The handler finds it by its mark,
# not by its text (E7).


def _terminal_record(*, idempotency_key: str = "key-1", state: str = "succeeded") -> object:
    from raes_contracts.operation_lifecycle import OperationAdmissionContext, OperationKind
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import OperationReceipt, OperationState, OperationStatus
    from raes_runtime.control_plane_store import ControlPlaneOperationRecord

    context = OperationAdmissionContext(
        actor_id="operator-r1",
        authorization_scope=("role:operator",),
        target_scope="target:stub",
        run_scope="run:ops",
        operation_kind=OperationKind.PROVISIONING,
        request_commitment=f"sha256:{'1' * 64}",
    )
    submitted_at = "2026-10-28T00:00:00Z"
    return ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id="operation-1",
            domain=RuntimeDomain.PROVISIONING,
            submitted_at=submitted_at,
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id="operation-1",
            domain=RuntimeDomain.PROVISIONING,
            state=OperationState(state),
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=context,
        ),
        request_fingerprint=context.request_commitment,
        idempotency_key=idempotency_key,
    )


def test_a_terminal_rewrite_keeps_the_marked_immutable_value_error() -> None:
    from raes_runtime.control_plane_store_transitions import _require_terminal_operation_transition
    from raes_runtime.record_immutability import is_immutable_value_error

    existing = _terminal_record()
    replacement = _terminal_record(idempotency_key="key-2")
    with pytest.raises(ValueError, match="operation identity is immutable after its durable claim") as raised:
        _require_terminal_operation_transition(existing, replacement)
    assert is_immutable_value_error(raised.value)

    existing = _terminal_record()
    replacement = _terminal_record(state="failed")
    with pytest.raises(ValueError, match="a terminal operation record cannot be rewritten") as rewritten:
        _require_terminal_operation_transition(existing, replacement)
    assert not is_immutable_value_error(rewritten.value)


def test_the_text_of_an_unmarked_error_does_not_select_the_immutable_value_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from raes_runtime import control_plane_store_transitions as transitions

    def _unmarked(*_args: object) -> bool:
        raise ValueError("operation identity is immutable after its durable claim")

    monkeypatch.setattr(transitions, "_require_operation_record_transition", _unmarked)
    existing = _terminal_record()
    replacement = _terminal_record(state="failed")
    with pytest.raises(ValueError, match="a terminal operation record cannot be rewritten"):
        transitions._require_terminal_operation_transition(existing, replacement)


@pytest.mark.parametrize("poisoned", [True, False], ids=["poisoned", "settled"])
def test_mixed_invocation_refuses_with_the_restart_category_only_when_poisoned(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, poisoned: bool
) -> None:
    from types import SimpleNamespace

    from raes_runtime import mixed_backend_invocation as invocation

    plane = SimpleNamespace(_durability_poisoned=False)
    execution = SimpleNamespace(dispatched=False, uncertain=False, state=None)
    cleanup: list[str] = []

    def failing_admission(plane_arg: SimpleNamespace, _execution: object) -> bool:
        plane_arg._durability_poisoned = poisoned
        raise _FOREIGN(SENTINEL)

    monkeypatch.setattr(invocation, "_reload", lambda *_args: cleanup.append("reload"))
    monkeypatch.setattr(invocation, "_admit_running", failing_admission)
    monkeypatch.setattr(invocation, "confirm_no_dispatch", lambda _execution: cleanup.append("confirm"))
    with caplog.at_level(logging.ERROR):
        if poisoned:
            with pytest.raises(OperationalError, match=_RESTART) as raised:
                invocation.run_mixed_invocation(plane, execution)
            _assert_restart_refusal(raised.value, caplog, "raes_runtime.mixed_backend_invocation")
            assert execution.state is None
        else:
            invocation.run_mixed_invocation(plane, execution)
            assert execution.state is invocation.OperationState.FAILED
    # The cleanup in the finally block runs before the refusal leaves the function.
    assert cleanup[-2:] == ["reload", "confirm"]
    assert _FOREIGN.__name__ not in caplog.text
