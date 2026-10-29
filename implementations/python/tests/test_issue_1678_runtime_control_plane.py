"""Issue 1678 regressions for the runtime control plane (ADR-116).

Routes map refusal categories to statuses, and a built-in exception from the
core is a defect that reaches the redacted 500 handler. Handlers that isolate
backend, provider and resolver code record one value-free log record. That
record does not show the class name of the foreign exception.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import nullcontext
from threading import Event
from time import monotonic
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import (
    AuthorizationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    OperationalError,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api._offload import run_in_threadpool
from raes_runtime.control_plane_api_participant_retrieval import _governed_view
from raes_runtime.control_plane_mutation import MutationReservationRequired, RuntimeMutationAuthority
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from raes_runtime.errors import RuntimeBudgetExhaustedError
from starlette.testclient import TestClient

SENTINEL = "value-sentinel-1678"
FOREIGN_TYPE = "ProviderSecretType1678"
_HEADERS = {"x-raes-client-verified": "true", "x-raes-client-identity": "backend-service"}
_OPERATOR = {"authorization": "Bearer operator-token-1678"}
_PROVISIONING = {"operations": [], "diagnostics": [], "realization_authority": []}


def _security(target_name: str) -> ControlPlaneSecurityConfig:
    return ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=True,
        trusted_identities={
            "backend-service": ControlPlaneIdentity(
                identity="backend-service", roles=frozenset({ControlPlaneRole.BACKEND}), target_name=target_name
            )
        },
        bearer_tokens={
            "operator-token-1678": ControlPlaneIdentity(
                identity="operator",
                roles=frozenset({ControlPlaneRole.OPERATOR, ControlPlaneRole.AUDITOR}),
                target_name=target_name,
            )
        },
    )


def _raising(error: BaseException):
    def call(*_args: object, **_kwargs: object) -> None:
        raise error

    return call


def _records(caplog: pytest.LogCaptureFixture, logger: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == logger]


def _assert_value_free(record: logging.LogRecord, error_type: str) -> None:
    assert SENTINEL not in record.getMessage()
    assert error_type in (record.exc_text or "")
    assert SENTINEL not in (record.exc_text or "")


def _foreign() -> Exception:
    """A provider failure whose class name is foreign content (ADR-104 conformance)."""

    return type(FOREIGN_TYPE, (RuntimeError,), {})(SENTINEL)


def _assert_foreign_free(record: logging.LogRecord) -> None:
    _assert_value_free(record, "raes_contracts.operational_logging.ForeignCodeFailure")
    assert FOREIGN_TYPE not in record.getMessage() + (record.exc_text or "")


def _served(monkeypatch: pytest.MonkeyPatch, method: str, error: BaseException) -> TestClient:
    control_plane = RuntimeControlPlane(create_stub_target())
    monkeypatch.setattr(control_plane, method, _raising(error))
    app = create_control_plane_app(control_plane, security=_security(control_plane.target_name))
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (ConflictError(SENTINEL), 409, "operation conflict"),
        (InvalidInputError(SENTINEL), 409, "operation conflict"),
        (AuthorizationError(SENTINEL), 403, "forbidden"),
        (NotFoundError(SENTINEL), 404, "not found"),
        (OperationalError(SENTINEL), 503, "control-plane unavailable"),
        (RuntimeBudgetExhaustedError(SENTINEL), 503, "control-plane call deadline exceeded"),
        (ValueError(SENTINEL), 500, "internal server error"),
        (KeyError(SENTINEL), 500, "internal server error"),
        (TypeError(SENTINEL), 500, "internal server error"),
    ],
)
def test_submission_route_maps_categories_and_reports_built_in_defects_as_500(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, status: int, detail: str
) -> None:
    with _served(monkeypatch, "submit_provisioning", error) as client:
        response = client.post("/operations/provisioning", json=_PROVISIONING, headers=_HEADERS)

    assert (response.status_code, response.json()) == (status, {"detail": detail})
    assert SENTINEL not in response.text


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (NotFoundError(SENTINEL), 404, "indeterminate operation not found"),
        (AuthorizationError(SENTINEL), 404, "indeterminate operation not found"),
        (ConflictError(SENTINEL), 409, "indeterminate resolution conflict"),
        (OperationalError(SENTINEL), 409, "indeterminate resolution conflict"),
        (KeyError(SENTINEL), 500, "internal server error"),
        (ValueError(SENTINEL), 500, "internal server error"),
    ],
)
def test_resolution_route_keeps_its_statuses_for_categories_only(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, status: int, detail: str
) -> None:
    with _served(monkeypatch, "resolve_indeterminate_operation", error) as client:
        response = client.post(
            "/operations/operation-1/resolution",
            json={"disposition": "accept-current-snapshot"},
            headers={**_OPERATOR, "idempotency-key": "resolution-1678"},
        )

    assert (response.status_code, response.json()) == (status, {"detail": detail})


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (NotFoundError(SENTINEL), 404, "operation not found"),
        (AuthorizationError(SENTINEL), 404, "operation not found"),
        (ConflictError(SENTINEL), 409, "operation supervision conflict"),
        (OperationalError(SENTINEL), 503, "operation supervision unavailable"),
        (ValueError(SENTINEL), 500, "internal server error"),
        (TypeError(SENTINEL), 500, "internal server error"),
        (RuntimeError(SENTINEL), 500, "internal server error"),
    ],
)
def test_supervision_route_maps_categories_and_reports_built_in_defects_as_500(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, status: int, detail: str
) -> None:
    with _served(monkeypatch, "stop_admission", error) as client:
        response = client.post("/execution/stop", headers=_OPERATOR)

    assert (response.status_code, response.json()) == (status, {"detail": detail})


@pytest.mark.parametrize(
    ("error", "status"),
    [(NotFoundError(SENTINEL), 404), (ConflictError(SENTINEL), 404), (ValueError(SENTINEL), 500)],
)
def test_participant_execution_read_maps_refusals_to_404_and_defects_to_500(
    monkeypatch: pytest.MonkeyPatch, error: BaseException, status: int
) -> None:
    with _served(monkeypatch, "participant_execution_state", error) as client:
        response = client.get("/participant-executions/exec-scope-1", headers=_OPERATOR)

    assert response.status_code == status
    assert SENTINEL not in response.text


def test_governed_view_leaves_the_mutation_reservation_signal_to_the_executor() -> None:
    signal = MutationReservationRequired(RuntimeMutationAuthority(), "participant-crossing")

    with pytest.raises(MutationReservationRequired):
        _governed_view(_raising(signal))


def test_auth_audit_failure_is_recorded_once_without_values(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with _served(monkeypatch, "record_audit", OSError(SENTINEL)) as client, caplog.at_level(logging.ERROR):
        response = client.get("/snapshot")

    assert response.status_code == 401
    [record] = _records(caplog, "raes_runtime.control_plane_api._auth")
    assert record.getMessage() == "control-plane-auth-audit-failed"
    _assert_value_free(record, "OSError")


@pytest.mark.parametrize(
    "interruption", [SystemExit(SENTINEL), type(FOREIGN_TYPE, (BaseException,), {})(SENTINEL)], ids=["exit", "foreign"]
)
def test_worker_interruption_cause_is_recorded_before_it_is_hidden(
    caplog: pytest.LogCaptureFixture, interruption: BaseException
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError, match="^control-plane worker interrupted$"):
        asyncio.run(run_in_threadpool(_raising(interruption)))

    # Only backend or provider code can end a worker with an interruption, so its type is foreign content.
    [record] = _records(caplog, "raes_runtime.control_plane_api._offload")
    _assert_foreign_free(record)
    assert "SystemExit" not in (record.exc_text or "")


def test_backend_method_failure_is_recorded_without_values(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.backend_calls import _call_backend_diagnostics

    with caplog.at_level(logging.ERROR):
        diagnostics = _call_backend_diagnostics(_raising(_foreign()), address="runtime.test.validate")

    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.backend-call-failed"]
    [record] = _records(caplog, "raes_runtime.backend_calls")
    assert record.getMessage() == "backend method failed at runtime.test.validate"
    _assert_foreign_free(record)


def test_backend_diagnostics_iterator_failure_is_recorded_and_refused(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.backend_call_contracts import _materialize_diagnostics

    class FailingIterable:
        def __iter__(self):
            raise _foreign()

    with caplog.at_level(logging.ERROR):
        diagnostics, message = _materialize_diagnostics(FailingIterable(), "runtime.test")

    assert (diagnostics, message) == ([], "Backend returned a diagnostics iterable that could not be validated.")
    [record] = _records(caplog, "raes_runtime.backend_call_contracts")
    _assert_foreign_free(record)
    assert _materialize_diagnostics(iter([None] * 1025), "runtime.test") == (
        [],
        "Backend returned too many diagnostics.",
    )


def test_recovery_observer_failure_is_recorded_and_stays_indeterminate(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.control_plane_recovery import _bound_observation_result

    plane = SimpleNamespace(
        _execution_adapter=SimpleNamespace(call=_raising(_foreign())),
        _supervision=SimpleNamespace(observation_ms=100),
    )
    with caplog.at_level(logging.ERROR):
        assert _bound_observation_result(plane, SimpleNamespace(observe_effect=None), object()) is None

    [record] = _records(caplog, "raes_runtime.control_plane_recovery")
    _assert_foreign_free(record)


def test_readiness_records_an_unexpected_lease_check_failure_only(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.control_plane_health import _lease_available

    with caplog.at_level(logging.ERROR):
        assert _lease_available(SimpleNamespace(_assert_runtime_owner=_raising(OSError(SENTINEL))), object()) is False
        assert (
            _lease_available(SimpleNamespace(_assert_runtime_owner=_raising(ConflictError(SENTINEL))), object())
            is False
        )
        assert _lease_available(SimpleNamespace(_assert_runtime_owner=lambda: None), object()) is True
        assert _lease_available(SimpleNamespace(_assert_runtime_owner=lambda: None), None) is False

    [record] = _records(caplog, "raes_runtime.control_plane_health")
    _assert_value_free(record, "OSError")


def test_store_readback_failure_poisons_and_is_recorded(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.control_plane_durability import RuntimeDurabilityMixin

    class Plane(RuntimeDurabilityMixin):
        poisoned = False

        def _poison_runtime_durability(self) -> None:
            self.poisoned = True

    plane = Plane()
    plane._store = SimpleNamespace(load_snapshot_state=_raising(OSError(SENTINEL)))
    original = RuntimeError("original store failure")
    with caplog.at_level(logging.ERROR):
        plane._resynchronize_after_store_error(
            original, operation_id="operation-1", expected_audit=object(), require_terminal_cut=True
        )

    assert plane.poisoned
    [record] = _records(caplog, "raes_runtime.control_plane_durability")
    _assert_value_free(record, "OSError")


def test_deadline_callback_failure_is_recorded_and_fenced(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.operation_execution_adapter import LocalExecutionAdapter

    fenced = Event()
    adapter = LocalExecutionAdapter()
    try:
        with caplog.at_level(logging.ERROR):
            adapter.arm_deadline(
                "invocation", monotonic(), _raising(RuntimeError(SENTINEL)), failure_handler=fenced.set
            )
            assert fenced.wait(2)
    finally:
        assert adapter.close(timeout_ms=1000)

    [record] = _records(caplog, "raes_runtime.operation_execution_adapter")
    _assert_value_free(record, "RuntimeError")


@pytest.mark.parametrize(("error", "logged"), [(_foreign(), True), (ConflictError(SENTINEL), False)])
def test_inject_revalidation_records_only_an_unexpected_resolver_failure(
    caplog: pytest.LogCaptureFixture, error: Exception, logged: bool
) -> None:
    from raes_runtime.control_plane_injects import RuntimeInjectMixin

    plane = SimpleNamespace(
        _require_inject_schedule=lambda _request: None,
        _mutation_authority=SimpleNamespace(external_call=nullcontext),
        _execution_adapter=SimpleNamespace(call=_raising(error)),
        _inject_execution=SimpleNamespace(revalidate=None),
        _snapshot=RuntimeSnapshot(),
        _supervision=SimpleNamespace(admission_ms=100),
    )
    with caplog.at_level(logging.ERROR):
        diagnostics = RuntimeInjectMixin._inject_live_diagnostics(plane, SimpleNamespace(request=None))

    assert [diagnostic.code for diagnostic in diagnostics] == ["runtime.inject.admission-refused"]
    records = _records(caplog, "raes_runtime.control_plane_injects")
    assert len(records) == int(logged)
    for record in records:
        _assert_foreign_free(record)


def test_inject_capture_failure_is_recorded_and_captured_as_failed(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.inject_capture import capture_inject

    plane = SimpleNamespace(
        _mutation_authority=SimpleNamespace(external_call=nullcontext),
        _execution_adapter=SimpleNamespace(call=_raising(_foreign())),
        _snapshot=RuntimeSnapshot(),
        _target=SimpleNamespace(manifest=None, observation_runtime=None),
    )
    record = SimpleNamespace(receipt=SimpleNamespace(operation_id="operation-1"))
    with caplog.at_level(logging.ERROR):
        result = capture_inject(plane, record, SimpleNamespace(observation_demands=(object(),)), lambda: 100)

    assert result.status == "failed"
    [log_record] = _records(caplog, "raes_runtime.inject_capture")
    _assert_foreign_free(log_record)


def _engine_reference():
    from raes_runtime.operation_temporal import EngineOperationReference

    return EngineOperationReference(
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


def test_activity_failure_cause_is_recorded_before_the_value_free_failure(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities

    activities = TemporalOperationActivities(
        provider=object(), effect_authority=None, control_authority=None, worker_identity="worker-1"
    )
    try:
        with caplog.at_level(logging.ERROR), pytest.raises(OperationalError) as raised:
            asyncio.run(activities._job(activities._control_jobs, "control", _raising(_foreign()), budget_ms=1000))
    finally:
        assert activities.close()

    assert str(raised.value) == "backend activity could not be established"
    # Not even a suppressed context: a value-free rendering of the chain would show the foreign type.
    assert (raised.value.__cause__, raised.value.__context__) == (None, None)
    [record] = _records(caplog, "raes_runtime.operation_temporal_worker")
    _assert_foreign_free(record)


def test_activity_observation_failure_is_recorded_before_indeterminate_readback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities

    class Authority:
        get_request = staticmethod(_raising(_foreign()))

        def indeterminate(self, _reference: object) -> str:
            return "indeterminate"

    activities = TemporalOperationActivities(
        provider=object(), effect_authority=Authority(), control_authority=Authority(), worker_identity="worker-1"
    )
    try:
        with caplog.at_level(logging.ERROR):
            assert activities._observe(_engine_reference()) == "indeterminate"
    finally:
        assert activities.close()

    [record] = _records(caplog, "raes_runtime.operation_temporal_worker")
    _assert_foreign_free(record)


def test_activity_reference_validation_detail_stays_out_of_engine_history() -> None:
    from raes_runtime.operation_temporal_worker import TemporalOperationActivities

    activities = TemporalOperationActivities(
        provider=object(), effect_authority=None, control_authority=None, worker_identity="worker-1"
    )
    try:
        with pytest.raises(InvalidInputError, match="^engine operation reference is invalid$") as raised:
            activities._reference({"worker_id": SENTINEL})
    finally:
        assert activities.close()

    assert raised.value.__suppress_context__


def test_worker_authority_transport_failure_is_recorded_without_values(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.operation_remote_authority import RemoteAuthorityConfiguration, RemoteOperationAuthority

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(SENTINEL, request=request)

    identity = ControlPlaneIdentity(
        identity="worker-1", roles=frozenset({ControlPlaneRole.BACKEND}), target_name="stub"
    )
    authority = RemoteOperationAuthority(
        RemoteAuthorityConfiguration(
            base_url="http://127.0.0.1:9",
            identity=identity,
            bearer_token=SecretStr("worker-token-1678"),
            allow_insecure_loopback=True,
        ),
        transport=httpx.MockTransport(refuse),
    )
    try:
        with caplog.at_level(logging.ERROR), pytest.raises(OperationalError) as raised:
            authority.get_request(_engine_reference())
    finally:
        assert authority.close()

    assert raised.value.__suppress_context__
    [record] = _records(caplog, "raes_runtime.operation_remote_authority")
    _assert_value_free(record, "ConnectError")


def test_runtime_fact_dispatch_failures_are_recorded_without_values(caplog: pytest.LogCaptureFixture) -> None:
    from raes_contracts.contracts.runtime_facts import RuntimeFactBindingDisposition
    from raes_runtime.runtime_fact_bindings import RuntimeFactBindingPlane
    from raes_runtime.runtime_fact_dispatch import RuntimeFactDispatchCommand, _RuntimeFactDispatchFailure

    with caplog.at_level(logging.ERROR), pytest.raises(_RuntimeFactDispatchFailure):
        RuntimeFactDispatchCommand(()).dispatch(send=_raising(_foreign()))
    plane = RuntimeFactBindingPlane(action_dispatcher=_raising(_foreign()))
    with caplog.at_level(logging.ERROR):
        assert plane._dispatch(()) is RuntimeFactBindingDisposition.DISPATCH_FAILED

    for logger in ("raes_runtime.runtime_fact_dispatch", "raes_runtime.runtime_fact_bindings"):
        [record] = _records(caplog, logger)
        _assert_foreign_free(record)


def test_runtime_finalizer_close_failure_is_recorded(caplog: pytest.LogCaptureFixture) -> None:
    from raes_runtime.control_plane_lifecycle import RuntimeLifecycleMixin

    class Runtime(RuntimeLifecycleMixin):
        failures = [ConflictError(SENTINEL)]

        def close(self) -> None:
            # Only the explicit finalizer call fails; the later collection closes cleanly.
            if self.failures:
                raise self.failures.pop()

    with caplog.at_level(logging.ERROR):
        Runtime().__del__()

    [record] = _records(caplog, "raes_runtime.control_plane_lifecycle")
    _assert_value_free(record, "ConflictError")


def test_backend_result_contract_diagnostics_do_not_echo_backend_values() -> None:
    from raes_runtime.evaluation_result_contracts import _normalized_evaluation_result
    from raes_runtime.workflow_result_contract_checks._context import _normalized_workflow_result

    workflow = {
        "state_schema_version": "workflow-step-state/v1",
        "workflow_status": SENTINEL,
        "run_id": "run-1",
        "started_at": "2000-01-01T00:00:00Z",
        "updated_at": "2000-01-01T00:00:00Z",
        "compensation_status": "not_required",
        "compensation_failures": [],
        "steps": {},
    }
    evaluation = {
        "state_schema_version": "evaluation-state/v1",
        "resource_type": "condition-binding",
        "run_id": "run-1",
        "status": SENTINEL,
        "observed_at": "2000-01-01T00:00:00Z",
        "updated_at": "2000-01-01T00:00:00Z",
    }

    _state, workflow_diagnostics = _normalized_workflow_result("orchestration.workflow.secret", workflow)
    _state, evaluation_diagnostics = _normalized_evaluation_result("evaluation.condition.secret", evaluation)

    assert [diagnostic.message for diagnostic in workflow_diagnostics] == ["Workflow result payload is invalid."]
    assert [diagnostic.message for diagnostic in evaluation_diagnostics] == ["Evaluation result payload is invalid."]
