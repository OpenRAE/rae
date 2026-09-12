"""Finish recursive lowering from retained source after apparatus resolution."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from raes.explicitness import ExplicitnessClass
from raes_contracts.planning import RealizationAuthorityMode
from raes_contracts.vocabulary import Closure

from ..semantics.realization_concerns import registered_realization_concern_descriptors
from .realization_recursive_constraints import compile_registered_constraint
from .realization_value_domains import nested_authored_value

if TYPE_CHECKING:
    from ..models import RuntimeModel
    from ..semantics.realization_apparatus_defaults import ApparatusRealizationDecisions


def _registered_concerns(scenario: object) -> dict[tuple[str, str], object]:
    """Index the registered recursive concerns one instantiated scenario declares."""

    if scenario is None:
        return {}
    return {
        (item.field_path, item.descriptor.concern_kind): item
        for item in registered_realization_concern_descriptors(
            declaration_names={"nodes": scenario.nodes, "content": scenario.content}
        )
    }


def _concern_pointer(concern: object) -> str:
    """Name the authored pointer one registered concern lowers from."""

    descriptor = concern.descriptor
    declaration = concern.declaration_name.replace("~", "~0").replace("/", "~1")
    return f"/{descriptor.section}/{declaration}/{'/'.join(descriptor.authored_path)}"


def _lowered_requirement(
    requirement: object, concern: object, scenario: object, decision: Closure
) -> tuple[object, bool]:
    """Lower one deferred requirement from its original instantiated source."""

    descriptor = concern.descriptor
    source = getattr(scenario, descriptor.section)[concern.declaration_name]
    structure, document, binding, error, root_open, pending = compile_registered_constraint(
        scenario,
        concern,
        scenario.explicitness,
        authored_value=nested_authored_value(source, descriptor.authored_path),
        field_pointer=_concern_pointer(concern),
        value_domain=requirement.value_domain,
        apparatus_closure=decision,
    )
    lowered = replace(
        requirement,
        structure=structure,
        constraint_document=document,
        constraint_binding=binding,
        structure_error=error or pending,
        recursive_pending=False,
        explicitness=ExplicitnessClass.OPEN if root_open else requirement.explicitness,
    )
    return lowered, root_open


def _resolved_requirement(
    requirement: object,
    *,
    registered: dict[tuple[str, str], object],
    decisions: ApparatusRealizationDecisions,
    scenario: object,
) -> tuple[object, bool]:
    """Resolve one requirement, refusing it when no apparatus decision lowers it."""

    concern = registered.get((requirement.field_path, requirement.requirement_kind))
    decision = decisions.get((requirement.address, requirement.field_path, requirement.requirement_kind))
    if concern is None or not isinstance(decision, Closure):
        return replace(requirement, recursive_pending=False, structure_error=True), False
    return _lowered_requirement(requirement, concern, scenario, decision)


def resolve_pending_recursive_constraints(
    model: RuntimeModel, decisions: ApparatusRealizationDecisions
) -> RuntimeModel:
    """No second authority tree: lower the model's original instantiated source."""

    if not any(requirement.recursive_pending for requirement in model.realization_requirements):
        return model
    scenario = model.realization_instance
    registered = _registered_concerns(scenario)
    requirements, opened = [], set()
    for requirement in model.realization_requirements:
        if not requirement.recursive_pending:
            requirements.append(requirement)
            continue
        resolved, root_open = _resolved_requirement(
            requirement, registered=registered, decisions=decisions, scenario=scenario
        )
        if root_open:
            opened.add((requirement.address, requirement.field_path, requirement.requirement_kind))
        requirements.append(resolved)
    authorities = tuple(
        replace(authority, mode=RealizationAuthorityMode.OPEN)
        if (authority.address, authority.field_path, authority.requirement_kind) in opened
        else authority
        for authority in model.realization_authority
    )
    return replace(model, realization_requirements=tuple(requirements), realization_authority=authorities)
