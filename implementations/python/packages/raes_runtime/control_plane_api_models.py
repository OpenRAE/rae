"""HTTP/JSON control-plane DTO conversion helpers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from raes_contracts.contracts import (
    EvaluationPlanModel,
    OperationStatusModel,
    OrchestrationPlanModel,
    ProvisioningPlanModel,
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
from raes_contracts.runtime_state import OperationStatus

from raes_runtime.snapshot_contract import runtime_snapshot_contract_model


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
        inventory_attempt_id=model.inventory_attempt_id,
        inventory_refresh=model.inventory_refresh,
        materialization_source=model.materialization_source,
        augmentation_scope_required=model.augmentation_scope_required,
        purpose=model.purpose,
        preparation=model.preparation,
        profile_authority=model.profile_authority,
        operations=[
            ProvisionOp(
                execution_policy=op.execution_policy,
                execution_policy_scopes=op.execution_policy_scopes,
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
        run_id=model.run_id,
        instantiation_id=model.instantiation_id,
        observation_demands=tuple(model.observation_demands),
    )


def _orchestration_plan(model: OrchestrationPlanModel) -> OrchestrationPlan:
    return OrchestrationPlan(
        operation_id=model.operation_id,
        materialization_source=model.materialization_source,
        augmentation_scope_required=model.augmentation_scope_required,
        purpose=model.purpose,
        operations=[
            OrchestrationOp(
                execution_policy=op.execution_policy,
                execution_policy_scopes=op.execution_policy_scopes,
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
        operation_id=model.operation_id,
        materialization_source=model.materialization_source,
        augmentation_scope_required=model.augmentation_scope_required,
        purpose=model.purpose,
        operations=[
            EvaluationOp(
                execution_policy=op.execution_policy,
                execution_policy_scopes=op.execution_policy_scopes,
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
        run_id=model.run_id,
        instantiation_id=model.instantiation_id,
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


_snapshot_model = runtime_snapshot_contract_model
