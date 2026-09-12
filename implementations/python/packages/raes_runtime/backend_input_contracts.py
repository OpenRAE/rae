"""Finite admission of portable backend inputs before hashing or isolation."""

from dataclasses import is_dataclass

from pydantic import BaseModel
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_value_limits import RUNTIME_SNAPSHOT_VALUE_LIMITS

_PORTABLE_INPUT_TYPES = (BaseModel, dict, list, tuple, str, int, float, bool)


def backend_input_violation(arguments: tuple[object, ...], *, authority=None, service_dependencies=()) -> str | None:
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
    return None
