"""Strict retained evidence for a separately authorized absence resolution."""

from typing import Literal

from pydantic import ConfigDict, model_validator
from raes_contracts.contracts import (
    BackendOperationControlModel,
    BackendOperationRequestModel,
    BackendOperationResponseModel,
    validate_backend_operation_response,
)
from raes_contracts.contracts.base import ContractModel
from raes_contracts.runtime_state import OperationKind, OperationState


class InvocationReconciliation(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["raes-invocation-reconciliation/v1"] = "raes-invocation-reconciliation/v1"
    request: BackendOperationRequestModel
    control: BackendOperationControlModel
    response: BackendOperationResponseModel

    @model_validator(mode="after")
    def _absence(self):
        validate_backend_operation_response(self.request, self.response, control=self.control)
        message = self.response.message
        if (
            message.kind != "reconciliation"
            or message.effects.effect != "absent"
            or not message.effects.cessation_established
        ):
            raise ValueError("reconciliation must establish scoped absence and cessation")
        return self


def valid_reconciliation_child(parent, child):
    evidence = child.reconciliation
    return bool(
        evidence is not None
        and parent.invocation is not None
        and parent.status.state is OperationState.INDETERMINATE
        and child.status.state is OperationState.SUCCEEDED
        and child.status.context.operation_kind is OperationKind.INDETERMINATE_RESOLUTION
        and child.status.context.parent_operation_id == parent.receipt.operation_id
        and (child.status.context.target_scope, child.status.context.run_scope)
        == (parent.status.context.target_scope, parent.status.context.run_scope)
        and "role:operator" in child.status.context.authorization_scope
        and evidence.control.actor_id == child.status.context.actor_id
        and evidence.control.authorization_scope == child.status.context.authorization_scope
        and evidence.request == parent.invocation.request
        and evidence.control in parent.invocation.controls
        and evidence.response in parent.invocation.responses
        and child.idempotency_key
        and child.idempotency_key != parent.idempotency_key
    )
