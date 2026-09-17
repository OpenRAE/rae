"""Normative SDL lineage and third-party provenance contracts."""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import ContractModel, NonEmptyString
from .corpus import PROVENANCE, corpus_family_root
from .versions import SDL_LINEAGE_LEDGER_SCHEMA_VERSION

PublicUrl = Annotated[str, Field(pattern=r"^https://[^\s]+$")]
Sha1 = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
FragmentPointer = Annotated[str, Field(pattern=r"^#[^\s]*$")]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class LineageSourceKind(str, Enum):
    GIT = "git"
    STANDARD = "standard"
    PUBLICATION = "publication"


class LineagePlane(str, Enum):
    SYNTAX = "syntax"
    SEMANTICS = "semantics"
    ARTIFACT_CODE = "artifact_code"
    EXAMPLE = "example"


class LineageClassification(str, Enum):
    ADOPTED_SYNTAX = "adopted_syntax"
    ADOPTED_SEMANTICS = "adopted_semantics"
    ADAPTED = "adapted"
    RAES_NATIVE = "raes_native"


class LineageDisposition(str, Enum):
    CURRENT = "current"
    REMOVED = "removed"
    PLANNED = "planned"


class CompatibilityStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    NONE = "none"
    PARTIAL = "partial"
    COMPATIBLE = "compatible"


class CompatibilityDirection(str, Enum):
    RAES_RELATIVE_TO_SOURCE = "raes_relative_to_source"
    NOT_APPLICABLE = "not_applicable"


class NoticeDecision(str, Enum):
    REQUIRED_INCLUDED = "required_included"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"


class BibliographicIdentityModel(ContractModel):
    citation_id: NonEmptyString
    title: NonEmptyString
    authors_or_maintainer: list[NonEmptyString] = Field(min_length=1)
    year: int = Field(ge=1800, le=2200)
    container_title: NonEmptyString | None = None
    doi: Annotated[str, Field(pattern=r"^10\.\d{4,9}/\S+$")] | None = None
    canonical_url: PublicUrl
    verified_on: IsoDate
    verification_evidence: NonEmptyString


class LineageSourceCaptureModel(ContractModel):
    artifact: NonEmptyString
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    scope: NonEmptyString


class LineageSourceBaseModel(ContractModel):
    source_id: NonEmptyString
    title: NonEmptyString
    version_or_edition: NonEmptyString
    canonical_url: PublicUrl
    citation_ref: NonEmptyString
    archival_capture: LineageSourceCaptureModel | None = None

    @model_validator(mode="after")
    def require_immutable_document_identity(self) -> LineageSourceBaseModel:
        mutable_identity = re.search(r"\b(?:reviewed|capture)\b", self.version_or_edition, re.IGNORECASE)
        floating_url = re.search(r"/(?:blob|tree)/(?:main|master|latest)(?:/|$)", self.canonical_url)
        if (mutable_identity or floating_url) and self.archival_capture is None:
            raise ValueError("a living source needs an immutable revision or digest-bound archival capture")
        return self


class GitLineageSourceModel(LineageSourceBaseModel):
    kind: Literal[LineageSourceKind.GIT]
    repository_url: PublicUrl
    commit: Sha1
    license_expression: NonEmptyString | None = None
    license_url: PublicUrl | None = None
    license_evidence_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_revision_urls(self) -> GitLineageSourceModel:
        if self.commit not in self.canonical_url:
            raise ValueError("git canonical_url must contain the declared commit")
        if self.license_url is not None and self.commit not in self.license_url:
            raise ValueError("git license_url must contain the declared commit")
        return self


class StandardLineageSourceModel(LineageSourceBaseModel):
    kind: Literal[LineageSourceKind.STANDARD]
    maintaining_body: NonEmptyString


class PublicationLineageSourceModel(LineageSourceBaseModel):
    kind: Literal[LineageSourceKind.PUBLICATION]


LineageSource = Annotated[
    GitLineageSourceModel | StandardLineageSourceModel | PublicationLineageSourceModel,
    Field(discriminator="kind"),
]


class AuthorityCoordinateModel(ContractModel):
    artifact: NonEmptyString
    pointer: FragmentPointer
    contract_id: NonEmptyString | None = None


class ArtifactBoundaryModel(ContractModel):
    artifact: NonEmptyString
    symbol_or_pointer: NonEmptyString


class LineageClaimModel(ContractModel):
    plane: LineagePlane
    classification: LineageClassification
    source_refs: list[NonEmptyString] = Field(default_factory=list)
    raes_boundaries: list[ArtifactBoundaryModel] = Field(min_length=1)
    source_boundaries: list[ArtifactBoundaryModel] = Field(default_factory=list)
    divergence: NonEmptyString
    compatibility: CompatibilityStatus
    compatibility_direction: CompatibilityDirection
    citation_refs: list[NonEmptyString] = Field(default_factory=list)
    internal_authority_refs: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_claim_dimensions(self) -> LineageClaimModel:
        if self.classification is LineageClassification.RAES_NATIVE:
            self._validate_native_dimensions()
        else:
            self._validate_external_dimensions()
        return self

    def _validate_native_dimensions(self) -> None:
        if self.source_refs or self.source_boundaries:
            raise ValueError("RAES-native claims must not name an external source boundary")
        if not self.internal_authority_refs:
            raise ValueError("RAES-native claims require internal authority refs")
        if self.compatibility is not CompatibilityStatus.NOT_APPLICABLE:
            raise ValueError("RAES-native claims have no source compatibility relation")
        if self.compatibility_direction is not CompatibilityDirection.NOT_APPLICABLE:
            raise ValueError("RAES-native claims have no source compatibility direction")

    def _validate_external_dimensions(self) -> None:
        if not self.source_refs or not self.source_boundaries or not self.citation_refs:
            raise ValueError("non-native claims require source, source boundary, and citation refs")
        if self.classification is LineageClassification.ADOPTED_SYNTAX and self.plane is not LineagePlane.SYNTAX:
            raise ValueError("adopted_syntax is valid only on the syntax plane")
        if self.classification is LineageClassification.ADOPTED_SEMANTICS and self.plane is not LineagePlane.SEMANTICS:
            raise ValueError("adopted_semantics is valid only on the semantics plane")
        if self.compatibility_direction is not CompatibilityDirection.RAES_RELATIVE_TO_SOURCE:
            raise ValueError("non-native claims assess RAES relative to the named source")


class LineageSubjectModel(ContractModel):
    subject_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*:[a-z][a-z0-9_-]*$")]
    subject_kind: Literal["top_level_field", "runtime_family", "concept_family", "reference_model"]
    disposition: LineageDisposition
    authority: AuthorityCoordinateModel
    claims: list[LineageClaimModel] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_subject_namespace(self) -> LineageSubjectModel:
        expected_namespace = {
            "top_level_field": "sdl-field",
            "runtime_family": "runtime-family",
            "concept_family": "concept-family",
            "reference_model": "reference-model",
        }[self.subject_kind]
        namespace = self.subject_id.split(":", 1)[0]
        if namespace != expected_namespace:
            raise ValueError(f"subject namespace {namespace!r} does not match subject_kind {self.subject_kind!r}")
        return self


class ThirdPartyDispositionModel(ContractModel):
    source_ref: NonEmptyString
    derivation_scope: list[ArtifactBoundaryModel] = Field(min_length=1)
    derivation_extent: NonEmptyString
    reviewed_license_ref: NonEmptyString
    notice_decision: NoticeDecision
    notice_artifact: NonEmptyString | None = None
    rationale: NonEmptyString
    reviewed_on: IsoDate
    evidence_refs: list[NonEmptyString] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_notice_resolution(self) -> ThirdPartyDispositionModel:
        if self.notice_decision is NoticeDecision.REQUIRED_INCLUDED and self.notice_artifact is None:
            raise ValueError("required notice disposition must name notice_artifact")
        if self.notice_decision is not NoticeDecision.REQUIRED_INCLUDED and self.notice_artifact is not None:
            raise ValueError("notice_artifact is valid only when a required notice is included")
        return self


class SDLLineageLedgerModel(ContractModel):
    schema_version: Literal[SDL_LINEAGE_LEDGER_SCHEMA_VERSION] = SDL_LINEAGE_LEDGER_SCHEMA_VERSION
    reviewed_on: IsoDate
    citations: list[BibliographicIdentityModel] = Field(min_length=1)
    sources: list[LineageSource] = Field(min_length=1)
    subjects: list[LineageSubjectModel] = Field(min_length=1)
    third_party_dispositions: list[ThirdPartyDispositionModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ledger_references(self) -> SDLLineageLedgerModel:
        citation_ids = self._unique_ids("citation", [item.citation_id for item in self.citations])
        source_ids = self._unique_ids("source", [item.source_id for item in self.sources])
        source_citations = {item.source_id: item.citation_ref for item in self.sources}
        self._unique_ids("subject", [item.subject_id for item in self.subjects])
        self._unique_ids(
            "third-party disposition source",
            [item.source_ref for item in self.third_party_dispositions],
        )
        disposition_sources = {item.source_ref for item in self.third_party_dispositions}
        disposition_artifacts = {
            item.source_ref: {boundary.artifact for boundary in item.derivation_scope}
            for item in self.third_party_dispositions
        }
        resolved_disposition_sources = {
            item.source_ref
            for item in self.third_party_dispositions
            if item.notice_decision is not NoticeDecision.UNKNOWN
        }
        for source in self.sources:
            if source.citation_ref not in citation_ids:
                raise ValueError(f"source {source.source_id!r} has unknown citation_ref")
        for subject in self.subjects:
            self._validate_subject(
                subject,
                source_ids,
                source_citations,
                citation_ids,
                disposition_sources,
                resolved_disposition_sources,
                disposition_artifacts,
            )
        for disposition in self.third_party_dispositions:
            if disposition.source_ref not in source_ids:
                raise ValueError(f"third-party disposition has unknown source_ref {disposition.source_ref!r}")
        return self

    @staticmethod
    def _unique_ids(label: str, values: list[str]) -> set[str]:
        if len(set(values)) != len(values):
            raise ValueError(f"{label} ids must be unique")
        return set(values)

    @staticmethod
    def _validate_subject(
        subject: LineageSubjectModel,
        source_ids: set[str],
        source_citations: dict[str, str],
        citation_ids: set[str],
        disposition_sources: set[str],
        resolved_disposition_sources: set[str],
        disposition_artifacts: dict[str, set[str]],
    ) -> None:
        for claim in subject.claims:
            SDLLineageLedgerModel._validate_claim_references(
                subject.subject_id,
                claim,
                source_ids,
                source_citations,
                citation_ids,
            )
            SDLLineageLedgerModel._validate_artifact_code_claim(
                subject.subject_id,
                claim,
                disposition_sources,
                resolved_disposition_sources,
                disposition_artifacts,
            )
            SDLLineageLedgerModel._validate_planned_compatibility(subject, claim)

    @staticmethod
    def _validate_claim_references(
        subject_id: str,
        claim: LineageClaimModel,
        source_ids: set[str],
        source_citations: dict[str, str],
        citation_ids: set[str],
    ) -> None:
        if set(claim.source_refs) - source_ids:
            raise ValueError(f"subject {subject_id!r} has unknown source refs")
        if set(claim.citation_refs) - citation_ids:
            raise ValueError(f"subject {subject_id!r} has unknown citation refs")
        expected_citations = {source_citations[source_ref] for source_ref in claim.source_refs}
        if set(claim.citation_refs) != expected_citations:
            raise ValueError(f"subject {subject_id!r} claim citation refs do not identify its sources")

    @staticmethod
    def _validate_artifact_code_claim(
        subject_id: str,
        claim: LineageClaimModel,
        disposition_sources: set[str],
        resolved_disposition_sources: set[str],
        disposition_artifacts: dict[str, set[str]],
    ) -> None:
        if claim.plane is not LineagePlane.ARTIFACT_CODE:
            return
        claim_sources = set(claim.source_refs)
        if not claim_sources.issubset(disposition_sources):
            raise ValueError(f"subject {subject_id!r} artifact/code claim lacks notice disposition")
        if not claim_sources.issubset(resolved_disposition_sources):
            raise ValueError(f"subject {subject_id!r} artifact/code claim has unresolved notice disposition")
        claim_artifacts = {boundary.artifact for boundary in claim.raes_boundaries}
        for source_ref in claim.source_refs:
            uncovered = claim_artifacts - disposition_artifacts.get(source_ref, set())
            if uncovered:
                raise ValueError(
                    f"subject {subject_id!r} artifact/code claim is outside the audited "
                    f"derivation scope for {source_ref!r}: {sorted(uncovered)}"
                )

    @staticmethod
    def _validate_planned_compatibility(subject: LineageSubjectModel, claim: LineageClaimModel) -> None:
        current_compatibility = {
            CompatibilityStatus.COMPATIBLE,
            CompatibilityStatus.PARTIAL,
        }
        if subject.disposition is LineageDisposition.PLANNED and claim.compatibility in current_compatibility:
            raise ValueError(f"planned subject {subject.subject_id!r} cannot claim current compatibility")


SDL_LINEAGE_LEDGER_FILENAME = "sdl-lineage-ledger-v2.json"


def sdl_lineage_ledger_path() -> Path:
    return corpus_family_root(PROVENANCE) / SDL_LINEAGE_LEDGER_FILENAME


def load_sdl_lineage_ledger() -> SDLLineageLedgerModel:
    payload = json.loads(sdl_lineage_ledger_path().read_text(encoding="utf-8"))
    return SDLLineageLedgerModel.model_validate(payload)


__all__ = ["SDLLineageLedgerModel", "load_sdl_lineage_ledger", "sdl_lineage_ledger_path"]
