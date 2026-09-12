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


def resolve_pending_recursive_constraints(
    model: RuntimeModel, decisions: ApparatusRealizationDecisions
) -> RuntimeModel:
    """No second authority tree: lower the model's original instantiated source."""

    if not any(requirement.recursive_pending for requirement in model.realization_requirements):
        return model
    scenario = model.realization_instance
    registered = (
        {}
        if scenario is None
        else {
            (item.field_path, item.descriptor.concern_kind): item
            for item in registered_realization_concern_descriptors(
                declaration_names={"nodes": scenario.nodes, "content": scenario.content}
            )
        }
    )
    requirements, opened = [], set()
    for requirement in model.realization_requirements:
        if requirement.recursive_pending:
            identity = (requirement.address, requirement.field_path, requirement.requirement_kind)
            concern = registered.get((requirement.field_path, requirement.requirement_kind))
            decision = decisions.get(identity)
            if concern is None or not isinstance(decision, Closure):
                requirement = replace(requirement, recursive_pending=False, structure_error=True)
            else:
                descriptor = concern.descriptor
                pointer = f"/{descriptor.section}/{concern.declaration_name.replace('~', '~0').replace('/', '~1')}/{'/'.join(descriptor.authored_path)}"
                source = getattr(scenario, descriptor.section)[concern.declaration_name]
                structure, document, binding, error, root_open, pending = compile_registered_constraint(
                    scenario,
                    concern,
                    scenario.explicitness,
                    authored_value=nested_authored_value(source, descriptor.authored_path),
                    field_pointer=pointer,
                    value_domain=requirement.value_domain,
                    apparatus_closure=decision,
                )
                requirement = replace(
                    requirement,
                    structure=structure,
                    constraint_document=document,
                    constraint_binding=binding,
                    structure_error=error or pending,
                    recursive_pending=False,
                    explicitness=ExplicitnessClass.OPEN if root_open else requirement.explicitness,
                )
                if root_open:
                    opened.add(identity)
        requirements.append(requirement)
    authorities = tuple(
        replace(authority, mode=RealizationAuthorityMode.OPEN)
        if (authority.address, authority.field_path, authority.requirement_kind) in opened
        else authority
        for authority in model.realization_authority
    )
    return replace(model, realization_requirements=tuple(requirements), realization_authority=authorities)
