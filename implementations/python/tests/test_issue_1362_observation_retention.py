"""Automatic history remains bounded without consuming operator recovery slots."""

from datetime import UTC, datetime

import pytest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    BackendOperationControlModel,
    backend_operation_control_digest,
    backend_operation_request_digest,
)
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_snapshots import _snapshot_payload
from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration
from test_issue_1362_distributed_authority import Dispatcher, worker
from test_issue_1362_provider_execution import Evidence, Provider, target
from test_issue_1362_runtime_supervision import supervisor

AUTOMATIC_LIMIT = 128


def absence_provider(provider, plane):
    def reconcile(control):
        return provider.report(
            provider.request,
            {
                "kind": "reconciliation",
                "control_id": control.control_id,
                "control_digest": backend_operation_control_digest(control),
                "effects": {
                    "effect": "absent",
                    "cessation_established": True,
                    "evidence_refs": [
                        {
                            "contract_id": "runtime-snapshot-v1",
                            "artifact_id": "scoped-witness",
                            "digest": canonical_json_digest(_snapshot_payload(plane._snapshot)),
                        }
                    ],
                },
            },
        )

    provider.reconcile_operation = reconcile


def test_local_automatic_poll_limit_preserves_cancel_reconciliation_and_later_admission(monkeypatch):
    provider = Provider()
    provider.observe_operation = lambda control: provider.report(
        provider.request, {"kind": "progress", "phase": "executing"}
    )
    plane = RuntimeControlPlane(
        target(provider),
        operation_evidence=Evidence(),
        supervision=OperationSupervisionConfiguration(execution_ms=600000),
    )
    pauses = []
    monkeypatch.setattr(plane._execution_adapter, "pause", lambda duration: pauses.append(duration))
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is OperationState.INDETERMINATE
        assert len(record.invocation.controls) == AUTOMATIC_LIMIT
        assert len(record.invocation.delivered_controls) == AUTOMATIC_LIMIT
        assert len(set(record.invocation.delivered_controls)) == AUTOMATIC_LIMIT
        assert min(pauses) >= 600000 // AUTOMATIC_LIMIT
        plane.cancel_operation(receipt.operation_id, control_id="cancel-after-polls", identity=supervisor())
        assert provider.cancels == 1
        assert (
            plane.get_control_response(
                receipt.operation_id, "cancel-after-polls", identity=supervisor()
            ).message.disposition
            == "accepted"
        )
        absence_provider(provider, plane)
        plane.supervise_operation(
            receipt.operation_id, action="reconcile", control_id="recover-after-polls", identity=supervisor()
        )
        child = plane.resolve_backend_absence(
            receipt.operation_id, "recover-after-polls", idempotency_key="verified-after-polls", identity=supervisor()
        )
        assert plane.get_operation(child.operation_id).state is OperationState.SUCCEEDED
        assert plane.get_operation(receipt.operation_id).state is OperationState.INDETERMINATE
        provider.observe_operation = Provider.observe_operation.__get__(provider)
        assert plane.submit_provisioning(ProvisioningPlan()).accepted
    finally:
        plane.close()


@pytest.mark.timeout(240)
def test_worker_observation_limit_retains_operator_recovery_after_reopen(tmp_path):
    provider, dispatcher = Provider(), Dispatcher()
    configured = target(provider)
    # This exercises retained capacity, not the default latency bound. Each
    # control still uses a finite, nonrenewable budget under loaded CI runners.
    supervision = OperationSupervisionConfiguration(
        execution_ms=600000, admission_ms=10000, observation_ms=10000, commit_ms=10000, drain_ms=10000
    )
    plane = RuntimeControlPlane(
        configured,
        store=LocalControlPlaneStore(tmp_path / "ledger"),
        distributed_execution=dispatcher,
        operation_evidence=Evidence(),
        supervision=supervision,
    )
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        request = dispatcher.commands[0]
        plane.claim_backend_invocation(
            request.binding, provider.operation_capabilities(), provider.check_operation(request), identity=worker()
        )
        plane.publish_backend_response(provider.start_operation(request), identity=worker())

        def observer(index):
            return BackendOperationControlModel(
                binding=request.binding,
                request_digest=backend_operation_request_digest(request),
                control_id=f"poll-{index}",
                actor_id=worker().identity,
                authorization_scope=("role:backend",),
                action="observe",
                budget={
                    "origin_id": f"poll-clock-{index}",
                    "started_at": datetime.now(UTC).isoformat(),
                    "limit_ms": 10000,
                    "remaining_ms": 10000,
                },
            )

        for index in range(AUTOMATIC_LIMIT):
            grant = plane.record_worker_observation(observer(index), identity=worker())
            plane.publish_backend_response(
                provider.report(request, {"kind": "progress", "phase": "executing"}), identity=worker()
            )
            assert grant.control.control_id == f"poll-{index}"
        with pytest.raises(ValueError):
            plane.record_worker_observation(observer(AUTOMATIC_LIMIT), identity=worker())
        plane.mark_backend_indeterminate(request.binding, identity=worker())
        retained = plane._store.load_records()[receipt.operation_id].invocation
        plane.close()
        plane = RuntimeControlPlane(
            configured,
            store=LocalControlPlaneStore(tmp_path / "ledger"),
            distributed_execution=Dispatcher(),
            operation_evidence=Evidence(),
            supervision=supervision,
        )
        assert plane._store.load_records()[receipt.operation_id].invocation == retained
        cancel = plane.cancel_operation(receipt.operation_id, control_id="cancel-reopened", identity=supervisor())
        grant = plane.claim_worker_control(receipt.operation_id, cancel.control_id, identity=worker())
        disposition = provider.cancel_operation(grant.control)
        plane.publish_backend_response(disposition, identity=worker())
        after_cancel = plane._store.load_records()[receipt.operation_id].invocation
        plane.publish_backend_response(disposition, identity=worker())
        assert plane._store.load_records()[receipt.operation_id].invocation == after_cancel
        absence_provider(provider, plane)
        reconcile = plane.supervise_operation(
            receipt.operation_id, action="reconcile", control_id="reconcile-reopened", identity=supervisor()
        )
        grant = plane.claim_worker_control(receipt.operation_id, reconcile.control_id, identity=worker())
        plane.publish_backend_response(provider.reconcile_operation(grant.control), identity=worker())
        child = plane.resolve_backend_absence(
            receipt.operation_id, reconcile.control_id, idempotency_key="verified-reopened", identity=supervisor()
        )
        assert plane.get_operation(child.operation_id).state is OperationState.SUCCEEDED
        assert plane.submit_provisioning(ProvisioningPlan()).accepted
    finally:
        plane.close()


def test_ordinary_response_limit_preserves_recovery_dispositions_and_terminal_outcome():
    from raes_runtime.operation_invocation_ledger import InvocationLedger
    from test_issue_1360_backend_operations import control, outcome, request, response

    operation = request()
    cancel, reconcile = control(), control("reconcile").model_copy(update={"control_id": "recovery"})
    responses = (
        response({"kind": "acknowledgement", "disposition": "accepted"}, sequence=1),
        *(response({"kind": "progress", "phase": "executing"}, sequence=index) for index in range(2, 769)),
    )
    ledger = InvocationLedger(
        request=operation,
        consumed=True,
        responses=responses,
        controls=(cancel, reconcile),
        delivered_controls=(cancel.control_id, reconcile.control_id),
    )
    with pytest.raises(ValueError, match="ordinary response capacity"):
        InvocationLedger.model_validate(
            ledger.model_copy(
                update={"responses": (*responses, response({"kind": "progress", "phase": "executing"}, sequence=769))}
            ).model_dump(mode="json")
        )
    disposition = response(
        {
            "kind": "control",
            "control_id": cancel.control_id,
            "control_digest": backend_operation_control_digest(cancel),
            "disposition": "accepted",
        },
        sequence=769,
    )
    evidence = response(
        {
            "kind": "reconciliation",
            "control_id": reconcile.control_id,
            "control_digest": backend_operation_control_digest(reconcile),
            "effects": {
                "effect": "absent",
                "cessation_established": True,
                "evidence_refs": [
                    {"contract_id": "runtime-snapshot-v1", "artifact_id": "witness", "digest": "sha256:" + "a" * 64}
                ],
            },
        },
        sequence=770,
    )
    recovered = InvocationLedger.model_validate(
        ledger.model_copy(update={"responses": (*responses, disposition, evidence)}).model_dump(mode="json")
    )
    assert recovered.responses[-2:] == (disposition, evidence)
    repeated_disposition = disposition.model_copy(update={"sequence": 771})
    with pytest.raises(ValueError, match="control response identity"):
        InvocationLedger.model_validate(
            recovered.model_copy(update={"responses": (*recovered.responses, repeated_disposition)}).model_dump(
                mode="json"
            )
        )
    terminal = response(outcome(), sequence=771)
    assert (
        InvocationLedger.model_validate(
            recovered.model_copy(update={"responses": (*recovered.responses, terminal)}).model_dump(mode="json")
        ).responses[-1]
        == terminal
    )


def test_manual_observation_cannot_consume_cancellation_or_reconciliation_slots():
    from raes_runtime.operation_invocation_ledger import InvocationLedger
    from raes_runtime.operation_transcript_policy import append_control
    from test_issue_1360_backend_operations import control, request

    ledger = InvocationLedger(request=request())
    for index in range(64):
        ledger = append_control(ledger, control("observe").model_copy(update={"control_id": f"manual-{index}"}))
    with pytest.raises(ValueError):
        append_control(ledger, control("observe").model_copy(update={"control_id": "overflow"}))
    for action in ("cancel", "reconcile"):
        for index in range(32):
            ledger = append_control(ledger, control(action).model_copy(update={"control_id": f"{action}-{index}"}))
    assert len(ledger.controls) == 128


def test_retained_authority_cannot_be_reclassified_or_discarded_to_free_capacity():
    from raes_runtime.operation_invocation_ledger import InvocationLedger, require_invocation_transition
    from raes_runtime.operation_transcript_policy import append_control
    from test_issue_1360_backend_operations import control, request

    retained = append_control(InvocationLedger(request=request()), control("observe"))
    with pytest.raises(ValueError, match="reclassified"):
        require_invocation_transition(retained, retained.model_copy(update={"automatic_controls": ("control-1",)}))
    with pytest.raises(ValueError, match="append-only"):
        require_invocation_transition(retained, retained.model_copy(update={"controls": ()}))


def test_temporal_polling_cadence_fits_a_long_admitted_execution(monkeypatch):
    import asyncio
    from datetime import timedelta

    from raes_runtime.operation_temporal import EngineOperationReference
    from raes_runtime.operation_temporal_workflow import RaeOperationWorkflow
    from temporalio import workflow
    from test_issue_1360_backend_operations import request

    operation = request()
    clock, sleeps, observations = [datetime.now(UTC)], [], []

    async def activity(name, *args, **kwargs):
        if name == "raes.observe":
            observations.append(name)
            return "succeeded" if len(observations) == AUTOMATIC_LIMIT else "running"
        assert name == "raes.invoke"
        return "running"

    async def sleep(duration):
        sleeps.append(duration)
        clock[0] += timedelta(seconds=duration)

    monkeypatch.setattr(workflow, "now", lambda: clock[0])
    monkeypatch.setattr(workflow, "execute_activity", activity)
    monkeypatch.setattr(workflow, "sleep", sleep)
    reference = EngineOperationReference(
        operation_id=operation.binding.operation_id,
        invocation_id=operation.binding.invocation_id,
        deployment_id=operation.binding.deployment_id,
        owner_generation=operation.binding.owner_generation,
        execution_generation=operation.binding.execution_generation,
        worker_id=operation.binding.worker_id,
        request_digest=backend_operation_request_digest(operation),
        effect_queue="effect",
        control_queue="control",
        execution_budget_ms=600000,
        control_budget_ms=2000,
    )
    assert asyncio.run(RaeOperationWorkflow().run(reference.model_dump(mode="json"))) == "succeeded"
    assert len(observations) == AUTOMATIC_LIMIT
    assert min(sleeps) >= 600000 / AUTOMATIC_LIMIT / 1000
