"""Issue 1678: the exception policy applies to the runtime plane code that dev merged (ADR-116).

The dev branch added run contexts, experiments and reference-only Temporal delivery
without the policy. These tests pin the refusal categories of that code and the
categories that its handlers now catch.
"""

from __future__ import annotations

import logging

import httpx
import pytest
from pydantic import SecretStr
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import (
    AuthorizationError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    OperationalError,
)
from raes_contracts.planning import PlanScope
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole, ControlPlaneSecurityConfig
from raes_runtime.control_plane_store import NewClaimRejected
from raes_runtime.runtime_sequence_reference import RuntimeSequenceReference

_DIGEST = "sha256:" + "a" * 64


def _worker(name: str = "state-worker") -> ControlPlaneIdentity:
    return ControlPlaneIdentity(identity=name, roles=frozenset({ControlPlaneRole.BACKEND}), target_name="stub")


def _reference(**update: object) -> RuntimeSequenceReference:
    values = {
        "engine_id": _DIGEST,
        "kind": "run",
        "execution_id": "one",
        "scope_id": "run:default",
        "request_digest": _DIGEST,
        "worker_id": "state-worker",
        "state_queue": "state",
    }
    return RuntimeSequenceReference(**{**values, **update})


def _plan(run: object, run_id: str) -> object:
    return run.plan(
        parse_sdl("name: devmerge\nnodes:\n  server:\n    type: compute\n"),
        run_scope=PlanScope(run_id=run_id),
    )


@pytest.mark.parametrize("method", ["advance_experiment", "cancel_experiment", "experiment_results"])
def test_unknown_experiment_is_not_found_rather_than_a_key_error(method: str) -> None:
    with (
        RuntimeControlPlane(create_stub_target()) as engine,
        pytest.raises(NotFoundError, match="runtime experiment is not admitted") as raised,
    ):
        getattr(engine, method)("experiment:absent")

    assert "experiment:absent" not in str(raised.value)


def test_cyclic_collection_of_a_closed_engine_writes_no_finalizer_failure(caplog: pytest.LogCaptureFixture) -> None:
    import gc

    with RuntimeControlPlane(create_stub_target()) as engine:
        pass
    engine._cycle = engine
    del engine
    with caplog.at_level(logging.ERROR, logger="raes_runtime.control_plane_lifecycle"):
        gc.collect()

    assert not [record for record in caplog.records if record.name == "raes_runtime.control_plane_lifecycle"]


def _authority(rpc_budget_ms: int = 2000) -> tuple[object, list[httpx.Request]]:
    from raes_runtime.operation_remote_authority import RemoteAuthorityConfiguration, RemoteOperationAuthority

    sent: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json="progress")

    authority = RemoteOperationAuthority(
        RemoteAuthorityConfiguration(
            base_url="http://127.0.0.1:9",
            identity=_worker(),
            bearer_token=SecretStr("worker-token-1678"),
            rpc_budget_ms=rpc_budget_ms,
            allow_insecure_loopback=True,
        ),
        transport=httpx.MockTransport(record),
    )
    return authority, sent


def test_remote_runtime_advance_refuses_a_foreign_reference_with_the_authorization_category() -> None:
    authority, sent = _authority()
    try:
        with pytest.raises(AuthorizationError, match="runtime worker reference is forbidden"):
            authority.advance_runtime(_reference(worker_id="foreign"))
    finally:
        assert authority.close()

    assert not sent


def test_remote_runtime_advance_refuses_a_reference_budget_below_the_authority_call() -> None:
    authority, sent = _authority(rpc_budget_ms=2000)
    try:
        with pytest.raises(InvalidInputError, match="runtime activity budget"):
            authority.advance_runtime(_reference(activity_budget_ms=2000))
    finally:
        assert authority.close()

    assert not sent


def test_closed_temporal_adapter_refuses_runtime_delivery_as_operational() -> None:
    pytest.importorskip("temporalio")
    from raes_runtime.operation_temporal import TemporalExecutionAdapter

    adapter = object.__new__(TemporalExecutionAdapter)
    adapter._closed = True
    with pytest.raises(OperationalError, match="Temporal execution adapter is closed"):
        adapter.submit_runtime(_reference())


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotFoundError("runtime execution is absent"), 404),
        (AuthorizationError("runtime sequence worker is forbidden"), 404),
        (OperationalError("runtime control plane is closed"), 503),
        (ConflictError("runtime run is retired"), 409),
        (InvalidInputError("runtime reference is invalid"), 409),
    ],
)
def test_runtime_progress_route_maps_refusal_categories(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status: int
) -> None:
    from fastapi.testclient import TestClient
    from raes_runtime.control_plane_api import create_control_plane_app

    def refuse(*_args: object, **_kwargs: object) -> str:
        raise error

    with RuntimeControlPlane(create_stub_target()) as engine:
        monkeypatch.setattr(engine, "advance_workflow", refuse)
        security = ControlPlaneSecurityConfig(bearer_tokens={"worker": _worker()})
        with TestClient(create_control_plane_app(engine, security=security)) as client:
            response = client.post(
                "/runtime/progress",
                json=_reference().model_dump(mode="json"),
                headers={"Authorization": "Bearer worker"},
            )

    assert response.status_code == status
    assert str(error) not in response.text


def test_runtime_progress_route_does_not_report_a_programming_error_as_a_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient
    from raes_runtime.control_plane_api import create_control_plane_app

    def defect(*_args: object, **_kwargs: object) -> str:
        raise ValueError("defect-value-1678")

    with RuntimeControlPlane(create_stub_target()) as engine:
        monkeypatch.setattr(engine, "advance_workflow", defect)
        security = ControlPlaneSecurityConfig(bearer_tokens={"worker": _worker()})
        app = create_control_plane_app(engine, security=security)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/runtime/progress",
                json=_reference().model_dump(mode="json"),
                headers={"Authorization": "Bearer worker"},
            )

    assert response.status_code == 500
    assert "defect-value-1678" not in response.text


@pytest.mark.parametrize(
    "error",
    [ConflictError("target resources are reserved by another run"), OperationalError("runtime engine is closed")],
)
def test_engine_reservation_category_blocks_a_new_claim_and_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    with RuntimeControlPlane(create_stub_target()) as engine:
        run = engine.open_run(run_scope="run:reserved")
        plan = _plan(run, "reserved")

        def refuse(_context: object) -> None:
            raise error

        monkeypatch.setattr(engine._engine, "reserve", refuse)
        with pytest.raises(type(error)) as raised:
            run.apply(plan)
        monkeypatch.undo()
        assert not run._store.load_records()

    assert raised.value is error


def test_closed_engine_effect_admission_is_not_replaced_by_the_reservation_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejection = NewClaimRejected("runtime engine effect admission is closed")
    with RuntimeControlPlane(create_stub_target()) as engine:
        run = engine.open_run(run_scope="run:closed-admission")
        plan = _plan(run, "closed-admission")

        def refuse(_context: object) -> None:
            raise rejection

        monkeypatch.setattr(engine._engine, "reserve", refuse)
        with pytest.raises(NewClaimRejected) as raised:
            run.apply(plan)
        monkeypatch.undo()

    assert raised.value is rejection
