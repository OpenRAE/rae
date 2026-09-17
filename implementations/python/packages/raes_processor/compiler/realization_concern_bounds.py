"""Typed bounds and compiled structure for one registered realization concern."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from raes.explicitness import ExplicitnessRecord
from raes.runtime_resource_limits import RuntimeProcessResourceLimit, process_resource_limit_identity_digest
from raes.scenario import InstantiatedScenario

from ..semantics.realization_concerns import RegisteredRealizationConcern
from ..semantics.realization_process_limits import (
    ProcessResourceLimitDemand,
    ProcessResourceLimitScope,
    RealizationValueConstraint,
)
from .realization_recursive_constraints import compile_registered_constraint
from .realization_value_domains import compiled_os_value_domain

__all__ = ["_ConcernStructure", "_ConcernValueBounds", "_concern_structure", "_concern_value_bounds"]


@dataclass(frozen=True)
class _ConcernValueBounds:
    """The typed value bounds one registered concern kind contributes."""

    value_constraints: tuple[RealizationValueConstraint, ...] = ()
    process_resource_limits: tuple[ProcessResourceLimitDemand, ...] = ()
    value_domain: object | None = None
    constraint_provenance: object | None = None


@dataclass(frozen=True)
class _ConcernStructure:
    """The compiled recursive structure one registered concern lowers to."""

    structure: object | None = None
    constraint_document: object | None = None
    constraint_binding: str | None = None
    structure_error: bool = False
    recursive_pending: bool = False
    root_open: bool = False


def _compiled_process_resource_limits(
    scenario: InstantiatedScenario,
    *,
    field_pointer: str,
    authored_value: object,
) -> tuple[tuple[RealizationValueConstraint, ...], tuple[ProcessResourceLimitDemand, ...]]:
    limits = tuple(authored_value) if isinstance(authored_value, list) else ()
    typed_limits = tuple(
        value if isinstance(value, RuntimeProcessResourceLimit) else RuntimeProcessResourceLimit.model_validate(value)
        for value in limits
    )
    constraints: list[RealizationValueConstraint] = []
    prefix = f"{field_pointer}/"
    for constraint in scenario.instantiation_provenance.capability_constraints:
        if not constraint.field_pointer.startswith(prefix):
            continue
        suffix = constraint.field_pointer.removeprefix(prefix).split("/")
        if len(suffix) != 2 or not suffix[0].isdigit() or suffix[1] not in {"soft", "hard"}:
            continue
        index = int(suffix[0])
        if index >= len(typed_limits):
            continue
        constraints.append(
            RealizationValueConstraint(
                identity_digest=process_resource_limit_identity_digest(typed_limits[index]),
                leaf=suffix[1],
                parameter=constraint.parameter,
                allowed_values=constraint.allowed_values,
            )
        )
    demands = tuple(
        ProcessResourceLimitDemand(
            identity_digest=process_resource_limit_identity_digest(value),
            resource=value.resource,
            scope=ProcessResourceLimitScope(value.scope.value),
            soft=value.soft,
            hard=value.hard,
        )
        for value in typed_limits
    )
    return tuple(constraints), demands


def _concern_value_bounds(
    scenario: InstantiatedScenario,
    descriptor: object,
    *,
    field_pointer: str,
    authored_value: object,
) -> _ConcernValueBounds:
    """Collect the typed bounds one concern kind publishes before compilation."""

    if descriptor.concern_kind == "process-resource-limits":
        value_constraints, process_resource_limits = _compiled_process_resource_limits(
            scenario,
            field_pointer=field_pointer,
            authored_value=authored_value,
        )
        return _ConcernValueBounds(value_constraints=value_constraints, process_resource_limits=process_resource_limits)
    if descriptor.concern_kind not in {"os-family", "os-distribution", "os-version"}:
        return _ConcernValueBounds()
    value_domain, constraint_provenance = compiled_os_value_domain(scenario, field_pointer=field_pointer)
    return _ConcernValueBounds(value_domain=value_domain, constraint_provenance=constraint_provenance)


def _concern_structure(
    scenario: InstantiatedScenario,
    registered: RegisteredRealizationConcern,
    explicitness: Mapping[str, ExplicitnessRecord],
    *,
    authored_value: object,
    field_pointer: str,
    value_domain: object | None,
) -> _ConcernStructure:
    """Compile the recursive structure one explicitly recorded concern lowers to."""

    structure, document, binding, error, root_open, pending = compile_registered_constraint(
        scenario,
        registered,
        explicitness,
        authored_value=authored_value,
        field_pointer=field_pointer,
        value_domain=value_domain,
    )
    return _ConcernStructure(
        structure=structure,
        constraint_document=document,
        constraint_binding=binding,
        structure_error=error,
        recursive_pending=pending,
        root_open=root_open,
    )
