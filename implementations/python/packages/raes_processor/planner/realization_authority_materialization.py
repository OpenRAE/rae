"""Materialize compiler realization posture into portable plan authority."""

from __future__ import annotations

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.bounded_domains import EnumDomain
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import (
    RealizationAuthorityBound,
    RealizationAuthorityMode,
    ResolvedRealizationAuthority,
)
from raes_contracts.vocabulary import Closure

from ..models import RuntimeModel
from ..semantics.realization import (
    ApparatusRealizationDecisions,
    ApparatusRealizationDefaultResolver,
    CompiledRealizationAuthority,
    CompiledRealizationRequirement,
)
from .operating_system_capability_domains import feasible_operating_system_domains

# These concerns are validated against closed semantic vocabularies before
# capability constraints are compiled, so their finite domains are safe to
# publish. Generic variable/value constraints are deliberately excluded.
_PUBLICATION_SAFE_CAPABILITY_CONCERN_BY_KIND = {
    "os-family": "nodes.os",
    "os-distribution": "nodes.os_distribution",
    "os-version": "nodes.os_version",
    "node-architecture": "nodes.architecture",
}


def _payload_pointer(path: tuple[str, ...]) -> str:
    return "/" + "/".join(token.replace("~", "~0").replace("/", "~1") for token in path)


def _matching_requirement(
    requirements: tuple[CompiledRealizationRequirement, ...],
    authority: CompiledRealizationAuthority,
) -> CompiledRealizationRequirement | None:
    return next(
        (
            requirement
            for requirement in requirements
            if (requirement.address, requirement.requirement_kind, requirement.field_path)
            == (authority.address, authority.requirement_kind, authority.field_path)
        ),
        None,
    )


def _resolved_mode(
    authority: CompiledRealizationAuthority,
    requirement: CompiledRealizationRequirement | None,
    manifest: BackendManifest,
    apparatus_default: ApparatusRealizationDefaultResolver | None,
    apparatus_decisions: ApparatusRealizationDecisions | None,
) -> RealizationAuthorityMode:
    if not authority.delegated:
        return authority.mode
    if requirement is None:
        raise ValueError("delegated realization authority requires a matching compiled demand")
    if apparatus_decisions is not None:
        identity = (requirement.address, requirement.field_path, requirement.requirement_kind)
        try:
            closure = apparatus_decisions[identity]
        except KeyError as exc:
            raise ValueError("delegated realization authority has no resolved apparatus decision") from exc
    else:
        closure = apparatus_default(requirement, manifest) if apparatus_default is not None else Closure.CLOSED_WORLD
    return RealizationAuthorityMode.OPEN if closure is Closure.OPEN_WORLD else RealizationAuthorityMode.CLOSED


def _publication_safe_enum_domain(values: tuple[object, ...]) -> EnumDomain | None:
    if not values or any(not isinstance(value, (str, int, float, bool)) for value in values):
        return None
    return EnumDomain(values=list(values))  # type: ignore[arg-type]


def _authority_bounds(
    model: RuntimeModel,
    authority: CompiledRealizationAuthority,
    requirement: CompiledRealizationRequirement | None,
    manifest: BackendManifest,
) -> tuple[RealizationAuthorityBound, ...]:
    if (
        requirement is not None
        and requirement.requirement_kind == "process-resource-limits"
        and requirement.value_constraints
    ):
        return _process_limit_authority_bounds(requirement)
    if authority.requirement_kind in {"os-family", "os-distribution", "os-version"}:
        return _operating_system_authority_bounds(model, authority, manifest)
    return _capability_authority_bounds(model, authority)


def _process_limit_authority_bounds(
    requirement: CompiledRealizationRequirement,
) -> tuple[RealizationAuthorityBound, ...]:
    bounds: list[RealizationAuthorityBound] = []
    for constraint in requirement.value_constraints:
        domain = _publication_safe_enum_domain(constraint.allowed_values)
        if domain is None:
            return ()
        bounds.append(
            RealizationAuthorityBound(
                identity_digest=constraint.identity_digest,
                value_pointer=f"/{constraint.leaf}",
                domain=domain,
            )
        )
    return tuple(bounds)


def _operating_system_authority_bounds(
    model: RuntimeModel,
    authority: CompiledRealizationAuthority,
    manifest: BackendManifest,
) -> tuple[RealizationAuthorityBound, ...]:
    node = model.node_deployments.get(authority.address)
    feasible, diagnostic = (
        feasible_operating_system_domains(model, node, manifest.provisioner)
        if node is not None and manifest.provisioner is not None
        else (None, None)
    )
    domain = (
        _publication_safe_enum_domain(feasible.values_for(authority.requirement_kind))
        if diagnostic is None and feasible is not None
        else None
    )
    return (RealizationAuthorityBound(value_pointer="", domain=domain),) if domain is not None else ()


def _capability_authority_bounds(
    model: RuntimeModel,
    authority: CompiledRealizationAuthority,
) -> tuple[RealizationAuthorityBound, ...]:
    concern = _PUBLICATION_SAFE_CAPABILITY_CONCERN_BY_KIND.get(authority.requirement_kind)
    constraint = next(
        (
            item
            for item in model.capability_constraints
            if item.address == authority.address and item.concern == concern
        ),
        None,
    )
    domain = _publication_safe_enum_domain(constraint.allowed_values) if constraint is not None else None
    return (RealizationAuthorityBound(value_pointer="", domain=domain),) if domain is not None else ()


def materialize_realization_authority(
    model: RuntimeModel,
    manifest: BackendManifest,
    *,
    apparatus_default: ApparatusRealizationDefaultResolver | None = None,
    apparatus_decisions: ApparatusRealizationDecisions | None = None,
) -> tuple[tuple[ResolvedRealizationAuthority, ...], list[Diagnostic]]:
    """Resolve delegation and safe bounds without serializing compiler demands."""

    resolved: list[ResolvedRealizationAuthority] = []
    diagnostics: list[Diagnostic] = []
    for authority in model.realization_authority:
        requirement = _matching_requirement(model.realization_requirements, authority)
        if requirement is not None and (requirement.structure_error or requirement.recursive_pending):
            diagnostics.append(_unsafe_bound_diagnostic(authority))
            continue
        try:
            mode = _resolved_mode(
                authority,
                requirement,
                manifest,
                apparatus_default,
                apparatus_decisions,
            )
        except ValueError:
            diagnostics.append(_unresolved_authority_diagnostic(authority))
            continue
        bounds = (
            _authority_bounds(model, authority, requirement, manifest)
            if mode is RealizationAuthorityMode.CONSTRAINED
            else ()
        )
        if (
            mode is RealizationAuthorityMode.CONSTRAINED
            and not bounds
            and (requirement is None or requirement.constraint_document is None)
        ):
            diagnostics.append(_unsafe_bound_diagnostic(authority))
            continue
        resolved.append(
            ResolvedRealizationAuthority(
                address=authority.address,
                field_path=authority.field_path,
                domain=authority.domain,
                requirement_kind=authority.requirement_kind,
                payload_pointer=_payload_pointer(authority.payload_path),
                mode=mode,
                source=authority.source,
                provenance=authority.provenance,
                governing_scope=authority.governing_scope,
                bounds=bounds,
                verification_scope=authority.verification_scope,
                required_observation_strength=authority.required_observation_strength,
                structure=requirement.structure if requirement is not None else None,
                constraint_document=requirement.constraint_document if requirement is not None else None,
                constraint_binding=requirement.constraint_binding if requirement is not None else None,
            )
        )
    return tuple(resolved), diagnostics


def _unresolved_authority_diagnostic(authority: CompiledRealizationAuthority) -> Diagnostic:
    return Diagnostic(
        code="realization.authority-unresolved",
        domain=authority.domain,
        address=authority.address,
        message=f"Resolved realization authority is unavailable for '{authority.requirement_kind}'.",
    )


def _unsafe_bound_diagnostic(authority: CompiledRealizationAuthority) -> Diagnostic:
    return Diagnostic(
        code="realization.authority-bound-unavailable",
        domain=authority.domain,
        address=authority.address,
        message=(
            f"No publication-safe typed author bound is available for '{authority.requirement_kind}' "
            f"at '{authority.field_path}'. This mixed demand needs an owning collection identity "
            "and representable leaf bounds; use supported bounded forms or extend the concern contract."
        ),
    )


__all__ = ["materialize_realization_authority"]
