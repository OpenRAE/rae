"""Static backend declarations and pure trial-control requirements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from .backend_operation import OperationContractModel, OperationGuarantee
from .base import NonEmptyString

if TYPE_CHECKING:
    from .admitted_trial_plan_components import AdmittedExecutionControlModel
    from .trial_cleanup import ExecutionRetryPolicyModel


class OperationSupervisionCapabilitiesModel(OperationContractModel):
    """Static support only; installed capability and willingness need live checks."""

    name: NonEmptyString = Field(max_length=256)
    guarantees: tuple[OperationGuarantee, ...] = Field(
        default=(), max_length=5, json_schema_extra={"uniqueItems": True}
    )


def required_trial_operation_guarantees(
    controls: AdmittedExecutionControlModel,
    retry_policy: ExecutionRetryPolicyModel,
) -> tuple[OperationGuarantee, ...]:
    """Derive supervision demands without authorizing execution or repetition."""

    required: set[OperationGuarantee] = set()
    if controls.on_timeout == "cancel":
        required.add("cancellation")
    if retry_policy.max_attempts > 1:
        required.add("cessation-evidence")
        if retry_policy.after_effect_policy == "disallow":
            required.add("effect-observation")
    return tuple(sorted(required))
