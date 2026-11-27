"""Strict retained evidence for a separately authorized absence resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Self

from pydantic import ConfigDict, model_validator
from raes_contracts.contracts import (
    BackendOperationControlModel,
    BackendOperationRequestModel,
    BackendOperationResponseModel,
    validate_backend_operation_response,
)
from raes_contracts.contracts.base import ContractModel
from raes_contracts.runtime_state import OperationKind, OperationState

if TYPE_CHECKING:
    from .control_plane_store import ControlPlaneOperationRecord


class InvocationReconciliation(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["raes-invocation-reconciliation/v1"] = "raes-invocation-reconciliation/v1"
    request: BackendOperationRequestModel
    control: BackendOperationControlModel
    response: BackendOperationResponseModel

    @model_validator(mode="after")
    def _absence(self) -> Self:
        validate_backend_operation_response(self.request, self.response, control=self.control)
        message = self.response.message
        if (
            message.kind != "reconciliation"
            or message.effects.effect != "absent"
            or not message.effects.cessation_established
        ):
            raise ValueError("reconciliation must establish scoped absence and cessation")
        return self


def valid_reconciliation_child(parent: ControlPlaneOperationRecord, child: ControlPlaneOperationRecord) -> bool:
    evidence = child.reconciliation
    return bool(
        evidence is not None
        and parent.invocation is not None
        and _matches_resolution_parent(parent, child)
        and _retains_reconciliation_authority(parent, child, evidence)
        and child.idempotency_key
        and child.idempotency_key != parent.idempotency_key
    )


def _matches_resolution_parent(parent: ControlPlaneOperationRecord, child: ControlPlaneOperationRecord) -> bool:
    context = child.status.context
    return (
        parent.status.state is OperationState.INDETERMINATE
        and child.status.state is OperationState.SUCCEEDED
        and context.operation_kind is OperationKind.INDETERMINATE_RESOLUTION
        and context.parent_operation_id == parent.receipt.operation_id
        and (context.target_scope, context.run_scope)
        == (parent.status.context.target_scope, parent.status.context.run_scope)
        and "role:operator" in context.authorization_scope
    )


def _retains_reconciliation_authority(
    parent: ControlPlaneOperationRecord, child: ControlPlaneOperationRecord, evidence: InvocationReconciliation
) -> bool:
    return (
        evidence.control.actor_id == child.status.context.actor_id
        and evidence.control.authorization_scope == child.status.context.authorization_scope
        and evidence.request == parent.invocation.request
        and evidence.control in parent.invocation.controls
        and evidence.response in parent.invocation.responses
    )
