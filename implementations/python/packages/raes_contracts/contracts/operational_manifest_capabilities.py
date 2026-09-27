"""Backend manifest declarations for operational capabilities outside the realization domains."""

from __future__ import annotations

from pydantic import Field, model_validator

from ..manifest_authority import validate_backend_supported_contract_versions
from ..operation_lifecycle import OperationKind
from .backend_operation import OperationGuarantee
from .base import ContractModel, NonEmptyString
from .trial_cleanup import CleanupActionKind
from .validators import _validate_unique_string_values


class CleanupCapabilitiesModel(ContractModel):
    """Backend support for the portable SCE-007 cleanup contract family."""

    name: NonEmptyString
    supported_contract_versions: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_action_kinds: list[CleanupActionKind] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_verification_methods: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supports_reusable_state: bool = False
    supports_residual_state_disclosure: bool = False

    @model_validator(mode="after")
    def _validate_cleanup_capability(self) -> CleanupCapabilitiesModel:
        _validate_unique_string_values("cleanup supported_contract_versions", self.supported_contract_versions)
        _validate_unique_string_values("cleanup supported_action_kinds", self.supported_action_kinds)
        _validate_unique_string_values("cleanup supported_verification_methods", self.supported_verification_methods)
        required = {"trial-cleanup-plan-v1", "trial-cleanup-receipt-v1"}
        if set(self.supported_contract_versions) != required:
            raise ValueError(
                "cleanup capabilities require contract versions trial-cleanup-plan-v1 and trial-cleanup-receipt-v1"
            )
        validate_backend_supported_contract_versions(self.supported_contract_versions)
        if self.supports_reusable_state and not self.supports_residual_state_disclosure:
            raise ValueError("reusable-state support requires residual-state disclosure")
        return self


class RecoveryObservationCapabilitiesModel(ContractModel):
    """Operational crash-recovery observation support declaration."""

    name: NonEmptyString
    supported_operation_kinds: list[OperationKind] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def _validate_supported_kinds(self) -> RecoveryObservationCapabilitiesModel:
        if len(self.supported_operation_kinds) != len(set(self.supported_operation_kinds)):
            raise ValueError("recovery supported_operation_kinds must be unique")
        if OperationKind.INDETERMINATE_RESOLUTION in self.supported_operation_kinds:
            raise ValueError("administrative resolution is not a recoverable backend effect")
        return self


class OperationSupervisionCapabilitiesModel(ContractModel):
    """Static declaration of the backend operation guarantees a backend provides.

    Planning compares authored execution choices with this declaration. It is
    neither contextual willingness nor evidence: runtime admission still checks
    the installed provider's capabilities and willingness before each dispatch.
    """

    name: NonEmptyString
    guarantees: list[OperationGuarantee] = Field(min_length=1, max_length=5, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _validate_guarantees(self) -> OperationSupervisionCapabilitiesModel:
        _validate_unique_string_values("operation supervision guarantees", self.guarantees)
        return self


__all__ = [
    "CleanupCapabilitiesModel",
    "OperationSupervisionCapabilitiesModel",
    "RecoveryObservationCapabilitiesModel",
]
