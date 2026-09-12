"""Portable completion proposal for the opt-in preparation protocol."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, model_validator
from pydantic_core import to_jsonable_python

from raes_contracts.canonical import jsonable_fallback

from ..diagnostics import Diagnostic, DiagnosticModel, portable_diagnostic_payload
from ..planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain, require_plan_operation_identity
from ..realization_preparation import BACKEND_PREPARATION_CONTRACT, RealizationPreparation
from ..realization_structure import validate_realization_value
from ..runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS
from .base import ContractModel
from .realization_plans import PlanOperationModel


class PreparationOperationModel(PlanOperationModel):
    """A provisioning operation selected under the original request authority."""

    action: ChangeAction

    @model_validator(mode="after")
    def _validate_selected_operation(self) -> PreparationOperationModel:
        require_plan_operation_identity(RuntimeDomain.PROVISIONING, self.address, self.resource_type)
        if not validate_realization_value(self.payload, python_carriers=True).conformant:
            raise ValueError("prepared payload exceeds its portable value bounds")
        return self


class BackendPreparationResponseModel(ContractModel):
    """One supported choice, never proof of delivery or independent observation."""

    contract_id: Literal["backend-realization-preparation-v1"] = BACKEND_PREPARATION_CONTRACT
    request_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    predecessor_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    success: StrictBool = True
    operations: list[PreparationOperationModel] = Field(max_length=16384)
    diagnostics: list[DiagnosticModel] = Field(default_factory=list, max_length=1024)

    @model_validator(mode="after")
    def _validate_operation_inventory(self) -> BackendPreparationResponseModel:
        if not validate_realization_value(self, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True).conformant:
            raise ValueError("preparation response exceeds the aggregate portable bounds")
        # Reuse the phase contract's unique-address and provisioning identity rules.
        ProvisioningPlan(operations=list(self.to_runtime().operations))
        return self

    def to_runtime(self) -> RealizationPreparation:
        return RealizationPreparation(
            request_digest=self.request_digest,
            predecessor_digest=self.predecessor_digest,
            success=self.success,
            operations=tuple(
                ProvisionOp(
                    action=operation.action,
                    address=operation.address,
                    resource_type=operation.resource_type,
                    payload=operation.payload,
                    ordering_dependencies=tuple(operation.ordering_dependencies),
                    refresh_dependencies=tuple(operation.refresh_dependencies),
                    profile_bindings=operation.profile_bindings,
                )
                for operation in self.operations
            ),
            diagnostics=tuple(Diagnostic(**item.model_dump()) for item in self.diagnostics),
        )


def preparation_response_model(response: RealizationPreparation) -> BackendPreparationResponseModel:
    """Convert an admitted in-process response to its closed transport shape."""

    if not validate_realization_value(response, limits=RUNTIME_SNAPSHOT_VALUE_LIMITS, python_carriers=True).conformant:
        raise ValueError("preparation response exceeds the aggregate portable bounds")
    return BackendPreparationResponseModel(
        request_digest=response.request_digest,
        predecessor_digest=response.predecessor_digest,
        success=response.success,
        operations=to_jsonable_python(response.operations, fallback=jsonable_fallback),
        diagnostics=[portable_diagnostic_payload(item) for item in response.diagnostics],
    )


__all__ = ["BackendPreparationResponseModel", "PreparationOperationModel", "preparation_response_model"]
