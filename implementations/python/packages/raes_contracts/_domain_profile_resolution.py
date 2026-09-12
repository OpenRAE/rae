"""Exact offline resolution for caller-supplied domain-profile definitions."""

from __future__ import annotations

from dataclasses import dataclass

from ._domain_profile_contracts import (
    AdmittedDomainProfileDefinitionModel,
    DomainProfileCoordinateModel,
    DomainProfileDefinitionModel,
    DomainProfileDefinitionProvenanceModel,
    DomainProfileResolutionContextModel,
    DomainProfileResolutionOutcome,
)
from .diagnostics import Diagnostic


@dataclass(frozen=True, slots=True)
class DomainProfileDefinitionResolution:
    outcome: DomainProfileResolutionOutcome
    definition: DomainProfileDefinitionModel | None
    provenance: DomainProfileDefinitionProvenanceModel | None
    diagnostics: tuple[Diagnostic, ...]

    @property
    def resolved(self) -> bool:
        return self.outcome is DomainProfileResolutionOutcome.RESOLVED


class _ResolutionRefusal(RuntimeError):
    def __init__(self, resolution: DomainProfileDefinitionResolution) -> None:
        self.resolution = resolution
        super().__init__(resolution.outcome.value)


def _resolution_failure(
    outcome: DomainProfileResolutionOutcome,
    message: str,
) -> DomainProfileDefinitionResolution:
    return DomainProfileDefinitionResolution(
        outcome=outcome,
        definition=None,
        provenance=None,
        diagnostics=(
            Diagnostic(
                code=f"domain-profile.{outcome.value}",
                domain="domain-profile",
                address="#",
                message=message,
            ),
        ),
    )


def _refuse_resolution(outcome: DomainProfileResolutionOutcome, message: str) -> None:
    raise _ResolutionRefusal(_resolution_failure(outcome, message))


def _validate_namespace_authority(
    coordinate: DomainProfileCoordinateModel,
    context: DomainProfileResolutionContextModel,
) -> None:
    namespace_rows = [
        admission for admission in context.namespace_admissions if admission.namespace == coordinate.namespace
    ]
    admitted_authorities = {admission.authority for admission in namespace_rows}
    if len(admitted_authorities) > 1:
        _refuse_resolution(
            DomainProfileResolutionOutcome.NAMESPACE_COLLISION,
            "the profile namespace resolves to conflicting admitted authorities",
        )
    if admitted_authorities != {coordinate.authority}:
        _refuse_resolution(
            DomainProfileResolutionOutcome.NAMESPACE_UNADMITTED,
            "the profile namespace is not admitted for the requested authority",
        )


def _identity_matches(
    coordinate: DomainProfileCoordinateModel,
    context: DomainProfileResolutionContextModel,
) -> list[AdmittedDomainProfileDefinitionModel]:
    return [
        item
        for item in context.definitions
        if item.definition.coordinate.namespace == coordinate.namespace
        and item.definition.coordinate.authority == coordinate.authority
        and item.definition.coordinate.profile_id == coordinate.profile_id
    ]


def _select_exact_definition(
    coordinate: DomainProfileCoordinateModel,
    context: DomainProfileResolutionContextModel,
) -> AdmittedDomainProfileDefinitionModel:
    identity_matches = _identity_matches(coordinate, context)
    if not identity_matches:
        _refuse_resolution(
            DomainProfileResolutionOutcome.DEFINITION_UNAVAILABLE,
            "the requested profile definition is absent from the supplied local context",
        )

    revision_matches = [item for item in identity_matches if item.definition.coordinate.revision == coordinate.revision]
    if not revision_matches:
        _refuse_resolution(
            DomainProfileResolutionOutcome.INCOMPATIBLE_REVISION,
            "the supplied profile definitions do not contain the exact requested revision",
        )

    available_digests = {item.definition.coordinate.definition_digest for item in revision_matches}
    if len(available_digests) > 1:
        _refuse_resolution(
            DomainProfileResolutionOutcome.COORDINATE_COLLISION,
            "the same logical profile coordinate resolves to conflicting definition digests",
        )
    exact = [
        item
        for item in revision_matches
        if item.definition.coordinate.definition_digest == coordinate.definition_digest
    ]
    if not exact:
        _refuse_resolution(
            DomainProfileResolutionOutcome.DIGEST_MISMATCH,
            "the supplied profile definition digest does not match the exact request",
        )
    if len(exact) > 1:
        _refuse_resolution(
            DomainProfileResolutionOutcome.COORDINATE_COLLISION,
            "the exact profile coordinate resolves to multiple supplied definitions",
        )
    return exact[0]


def resolve_domain_profile_definition(
    coordinate: DomainProfileCoordinateModel,
    context: DomainProfileResolutionContextModel,
) -> DomainProfileDefinitionResolution:
    """Resolve one exact profile from supplied local data without discovery."""

    try:
        _validate_namespace_authority(coordinate, context)
        selected = _select_exact_definition(coordinate, context)
        resolution = DomainProfileDefinitionResolution(
            outcome=DomainProfileResolutionOutcome.RESOLVED,
            definition=selected.definition,
            provenance=selected.provenance,
            diagnostics=(),
        )
    except _ResolutionRefusal as exc:
        resolution = exc.resolution
    return resolution
