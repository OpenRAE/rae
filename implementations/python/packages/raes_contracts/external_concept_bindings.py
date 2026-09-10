"""Pure offline semantic admission for external concept-binding assertions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from .contracts import (
    ActivityStreamsActivityTypesSourceModel,
    AtlasTacticsSourceModel,
    AttackEnterpriseTacticsSourceModel,
    ExternalConceptBindingDocumentModel,
    ExternalConceptSchemeCoordinateModel,
    ExternalConceptSubjectModel,
    FipaCommunicativeActsSourceModel,
    NistCsfDefensiveCategorySourceModel,
)
from .contracts.base import ContractModel, NonEmptyString, PrefixedDigestString
from .diagnostics import Diagnostic, Severity
from .uri_safety import validate_safe_absolute_uri

_DOMAIN = "external-concept-binding"


class ExternalConceptResolutionOutcome(str, Enum):
    RESOLVED_CURRENT = "resolved-current"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    AMBIGUOUS = "ambiguous"
    SUPERSEDED = "superseded"
    UNKNOWN_CONCEPT = "unknown-concept"
    SUBJECT_NOT_FOUND = "subject-not-found"


class ExternalConceptSnapshotTermModel(ContractModel):
    concept_id: NonEmptyString
    status: Literal["current", "superseded"] = "current"
    successor_concept_ids: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_successors(self) -> ExternalConceptSnapshotTermModel:
        if self.status == "current" and self.successor_concept_ids:
            raise ValueError("current external concepts must not declare successors")
        if self.status == "superseded" and not self.successor_concept_ids:
            raise ValueError("superseded external concepts require successor_concept_ids")
        if len(self.successor_concept_ids) != len(set(self.successor_concept_ids)):
            raise ValueError("external concept successor ids must be unique")
        return self


class ExternalConceptSchemeSnapshotModel(ContractModel):
    """Neutral local resolver input adapted from one pinned external source."""

    scheme_id: NonEmptyString
    authority: NonEmptyString
    revision: NonEmptyString
    source_locator: NonEmptyString
    source_digest: PrefixedDigestString
    concepts: list[ExternalConceptSnapshotTermModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_locator(self) -> ExternalConceptSchemeSnapshotModel:
        validate_safe_absolute_uri(
            self.source_locator,
            field_name="external concept snapshot source_locator",
            forbidden_schemes={"file", "data"},
            forbid_fragment=True,
        )
        return self


@dataclass(frozen=True, slots=True)
class ExternalConceptBindingResolution:
    binding_id: str
    outcome: ExternalConceptResolutionOutcome
    active: bool
    resolved_concept_id: str | None
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class ExternalConceptBindingAdmissionReport:
    binding_set_id: str
    results: tuple[ExternalConceptBindingResolution, ...]

    @property
    def admitted(self) -> bool:
        return bool(self.results) and all(result.active for result in self.results)


def _diagnostic(
    code: str,
    address: str,
    message: str,
    *,
    severity: Severity = Severity.ERROR,
) -> Diagnostic:
    return Diagnostic(code=code, domain=_DOMAIN, address=address, message=message, severity=severity)


def _result(
    *,
    binding_id: str,
    outcome: ExternalConceptResolutionOutcome,
    address: str,
    message: str,
    resolved_concept_id: str | None = None,
    severity: Severity = Severity.ERROR,
) -> ExternalConceptBindingResolution:
    return ExternalConceptBindingResolution(
        binding_id=binding_id,
        outcome=outcome,
        active=outcome == ExternalConceptResolutionOutcome.RESOLVED_CURRENT,
        resolved_concept_id=resolved_concept_id,
        diagnostics=()
        if outcome == ExternalConceptResolutionOutcome.RESOLVED_CURRENT
        else (_diagnostic(f"external-concept.{outcome.value}", address, message, severity=severity),),
    )


def _subject_resolution(
    subject: ExternalConceptSubjectModel,
    candidates: tuple[ExternalConceptSubjectModel, ...],
    *,
    binding_id: str,
    address: str,
) -> ExternalConceptBindingResolution | None:
    exact = [candidate for candidate in candidates if candidate == subject]
    resolution: ExternalConceptBindingResolution | None
    if len(exact) > 1:
        resolution = _result(
            binding_id=binding_id,
            outcome=ExternalConceptResolutionOutcome.AMBIGUOUS,
            address=address,
            message="the exact RAES subject coordinate resolves to multiple supplied candidates",
        )
    elif len(exact) == 1:
        resolution = None
    else:
        same_coordinate = [
            candidate
            for candidate in candidates
            if (
                candidate.subject_kind == subject.subject_kind
                and candidate.owning_contract_id == subject.owning_contract_id
                and candidate.lifecycle_phase == subject.lifecycle_phase
                and candidate.canonical_ref == subject.canonical_ref
            )
        ]
        if same_coordinate:
            resolution = _result(
                binding_id=binding_id,
                outcome=ExternalConceptResolutionOutcome.STALE,
                address=address,
                message="the supplied RAES subject digest does not match the asserted artifact digest",
            )
        else:
            resolution = _result(
                binding_id=binding_id,
                outcome=ExternalConceptResolutionOutcome.SUBJECT_NOT_FOUND,
                address=address,
                message="the exact RAES subject coordinate is unavailable in the supplied local subject index",
            )
    return resolution


def _snapshot_matches_coordinate(
    snapshot: ExternalConceptSchemeSnapshotModel,
    scheme: ExternalConceptSchemeCoordinateModel,
) -> bool:
    return (
        snapshot.revision == scheme.revision
        and (scheme.source_locator is None or snapshot.source_locator == scheme.source_locator)
        and (scheme.source_digest is None or snapshot.source_digest.casefold() == scheme.source_digest.casefold())
    )


def _matching_scheme_snapshot(
    scheme: ExternalConceptSchemeCoordinateModel,
    snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...],
    *,
    binding_id: str,
    address: str,
) -> tuple[ExternalConceptSchemeSnapshotModel | None, ExternalConceptBindingResolution | None]:
    identity_matches = [
        snapshot
        for snapshot in snapshots
        if snapshot.scheme_id == scheme.scheme_id and snapshot.authority == scheme.authority
    ]
    snapshot: ExternalConceptSchemeSnapshotModel | None = None
    resolution: ExternalConceptBindingResolution | None = None
    if not identity_matches:
        resolution = _result(
            binding_id=binding_id,
            outcome=ExternalConceptResolutionOutcome.UNAVAILABLE,
            address=address,
            message="no matching local scheme snapshot was supplied; the assertion remains inactive",
            severity=Severity.WARNING,
        )
    else:
        exact = [candidate for candidate in identity_matches if _snapshot_matches_coordinate(candidate, scheme)]
        if not exact:
            resolution = _result(
                binding_id=binding_id,
                outcome=ExternalConceptResolutionOutcome.STALE,
                address=address,
                message="the supplied scheme snapshot conflicts with the asserted revision or digest",
            )
        elif len(exact) > 1:
            resolution = _result(
                binding_id=binding_id,
                outcome=ExternalConceptResolutionOutcome.AMBIGUOUS,
                address=address,
                message="the exact scheme coordinate resolves to multiple supplied snapshots",
            )
        else:
            snapshot = exact[0]
    return snapshot, resolution


def _concept_resolution(
    scheme: ExternalConceptSchemeCoordinateModel,
    snapshot: ExternalConceptSchemeSnapshotModel,
    *,
    binding_id: str,
    address: str,
) -> ExternalConceptBindingResolution:
    concept_candidates = [term for term in snapshot.concepts if term.concept_id == scheme.concept_id]
    if not concept_candidates:
        resolution = _result(
            binding_id=binding_id,
            outcome=ExternalConceptResolutionOutcome.UNKNOWN_CONCEPT,
            address=address,
            message="the asserted concept is absent from the exact supplied scheme revision",
        )
    elif len(concept_candidates) > 1:
        resolution = _result(
            binding_id=binding_id,
            outcome=ExternalConceptResolutionOutcome.AMBIGUOUS,
            address=address,
            message="the asserted concept resolves to multiple candidates in the exact supplied scheme revision",
        )
    else:
        term = concept_candidates[0]
        if term.status == "superseded":
            resolution = _result(
                binding_id=binding_id,
                outcome=ExternalConceptResolutionOutcome.SUPERSEDED,
                address=address,
                message="the original concept is superseded; automatic successor rewriting is forbidden",
                resolved_concept_id=scheme.concept_id,
            )
        else:
            resolution = _result(
                binding_id=binding_id,
                outcome=ExternalConceptResolutionOutcome.RESOLVED_CURRENT,
                address=address,
                message="resolved",
                resolved_concept_id=scheme.concept_id,
            )
    return resolution


def _scheme_resolution(
    scheme: ExternalConceptSchemeCoordinateModel,
    snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...],
    *,
    binding_id: str,
    address: str,
) -> ExternalConceptBindingResolution:
    snapshot, resolution = _matching_scheme_snapshot(
        scheme,
        snapshots,
        binding_id=binding_id,
        address=address,
    )
    if resolution is None:
        assert snapshot is not None
        resolution = _concept_resolution(
            scheme,
            snapshot,
            binding_id=binding_id,
            address=address,
        )
    return resolution


def admit_external_concept_bindings(
    document: ExternalConceptBindingDocumentModel,
    *,
    subjects: tuple[ExternalConceptSubjectModel, ...],
    scheme_snapshots: tuple[ExternalConceptSchemeSnapshotModel, ...],
) -> ExternalConceptBindingAdmissionReport:
    """Resolve a structurally admitted document using only explicit local inputs."""

    results: list[ExternalConceptBindingResolution] = []
    for position, binding_id in enumerate(sorted(document.bindings)):
        binding = document.bindings[binding_id]
        address = f"/bindings/{position}"
        subject_result = _subject_resolution(
            binding.subject,
            subjects,
            binding_id=binding_id,
            address=f"{address}/subject",
        )
        if subject_result is not None:
            results.append(subject_result)
            continue
        results.append(
            _scheme_resolution(
                binding.scheme,
                scheme_snapshots,
                binding_id=binding_id,
                address=f"{address}/scheme",
            )
        )
    return ExternalConceptBindingAdmissionReport(binding_set_id=document.binding_set_id, results=tuple(results))


def adapt_attack_enterprise_tactics_snapshot(
    source: AttackEnterpriseTacticsSourceModel,
) -> ExternalConceptSchemeSnapshotModel:
    return ExternalConceptSchemeSnapshotModel(
        scheme_id="mitre-attack-enterprise-tactics",
        authority=source.source_authority,
        revision=source.source_version,
        source_locator=source.source_url,
        source_digest=source.source_digest,
        concepts=[ExternalConceptSnapshotTermModel(concept_id=term.tactic_id) for term in source.tactics],
    )


def adapt_atlas_tactics_snapshot(source: AtlasTacticsSourceModel) -> ExternalConceptSchemeSnapshotModel:
    """Project the pinned ATLAS source through the same scheme-neutral boundary."""
    return ExternalConceptSchemeSnapshotModel(
        scheme_id="mitre-atlas-tactics",
        authority=source.source_authority,
        revision=source.source_version,
        source_locator=source.source_url,
        source_digest=source.source_digest,
        concepts=[ExternalConceptSnapshotTermModel(concept_id=term.tactic_id) for term in source.tactics],
    )


def adapt_nist_csf_defensive_categories_snapshot(
    source: NistCsfDefensiveCategorySourceModel,
) -> ExternalConceptSchemeSnapshotModel:
    return ExternalConceptSchemeSnapshotModel(
        scheme_id="nist-csf-defensive-categories",
        authority=source.source_authority,
        revision=source.source_version,
        source_locator=source.source_url,
        source_digest=source.source_digest,
        concepts=[ExternalConceptSnapshotTermModel(concept_id=term.category_id) for term in source.categories],
    )


def adapt_activitystreams_activity_types_snapshot(
    source: ActivityStreamsActivityTypesSourceModel,
) -> ExternalConceptSchemeSnapshotModel:
    return ExternalConceptSchemeSnapshotModel(
        scheme_id="w3c-activitystreams-activity-types",
        authority=source.source_authority,
        revision=source.source_version,
        source_locator=source.source_url,
        source_digest=source.source_digest,
        concepts=[ExternalConceptSnapshotTermModel(concept_id=term.concept_id) for term in source.activity_types],
    )


def adapt_fipa_communicative_acts_snapshot(
    source: FipaCommunicativeActsSourceModel,
) -> ExternalConceptSchemeSnapshotModel:
    return ExternalConceptSchemeSnapshotModel(
        scheme_id="fipa-communicative-act-library",
        authority=source.source_authority,
        revision=source.source_version,
        source_locator=source.source_url,
        source_digest=source.source_digest,
        concepts=[ExternalConceptSnapshotTermModel(concept_id=act.concept_id) for act in source.communicative_acts],
    )


__all__ = [
    "ExternalConceptBindingAdmissionReport",
    "ExternalConceptBindingResolution",
    "ExternalConceptResolutionOutcome",
    "ExternalConceptSchemeSnapshotModel",
    "ExternalConceptSnapshotTermModel",
    "adapt_activitystreams_activity_types_snapshot",
    "adapt_attack_enterprise_tactics_snapshot",
    "adapt_atlas_tactics_snapshot",
    "adapt_fipa_communicative_acts_snapshot",
    "adapt_nist_csf_defensive_categories_snapshot",
    "admit_external_concept_bindings",
]
