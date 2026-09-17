"""Bounded, plan-owned profile constraints; target support is never plan data."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from ._base import ContractModel
from .addressing import require_compiled_address
from .canonical import canonical_json_digest
from .domain_profiles import (
    AdmittedDomainProfileDefinitionModel,
    DomainProfileAdmissionPolicyModel,
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingUse,
    DomainProfileOperation,
    DomainProfileResolutionContextModel,
    admit_domain_profile_bindings,
    resolve_domain_profile_definition,
)
from .realization_structure import (
    RealizationConstraintDocument,
    evaluate_realization_constraint,
    realization_constraint_binding,
    validate_realization_value,
)

PLAN_PROFILE_CONTRACT = "plan-realization-profiles-v1"
_POLICY = DomainProfileAdmissionPolicyModel(
    required_operations=tuple(sorted((DomainProfileOperation.COMPARISON, DomainProfileOperation.EXECUTION), key=str))
)
_REFUSAL = "Plan profiles lack a valid pinned, supported realization constraint."


def profile_context_digest(context: DomainProfileResolutionContextModel) -> str:
    """Bind exact local definition admission, operation support and work limits."""

    if (
        not isinstance(context, DomainProfileResolutionContextModel)
        or not validate_realization_value(context, python_carriers=True).conformant
    ):
        raise ValueError(_REFUSAL)
    context = DomainProfileResolutionContextModel.model_validate(context.model_dump(mode="json"))
    return canonical_json_digest({"host": PLAN_PROFILE_CONTRACT, "context": context.model_dump(mode="json")})


class ProfileBindingConstraint(ContractModel):
    """One recursive value authority for an exact path in the binding tree."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    binding_path: tuple[str, ...] = Field(min_length=1, max_length=16)
    document: RealizationConstraintDocument
    source_binding: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class PlanProfileAuthority(ContractModel):
    """Public values and immutable definitions, not executable support claims.

    Bindings are an explicit publication-safe programmatic input. Credentials,
    secret material, opaque exchange and observation claims have no host here.
    Source/trust provenance remains distinct from selected value provenance.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_id: Literal["plan-realization-profiles-v1"] = PLAN_PROFILE_CONTRACT
    definitions: tuple[AdmittedDomainProfileDefinitionModel, ...] = Field(min_length=1, max_length=256)
    bindings: tuple[DomainProfileBindingModel, ...] = Field(min_length=1, max_length=256)
    constraints: tuple[ProfileBindingConstraint, ...] = Field(min_length=1, max_length=256)


def profile_resource_address(binding: DomainProfileBindingModel) -> str:
    """Resolve the host's fixed owner form; arbitrary JSON pointers grant nothing."""

    prefix = "#/resources/"
    if not binding.owner.canonical_address.startswith(prefix):
        raise ValueError(_REFUSAL)
    address = binding.owner.canonical_address.removeprefix(prefix)
    require_compiled_address(address)
    if not address.startswith("provision."):
        raise ValueError(_REFUSAL)
    return address


def profile_binding_tree(
    bindings: tuple[DomainProfileBindingModel, ...],
) -> dict[tuple[str, ...], DomainProfileBindingModel]:
    """Flatten only after bounded shape admission, retaining full nested identity."""

    if not validate_realization_value(bindings, python_carriers=True).conformant:
        raise ValueError(_REFUSAL)
    pending = [((), item) for item in bindings]
    result = {}
    while pending:
        parent, binding = pending.pop()
        if not isinstance(binding, DomainProfileBindingModel):
            raise ValueError(_REFUSAL)
        path = (*parent, binding.binding_id)
        if path in result or len(path) > 16 or len(result) >= 256:
            raise ValueError(_REFUSAL)
        result[path] = binding
        pending.extend((path, child) for child in binding.children)
    return result


def _require_constraint_and_definition_cover(
    authority: PlanProfileAuthority,
    bindings: dict[tuple[str, ...], DomainProfileBindingModel],
) -> dict[str, object]:
    """Require constraints and definitions to cover the binding tree exactly."""

    constraints = {item.binding_path: item for item in authority.constraints}
    if len(constraints) != len(authority.constraints) or constraints.keys() != bindings.keys():
        raise ValueError(_REFUSAL)
    definitions = {item.definition.coordinate.definition_digest: item.definition for item in authority.definitions}
    if len(definitions) != len(authority.definitions) or definitions.keys() != {
        item.coordinate.definition_digest for item in bindings.values()
    }:
        raise ValueError(_REFUSAL)
    return definitions


def _require_resolvable_definitions(
    definitions: dict[str, object], context: DomainProfileResolutionContextModel
) -> None:
    """Require every pinned definition to resolve identically in the local context."""

    for definition in definitions.values():
        resolved = resolve_domain_profile_definition(definition.coordinate, context)
        if not resolved.resolved or resolved.definition != definition:
            raise ValueError(_REFUSAL)


def _binding_owner_admitted(binding: DomainProfileBindingModel) -> bool:
    """Report whether one binding is owned by the planning constraint contract."""

    owner = binding.owner
    return (
        owner.owning_contract_id == PLAN_PROFILE_CONTRACT
        and owner.concept_family == "resource-realization"
        and owner.lifecycle_phase == "planning"
        and owner.use is DomainProfileBindingUse.CONSTRAINT
        and binding.provenance.basis is DomainProfileBindingBasis.AUTHOR_SUPPLIED
    )


def _require_binding_ownership(
    bindings: dict[tuple[str, ...], DomainProfileBindingModel],
    authority: PlanProfileAuthority,
) -> None:
    """Require each binding to keep its owner, resource, and authored constraint."""

    constraints = {item.binding_path: item for item in authority.constraints}
    for path, binding in bindings.items():
        nested_owner_differs = len(path) > 1 and profile_resource_address(
            bindings[path[:-1]]
        ) != profile_resource_address(binding)
        if not _binding_owner_admitted(binding) or nested_owner_differs:
            raise ValueError(_REFUSAL)
        profile_resource_address(binding)
        constraint = constraints[path]
        if (
            constraint.document.semantic_profile != binding.coordinate.definition_digest
            or constraint.source_binding != realization_constraint_binding(constraint.document, binding.value)
        ):
            raise ValueError(_REFUSAL)


def _require_authority(
    authority: object, context: object
) -> tuple[PlanProfileAuthority, DomainProfileResolutionContextModel]:
    if not isinstance(authority, PlanProfileAuthority) or not isinstance(context, DomainProfileResolutionContextModel):
        raise ValueError(_REFUSAL)
    if not validate_realization_value((authority, context), python_carriers=True).conformant:
        raise ValueError(_REFUSAL)
    authority = PlanProfileAuthority.model_validate(authority.model_dump(mode="json"))
    context = DomainProfileResolutionContextModel.model_validate(context.model_dump(mode="json"))
    bindings = profile_binding_tree(authority.bindings)
    definitions = _require_constraint_and_definition_cover(authority, bindings)
    _require_resolvable_definitions(definitions, context)
    _require_binding_ownership(bindings, authority)
    if not admit_domain_profile_bindings(authority.bindings, context, policy=_POLICY).admitted:
        raise ValueError(_REFUSAL)
    return authority, context


def profile_authority_violation(authority: object, context: object) -> str | None:
    """Revalidate pinned input against separately configured local trust/support."""

    try:
        _require_authority(authority, context)
    except (AttributeError, TypeError, ValueError, RecursionError):
        return _REFUSAL
    return None


def profile_selection_violation(authority: object, bindings: object, context: object) -> str | None:
    """Conjoin every nested profile relation; absence and opaque data fail closed."""

    try:
        authority, context = _require_authority(authority, context)
        if type(bindings) is not tuple:
            raise ValueError(_REFUSAL)
        selected = profile_binding_tree(bindings)
        selected = {
            path: DomainProfileBindingModel.model_validate(value.model_dump(mode="json"))
            for path, value in selected.items()
        }
        original = profile_binding_tree(authority.bindings)
        if original.keys() != selected.keys():
            raise ValueError(_REFUSAL)
        for constraint in authority.constraints:
            before, after = original[constraint.binding_path], selected[constraint.binding_path]
            if (
                after.coordinate != before.coordinate
                or after.owner != before.owner
                or after.provenance.basis is not DomainProfileBindingBasis.BACKEND_SELECTED
                or not evaluate_realization_constraint(constraint.document, after.value).conformant
            ):
                raise ValueError(_REFUSAL)
        if not admit_domain_profile_bindings(bindings, context, policy=_POLICY).admitted:
            raise ValueError(_REFUSAL)
    except (AttributeError, TypeError, ValueError, RecursionError):
        return _REFUSAL
    return None


__all__ = [
    "PLAN_PROFILE_CONTRACT",
    "PlanProfileAuthority",
    "ProfileBindingConstraint",
    "profile_authority_violation",
    "profile_binding_tree",
    "profile_context_digest",
    "profile_resource_address",
    "profile_selection_violation",
]
