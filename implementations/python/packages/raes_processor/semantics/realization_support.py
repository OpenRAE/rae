"""Manifest admission for compiled SEM-218 realization requirements."""

from __future__ import annotations

from raes.explicitness import ExplicitnessClass
from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.apparatus import (
    DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND,
    RealizationSupportDeclaration,
)
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.realization_structure import RealizationCollection, RealizationRecord
from raes_contracts.vocabulary import RealizationSupportMode

from .realization_apparatus_defaults import (
    ApparatusRealizationDefaultResolver,
    effective_realization_explicitness,
)
from .realization_concerns import realization_concern_descriptor
from .realization_observation_admission import has_required_observation_support
from .realization_process_limits import process_resource_limit_support_diagnostic
from .realization_requirement import CompiledRealizationRequirement


def realization_support_diagnostics(
    requirements: tuple[CompiledRealizationRequirement, ...],
    manifest: BackendManifest,
    *,
    apparatus_default: ApparatusRealizationDefaultResolver | None = None,
) -> list[Diagnostic]:
    """Match compiled requirements against one manifest's realization support."""

    return [
        diagnostic
        for requirement in requirements
        if (
            diagnostic := _realization_support_diagnostic(
                requirement,
                manifest,
                apparatus_default,
            )
        )
        is not None
    ]


def _realization_support_diagnostic(
    requirement: CompiledRealizationRequirement,
    manifest: BackendManifest,
    apparatus_default: ApparatusRealizationDefaultResolver | None,
) -> Diagnostic | None:
    explicitness = effective_realization_explicitness(requirement, manifest, apparatus_default)
    declarations = [
        declaration for declaration in manifest.realization_support if declaration.domain == requirement.domain
    ]
    if requirement.requirement_kind == "process-resource-limits":
        process_diagnostic = process_resource_limit_support_diagnostic(
            requirement, declarations, explicitness, manifest.realization_envelope
        )
        if process_diagnostic is not None:
            return process_diagnostic
    if isinstance(requirement.structure, (RealizationCollection, RealizationRecord)) or (
        requirement.constraint_document is not None
        and requirement.constraint_document.root.kind in {"recursive-record", "keyed-collection", "sequence"}
    ):
        exact_diagnostic = _exact_support_diagnostic(requirement, declarations)
        if exact_diagnostic is not None:
            return exact_diagnostic
    if requirement.requirement_kind == "process-resource-limits":
        diagnostic = None
    elif explicitness is ExplicitnessClass.OPEN:
        diagnostic = _open_support_diagnostic(requirement, declarations)
    elif explicitness is ExplicitnessClass.EXACT:
        diagnostic = _exact_support_diagnostic(requirement, declarations)
    elif explicitness is ExplicitnessClass.CONSTRAINED:
        diagnostic = _constraint_support_diagnostic(requirement, declarations)
    else:
        diagnostic = None
    return diagnostic


def _observation_kind(requirement: CompiledRealizationRequirement) -> str:
    return (
        "operating-system"
        if requirement.requirement_kind in {"os-family", "os-distribution", "os-version"}
        else requirement.requirement_kind
    )


def _open_support_diagnostic(
    requirement: CompiledRealizationRequirement,
    declarations: list[RealizationSupportDeclaration],
) -> Diagnostic | None:
    diagnostic = None
    if requirement.requirement_kind != "compute-substrate":
        supporting = [
            declaration
            for declaration in declarations
            if declaration.support_mode is RealizationSupportMode.OPEN_REALIZATION
        ]
        if supporting:
            sufficiently_observed = requirement.verification_scope is None or has_required_observation_support(
                requirement,
                supporting,
                observation_kind=_observation_kind(requirement),
            )
            if not sufficiently_observed:
                diagnostic = _under_observed_support_diagnostic(requirement, posture="open")
        else:
            diagnostic = Diagnostic(
                code="realization.unsupported-open-requirement",
                domain=requirement.domain,
                address=requirement.address,
                message=(
                    "Backend declares no open realization support for "
                    f"'{requirement.requirement_kind}' requirement at "
                    f"'{requirement.field_path}' in domain '{requirement.domain}'."
                ),
                severity=Severity.ERROR,
            )
    return diagnostic


def _exact_support_diagnostic(
    requirement: CompiledRealizationRequirement,
    declarations: list[RealizationSupportDeclaration],
) -> Diagnostic | None:
    descriptor = realization_concern_descriptor(requirement.requirement_kind)
    requires_concern_specific_support = bool(
        descriptor is not None
        and descriptor.authored_path[:1] == ("runtime",)
        and requirement.requirement_kind != "process-resource-limits"
    )
    exact_declarations = [
        declaration
        for declaration in declarations
        if DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND in declaration.supported_exact_requirement_kinds
        and (
            not requires_concern_specific_support
            or requirement.requirement_kind in declaration.supported_exact_requirement_kinds
        )
    ]
    if not exact_declarations:
        return Diagnostic(
            code="realization.unsupported-exact-requirement",
            domain=requirement.domain,
            address=requirement.address,
            message=(
                "Backend declares no generic and concern-specific exact realization support "
                f"('{DECLARED_CAPABILITY_MATCH_REQUIREMENT_KIND}') for exact "
                f"'{requirement.requirement_kind}' requirement at '{requirement.field_path}' "
                f"in domain '{requirement.domain}'."
            ),
            severity=Severity.ERROR,
        )
    if requirement.verification_scope is None or has_required_observation_support(
        requirement,
        exact_declarations,
        observation_kind=_observation_kind(requirement),
    ):
        return None
    return _under_observed_support_diagnostic(requirement, posture="exact")


def _constraint_support_diagnostic(
    requirement: CompiledRealizationRequirement,
    declarations: list[RealizationSupportDeclaration],
) -> Diagnostic | None:
    supporting = [
        declaration
        for declaration in declarations
        if requirement.requirement_kind in declaration.supported_constraint_kinds
    ]
    if not supporting:
        return Diagnostic(
            code="realization.unsupported-constraint-requirement",
            domain=requirement.domain,
            address=requirement.address,
            message=(
                "Backend declares no constraint realization support "
                f"for constraint kind '{requirement.requirement_kind}' at "
                f"'{requirement.field_path}' in domain '{requirement.domain}'."
            ),
            severity=Severity.ERROR,
        )
    if requirement.verification_scope is not None and not has_required_observation_support(
        requirement,
        supporting,
        observation_kind=_observation_kind(requirement),
    ):
        return _under_observed_support_diagnostic(requirement, posture="constraint")
    return None


def _under_observed_support_diagnostic(
    requirement: CompiledRealizationRequirement,
    *,
    posture: str,
) -> Diagnostic:
    return Diagnostic(
        code=f"realization.under-observed-{posture}-requirement",
        domain=requirement.domain,
        address=requirement.address,
        message=(
            f"Backend declares no '{requirement.verification_scope.value}' corroboration "
            f"for {posture} '{requirement.requirement_kind}' requirement at "
            f"'{requirement.field_path}' in domain '{requirement.domain}'."
        ),
        severity=Severity.ERROR,
    )


__all__ = ["realization_support_diagnostics"]
