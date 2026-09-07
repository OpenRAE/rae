"""Reference HTTP/JSON control-plane API tests."""

from __future__ import annotations

import asyncio
import sqlite3
import textwrap
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path
from threading import Barrier as ThreadBarrier
from threading import Event
from typing import Any, Protocol, TypeVar

import httpx
import pytest
from fastapi import HTTPException
from raes import parse_sdl
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import (
    ParticipantContextViewModel,
    ParticipantHistoryViewModel,
    ParticipantStatusViewModel,
)
from raes_contracts.plan_projection import evaluation_plan_model, orchestration_plan_model, provisioning_plan_model
from raes_contracts.planning import ChangeAction, OrchestrationOp, OrchestrationPlan, ProvisioningPlan
from raes_contracts.runtime_state import (
    ExplicitnessClass,
    ExplicitnessProvenance,
    OperationAdmissionContext,
    OperationKind,
    RealizationProvenanceEntry,
    RuntimeSnapshot,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import OperationReceipt, OperationState, OperationStatus, RuntimeDomain
from raes_processor.planner import plan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api._auth import _ControlPlaneApiAuth
from raes_runtime.control_plane_api._offload import _control_plane_calls, _ControlPlaneCallExecutor
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
)
from raes_runtime.control_plane_store import ControlPlaneOperationRecord, LocalControlPlaneStore
from starlette.requests import Request
from starlette.testclient import TestClient

_T = TypeVar("_T")


def _run(coroutine: Coroutine[Any, Any, _T]) -> _T:
    """Run one coroutine without replacing or closing pytest's default loop."""

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def _scenario(yaml_str: str):
    return parse_sdl(textwrap.dedent(yaml_str))


def _provisioning_payload(plan_value: object) -> dict[str, object]:
    return provisioning_plan_model(plan_value).model_dump(mode="json", exclude_none=True)


def _admit_workflow_prerequisites(control_plane: RuntimeControlPlane, execution_plan: object) -> None:
    control_plane.register_planner_produced_plan(execution_plan)
    provisioning = control_plane.submit_provisioning(execution_plan.provisioning)
    evaluation = control_plane.submit_evaluation(execution_plan.evaluation)
    assert provisioning.accepted, provisioning.diagnostics
    assert evaluation.accepted, evaluation.diagnostics


def _participant_operation_record(operation_id: str, participant_address: str) -> ControlPlaneOperationRecord:
    submitted_at = "2026-06-05T10:00:00Z"
    context = OperationAdmissionContext(
        actor_id="embedded-process",
        authorization_scope=("process:trusted-embedder",),
        target_scope="target:stub",
        run_scope="run:test",
        operation_kind=OperationKind.PARTICIPANT_ACTION,
        request_commitment=f"sha256:{'a' * 64}",
    )
    return ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at=submitted_at,
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            state=OperationState.RUNNING,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=context,
            changed_addresses=[participant_address],
        ),
    )


class _BarrierLike(Protocol):
    def wait(self, timeout: float | None = None) -> int: ...


_CROSS_PROCESS_BARRIER_TIMEOUT_SECONDS = 60
_CROSS_PROCESS_JOIN_TIMEOUT_SECONDS = 75


def _save_operation_in_process(store_path: str, index: int, barrier: _BarrierLike) -> None:
    record = replace(
        _participant_operation_record(
            f"process-operation-{index}",
            f"participant.behavior.process-subject-{index}",
        ),
        idempotency_key=f"process-key-{index}",
        request_fingerprint=f"process-fingerprint-{index}",
    )
    barrier.wait(timeout=_CROSS_PROCESS_BARRIER_TIMEOUT_SECONDS)
    LocalControlPlaneStore(Path(store_path)).save_record(record)


def _test_security(
    target_name: str,
    *,
    max_request_bytes: int = 1_000_000,
    max_pending_mutations: int = 32,
) -> ControlPlaneSecurityConfig:
    return ControlPlaneSecurityConfig(
        max_request_bytes=max_request_bytes,
        max_pending_mutations=max_pending_mutations,
        trust_proxy_identity_headers=True,
        trusted_identities={
            "backend-service": ControlPlaneIdentity(
                identity="backend-service",
                roles=frozenset({ControlPlaneRole.BACKEND}),
                target_name=target_name,
            ),
        },
        bearer_tokens={
            "test-operator-token": ControlPlaneIdentity(
                identity="operator",
                roles=frozenset({ControlPlaneRole.OPERATOR, ControlPlaneRole.AUDITOR}),
                target_name=target_name,
            ),
            "test-auditor-token": ControlPlaneIdentity(
                identity="auditor",
                roles=frozenset({ControlPlaneRole.AUDITOR}),
                target_name=target_name,
            ),
        },
    )


def test_control_plane_strict_defaults_ship_without_builtin_principals():
    security = ControlPlaneSecurityConfig.strict_defaults()

    assert security.require_verified_identity is True
    assert security.trust_proxy_identity_headers is False
    assert security.trusted_identities == {}
    assert security.bearer_tokens == {}


def test_control_plane_security_rejects_nonpositive_mutation_queue_bound() -> None:
    with pytest.raises(ValueError, match="max_pending_mutations must be positive"):
        ControlPlaneSecurityConfig(max_pending_mutations=0)


def test_control_plane_security_rejects_nonpositive_rejection_audit_bound() -> None:
    with pytest.raises(ValueError, match="max_pending_rejection_audits must be positive"):
        ControlPlaneSecurityConfig(max_pending_rejection_audits=0)


def test_control_plane_api_default_security_does_not_trust_builtin_headers_or_tokens():
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(control_plane)

    with TestClient(app) as client:
        header_response = client.get(
            "/snapshot",
            headers={
                "x-raes-client-verified": "true",
                "x-raes-client-identity": "backend-service",
            },
        )
        token_response = client.get(
            "/snapshot",
            headers={"authorization": "Bearer operator-token"},
        )

    assert header_response.status_code == 401
    assert token_response.status_code == 401


def test_control_plane_api_openapi_documents_explicit_error_responses():
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )

    operation_responses = app.openapi()["paths"]

    assert "409" in operation_responses["/operations/provisioning"]["post"]["responses"]
    assert "409" in operation_responses["/operations/orchestration"]["post"]["responses"]
    assert "409" in operation_responses["/operations/evaluation"]["post"]["responses"]
    assert "404" in operation_responses["/operations/{operation_id}"]["get"]["responses"]
    assert "409" in operation_responses["/workflows/{workflow_address}/cancel"]["post"]["responses"]
    assert "409" in operation_responses["/workflows/reconcile-timeouts"]["post"]["responses"]
    assert "409" in operation_responses["/participants/{participant_address}/episodes/initialize"]["post"]["responses"]
    assert "409" in operation_responses["/participants/{participant_address}/episodes/reset"]["post"]["responses"]
    assert "409" in operation_responses["/participants/{participant_address}/episodes/restart"]["post"]["responses"]
    terminate_responses = operation_responses["/participants/{participant_address}/episodes/terminate"]["post"][
        "responses"
    ]
    assert "400" in terminate_responses
    assert "409" in terminate_responses
    assert "404" in operation_responses["/participants/{participant_address}/status"]["get"]["responses"]
    history_path = "/participants/{participant_address}/episodes/{episode_id}/history"
    assert "404" in operation_responses[history_path]["get"]["responses"]
    assert "404" in operation_responses["/participants/{participant_address}/context"]["get"]["responses"]
    assert "/apparatus/operational-summary" in operation_responses


def test_control_plane_call_lookup_fails_closed_without_configured_executor() -> None:
    target = create_stub_target()
    app = create_control_plane_app(RuntimeControlPlane(target), security=_test_security(target.name))
    del app.state.control_plane_call_executor
    request = Request({"type": "http", "app": app})

    with pytest.raises(RuntimeError, match="executor is not configured"):
        _control_plane_calls(request)


def test_control_plane_api_accepts_evaluation_plan() -> None:
    scenario = _scenario("""
name: evaluation-route
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(control_plane, security=_test_security(target.name))
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    with TestClient(app) as client:
        response = client.post(
            "/operations/evaluation",
            json=evaluation_plan_model(execution_plan.evaluation).model_dump(mode="json", exclude_none=True),
            headers=headers,
        )

    assert response.status_code == 200
    receipt = response.json()
    assert receipt["context"]["actor_id"] == "backend-service"
    assert receipt["context"]["target_scope"] == f"target:{target.name}"
    assert receipt["context"]["operation_kind"] == "evaluation"
    assert receipt["context"]["request_commitment"].startswith("sha256:")
    status = control_plane.get_operation(receipt["operation_id"])
    assert status is not None
    assert status.state is OperationState.SUCCEEDED
    assert status.context.model_dump(mode="json") == receipt["context"]


def test_control_plane_api_audits_denied_operation_receipt_as_denied() -> None:
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    submitted_plan = OrchestrationPlan(
        operations=[
            OrchestrationOp(
                action=ChangeAction.CREATE,
                address="orchestration.workflow.test",
                resource_type="workflow",
                payload={},
                ordering_dependencies=("orchestration.workflow.missing",),
            )
        ],
        startup_order=["orchestration.workflow.test"],
    )
    authorization_plan = plan(compile_runtime_model(_scenario("name: admission-authorization")), target.manifest)
    # Planner validity is intentionally out of scope; this test targets the
    # operation-admission rejection and its audit record after authorization.
    control_plane.register_planner_produced_plan(replace(authorization_plan, orchestration=submitted_plan))
    app = create_control_plane_app(control_plane, security=_test_security(target.name))
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    with TestClient(app) as client:
        response = client.post(
            "/operations/orchestration",
            json=orchestration_plan_model(submitted_plan).model_dump(mode="json", exclude_none=True),
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["accepted"] is False
    audits = [event for event in control_plane.audit_log() if event.operation_id == response.json()["operation_id"]]
    assert len(audits) == 1
    assert audits[0].action == "orchestration_admission"
    assert all(event.identity == "backend-service" and event.allowed is False for event in audits)


@pytest.mark.parametrize("domain", ["orchestration", "evaluation"])
def test_control_plane_api_rejects_unregistered_nonempty_phase_plan(domain: str) -> None:
    scenario = _scenario("""
name: authorization-gate
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  validate:
    entity: blue
    success: {assertions: [health]}
workflows:
  response:
    start: run
    steps:
      run:
        type: objective
        objective: validate
        on_success: finish
      finish: {type: end}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    submitted_plan = getattr(execution_plan, domain)
    assert submitted_plan.operations
    projector = orchestration_plan_model if domain == "orchestration" else evaluation_plan_model
    payload = projector(submitted_plan).model_dump(mode="json", exclude_none=True)
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(control_plane, security=_test_security(target.name))

    with TestClient(app) as client:
        response = client.post(
            f"/operations/{domain}",
            json=payload,
            headers={
                "x-raes-client-verified": "true",
                "x-raes-client-identity": "backend-service",
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": f"{domain} plan is not planner-authorized"}
    assert control_plane.audit_log()[-1].reason == "planner-authorization-mismatch"


def test_control_plane_api_redacts_unexpected_route_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(control_plane, security=_test_security(target.name))
    monkeypatch.setattr(
        control_plane,
        "get_snapshot",
        lambda: (_ for _ in ()).throw(RuntimeError("SECRET-BACKEND-DETAIL")),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/snapshot",
            headers={"authorization": "Bearer test-auditor-token"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    assert "SECRET-BACKEND-DETAIL" not in response.text
    assert control_plane.audit_log()[-1].reason == "internal-error:RuntimeError"


def test_control_plane_api_accepts_orchestration_plan_and_exposes_snapshot():
    scenario = _scenario("""
name: workflow
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  validate:
    entity: blue
    success: {assertions: [health]}
workflows:
  response:
    start: run
    steps:
      run:
        type: objective
        objective: validate
        on_success: finish
      finish: {type: end}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane = RuntimeControlPlane(target)
    _admit_workflow_prerequisites(control_plane, execution_plan)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    with TestClient(app) as client:
        response = client.post(
            "/operations/orchestration",
            json={
                "operations": [
                    {
                        "action": op.action.value,
                        "address": op.address,
                        "resource_type": op.resource_type,
                        "payload": op.payload,
                        "ordering_dependencies": list(op.ordering_dependencies),
                        "refresh_dependencies": list(op.refresh_dependencies),
                    }
                    for op in execution_plan.orchestration.operations
                ],
                "startup_order": execution_plan.orchestration.startup_order,
                "diagnostics": [],
            },
            headers=headers,
        )
        assert response.status_code == 200
        receipt = response.json()
        status_response = client.get(
            f"/operations/{receipt['operation_id']}",
            headers=headers,
        )
        assert status_response.status_code == 200
        snapshot_response = client.get("/snapshot", headers=headers)
        assert snapshot_response.status_code == 200
        snapshot = snapshot_response.json()
        assert snapshot["orchestration_results"]
        assert snapshot["orchestration_results"]["orchestration.workflow.response"]["workflow_status"] == "running"


def test_control_plane_api_exposes_operational_apparatus_summary_to_auditors():
    scenario = _scenario("""
name: workflow
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  validate:
    entity: blue
    success: {assertions: [health]}
workflows:
  response:
    start: run
    steps:
      run:
        type: objective
        objective: validate
        on_success: finish
      finish: {type: end}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane = RuntimeControlPlane(target)
    _admit_workflow_prerequisites(control_plane, execution_plan)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    backend_headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }
    auditor_headers = {"authorization": "Bearer test-auditor-token"}

    with TestClient(app) as client:
        receipt = client.post(
            "/operations/orchestration",
            json={
                "operations": [
                    {
                        "action": op.action.value,
                        "address": op.address,
                        "resource_type": op.resource_type,
                        "payload": op.payload,
                        "ordering_dependencies": list(op.ordering_dependencies),
                        "refresh_dependencies": list(op.refresh_dependencies),
                    }
                    for op in execution_plan.orchestration.operations
                ],
                "startup_order": execution_plan.orchestration.startup_order,
                "diagnostics": [],
            },
            headers=backend_headers,
        ).json()
        response = client.get("/apparatus/operational-summary", headers=auditor_headers)

    assert response.status_code == 200
    summary = response.json()
    assert summary["target"] == target.name
    assert summary["resources"]["total"] >= 1
    assert summary["resources"]["by_domain"]["orchestration"] >= 1
    assert summary["operations"]["by_state"]["succeeded"] == 3
    orchestration_record = next(
        record for record in summary["operations"]["recent"] if record["operation_id"] == receipt["operation_id"]
    )
    assert orchestration_record["diagnostic_count"] == 0
    assert orchestration_record["diagnostic_codes"] == []
    assert orchestration_record["changed_addresses"]
    assert summary["runtime_surfaces"]["orchestration_results"] >= 1
    assert summary["runtime_surfaces"]["orchestration_history"] >= 1
    assert summary["audit"]["allowed"] >= 2
    assert summary["audit"]["denied"] == 0
    assert summary["audit"]["recent"][-1]["identity"] == "auditor"
    assert "details" not in summary["audit"]["recent"][-1]


def test_control_plane_api_operational_apparatus_summary_requires_read_role():
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )

    with TestClient(app) as client:
        response = client.get("/apparatus/operational-summary")

    assert response.status_code == 401
    assert control_plane.audit_log()
    assert control_plane.audit_log()[-1].allowed is False


def test_operational_apparatus_summary_snapshots_operations_safely_during_mutation() -> None:
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    control_plane._claim_record(_participant_operation_record("existing", "participant.alice"))
    iteration_started = Event()
    mutation_completed = Event()

    class PausingOperationRecords(dict[str, ControlPlaneOperationRecord]):
        def values(self):  # type: ignore[override]
            live_values = super().values()

            def iter_values():
                iterator = iter(live_values)
                yield next(iterator)
                iteration_started.set()
                mutation_completed.wait(timeout=2)
                yield from iterator

            return iter_values()

        def __setitem__(self, key: str, value: ControlPlaneOperationRecord) -> None:
            super().__setitem__(key, value)
            mutation_completed.set()

    control_plane._operations = PausingOperationRecords(control_plane._operations)

    with ThreadPoolExecutor(max_workers=2) as executor:
        summary = executor.submit(control_plane.operational_apparatus_summary)
        assert iteration_started.wait(timeout=2)
        persistence = executor.submit(
            control_plane._claim_record,
            _participant_operation_record("concurrent", "participant.bob"),
        )
        result = summary.result(timeout=3)
        persistence.result(timeout=3)

    assert result["operations"]["total"] == 1
    assert control_plane.get_operation("concurrent") is not None


def test_control_plane_api_rejects_unauthenticated_mutations():
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )

    with TestClient(app) as client:
        response = client.post(
            "/operations/provisioning",
            json={"operations": [], "diagnostics": [], "realization_authority": []},
        )

    assert response.status_code == 401


def test_control_plane_api_supports_idempotent_retries():
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
        "idempotency-key": "same-request",
    }

    with TestClient(app) as client:
        first = client.post(
            "/operations/provisioning",
            json={"operations": [], "diagnostics": [], "realization_authority": []},
            headers=headers,
        )
        second = client.post(
            "/operations/provisioning",
            json={"operations": [], "diagnostics": [], "realization_authority": []},
            headers=headers,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["operation_id"] == second.json()["operation_id"]


def test_slow_backend_submission_does_not_block_unrelated_http_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    entered = Event()
    release = Event()
    real_submit = control_plane.submit_provisioning

    def blocking_submit(
        submitted_plan: ProvisioningPlan,
        *,
        base_snapshot: RuntimeSnapshot | None = None,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test backend was not released")
        return real_submit(
            submitted_plan,
            base_snapshot=base_snapshot,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=identity,
        )

    monkeypatch.setattr(control_plane, "submit_provisioning", blocking_submit)
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            submission = asyncio.create_task(
                client.post(
                    "/operations/provisioning",
                    json={"operations": [], "diagnostics": [], "realization_authority": []},
                    headers=headers,
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert not submission.done()
                snapshot = await asyncio.wait_for(
                    client.get("/snapshot", headers=headers),
                    timeout=1,
                )
                assert snapshot.status_code == 200
            finally:
                release.set()
            response = await asyncio.wait_for(submission, timeout=2)
            assert response.status_code == 200

    _run(exercise())


def test_control_plane_rejects_mutation_queue_overload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name, max_pending_mutations=1),
    )
    entered = Event()
    release = Event()
    real_submit = control_plane.submit_provisioning

    def blocking_submit(
        submitted_plan: ProvisioningPlan,
        *,
        base_snapshot: RuntimeSnapshot | None = None,
        idempotency_key: str = "",
        request_fingerprint: str = "",
        identity: object | None = None,
    ) -> OperationReceipt:
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test backend was not released")
        return real_submit(
            submitted_plan,
            base_snapshot=base_snapshot,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            identity=identity,
        )

    monkeypatch.setattr(control_plane, "submit_provisioning", blocking_submit)
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = asyncio.create_task(
                client.post(
                    "/operations/provisioning",
                    json={"operations": [], "diagnostics": [], "realization_authority": []},
                    headers={**headers, "idempotency-key": "first"},
                )
            )
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                overloaded = await asyncio.wait_for(
                    client.post(
                        "/operations/provisioning",
                        json={"operations": [], "diagnostics": [], "realization_authority": []},
                        headers={**headers, "idempotency-key": "second"},
                    ),
                    timeout=1,
                )
                assert overloaded.status_code == 503
                assert overloaded.json() == {"detail": "control-plane mutation queue is full"}
                assert overloaded.headers["retry-after"] == "1"
            finally:
                release.set()
            assert (await asyncio.wait_for(first, timeout=2)).status_code == 200

    _run(exercise())


def test_control_plane_executor_serializes_target_mutations() -> None:
    executor = _ControlPlaneCallExecutor(max_pending_mutations=2)
    first_entered = Event()
    release_first = Event()
    execution_order: list[str] = []

    def mutation(label: str) -> str:
        execution_order.append(f"start:{label}")
        if label == "first":
            first_entered.set()
            if not release_first.wait(timeout=5):
                raise TimeoutError("first mutation was not released")
        execution_order.append(f"end:{label}")
        return label

    async def exercise() -> None:
        first = asyncio.create_task(executor.mutate(mutation, "first"))
        second: asyncio.Task[str] | None = None
        try:
            assert await asyncio.to_thread(first_entered.wait, 2)
            second = asyncio.create_task(executor.mutate(mutation, "second"))
            await asyncio.sleep(0.05)
            assert execution_order == ["start:first"]
        finally:
            release_first.set()
        assert second is not None
        assert await asyncio.gather(first, second) == ["first", "second"]

    _run(exercise())
    assert execution_order == ["start:first", "end:first", "start:second", "end:second"]


def test_control_plane_executor_rejects_nonpositive_queue_bound() -> None:
    with pytest.raises(ValueError, match="max_pending_mutations must be positive"):
        _ControlPlaneCallExecutor(max_pending_mutations=0)


def test_control_plane_api_persists_operations_and_snapshot(tmp_path: Path):
    scenario = _scenario("""
name: workflow
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    store = LocalControlPlaneStore(tmp_path / "cp-store")
    control_plane = RuntimeControlPlane(target, store=store)
    control_plane.register_planner_produced_provisioning_plan(execution_plan)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    with TestClient(app) as client:
        receipt = client.post(
            "/operations/provisioning",
            json=_provisioning_payload(execution_plan.provisioning),
            headers=headers,
        ).json()

    control_plane.close()
    restarted = RuntimeControlPlane(target, store=store)
    assert restarted.get_operation(receipt["operation_id"]) is not None
    assert restarted.get_snapshot().snapshot.entries
    restarted.close()


def test_backend_principal_cannot_rewrite_registered_realization_authority() -> None:
    scenario = _scenario("""
name: authority-integrity
realization:
  default: closed
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane = RuntimeControlPlane(target)
    control_plane.register_planner_produced_provisioning_plan(execution_plan)
    app = create_control_plane_app(control_plane, security=_test_security(target.name))
    payload = _provisioning_payload(execution_plan.provisioning)
    closed_entry = next(
        entry for entry in payload["realization_authority"] if entry["requirement_kind"] == "runtime-environment"
    )
    closed_entry["mode"] = "open"
    closed_entry["source"] = "authored-scope"

    with TestClient(app) as client:
        response = client.post(
            "/operations/provisioning",
            json=payload,
            headers={
                "x-raes-client-verified": "true",
                "x-raes-client-identity": "backend-service",
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "provisioning plan is not planner-authorized"}
    assert control_plane.snapshot.entries == {}


def test_authenticated_snapshot_preserves_realization_governing_scope_from_store(tmp_path: Path):
    target = create_stub_target()
    store = LocalControlPlaneStore(tmp_path / "cp-store")
    store.save_snapshot(
        RuntimeSnapshot(
            realization_provenance=(
                RealizationProvenanceEntry(
                    address="node.web",
                    field_path="nodes.web.os",
                    domain="runtime-realization",
                    requirement_kind="os-family",
                    explicitness=ExplicitnessClass.OPEN,
                    provenance=ExplicitnessProvenance.BACKEND_REALIZED,
                    governing_scope="#/",
                ),
            )
        )
    )
    restarted = RuntimeControlPlane(target, store=store)
    app = create_control_plane_app(
        restarted,
        security=_test_security(target.name),
    )

    with TestClient(app) as client:
        response = client.get(
            "/snapshot",
            headers={"authorization": "Bearer test-auditor-token"},
        )

    assert response.status_code == 200
    assert response.json()["realization_provenance"] == [
        {
            "address": "node.web",
            "field_path": "nodes.web.os",
            "domain": "runtime-realization",
            "requirement_kind": "os-family",
            "explicitness": "open",
            "provenance": "backend-realized",
            "governing_scope": "#/",
        }
    ]


def test_control_plane_api_records_audit_events_for_denials():
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )

    with TestClient(app) as client:
        response = client.get("/snapshot")

    assert response.status_code == 401
    assert control_plane.audit_log()
    assert control_plane.audit_log()[-1].allowed is False


def test_control_plane_api_enforces_request_size_limit():
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    security = _test_security(target.name, max_request_bytes=32)
    app = create_control_plane_app(control_plane, security=security)
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    with TestClient(app) as client:
        response = client.post(
            "/operations/provisioning",
            json={"operations": [], "diagnostics": [], "padding": "x" * 100},
            headers=headers,
        )

    assert response.status_code == 413


def test_control_plane_api_rejects_invalid_content_length_header():
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
        "content-type": "application/json",
        "content-length": "not-a-number",
    }

    with TestClient(app) as client:
        response = client.post(
            "/operations/provisioning",
            content=b'{"operations":[],"diagnostics":[]}',
            headers=headers,
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid content-length"}
    assert control_plane.audit_log()[-1].reason == "invalid content-length"


def test_control_plane_api_enforces_request_size_limit_without_content_length():
    """A chunked body (no content-length) must still be rejected with 413."""
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    security = _test_security(target.name, max_request_bytes=32)
    app = create_control_plane_app(control_plane, security=security)
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
        "content-type": "application/json",
    }

    def _chunked_body():
        for _ in range(100):
            yield b"x" * 32

    with TestClient(app) as client:
        response = client.post(
            "/operations/provisioning",
            content=_chunked_body(),
            headers=headers,
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "request too large"}
    assert control_plane.audit_log()[-1].reason == "request too large"


def test_control_plane_api_rejects_invalid_bearer_token_instead_of_trusting_headers():
    """An unresolvable bearer token must fail closed, not fall through to header identity."""
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )

    with TestClient(app) as client:
        response = client.get(
            "/snapshot",
            headers={
                "authorization": "Bearer revoked-token",
                "x-raes-client-verified": "true",
                "x-raes-client-identity": "backend-service",
            },
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid bearer token"}
    assert control_plane.audit_log()[-1].reason == "invalid bearer token"
    assert control_plane.audit_log()[-1].allowed is False


def test_control_plane_auth_rejects_non_ascii_bearer_token_as_unauthorized():
    """A non-ASCII token must be reported unauthorized, not crash the comparison.

    Starlette decodes header bytes as latin-1, so a raw request can deliver a
    non-ASCII token string even though HTTP clients refuse to encode one. A
    ``str``-based constant-time comparison would raise ``TypeError`` there and
    surface as a 500 instead of a 401.
    """
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    auth = _ControlPlaneApiAuth(control_plane, _test_security(target.name))
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/snapshot",
            "headers": [(b"authorization", "Bearer token-\xf6\xe9".encode("latin-1"))],
            "query_string": b"",
        },
    )

    with pytest.raises(HTTPException) as excinfo:
        auth.read_identity(request)

    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "invalid bearer token"


def test_control_plane_api_rejects_bearer_token_bound_to_another_target():
    """A bearer token scoped to a different target must not authenticate here.

    The header-identity path already enforces this binding; the bearer path must
    apply the same check rather than returning the identity unconditionally.
    """
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    security = ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=False,
        bearer_tokens={
            "other-target-token": ControlPlaneIdentity(
                identity="operator",
                roles=frozenset({ControlPlaneRole.OPERATOR}),
                target_name="some-other-target",
            ),
        },
    )
    app = create_control_plane_app(control_plane, security=security)

    with TestClient(app) as client:
        response = client.get(
            "/snapshot",
            headers={"authorization": "Bearer other-target-token"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "identity is not authorized for this target"}


@pytest.mark.parametrize("authentication_path", ["bearer", "verified-proxy"])
def test_control_plane_api_rejects_identity_without_target_binding(authentication_path: str) -> None:
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    identity = ControlPlaneIdentity(
        identity="unbound-auditor",
        roles=frozenset({ControlPlaneRole.AUDITOR}),
    )
    if authentication_path == "bearer":
        security = ControlPlaneSecurityConfig(bearer_tokens={"unbound-token": identity})
        headers = {"authorization": "Bearer unbound-token"}
    else:
        security = ControlPlaneSecurityConfig(
            trust_proxy_identity_headers=True,
            trusted_identities={"unbound-auditor": identity},
        )
        headers = {
            "x-raes-client-verified": "true",
            "x-raes-client-identity": "unbound-auditor",
        }
    app = create_control_plane_app(control_plane, security=security)

    with TestClient(app) as client:
        response = client.get("/snapshot", headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "identity is not authorized for this target"}


def test_control_plane_security_config_mappings_cannot_be_mutated_after_construction():
    """``strict_defaults`` must stay fail-closed; frozen=True alone does not stop dict mutation."""
    security = ControlPlaneSecurityConfig.strict_defaults()
    intruder = ControlPlaneIdentity(identity="intruder", roles=frozenset({ControlPlaneRole.OPERATOR}))

    with pytest.raises(TypeError):
        security.bearer_tokens["stolen"] = intruder  # type: ignore[index]
    with pytest.raises(TypeError):
        security.trusted_identities["stolen"] = intruder  # type: ignore[index]

    assert security.bearer_tokens == {}
    assert security.trusted_identities == {}


def test_request_size_guard_stops_reading_an_oversized_chunked_body():
    """The ASGI guard must stop after the first chunk that crosses the cap."""
    target = create_stub_target()
    control_plane = RuntimeControlPlane(target)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name, max_request_bytes=64),
    )
    chunk = b"x" * 32
    total_chunks = 1000
    delivered = 0

    async def receive() -> dict[str, object]:
        nonlocal delivered
        if delivered >= total_chunks:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered += 1
        return {"type": "http.request", "body": chunk, "more_body": True}

    sent: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/operations/provisioning",
        "raw_path": b"/operations/provisioning",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }

    _run(app(scope, receive, send))

    assert any(message.get("status") == 413 for message in sent)
    assert delivered <= 3


def test_local_control_plane_store_commits_snapshot_to_wal_database(tmp_path: Path):
    store_path = tmp_path / "cp-store"
    store = LocalControlPlaneStore(store_path)
    store.save_snapshot(RuntimeSnapshot())

    with closing(sqlite3.connect(store_path / "control-plane.sqlite3")) as connection, connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
        state_count = connection.execute("SELECT COUNT(*) FROM state").fetchone()
        integrity = connection.execute("PRAGMA quick_check").fetchone()

    assert journal_mode == ("wal",)
    assert state_count == (1,)
    assert integrity == ("ok",)


def test_local_control_plane_store_rolls_back_snapshot_transaction_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    store = LocalControlPlaneStore(tmp_path / "cp-store")
    real_upsert = store._upsert_snapshot

    def fail_upsert(connection: sqlite3.Connection, snapshot: RuntimeSnapshot) -> None:
        real_upsert(connection, snapshot)
        raise OSError("commit failed")

    monkeypatch.setattr(store, "_upsert_snapshot", fail_upsert)
    snapshot = RuntimeSnapshot()

    with pytest.raises(OSError, match="commit failed"):
        store.save_snapshot(snapshot)

    assert store.load_snapshot() == RuntimeSnapshot()


def test_local_control_plane_store_preserves_concurrent_operation_writes(tmp_path: Path) -> None:
    store_path = tmp_path / "cp-store"
    stores = (LocalControlPlaneStore(store_path), LocalControlPlaneStore(store_path))
    records = [
        replace(
            _participant_operation_record(
                f"operation-{index}",
                f"participant.behavior.subject-{index}",
            ),
            idempotency_key=f"key-{index}",
            request_fingerprint=f"fingerprint-{index}",
        )
        for index in range(32)
    ]

    def save(index: int) -> None:
        stores[index % len(stores)].save_record(records[index])

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save, range(len(records))))

    assert set(LocalControlPlaneStore(store_path).load_records()) == {record.receipt.operation_id for record in records}


def test_local_control_plane_store_preserves_cross_process_operation_writes(tmp_path: Path) -> None:
    store_path = tmp_path / "cp-store"
    LocalControlPlaneStore(store_path)
    context = get_context("spawn")
    barrier = context.Barrier(4)
    processes = [
        context.Process(
            target=_save_operation_in_process,
            args=(str(store_path), index, barrier),
        )
        for index in range(4)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=_CROSS_PROCESS_JOIN_TIMEOUT_SECONDS)
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)

    assert [process.exitcode for process in processes] == [0, 0, 0, 0]
    assert set(LocalControlPlaneStore(store_path).load_records()) == {
        f"process-operation-{index}" for index in range(4)
    }


def test_local_control_plane_store_claims_idempotency_key_once_across_instances(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "cp-store"
    stores = (LocalControlPlaneStore(store_path), LocalControlPlaneStore(store_path))
    records = tuple(
        replace(
            _participant_operation_record(
                f"operation-{index}",
                f"participant.behavior.subject-{index}",
            ),
            idempotency_key="shared-key",
            request_fingerprint="same-request",
        )
        for index in range(2)
    )
    barrier = ThreadBarrier(2)

    def claim(index: int) -> ControlPlaneOperationRecord:
        barrier.wait()
        return stores[index].claim_record(records[index])

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(executor.map(claim, range(2)))

    assert len({record.receipt.operation_id for record in claimed}) == 1
    assert len(LocalControlPlaneStore(store_path).load_records()) == 1


def test_control_plane_api_cancels_workflow_runs():
    scenario = _scenario("""
name: workflow
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  validate:
    entity: blue
    success: {assertions: [health]}
workflows:
  response:
    start: run
    steps:
      run:
        type: objective
        objective: validate
        on_success: finish
      finish: {type: end}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane = RuntimeControlPlane(target)
    _admit_workflow_prerequisites(control_plane, execution_plan)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    with TestClient(app) as client:
        client.post(
            "/operations/orchestration",
            json={
                "operations": [
                    {
                        "action": op.action.value,
                        "address": op.address,
                        "resource_type": op.resource_type,
                        "payload": op.payload,
                        "ordering_dependencies": list(op.ordering_dependencies),
                        "refresh_dependencies": list(op.refresh_dependencies),
                    }
                    for op in execution_plan.orchestration.operations
                ],
                "startup_order": execution_plan.orchestration.startup_order,
                "diagnostics": [],
            },
            headers=headers,
        )
        cancel = client.post(
            "/workflows/orchestration.workflow.response/cancel",
            json={"reason": "operator requested stop"},
            headers=headers,
        )
        snapshot = client.get("/snapshot", headers=headers).json()

    assert cancel.status_code == 200
    result = snapshot["orchestration_results"]["orchestration.workflow.response"]
    assert result["workflow_status"] == "cancelled"
    assert result["terminal_reason"] == "operator requested stop"


def test_control_plane_api_reconciles_workflow_timeouts():
    scenario = _scenario("""
name: workflow
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  validate:
    entity: blue
    success: {assertions: [health]}
workflows:
  response:
    start: run
    timeout: 1
    steps:
      run:
        type: objective
        objective: validate
        on_success: finish
      finish: {type: end}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane = RuntimeControlPlane(target)
    _admit_workflow_prerequisites(control_plane, execution_plan)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    with TestClient(app) as client:
        client.post(
            "/operations/orchestration",
            json={
                "operations": [
                    {
                        "action": op.action.value,
                        "address": op.address,
                        "resource_type": op.resource_type,
                        "payload": op.payload,
                        "ordering_dependencies": list(op.ordering_dependencies),
                        "refresh_dependencies": list(op.refresh_dependencies),
                    }
                    for op in execution_plan.orchestration.operations
                ],
                "startup_order": execution_plan.orchestration.startup_order,
                "diagnostics": [],
            },
            headers=headers,
        )
        workflow_address = "orchestration.workflow.response"
        seeded = dict(control_plane._snapshot.orchestration_results[workflow_address])
        seeded["started_at"] = "2000-01-01T00:00:00Z"
        seeded["updated_at"] = "2000-01-01T00:00:01Z"
        control_plane._snapshot = control_plane._snapshot.with_entries(
            dict(control_plane._snapshot.entries),
            orchestration_results={
                **control_plane._snapshot.orchestration_results,
                workflow_address: seeded,
            },
        )
        reconcile = client.post(
            "/workflows/reconcile-timeouts",
            headers=headers,
        )
        assert reconcile.status_code == 200
        snapshot = client.get("/snapshot", headers=headers).json()

    result = snapshot["orchestration_results"]["orchestration.workflow.response"]
    assert result["workflow_status"] == "timed_out"
    assert result["terminal_reason"] == "workflow timed out"


def test_control_plane_api_cancellation_triggers_compensation_history():
    scenario = _scenario("""
name: workflow
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  validate:
    entity: blue
    success: {assertions: [health]}
workflows:
  rollback:
    start: finish
    steps:
      finish: {type: end}
  response:
    start: run
    compensation:
      mode: automatic
      on: [cancelled]
    steps:
      run:
        type: objective
        objective: validate
        compensate_with: rollback
        on_success: finish
        on_failure: finish
      finish: {type: end}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane = RuntimeControlPlane(target)
    _admit_workflow_prerequisites(control_plane, execution_plan)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    with TestClient(app) as client:
        client.post(
            "/operations/orchestration",
            json={
                "operations": [
                    {
                        "action": op.action.value,
                        "address": op.address,
                        "resource_type": op.resource_type,
                        "payload": op.payload,
                        "ordering_dependencies": list(op.ordering_dependencies),
                        "refresh_dependencies": list(op.refresh_dependencies),
                    }
                    for op in execution_plan.orchestration.operations
                ],
                "startup_order": execution_plan.orchestration.startup_order,
                "diagnostics": [],
            },
            headers=headers,
        )
        workflow_address = "orchestration.workflow.response"
        seeded = dict(control_plane._snapshot.orchestration_results[workflow_address])
        seeded["steps"] = {
            **seeded["steps"],
            "run": {"lifecycle": "completed", "outcome": "succeeded", "attempts": 1},
        }
        control_plane._snapshot = control_plane._snapshot.with_entries(
            dict(control_plane._snapshot.entries),
            orchestration_results={
                **control_plane._snapshot.orchestration_results,
                workflow_address: seeded,
            },
            orchestration_history={
                **control_plane._snapshot.orchestration_history,
                workflow_address: [
                    *control_plane._snapshot.orchestration_history[workflow_address],
                    {
                        "event_type": "step_completed",
                        "timestamp": seeded["updated_at"],
                        "step_name": "run",
                        "branch_name": None,
                        "join_step": None,
                        "outcome": "succeeded",
                        "details": {},
                    },
                ],
            },
        )
        cancel = client.post(
            "/workflows/orchestration.workflow.response/cancel",
            json={"reason": "operator requested stop"},
            headers=headers,
        )
        snapshot = client.get("/snapshot", headers=headers).json()

    assert cancel.status_code == 200
    result = snapshot["orchestration_results"]["orchestration.workflow.response"]
    history = snapshot["orchestration_history"]["orchestration.workflow.response"]
    assert result["workflow_status"] == "cancelled"
    assert result["compensation_status"] == "succeeded"
    assert any(event["event_type"] == "compensation_started" for event in history)
    assert any(
        event["event_type"] == "compensation_workflow_completed"
        and event["details"].get("workflow_address") == "orchestration.workflow.rollback"
        for event in history
    )


def test_control_plane_api_timeout_triggers_compensation_history():
    scenario = _scenario("""
name: workflow
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  validate:
    entity: blue
    success: {assertions: [health]}
workflows:
  rollback:
    start: finish
    steps:
      finish: {type: end}
  response:
    start: run
    timeout: 1
    compensation:
      mode: automatic
      on: [timed_out]
    steps:
      run:
        type: objective
        objective: validate
        compensate_with: rollback
        on_success: finish
        on_failure: finish
      finish: {type: end}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane = RuntimeControlPlane(target)
    _admit_workflow_prerequisites(control_plane, execution_plan)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
    }

    with TestClient(app) as client:
        client.post(
            "/operations/orchestration",
            json={
                "operations": [
                    {
                        "action": op.action.value,
                        "address": op.address,
                        "resource_type": op.resource_type,
                        "payload": op.payload,
                        "ordering_dependencies": list(op.ordering_dependencies),
                        "refresh_dependencies": list(op.refresh_dependencies),
                    }
                    for op in execution_plan.orchestration.operations
                ],
                "startup_order": execution_plan.orchestration.startup_order,
                "diagnostics": [],
            },
            headers=headers,
        )
        workflow_address = "orchestration.workflow.response"
        seeded = dict(control_plane._snapshot.orchestration_results[workflow_address])
        seeded["started_at"] = "2000-01-01T00:00:00Z"
        seeded["updated_at"] = "2000-01-01T00:00:01Z"
        seeded["steps"] = {
            **seeded["steps"],
            "run": {"lifecycle": "completed", "outcome": "succeeded", "attempts": 1},
        }
        control_plane._snapshot = control_plane._snapshot.with_entries(
            dict(control_plane._snapshot.entries),
            orchestration_results={
                **control_plane._snapshot.orchestration_results,
                workflow_address: seeded,
            },
            orchestration_history={
                **control_plane._snapshot.orchestration_history,
                workflow_address: [
                    *control_plane._snapshot.orchestration_history[workflow_address],
                    {
                        "event_type": "step_completed",
                        "timestamp": "2000-01-01T00:00:01Z",
                        "step_name": "run",
                        "branch_name": None,
                        "join_step": None,
                        "outcome": "succeeded",
                        "details": {},
                    },
                ],
            },
        )
        client.post("/workflows/reconcile-timeouts", headers=headers)
        snapshot = client.get("/snapshot", headers=headers).json()

    result = snapshot["orchestration_results"]["orchestration.workflow.response"]
    history = snapshot["orchestration_history"]["orchestration.workflow.response"]
    assert result["workflow_status"] == "timed_out"
    assert result["compensation_status"] == "succeeded"
    assert any(event["event_type"] == "compensation_completed" for event in history)


class TestParticipantEpisodeHttpRoutes:
    """RUN-311 — HTTP surface for participant episode lifecycle control.

    Each POST route must drive the same state-machine transitions as the
    in-process control plane and the resulting ``/snapshot`` response
    must expose the mutated ``participant_episode_results`` /
    ``participant_episode_history`` fields in the RuntimeSnapshot envelope.
    """

    def _build_client(self):
        target = create_stub_target()
        control_plane = RuntimeControlPlane(target)
        app = create_control_plane_app(
            control_plane,
            security=_test_security(target.name),
        )
        return TestClient(app)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "x-raes-client-verified": "true",
            "x-raes-client-identity": "backend-service",
        }

    def test_initialize_route_creates_first_episode(self):
        client = self._build_client()

        response = client.post(
            "/participants/participant.alice/episodes/initialize",
            headers=self._headers,
            json={},
        )
        snapshot = client.get("/snapshot", headers=self._headers).json()

        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] is True
        assert body["domain"] == "participant"
        state = snapshot["participant_episode_results"]["participant.alice"]
        assert state["status"] == "running"
        assert state["sequence_number"] == 0
        history = snapshot["participant_episode_history"]["participant.alice"]
        assert [event["event_type"] for event in history] == [
            "episode_initialized",
            "episode_running",
        ]

    def test_reset_route_allocates_new_episode(self):
        client = self._build_client()
        client.post(
            "/participants/participant.alice/episodes/initialize",
            headers=self._headers,
            json={},
        )

        response = client.post(
            "/participants/participant.alice/episodes/reset",
            headers=self._headers,
            json={"reason": "operator reset"},
        )
        snapshot = client.get("/snapshot", headers=self._headers).json()

        assert response.status_code == 200
        state = snapshot["participant_episode_results"]["participant.alice"]
        assert state["sequence_number"] == 1
        assert state["last_control_action"] == "reset"
        assert state["previous_episode_id"] == "participant.alice-episode-1"

    def test_terminate_route_drives_state_to_terminated(self):
        client = self._build_client()
        client.post(
            "/participants/participant.alice/episodes/initialize",
            headers=self._headers,
            json={},
        )

        response = client.post(
            "/participants/participant.alice/episodes/terminate",
            headers=self._headers,
            json={"terminal_reason": "completed"},
        )
        snapshot = client.get("/snapshot", headers=self._headers).json()

        assert response.status_code == 200
        state = snapshot["participant_episode_results"]["participant.alice"]
        assert state["status"] == "terminated"
        assert state["terminal_reason"] == "completed"
        history = snapshot["participant_episode_history"]["participant.alice"]
        assert history[-1]["event_type"] == "episode_completed"

    def test_terminate_route_rejects_invalid_terminal_reason(self):
        client = self._build_client()
        client.post(
            "/participants/participant.alice/episodes/initialize",
            headers=self._headers,
            json={},
        )

        response = client.post(
            "/participants/participant.alice/episodes/terminate",
            headers=self._headers,
            json={"terminal_reason": "exploded"},
        )

        assert response.status_code == 400
        assert "invalid terminal_reason" in response.json()["detail"]

    def test_restart_route_resumes_after_termination(self):
        client = self._build_client()
        client.post(
            "/participants/participant.alice/episodes/initialize",
            headers=self._headers,
            json={},
        )
        client.post(
            "/participants/participant.alice/episodes/terminate",
            headers=self._headers,
            json={"terminal_reason": "completed"},
        )

        response = client.post(
            "/participants/participant.alice/episodes/restart",
            headers=self._headers,
            json={},
        )
        snapshot = client.get("/snapshot", headers=self._headers).json()

        assert response.status_code == 200
        state = snapshot["participant_episode_results"]["participant.alice"]
        assert state["sequence_number"] == 1
        assert state["status"] == "running"
        assert state["last_control_action"] == "restart"

    def test_routes_require_authenticated_identity(self):
        client = self._build_client()

        response = client.post(
            "/participants/participant.alice/episodes/initialize",
            json={},
        )
        assert response.status_code == 401

    def test_retrieval_routes_require_authenticated_identity(self):
        client = self._build_client()

        status = client.get("/participants/participant.alice/status")
        history = client.get(
            "/participants/participant.alice/episodes/participant.alice-episode-1/history",
        )
        context = client.get(
            "/participants/participant.alice/context",
            params={"view_ref": "views.context.network-posture.v1"},
        )

        assert status.status_code == 401
        assert history.status_code == 401
        assert context.status_code == 401

    def test_routes_reject_unknown_body_fields(self):
        """Closed-world request bodies — unknown fields must be rejected."""
        client = self._build_client()

        response = client.post(
            "/participants/participant.alice/episodes/initialize",
            headers=self._headers,
            json={"episode_id": "alice-1", "unknown": "value"},
        )
        assert response.status_code == 422

    def test_status_route_returns_api_408_status_view(self):
        client = self._build_client()
        client.post(
            "/participants/participant.alice/episodes/initialize",
            headers=self._headers,
            json={},
        )

        response = client.get(
            "/participants/participant.alice/status",
            headers=self._headers,
        )

        assert response.status_code == 200
        view = ParticipantStatusViewModel.model_validate(response.json())
        assert view.participant_address == "participant.alice"
        assert view.episode_id == "participant.alice-episode-1"
        assert view.episode_state is not None
        assert view.episode_state.status == "running"

    def test_status_route_scopes_open_operations_to_participant(self):
        target = create_stub_target()
        control_plane = RuntimeControlPlane(target)
        control_plane.initialize_participant_episode("participant.alice")
        control_plane.initialize_participant_episode("participant.bob")
        control_plane._operations = {
            "op-alice": _participant_operation_record("op-alice", "participant.alice"),
            "op-bob": _participant_operation_record("op-bob", "participant.bob"),
        }
        client = TestClient(
            create_control_plane_app(
                control_plane,
                security=_test_security(target.name),
            )
        )

        response = client.get(
            "/participants/participant.alice/status",
            headers=self._headers,
        )

        assert response.status_code == 200
        view = ParticipantStatusViewModel.model_validate(response.json())
        assert view.open_operation_refs == ["op-alice"]

    def test_history_route_returns_api_408_history_view(self):
        client = self._build_client()
        client.post(
            "/participants/participant.alice/episodes/initialize",
            headers=self._headers,
            json={},
        )

        response = client.get(
            "/participants/participant.alice/episodes/participant.alice-episode-1/history",
            headers=self._headers,
        )

        assert response.status_code == 200
        view = ParticipantHistoryViewModel.model_validate(response.json())
        assert view.participant_address == "participant.alice"
        assert view.episode_id == "participant.alice-episode-1"
        assert [event.event_type for event in view.episode_history] == [
            "episode_initialized",
            "episode_running",
        ]
        assert view.completeness == "complete"

    def test_context_route_returns_api_408_sem214_view(self):
        client = self._build_client()
        client.post(
            "/participants/participant.alice/episodes/initialize",
            headers=self._headers,
            json={},
        )

        response = client.get(
            "/participants/participant.alice/context",
            params={
                "view_ref": "views.context.network-posture.v1",
                "episode_id": "participant.alice-episode-1",
                "payload_ref": "evidence.context.alice.network-posture",
                "meaning_ref": "attacker.override",
                "audience_scope": "audience_neutral",
                "observation_point": "future-state",
                "comparability_class": "backend_specific_non_comparable",
                "backend_disclosure_ref": "attacker.disclosure",
            },
            headers=self._headers,
        )

        assert response.status_code == 200
        view = ParticipantContextViewModel.model_validate(response.json())
        assert view.participant_address == "participant.alice"
        assert view.view_ref == "views.context.network-posture.v1"
        assert view.derived_from_refs == ["runtime.snapshot.current"]
        assert view.meaning_ref == "views.context.network-posture.v1"
        assert view.participant_scope == "participant_local"
        assert view.audience_scope == "participant_visible"
        assert view.observation_point == "participant.alice-episode-1"
        assert view.source_layers[0].source_layer == "source_snapshot"
        assert view.source_layers[0].evidence_refs == ["runtime.snapshot.current"]
        assert view.transformation.transformation_rule_ref == "views.context.network-posture.v1"
        assert view.comparability.comparability_class == "portable_equivalent"
        assert view.comparability.backend_disclosure_refs == []
        assert view.payload_ref == "evidence.context.alice.network-posture"

    def test_retrieval_routes_return_404_for_unknown_participants(self):
        client = self._build_client()

        status = client.get("/participants/participant.unknown/status", headers=self._headers)
        history = client.get(
            "/participants/participant.unknown/episodes/episode-1/history",
            headers=self._headers,
        )
        context = client.get(
            "/participants/participant.unknown/context",
            params={"view_ref": "views.context.network-posture.v1"},
            headers=self._headers,
        )

        assert status.status_code == 404
        assert history.status_code == 404
        assert context.status_code == 404
