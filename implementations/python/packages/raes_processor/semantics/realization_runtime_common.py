"""Shared primitives for SEM-218 runtime realization evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.apparatus import (
    DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND,
    RealizationSupportDeclaration,
)
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.runtime_state import (
    RealizationObservationDisclosure,
    RealizationProvenanceEntry,
    RuntimeSnapshot,
)
from raes_contracts.vocabulary import (
    RealizationSupportMode,
    observation_strength_satisfies,
    verification_scope_satisfies,
)

from .realization_concerns import project_realization_concern
from .realization_snapshot_sanitization import invalid_observation_diagnostic

if TYPE_CHECKING:
    from raes_contracts.planning import ResolvedRealizationAuthority

    from .realization import CompiledRealizationRequirement

BACKEND_CONTRACT_INVALID = "runtime.backend-contract-invalid"
MISSING_CONCERN_VALUE = object()
OPERATING_SYSTEM_REQUIREMENT_KINDS = frozenset({"os-family", "os-distribution", "os-version"})


def matching_observation(
    requirement: CompiledRealizationRequirement | ResolvedRealizationAuthority,
    returned_snapshot: RuntimeSnapshot,
) -> RealizationObservationDisclosure | None:
    if requirement.requirement_kind in OPERATING_SYSTEM_REQUIREMENT_KINDS:
        return next(
            (
                entry
                for entry in returned_snapshot.realization_observations
                if entry.address == requirement.address
                and entry.domain == requirement.domain
                and entry.requirement_kind == "operating-system"
            ),
            None,
        )
    return next(
        (
            entry
            for entry in returned_snapshot.realization_observations
            if (
                entry.address,
                entry.field_path,
                entry.domain,
                entry.requirement_kind,
            )
            == (
                requirement.address,
                requirement.field_path,
                requirement.domain,
                requirement.requirement_kind,
            )
        ),
        None,
    )


def manifest_corroborates(
    requirement: CompiledRealizationRequirement,
    observation: RealizationObservationDisclosure,
    manifest: BackendManifest | None,
) -> bool:
    if manifest is None:
        return False
    capability_kind = (
        "operating-system"
        if requirement.requirement_kind in OPERATING_SYSTEM_REQUIREMENT_KINDS
        else requirement.requirement_kind
    )
    return any(
        (capability := declaration.observation_capabilities.get(capability_kind)) is not None
        and observation_posture_supported(requirement, declaration)
        and verification_scope_satisfies(capability.verification_scope, observation.verification_scope)
        and observation_strength_satisfies(capability.observation_strength, observation.observation_strength)
        for declaration in manifest.realization_support
        if declaration.domain == requirement.domain
    )


def observation_posture_supported(
    requirement: CompiledRealizationRequirement,
    declaration: RealizationSupportDeclaration,
) -> bool:
    if requirement.requirement_kind == "compute-substrate" and requirement.explicitness in {
        ExplicitnessClass.OPEN,
        ExplicitnessClass.CONSTRAINED,
    }:
        supported = requirement.requirement_kind in declaration.supported_constraint_kinds
    elif requirement.explicitness is ExplicitnessClass.OPEN:
        supported = declaration.support_mode is RealizationSupportMode.OPEN_REALIZATION
    elif requirement.explicitness is ExplicitnessClass.CONSTRAINED:
        supported = requirement.requirement_kind in declaration.supported_constraint_kinds
    else:
        supported = DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND in declaration.supported_exact_requirement_kinds
    return supported


def observed_projection(
    requirement: CompiledRealizationRequirement,
    realized_value: object,
) -> tuple[Diagnostic | None, object]:
    if realized_value is MISSING_CONCERN_VALUE:
        return None, MISSING_CONCERN_VALUE
    try:
        projection = project_realization_concern(
            requirement.requirement_kind,
            realized_value,
            observed=True,
            recursive=requirement.constraint_document is not None,
        )
    except (TypeError, ValueError):
        return invalid_observation_diagnostic(requirement), MISSING_CONCERN_VALUE
    return None, projection


def realization_provenance_entry(
    requirement: CompiledRealizationRequirement,
    honoured: bool,
) -> RealizationProvenanceEntry:
    return RealizationProvenanceEntry(
        address=requirement.address,
        field_path=requirement.field_path,
        domain=requirement.domain,
        requirement_kind=requirement.requirement_kind,
        explicitness=requirement.explicitness,
        provenance=(requirement.provenance if honoured else ExplicitnessProvenance.BACKEND_REALIZED),
        governing_scope=requirement.governing_scope,
    )


def silent_approximation_diagnostic(
    requirement: CompiledRealizationRequirement,
) -> Diagnostic:
    return Diagnostic(
        code=BACKEND_CONTRACT_INVALID,
        domain=requirement.domain,
        address=requirement.address,
        message=(
            f"Backend did not realize the exact '{requirement.requirement_kind}' requirement at "
            f"'{requirement.field_path}' as the author declared it (the realized value is absent "
            f"or differs); silent approximation or omission of an exact declaration is forbidden "
            f"(SEM-218 I2)."
        ),
        severity=Severity.ERROR,
    )


def concern_value(payload: dict[str, object], path: tuple[str, ...]) -> object:
    current: object = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return MISSING_CONCERN_VALUE
        current = current[key]
    return current


__all__ = [
    "BACKEND_CONTRACT_INVALID",
    "MISSING_CONCERN_VALUE",
    "OPERATING_SYSTEM_REQUIREMENT_KINDS",
    "concern_value",
    "manifest_corroborates",
    "matching_observation",
    "observation_posture_supported",
    "observed_projection",
    "realization_provenance_entry",
    "silent_approximation_diagnostic",
]
