"""Scientific-scenario completeness taxonomy and delivery assessment contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from raes_contracts._base import ContractModel, NonEmptyString
from raes_contracts.behavioral_claims import BehavioralClaimBindingModel, BehavioralRelationId

from .behavioral_authority_errors import BehavioralAuthorityArtifactError
from .behavioral_relations import load_behavioral_relation_catalog, validate_behavioral_claim_binding
from .corpus import PROFILES, corpus_family_root
from .versions import (
    SCIENTIFIC_COMPLETENESS_ASSESSMENT_SCHEMA_VERSION,
    SCIENTIFIC_COMPLETENESS_TAXONOMY_SCHEMA_VERSION,
)

ProfileId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*$")]
ConcernId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*$")]
RevisionId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.-]*$")]
IssueRef = Annotated[str, Field(pattern=r"^#[1-9][0-9]*$")]
ContractId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*-v[1-9][0-9]*$")]


def _validate_repo_path(value: str) -> str:
    if value.startswith("/") or ".." in Path(value).parts:
        raise ValueError("repository path must be relative and must not contain parent traversal")
    return value


RepoPath = Annotated[str, Field(pattern=r"^[^/\s][^\s]*$"), AfterValidator(_validate_repo_path)]


class ProfileDisposition(str, Enum):
    REQUIRED = "required"
    ALLOWED_UNDERSPECIFIED = "allowed-underspecified"
    EXCLUDED = "excluded"


class DeliveryStatus(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    EXTERNAL_CONTRACT = "external-contract"
    DELIBERATELY_EXCLUDED = "deliberately-excluded"
    MISSING = "missing"


class EvidenceKind(str, Enum):
    NORMATIVE_SPEC = "normative-spec"
    PUBLISHED_SCHEMA = "published-schema"
    CONTRACT = "contract"
    IMPLEMENTATION = "implementation"
    TEST = "test"
    CONFORMANCE = "conformance"
    EXAMPLE = "example"
    DOCUMENTATION = "documentation"


_EXECUTABLE_EVIDENCE_KINDS = {
    EvidenceKind.IMPLEMENTATION,
    EvidenceKind.TEST,
    EvidenceKind.CONFORMANCE,
}


class CompletenessConcernModel(ContractModel):
    concern_id: ConcernId
    title: NonEmptyString
    definition: NonEmptyString
    semantic_owner: NonEmptyString


class CompletenessProfileModel(ContractModel):
    profile_id: ProfileId
    title: NonEmptyString
    intended_claim: NonEmptyString
    explicit_non_claims: list[NonEmptyString] = Field(min_length=1)
    behavioral_claims: list[BehavioralClaimBindingModel] = Field(min_length=1)
    non_claimed_relation_ids: list[BehavioralRelationId] = Field(min_length=1)
    dispositions: dict[ConcernId, ProfileDisposition]
    example_refs: list[RepoPath] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_behavioral_claims(self) -> CompletenessProfileModel:

        try:
            self._check_behavioral_claims()
        except BehavioralAuthorityArtifactError as exc:
            # A Pydantic validator raises only ValueError (E3); the loader has logged the damage.
            raise ValueError("the packaged behavioral relation authority is damaged") from exc
        return self

    def _check_behavioral_claims(self) -> None:

        catalog = load_behavioral_relation_catalog()
        claimed_ids = [claim.relation_id for claim in self.behavioral_claims]
        if len(claimed_ids) != len(set(claimed_ids)):
            raise ValueError("scientific-completeness behavioral claim relation ids must be unique")
        nonclaimed_ids = set(self.non_claimed_relation_ids)
        missing = sorted(nonclaimed_ids - set(catalog.relations))
        if missing:
            raise ValueError(f"scientific-completeness profile references unknown relations: {missing}")
        overlap = sorted(set(claimed_ids) & nonclaimed_ids)
        if overlap:
            raise ValueError(f"relations cannot be both claimed and explicitly non-claimed: {overlap}")
        for claim in self.behavioral_claims:
            validate_behavioral_claim_binding(claim)


class ScientificCompletenessTaxonomyModel(ContractModel):
    schema_version: Literal[SCIENTIFIC_COMPLETENESS_TAXONOMY_SCHEMA_VERSION] = (
        SCIENTIFIC_COMPLETENESS_TAXONOMY_SCHEMA_VERSION
    )
    profile_family: Literal["scientific-scenario-completeness"] = "scientific-scenario-completeness"
    revision: RevisionId
    concerns: list[CompletenessConcernModel] = Field(min_length=1)
    profiles: list[CompletenessProfileModel] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_taxonomy_identity(self) -> ScientificCompletenessTaxonomyModel:
        concern_ids = [concern.concern_id for concern in self.concerns]
        if len(concern_ids) != len(set(concern_ids)):
            raise ValueError("taxonomy concern ids must be unique")
        profile_ids = [profile.profile_id for profile in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("taxonomy profile ids must be unique")
        expected = set(concern_ids)
        for profile in self.profiles:
            if set(profile.dispositions) != expected:
                raise ValueError(f"profile {profile.profile_id!r} dispositions must exactly cover taxonomy concerns")
        return self


class CompletenessEvidenceModel(ContractModel):
    kind: EvidenceKind
    path: RepoPath
    claim: NonEmptyString
    contract_id: ContractId | None = None

    @model_validator(mode="after")
    def validate_contract_evidence(self) -> CompletenessEvidenceModel:
        if self.kind in {EvidenceKind.CONTRACT, EvidenceKind.PUBLISHED_SCHEMA} and self.contract_id is None:
            raise ValueError("contract and published-schema evidence require contract_id")
        if self.kind not in {EvidenceKind.CONTRACT, EvidenceKind.PUBLISHED_SCHEMA} and self.contract_id is not None:
            raise ValueError("contract_id is valid only for contract or published-schema evidence")
        return self


class ConcernDeliveryAssessmentModel(ContractModel):
    concern_id: ConcernId
    status: DeliveryStatus
    evidence: list[CompletenessEvidenceModel] = Field(default_factory=list)
    limitation: NonEmptyString
    issue_refs: list[IssueRef] = Field(default_factory=list)
    external_contract_refs: list[ContractId] = Field(default_factory=list)
    satisfiability_witness_refs: dict[ContractId, RepoPath] = Field(default_factory=dict)
    binding_obligation: NonEmptyString | None = None
    exclusion_rationale: NonEmptyString | None = None

    def _validate_implemented_evidence(self) -> None:
        if self.status is DeliveryStatus.IMPLEMENTED and not any(
            item.kind in _EXECUTABLE_EVIDENCE_KINDS for item in self.evidence
        ):
            raise ValueError("implemented status requires executable evidence")

    def _validate_external_contract(self) -> None:
        if self.status is not DeliveryStatus.EXTERNAL_CONTRACT:
            if self._has_external_contract_bindings():
                raise ValueError("external contract bindings are valid only for external-contract status")
            return
        self._validate_external_contract_bindings()

    def _has_external_contract_bindings(self) -> bool:
        return bool(
            self.external_contract_refs or self.satisfiability_witness_refs or self.binding_obligation is not None
        )

    def _validate_external_contract_bindings(self) -> None:
        if not self.external_contract_refs or not self.satisfiability_witness_refs or self.binding_obligation is None:
            raise ValueError(
                "external-contract status requires named contract refs, "
                "satisfiability witnesses, and a binding obligation"
            )
        evidence_contracts = {item.contract_id for item in self.evidence if item.contract_id is not None}
        if not set(self.external_contract_refs).issubset(evidence_contracts):
            raise ValueError("external-contract status requires evidence for every named contract")
        if set(self.satisfiability_witness_refs) != set(self.external_contract_refs):
            raise ValueError(
                "external-contract status requires exactly one satisfiability witness for every named contract"
            )

    def _validate_exclusion(self) -> None:
        if self.status is DeliveryStatus.DELIBERATELY_EXCLUDED:
            if self.exclusion_rationale is None:
                raise ValueError("deliberately-excluded status requires exclusion_rationale")
        elif self.exclusion_rationale is not None:
            raise ValueError("exclusion_rationale is valid only for deliberately-excluded status")

    def _validate_issue_refs(self) -> None:
        if self.status in {DeliveryStatus.PARTIAL, DeliveryStatus.MISSING} and not self.issue_refs:
            raise ValueError("partial and missing statuses require at least one issue ref")

    @model_validator(mode="after")
    def validate_status_evidence(self) -> ConcernDeliveryAssessmentModel:
        self._validate_implemented_evidence()
        self._validate_external_contract()
        self._validate_exclusion()
        self._validate_issue_refs()
        return self


class ScientificCompletenessAssessmentModel(ContractModel):
    schema_version: Literal[SCIENTIFIC_COMPLETENESS_ASSESSMENT_SCHEMA_VERSION] = (
        SCIENTIFIC_COMPLETENESS_ASSESSMENT_SCHEMA_VERSION
    )
    profile_family: Literal["scientific-scenario-completeness"] = "scientific-scenario-completeness"
    taxonomy_revision: RevisionId
    assessment_revision: RevisionId
    assessed_on: Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
    concerns: list[ConcernDeliveryAssessmentModel] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_assessment_identity(self) -> ScientificCompletenessAssessmentModel:
        concern_ids = [item.concern_id for item in self.concerns]
        if len(concern_ids) != len(set(concern_ids)):
            raise ValueError("assessment concern ids must be unique")
        return self


@dataclass(frozen=True)
class ProfileCompletenessResult:
    profile_id: str
    complete: bool
    blocking_concerns: tuple[str, ...]


def evaluate_profile_completeness(
    taxonomy: ScientificCompletenessTaxonomyModel,
    assessment: ScientificCompletenessAssessmentModel,
) -> tuple[ProfileCompletenessResult, ...]:
    """Join one taxonomy revision to one assessment and compute outcomes."""

    if assessment.profile_family != taxonomy.profile_family:
        raise ValueError("assessment profile_family must match taxonomy")
    if assessment.taxonomy_revision != taxonomy.revision:
        raise ValueError("assessment taxonomy_revision must match taxonomy revision")
    taxonomy_ids = {concern.concern_id for concern in taxonomy.concerns}
    assessment_by_id = {item.concern_id: item for item in assessment.concerns}
    if set(assessment_by_id) != taxonomy_ids:
        raise ValueError("assessment concerns must exactly cover taxonomy concerns")
    satisfying = {DeliveryStatus.IMPLEMENTED, DeliveryStatus.EXTERNAL_CONTRACT}
    results: list[ProfileCompletenessResult] = []
    for profile in taxonomy.profiles:
        blocking = tuple(
            sorted(
                concern_id
                for concern_id, disposition in profile.dispositions.items()
                if disposition is ProfileDisposition.REQUIRED and assessment_by_id[concern_id].status not in satisfying
            )
        )
        results.append(
            ProfileCompletenessResult(
                profile_id=profile.profile_id,
                complete=not blocking,
                blocking_concerns=blocking,
            )
        )
    return tuple(results)


def scientific_completeness_root() -> Path:
    return corpus_family_root(PROFILES) / "scientific-completeness"


@cache
def load_scientific_completeness_taxonomy() -> ScientificCompletenessTaxonomyModel:
    path = scientific_completeness_root() / "scientific-scenario-completeness-rev1.json"
    return ScientificCompletenessTaxonomyModel.model_validate_json(path.read_text(encoding="utf-8"))


@cache
def load_scientific_completeness_assessment() -> ScientificCompletenessAssessmentModel:
    path = scientific_completeness_root() / "delivery-assessment-2026-07-12.json"
    return ScientificCompletenessAssessmentModel.model_validate_json(path.read_text(encoding="utf-8"))


__all__ = [
    "DeliveryStatus",
    "ProfileCompletenessResult",
    "ProfileDisposition",
    "ScientificCompletenessAssessmentModel",
    "ScientificCompletenessTaxonomyModel",
    "evaluate_profile_completeness",
    "load_scientific_completeness_assessment",
    "load_scientific_completeness_taxonomy",
    "scientific_completeness_root",
]
