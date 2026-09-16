"""Finite admission of portable backend inputs before hashing or isolation."""

from __future__ import annotations

from dataclasses import is_dataclass

from pydantic import BaseModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

from .backend_realization_authority import _RealizationApplyContext

_PORTABLE_INPUT_TYPES = (BaseModel, dict, list, tuple, str, int, float, bool)


def backend_input_violation(
    arguments: tuple[object, ...],
    *,
    authority: _RealizationApplyContext | None = None,
    service_dependencies: tuple[object, ...] = (),
) -> str | None:
    """Bound value carriers without traversing injected service dependencies."""

    if authority is not None:
        arguments = (
            *arguments,
            authority.plan,
            authority.operation_plan,
            authority.completion_plan,
            authority.requirements,
        )
    values = {
        id(value): value
        for value in arguments
        if (isinstance(value, _PORTABLE_INPUT_TYPES) or is_dataclass(value))
        and not any(value is service for service in service_dependencies)
    }
    for value in values.values():
        if not validate_realization_value(
            value,
            limits=RUNTIME_SNAPSHOT_VALUE_LIMITS,
            python_carriers=True,
        ).conformant:
            return "Backend call input exceeds the admitted portable value bounds."
        if isinstance(value, (ProvisioningPlan, OrchestrationPlan, EvaluationPlan)):
            invalid = _operation_plan_violation(value)
            if invalid:
                return invalid
    return None


def _operation_plan_violation(value: ProvisioningPlan | OrchestrationPlan | EvaluationPlan) -> str | None:
    invalid = None
    if type(value.augmentation_scope_required) is not bool:
        invalid = "Operation plan scope authorization must be a canonical boolean."
    elif not isinstance(value.diagnostics, (list, tuple)) or any(
        not isinstance(diagnostic, Diagnostic) or diagnostic.is_error for diagnostic in value.diagnostics
    ):
        invalid = "An invalid operation plan cannot authorize backend execution."
    elif value.purpose != "execution":
        invalid = "A descriptive inspection plan cannot authorize backend execution."
    return invalid
