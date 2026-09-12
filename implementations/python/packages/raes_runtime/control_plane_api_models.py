"""HTTP/JSON control-plane DTO conversion helpers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from raes_contracts.account_credentials import (
    account_placement_has_credential_bindings,
    value_free_account_placement_payload,
)
from raes_contracts.contracts import (
    EvaluationPlanModel,
    OperationStatusModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
    RuntimeSnapshotEnvelopeModel,
)
from raes_contracts.diagnostics import Diagnostic, Severity, portable_diagnostic_payload
from raes_contracts.participant_episode import ParticipantEpisodeTerminalReason
from raes_contracts.planning import (
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    OrchestrationOp,
    OrchestrationPlan,
    ProvisioningPlan,
    ProvisionOp,
    RealizationAuthorityBound,
    ResolvedRealizationAuthority,
)
from raes_contracts.runtime_state import OperationStatus, RuntimeSnapshotEnvelope

from raes_runtime.control_plane_store_payloads import _realization_observations_payload


class _ParticipantInitializeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str | None = None


class _ParticipantResetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str | None = None
    reason: str = Field(default="reset by operator")


class _ParticipantRestartBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str | None = None
    reason: str = Field(default="restarted by operator")


class _ParticipantTerminateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terminal_reason: str = Field(default=ParticipantEpisodeTerminalReason.INTERRUPTED.value)
    detail: str = Field(default="terminated by operator")


class _ParticipantExecutionControlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start", "pause", "resume", "drain", "reset", "teardown"]
    expected_generation: int = Field(ge=0)
    timeout_seconds: int | None = Field(default=None, ge=1)


def _diagnostic_from_mapping(payload: dict[str, Any]) -> Diagnostic:
    return Diagnostic(
        code=str(payload.get("code", "runtime.control-plane")),
        domain=str(payload.get("domain", "runtime")),
        address=str(payload.get("address", "runtime.control-plane")),
        message=str(payload.get("message", "")),
        severity=Severity(str(payload.get("severity", "error"))),
    )


def _provisioning_plan(model: ProvisioningPlanModel) -> ProvisioningPlan:
    from raes_contracts.planning import PlannedRealizationConstraint

    return ProvisioningPlan(
        preparation=model.preparation,
        profile_authority=model.profile_authority,
        operations=[
            ProvisionOp(
                action=ChangeAction(str(op.action)),
                address=op.address,
                resource_type=op.resource_type,
                payload=dict(op.payload),
                ordering_dependencies=tuple(op.ordering_dependencies),
                refresh_dependencies=tuple(op.refresh_dependencies),
                profile_bindings=op.profile_bindings,
            )
            for op in model.operations
        ],
        diagnostics=[_diagnostic_from_mapping(payload) for payload in model.diagnostics],
        realization_authority=tuple(
            ResolvedRealizationAuthority(
                address=entry.address,
                field_path=entry.field_path,
                domain=entry.domain,
                requirement_kind=entry.requirement_kind,
                payload_pointer=entry.payload_pointer,
                mode=entry.mode,
                source=entry.source,
                provenance=entry.provenance,
                governing_scope=entry.governing_scope,
                bounds=tuple(
                    RealizationAuthorityBound(
                        value_pointer=bound.value_pointer,
                        domain=bound.domain,
                        identity_digest=bound.identity_digest,
                    )
                    for bound in entry.bounds
                ),
                verification_scope=entry.verification_scope,
                required_observation_strength=entry.required_observation_strength,
                structure=entry.structure,
                constraint_document=entry.constraint_document,
                constraint_binding=entry.constraint_binding,
            )
            for entry in model.realization_authority
        ),
        realization_envelope=model.realization_envelope,
        realization_constraints=tuple(
            PlannedRealizationConstraint(
                address=item.address,
                field_path=item.field_path,
                concern=item.concern,
                posture=item.posture,
                value_domain=item.value_domain,
                governing_scope=item.governing_scope,
                provenance=item.provenance,
            )
            for item in model.realization_constraints
        ),
        operation_id=model.operation_id,
        observation_demands=tuple(model.observation_demands),
    )


def _orchestration_plan(model: OrchestrationPlanModel) -> OrchestrationPlan:
    return OrchestrationPlan(
        operations=[
            OrchestrationOp(
                action=ChangeAction(str(op.action)),
                address=op.address,
                resource_type=op.resource_type,
                payload=dict(op.payload),
                ordering_dependencies=tuple(op.ordering_dependencies),
                refresh_dependencies=tuple(op.refresh_dependencies),
            )
            for op in model.operations
        ],
        startup_order=list(model.startup_order),
        diagnostics=[_diagnostic_from_mapping(payload) for payload in model.diagnostics],
        observation_demands=tuple(model.observation_demands),
    )


def _evaluation_plan(model: EvaluationPlanModel) -> EvaluationPlan:
    return EvaluationPlan(
        operations=[
            EvaluationOp(
                action=ChangeAction(str(op.action)),
                address=op.address,
                resource_type=op.resource_type,
                payload=dict(op.payload),
                ordering_dependencies=tuple(op.ordering_dependencies),
                refresh_dependencies=tuple(op.refresh_dependencies),
            )
            for op in model.operations
        ],
        startup_order=list(model.startup_order),
        diagnostics=[_diagnostic_from_mapping(payload) for payload in model.diagnostics],
        observation_demands=tuple(model.observation_demands),
    )


def _operation_status_model(status: OperationStatus) -> OperationStatusModel:
    return OperationStatusModel.model_validate(
        {
            "schema_version": status.schema_version,
            "operation_id": status.operation_id,
            "domain": status.domain.value,
            "state": status.state.value,
            "submitted_at": status.submitted_at,
            "updated_at": status.updated_at,
            "context": status.context.model_dump(mode="json"),
            "diagnostics": [portable_diagnostic_payload(diag) for diag in status.diagnostics],
            "changed_addresses": list(status.changed_addresses),
        }
    )


def _snapshot_model(envelope: RuntimeSnapshotEnvelope) -> RuntimeSnapshotEnvelopeModel:
    snapshot = envelope.snapshot
    payload = {
        "schema_version": envelope.schema_version,
        "entries": {
            address: {
                "address": entry.address,
                "domain": entry.domain.value,
                "resource_type": entry.resource_type,
                "payload": dict(entry.payload),
                "ordering_dependencies": list(entry.ordering_dependencies),
                "refresh_dependencies": list(entry.refresh_dependencies),
                "status": entry.status,
            }
            for address, entry in snapshot.entries.items()
        },
        "orchestration_results": dict(snapshot.orchestration_results),
        "orchestration_history": dict(snapshot.orchestration_history),
        "evaluation_results": dict(snapshot.evaluation_results),
        "evaluation_history": dict(snapshot.evaluation_history),
        "proposition_truth_results": dict(snapshot.proposition_truth_results),
        "participant_episode_results": dict(snapshot.participant_episode_results),
        "participant_episode_history": dict(snapshot.participant_episode_history),
        "participant_behavior_history": dict(snapshot.participant_behavior_history),
        "participant_control_history": dict(snapshot.participant_control_history),
        "participant_crossing_history": dict(snapshot.participant_crossing_history),
        "information_state_history": dict(snapshot.information_state_history),
        "participant_autonomous_execution_states": dict(snapshot.participant_autonomous_execution_states),
        "participant_execution_services": dict(snapshot.participant_execution_services),
        "participant_resource_budget_states": dict(snapshot.participant_resource_budget_states),
        "participant_resource_pool_states": dict(snapshot.participant_resource_pool_states),
        "participant_resource_budget_events": dict(snapshot.participant_resource_budget_events),
        "shared_state_records": dict(snapshot.shared_state_records),
        "shared_state_history": dict(snapshot.shared_state_history),
        "joint_action_records": dict(snapshot.joint_action_records),
        "time_management_contexts": dict(snapshot.time_management_contexts),
        "time_model_state": (
            snapshot.time_model_state.model_dump(mode="json") if snapshot.time_model_state is not None else None
        ),
        "realization_provenance": [
            {
                "address": entry.address,
                "field_path": entry.field_path,
                "domain": entry.domain,
                "requirement_kind": entry.requirement_kind,
                "explicitness": entry.explicitness.value,
                "provenance": entry.provenance.value,
                "governing_scope": entry.governing_scope,
                **(
                    {"artifact_satisfaction": entry.artifact_satisfaction.model_dump(mode="json")}
                    if entry.artifact_satisfaction is not None
                    else {}
                ),
            }
            for entry in snapshot.realization_provenance
        ],
        "realization_observations": _realization_observations_payload(snapshot),
        "realization_envelope": (
            snapshot.realization_envelope.model_dump(mode="json") if snapshot.realization_envelope is not None else None
        ),
        "metadata": dict(snapshot.metadata),
    }
    for entry in payload["entries"].values():
        if entry["resource_type"] != "account-placement":
            continue
        entry_payload = entry["payload"]
        if account_placement_has_credential_bindings(entry_payload):
            entry["payload"] = value_free_account_placement_payload(entry_payload)
    return RuntimeSnapshotEnvelopeModel.model_validate(payload)
