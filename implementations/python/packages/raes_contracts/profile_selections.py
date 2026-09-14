"""Typed selections on existing provisioning owners, using the shared host."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .domain_profiles import (
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingUse,
    DomainProfileResolutionContextModel,
)
from .realization_profiles import (
    PLAN_PROFILE_CONTRACT,
    PlanProfileAuthority,
    ProfileBindingConstraint,
    profile_binding_tree,
    profile_resource_address,
)
from .realization_structure import (
    RealizationClosure,
    normalize_realization_literal,
    realization_constraint_binding,
)


def profile_selection_binding(value: object) -> DomainProfileBindingModel | None:
    """Recognize a binding by its contract, independent of serialized defaults.

    An absent selection and the incumbent service mapping are separate
    alternatives. A mapping with binding fields must validate as a binding;
    adding a legacy service discriminator cannot hide a malformed binding.
    """

    if value is None:
        return None
    if isinstance(value, Mapping) and not value.keys() & DomainProfileBindingModel.model_fields.keys():
        if "interface_profile" in value or "target_service_ref" in value:
            return None
    return DomainProfileBindingModel.model_validate(value)


def _authored_domain_profile(resource: object, by_address: Mapping[str, object]) -> DomainProfileBindingModel | None:
    payload = resource.payload
    topology = payload.get("domain_topology") if isinstance(payload, Mapping) else None
    profile = topology.get("profile") if isinstance(topology, Mapping) else None
    if not isinstance(profile, (Mapping, DomainProfileBindingModel)):
        return None
    binding = DomainProfileBindingModel.model_validate(profile)
    owner_resource = by_address.get(profile_resource_address(binding))
    if owner_resource is None or owner_resource.resource_type != "domain-controller-placement":
        raise ValueError("Identity profile requires its existing controller-placement owner")
    if owner_resource.payload.get("domain_topology", {}).get("domain_id") != topology.get("domain_id"):
        raise ValueError("Identity profile cannot cross domain authority")
    return binding


def _authored_placement_profile(resource: object) -> DomainProfileBindingModel | None:
    selection = {
        "account-placement": ("materialization_profile", "account-materialization"),
        "generated-artifact": ("generator", "artifact-generation"),
        "content-placement": ("service_materialization", "service-materialization"),
    }.get(resource.resource_type)
    if selection is None:
        return None
    field_name, expected_context = selection
    payload = resource.payload
    spec = payload.get("spec") if isinstance(payload, Mapping) else None
    raw = spec.get(field_name) if isinstance(spec, Mapping) else None
    if raw is None or (field_name == "generator" and isinstance(raw, str)):
        return None
    binding = (
        profile_selection_binding(raw)
        if field_name == "service_materialization"
        else DomainProfileBindingModel.model_validate(raw)
    )
    if binding is not None:
        _require_selection_owner(binding, resource.address, expected_context)
    return binding


def authored_resource_profiles(resources: Iterable[object]) -> tuple[DomainProfileBindingModel, ...]:
    """Read only explicit typed selections at their closed core owner paths."""

    bindings = []
    resources = tuple(resources)
    by_address = {resource.address: resource for resource in resources}
    domains = {}
    for resource in resources:
        domain = _authored_domain_profile(resource, by_address)
        if domain is not None:
            domains[profile_resource_address(domain)] = domain
        binding = _authored_placement_profile(resource)
        if binding is not None:
            bindings.append(binding)
    for address, binding in domains.items():
        _require_selection_owner(binding, address, "identity-domain")
        bindings.append(binding)
    result = tuple(bindings)
    profile_binding_tree(result)
    return result


def _require_selection_owner(binding: DomainProfileBindingModel, address: str, expected_context: str) -> None:
    owner = binding.owner
    if (
        profile_resource_address(binding) != address
        or owner.owning_contract_id != PLAN_PROFILE_CONTRACT
        or owner.concept_family != "resource-realization"
        or owner.lifecycle_phase != "planning"
        or owner.context != expected_context
        or owner.use is not DomainProfileBindingUse.CONSTRAINT
        or binding.provenance.basis is not DomainProfileBindingBasis.AUTHOR_SUPPLIED
    ):
        raise ValueError("Authored profile selection does not match its core owner")


def selected_profile_authority(
    bindings: tuple[DomainProfileBindingModel, ...],
    context: DomainProfileResolutionContextModel | None,
    supplied: PlanProfileAuthority | None,
) -> PlanProfileAuthority | None:
    """Bind exact authored values to pinned definitions, never infer target support."""

    if not bindings:
        return supplied
    tree = profile_binding_tree(bindings)
    constraints = []
    for path, binding in tree.items():
        document = normalize_realization_literal(
            binding.value,
            semantic_profile=binding.coordinate.definition_digest,
            default_closure=RealizationClosure(
                posture="closed", universe="profile-value", profile="authored-profile-selection/v1"
            ),
        ).document
        constraints.append(
            ProfileBindingConstraint(
                binding_path=path,
                document=document,
                source_binding=realization_constraint_binding(document, binding.value),
            )
        )
    if supplied is not None:
        existing = profile_binding_tree(supplied.bindings)
        if any(existing.get(path) != item for path, item in tree.items()):
            raise ValueError("Programmatic authority contradicts an authored profile selection")
        supplied_constraints = {item.binding_path: item for item in supplied.constraints}
        if len(supplied_constraints) != len(supplied.constraints) or any(
            supplied_constraints.get(item.binding_path) != item for item in constraints
        ):
            raise ValueError("Programmatic constraint must preserve the exact authored selection")
        return supplied
    if context is None:
        raise ValueError("Required authored profiles have no independent target context")
    digests = {binding.coordinate.definition_digest for binding in tree.values()}
    definitions = tuple(item for item in context.definitions if item.definition.coordinate.definition_digest in digests)
    return PlanProfileAuthority(definitions=definitions, bindings=bindings, constraints=tuple(constraints))
