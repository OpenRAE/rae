"""In-process trial handoff preserves admission and cleanup boundaries."""

import json
from dataclasses import replace

import pytest
from paths import REPO_ROOT
from raes_backend_protocols import BackendTrialUnit
from raes_contracts.contracts import (
    CleanupObligationResultModel,
    EvaluationPlanModel,
    ExperimentEvidenceRecordModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
    TrialCleanupReceiptModel,
)
from raes_contracts.operation_lifecycle import OperationAdmissionContext, OperationKind
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import OperationReceipt, RuntimeSnapshot
from raes_contracts.trial_unit import TrialUnitRequest, TrialUnitResult, validate_trial_unit_result
from raes_processor.trial_compiler import compile_admitted_trial_plan
from test_issue_1626_trial_participant_bindings import _participant_request


def _request():
    compiled = compile_admitted_trial_plan(_participant_request())
    assert compiled.plan is not None, compiled.diagnostics
    entry = next(iter(compiled.plan.entries.values()))
    return TrialUnitRequest(
        plan=compiled.plan,
        plan_entry_id=entry.plan_entry_id,
        execution_attempt_id="attempt-1",
        instantiated_sdl_digest="sha256:" + "a" * 64,
        provisioning_plan=ProvisioningPlanModel(
            realization_authority=[], run_id=entry.run_id, instantiation_id=entry.plan_entry_id
        ),
        orchestration_plan=OrchestrationPlanModel(),
        evaluation_plan=EvaluationPlanModel(run_id=entry.run_id, instantiation_id=entry.plan_entry_id),
    )


def test_request_carries_sealed_configuration_controls_and_cleanup_without_recomputation():
    request = _request()
    entry = request.plan.entries[request.plan_entry_id]
    assert request.run_id == entry.run_id
    assert request.participant_configurations == tuple(entry.participant_configurations)
    assert request.participant_configurations
    assert request.execution_controls == entry.execution_controls
    assert request.cleanup_plan == request.plan.cleanup_plans[entry.execution_controls.cleanup_plan_ref]
    detached = replace(request)
    request.plan.entries[request.plan_entry_id].participant_configurations.clear()
    assert detached.participant_configurations


@pytest.mark.parametrize("change", ["unknown-entry", "attempt-is-run", "wrong-run", "inspection", "nested-tamper"])
def test_request_rejects_invalid_entry_and_projection_handoffs(change):
    request = _request()
    if change == "unknown-entry":
        changed = {"plan_entry_id": "other-entry"}
    elif change == "attempt-is-run":
        changed = {"execution_attempt_id": request.run_id}
    elif change == "wrong-run":
        changed = {"evaluation_plan": request.evaluation_plan.model_copy(update={"run_id": "other-run"})}
    elif change == "inspection":
        changed = {"provisioning_plan": request.provisioning_plan.model_copy(update={"purpose": "inspection"})}
    else:
        entry = request.plan.entries[request.plan_entry_id]
        controls = entry.execution_controls.model_copy(update={"attempt_timeout_seconds": True})
        request.plan.entries[request.plan_entry_id] = entry.model_copy(update={"execution_controls": controls})
        changed = {}
    with pytest.raises(ValueError):
        replace(request, **changed)


def _evidence(request, evidence_id="cleanup-evidence"):
    path = REPO_ROOT / "contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/reference.json"
    payload = json.loads(path.read_text())
    payload["run_ref"]["ref_id"] = request.run_id
    payload["evidence_record_id"] = evidence_id
    return ExperimentEvidenceRecordModel.model_validate(payload)


def _result(request, *, cleanup_status="succeeded", trial_outcome="succeeded"):
    evidence = _evidence(request)
    receipt = TrialCleanupReceiptModel(
        receipt_id="cleanup-receipt",
        cleanup_plan_ref=request.cleanup_plan.plan_id,
        plan_entry_id=request.plan_entry_id,
        run_id=request.run_id,
        execution_attempt_id=request.execution_attempt_id,
        trial_outcome=trial_outcome,
        cleanup_status=cleanup_status,
        obligation_results={
            key: CleanupObligationResultModel(
                obligation_id=key,
                status="succeeded" if cleanup_status == "succeeded" else "failed",
                evidence_refs=[evidence.evidence_record_id],
                residual_state_refs=[] if cleanup_status == "succeeded" else ["owned-residual"],
            )
            for key in request.cleanup_plan.cleanup_obligations
        },
    )
    context = OperationAdmissionContext(
        actor_id="operator",
        authorization_scope=("runtime:execute",),
        target_scope="target:trial",
        run_scope=f"run:{request.run_id}",
        operation_kind=OperationKind.PROVISIONING,
        request_commitment="sha256:" + "b" * 64,
    )
    return TrialUnitResult(
        operation_receipts=(
            OperationReceipt("operation-1", RuntimeDomain.PROVISIONING, "2026-10-25T12:00:00Z", True, context),
        ),
        execution_snapshot=RuntimeSnapshot(orchestration_results={"workflow": {"status": "completed"}}),
        evidence=(_evidence(request, "trial-evidence"),),
        cleanup_receipt=receipt,
        cleanup_evidence=(evidence,),
    )


@pytest.mark.parametrize("cleanup_status", ["succeeded", "failed", "unverified"])
def test_protocol_handoff_preserves_trial_observations_and_independent_cleanup(cleanup_status):
    request = _request()
    expected = _result(request, cleanup_status=cleanup_status)

    class Adapter:
        def execute_trial(self, supplied: TrialUnitRequest) -> TrialUnitResult:
            assert supplied.participant_configurations == request.participant_configurations
            return expected

    adapter: BackendTrialUnit = Adapter()
    result = adapter.execute_trial(request)
    validate_trial_unit_result(request, result, target_scope="target:trial")
    assert result.cleanup_receipt.trial_outcome == "succeeded"
    assert result.cleanup_receipt.cleanup_status == cleanup_status
    assert result.execution_snapshot.orchestration_results["workflow"]["status"] == "completed"
    assert result.evidence[0].evidence_record_id == "trial-evidence"
    assert result.cleanup_evidence[0].evidence_record_id == "cleanup-evidence"


@pytest.mark.parametrize(
    "change",
    ["attempt", "cleanup-plan", "missing-obligation", "run-scope", "target-scope", "evidence-run", "missing-evidence"],
)
def test_result_validator_rejects_wrong_joins_and_missing_cleanup_evidence(change):
    request = _request()
    result = _result(request)
    if change in {"attempt", "cleanup-plan", "missing-obligation"}:
        update = {
            "attempt": {"execution_attempt_id": "other-attempt"},
            "cleanup-plan": {"cleanup_plan_ref": "other-cleanup"},
            "missing-obligation": {"obligation_results": {}},
        }[change]
        result = replace(result, cleanup_receipt=result.cleanup_receipt.model_copy(update=update))
    elif change in {"run-scope", "target-scope"}:
        receipt = result.operation_receipts[0]
        key = "run_scope" if change == "run-scope" else "target_scope"
        result = replace(
            result, operation_receipts=(replace(receipt, context=receipt.context.model_copy(update={key: "other"})),)
        )
    elif change == "evidence-run":
        evidence = result.evidence[0]
        result = replace(
            result,
            evidence=(
                evidence.model_copy(update={"run_ref": evidence.run_ref.model_copy(update={"ref_id": "other-run"})}),
            ),
        )
    else:
        result = replace(result, cleanup_evidence=())
    with pytest.raises(ValueError):
        validate_trial_unit_result(request, result, target_scope="target:trial")


def test_result_detaches_execution_snapshot_before_backend_teardown():
    request = _request()
    original = RuntimeSnapshot(orchestration_results={"workflow": {"status": "completed"}})
    result = replace(_result(request), execution_snapshot=original)
    original.orchestration_results.clear()
    assert result.execution_snapshot.orchestration_results
    assert "configuration_digest" not in repr(request)
    assert "policy.temperature" not in repr(request)
    assert "workflow" not in repr(result)
    assert "payload_summary" not in repr(result)


@pytest.mark.parametrize("attempt_id", [True, 1, "", " ", "x" * 257])
def test_request_rejects_non_string_blank_and_unbounded_attempt_identity(attempt_id):
    with pytest.raises(ValueError, match="identity"):
        replace(_request(), execution_attempt_id=attempt_id)


def test_result_rejects_unbounded_evidence_before_copying():
    request = _request()
    with pytest.raises(ValueError, match="bounded|limits"):
        replace(_result(request), evidence=(_evidence(request),) * 4097)


def test_result_validation_reconstructs_nested_models_again():
    request = _request()
    result = _result(request)
    result.cleanup_receipt.obligation_results.clear()
    with pytest.raises(ValueError, match="required cleanup obligation"):
        validate_trial_unit_result(request, result, target_scope="target:trial")


def test_request_accepts_existing_public_realization_outputs():
    from raes_contracts.contracts import ExperimentTaskModel
    from raes_processor.trial_realization import realize_admitted_trial_entry
    from test_sce_002_trial_realization import _TASK_FIXTURE, _plan_and_entry, _realization_inputs

    inputs, plan, entry = _plan_and_entry()
    task = ExperimentTaskModel.model_validate_json(_TASK_FIXTURE.read_text())
    realized = realize_admitted_trial_entry(
        inputs=_realization_inputs(inputs, plan, task), plan_entry_id=entry.plan_entry_id
    )
    request = TrialUnitRequest(
        plan=plan,
        plan_entry_id=entry.plan_entry_id,
        execution_attempt_id="attempt-1",
        instantiated_sdl_digest=realized.snapshot_digest,
        provisioning_plan=realized.provisioning_plan,
        orchestration_plan=realized.orchestration_plan,
        evaluation_plan=realized.evaluation_plan,
    )
    assert request.participant_configurations == realized.participant_configurations
    assert request.provisioning_plan.run_id == entry.run_id
