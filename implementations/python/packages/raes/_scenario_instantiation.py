"""Private helpers for validating instantiated scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from pydantic import BaseModel
from raes_contracts.json_pointer import is_array_index_token

from ._base import VARIABLE_TOKEN_RE
from ._capability_binding_normalization import normalize_capability_binding
from ._phase_base import JSONScalar, json_value_equal
from .parameter_derivations import ParameterDerivation

if TYPE_CHECKING:
    from .phase_contracts import CapabilityConstraint


def validate_capability_constraint_outputs(
    scenario: BaseModel,
    payload: object,
    constraints: tuple[CapabilityConstraint, ...],
    bindings: Mapping[tuple[str, ...], JSONScalar],
) -> None:
    """Retain whole-field finite binding equality and owner normalization."""

    for constraint in constraints:
        try:
            concrete_value = resolve_json_pointer(payload, constraint.field_pointer)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Capability constraint field_pointer does not resolve: {constraint.field_pointer}"
            ) from exc
        if constraint.parameter not in bindings:
            raise ValueError("Capability constraint references an unresolved parameter identity")
        binding = bindings[constraint.parameter]
        if not json_value_equal(concrete_value, binding):
            binding = normalize_capability_binding(scenario, constraint.field_pointer, binding)
            if not json_value_equal(concrete_value, binding):
                raise ValueError("Capability constraint binding does not match the concrete field value")


def validate_parameter_derivation_outputs(
    scenario: BaseModel,
    payload: object,
    derivations: tuple[ParameterDerivation, ...],
    bindings: Mapping[tuple[str, ...], JSONScalar],
) -> None:
    """Check portable derivations against concrete fields through their owner."""

    for derivation in derivations:
        try:
            concrete_value = resolve_json_pointer(payload, derivation.field_pointer)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError("Parameter derivation field_pointer does not resolve") from exc
        derived_value = derivation.resolve(bindings)
        if not json_value_equal(concrete_value, derived_value):
            normalized = normalize_capability_binding(scenario, derivation.field_pointer, derived_value)
            if not json_value_equal(concrete_value, normalized):
                raise ValueError("Parameter derivation output does not match the concrete field value")


def collect_variable_tokens(value: object) -> list[str]:
    """Return the names of every ``${name}`` token found in string values.

    Mirrors ``instantiate._substitute_value``: every string is a substitution
    site and mapping keys are not. An instantiated scenario is fully concrete,
    so no token may survive in any string value.
    """
    found: list[str] = []
    if isinstance(value, Mapping):
        for nested in value.values():
            found.extend(collect_variable_tokens(nested))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(collect_variable_tokens(item))
    elif isinstance(value, str):
        found.extend(VARIABLE_TOKEN_RE.findall(value))
    return found


def resolve_json_pointer(payload: object, pointer: str) -> object:
    """Resolve an RFC 6901-style JSON pointer against a scenario payload."""
    current = payload
    for raw_segment in pointer.split("/")[1:]:
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            current = current[segment]
        elif isinstance(current, (list, tuple)):
            if not is_array_index_token(segment):
                raise ValueError("JSON Pointer array index must be a canonical non-negative integer")
            current = current[int(segment)]
        else:
            raise TypeError("JSON Pointer traverses a scalar value")
    return current
