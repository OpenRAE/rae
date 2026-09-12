"""Value extraction and finite-domain helpers for realization compilation."""

from __future__ import annotations

from raes.architectures import normalize_architecture
from raes.scenario import InstantiatedScenario
from raes_contracts.bounded_domains import EnumDomain


def nested_authored_value(source: object, path: tuple[str, ...]) -> object:
    """Resolve one registered concern value from an authored declaration."""

    current = source
    for token in path:
        if current is None:
            return None
        current = getattr(current, token, None)
    return current


def compiled_os_value_domain(
    scenario: InstantiatedScenario,
    *,
    field_pointer: str,
) -> tuple[EnumDomain | None, str | None]:
    """Recover the finite authoring-variable domain for an OS identity leaf."""

    constraint = next(
        (
            item
            for item in scenario.instantiation_provenance.capability_constraints
            if item.field_pointer == field_pointer
        ),
        None,
    )
    if constraint is None:
        return None, None
    return EnumDomain(values=list(constraint.allowed_values)), "variable-allowed-values"


def compiled_architecture_value_domain(scenario: InstantiatedScenario, *, field_pointer: str) -> EnumDomain | None:
    """Canonicalize the retained finite architecture domain through its owner."""

    constraint = next(
        (
            item
            for item in scenario.instantiation_provenance.capability_constraints
            if item.field_pointer == field_pointer
        ),
        None,
    )
    if constraint is None:
        return None
    values = (normalize_architecture(value) for value in constraint.allowed_values)
    return EnumDomain(values=list(dict.fromkeys(getattr(value, "value", value) for value in values)))
