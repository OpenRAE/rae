"""Closed scheme-neutral semantic projection report contract."""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..canonical import canonical_json_digest
from ..diagnostics import DiagnosticModel
from ..versions import SEMANTIC_PROJECTION_REPORT_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .external_concept_bindings import (
    ExternalConceptLifecyclePhase,
    ExternalConceptSubjectModel,
)
from .schema_invariants import add_raes_invariant
from .semantic_projection_profile_registry import (
    PROFILE_ADAPTERS,
    PROFILE_AXES,
    PROFILE_PRODUCERS,
    binding_posture,
)

_REPORT_VALIDATOR = "raes_contracts.contracts.SemanticProjectionReportModel.model_validate"
_WITNESS_FRAME_JOIN_ERROR = "projection witness must join the exact frame subject, producer, and profile"
_PREDICATE_IDS = Literal["declared", "admitted", "observed", "verified"]


def _require_sorted_unique(values: tuple[object, ...], label: str, *, non_empty: bool = False) -> None:
    if non_empty and not values:
        raise ValueError(f"{label} must not be empty")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be sorted and unique")


class SemanticProjectionClassification(str, Enum):
    WITNESS = "witness"
    GAP = "gap"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"
    EXCLUDED = "excluded"


class SemanticProjectionSchemeScopeModel(ContractModel):
    scheme_id: NonEmptyString
    authority: NonEmptyString
    revision: NonEmptyString
    source_digest: PrefixedDigestString
    included_concept_ids: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def _validate_inclusion_set(self) -> SemanticProjectionSchemeScopeModel:
        _require_sorted_unique(self.included_concept_ids, "included concept ids", non_empty=True)
        return self


class SemanticProjectionSubjectScopeModel(ContractModel):
    subject_kind: NonEmptyString
    owning_contract_id: NonEmptyString
    lifecycle_phase: ExternalConceptLifecyclePhase
    artifact_digests: tuple[PrefixedDigestString, ...] = Field(min_length=1, max_length=4096)
    complete: bool

    @model_validator(mode="after")
    def _validate_artifacts(self) -> SemanticProjectionSubjectScopeModel:
        _require_sorted_unique(self.artifact_digests, "subject artifact digests", non_empty=True)
        return self


class SemanticProjectionPredicateProfileModel(ContractModel):
    predicate_id: _PREDICATE_IDS
    profile_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*/v[1-9][0-9]*$", max_length=128)
    profile_version: NonEmptyString
    profile_digest: PrefixedDigestString
    producer_contract_id: NonEmptyString
    adapter_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)
    adapter_version: NonEmptyString
    adapter_digest: PrefixedDigestString
    allow_approximate_bindings: bool = False
    allow_lossy_bindings: bool = False
    configuration_axis: Literal["applicable", "not-applicable"]
    state_axis: Literal["applicable", "not-applicable"]
    transformations_axis: Literal["applicable", "forbidden"]

    @model_validator(mode="after")
    def _validate_profile_binding(self) -> SemanticProjectionPredicateProfileModel:
        posture = binding_posture(self.allow_approximate_bindings, self.allow_lossy_bindings)
        expected_profile_id = f"semantic-projection-{self.predicate_id}-{posture}/v1"
        if (self.profile_id, self.profile_version) != (expected_profile_id, "1"):
            raise ValueError("predicate profile id and version must match the closed native predicate")
        if (self.adapter_id, self.adapter_version) != (PROFILE_ADAPTERS[self.predicate_id], "1"):
            raise ValueError("predicate profile must select the fixed trusted owner adapter")
        if self.producer_contract_id != PROFILE_PRODUCERS[self.predicate_id]:
            raise ValueError("predicate profile must select the native predicate's owning contract")
        expected_adapter_digest = canonical_json_digest(
            {"adapter_id": self.adapter_id, "adapter_version": self.adapter_version}
        )
        if self.adapter_digest != expected_adapter_digest:
            raise ValueError("predicate profile adapter digest must identify the fixed trusted implementation")
        if (self.configuration_axis, self.state_axis, self.transformations_axis) != PROFILE_AXES[self.predicate_id]:
            raise ValueError("predicate profile context axes must match the governed native authority")
        if self.profile_digest != canonical_semantic_projection_predicate_profile_digest(self):
            raise ValueError("predicate profile digest does not match the complete profile")
        return self


class SemanticProjectionPerspectiveModel(ContractModel):
    perspective_kind: Literal["author", "validator", "observer", "verifier", "participant"]
    party_ref: NonEmptyString
    participant_address: NonEmptyString | None = None
    episode_id: NonEmptyString | None = None
    audience_ref: NonEmptyString | None = None
    projection_policy_id: NonEmptyString | None = None
    projection_policy_revision: NonEmptyString | None = None
    projection_policy_digest: PrefixedDigestString | None = None
    applicable_cut_ref: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_participant_coordinates(self) -> SemanticProjectionPerspectiveModel:
        participant_values = (
            self.participant_address,
            self.episode_id,
            self.audience_ref,
            self.projection_policy_id,
            self.projection_policy_revision,
            self.projection_policy_digest,
            self.applicable_cut_ref,
        )
        if self.perspective_kind == "participant" and any(value is None for value in participant_values):
            raise ValueError("participant perspective requires audience, policy, episode, and cut coordinates")
        if self.perspective_kind != "participant" and any(value is not None for value in participant_values):
            raise ValueError("participant-only coordinates are forbidden for non-participant perspectives")
        return self


class SemanticProjectionApplicableCoordinateModel(ContractModel):
    posture: Literal["applicable"]
    coordinate_id: NonEmptyString
    coordinate_version: NonEmptyString
    coordinate_digest: PrefixedDigestString
    cut_ref: NonEmptyString


class SemanticProjectionNotApplicableCoordinateModel(ContractModel):
    posture: Literal["not-applicable"]
    basis_ref: NonEmptyString


SemanticProjectionContextCoordinate = (
    SemanticProjectionApplicableCoordinateModel | SemanticProjectionNotApplicableCoordinateModel
)


class SemanticProjectionQuantifierModel(ContractModel):
    kind: Literal["existential", "universal", "threshold"]
    quantified_unit: Literal["distinct-native-subjects", "binding-subject-pairs"]
    threshold: int | None = Field(default=None, ge=1, le=4096)

    @model_validator(mode="after")
    def _validate_threshold(self) -> SemanticProjectionQuantifierModel:
        if (self.kind == "threshold") != (self.threshold is not None):
            raise ValueError("threshold quantification requires one positive threshold and other kinds forbid it")
        return self


class SemanticProjectionEvidenceBoundaryModel(ContractModel):
    boundary_id: NonEmptyString
    boundary_revision: NonEmptyString
    boundary_digest: PrefixedDigestString
    freshness_policy_id: NonEmptyString
    freshness_policy_revision: NonEmptyString
    freshness_policy_digest: PrefixedDigestString
    evaluation_cut_ref: NonEmptyString
    time_domain: NonEmptyString
    clock_authority: NonEmptyString


class SemanticProjectionBindingCoordinateModel(ContractModel):
    schema_version: Literal["external-concept-bindings/v1"]
    binding_set_id: NonEmptyString
    binding_set_version: NonEmptyString
    binding_set_digest: PrefixedDigestString


class SemanticProjectionTransformationCoordinateModel(ContractModel):
    transformation_id: NonEmptyString
    transformation_version: NonEmptyString
    transformation_digest: PrefixedDigestString
    status: Literal["success", "refused"]
    artifact_kind: Literal["sdl-authoring", "portable-contract"]
    source_profile: NonEmptyString
    target_profile: NonEmptyString
    canonicalization_profile: NonEmptyString
    source_digest: PrefixedDigestString
    target_digest: PrefixedDigestString | None = None
    policy_digest: PrefixedDigestString
    derivation_digest: PrefixedDigestString
    preservation_profile: NonEmptyString
    preservation_outcome: Literal["verified", "failed", "not-applicable"]


class SemanticProjectionFrameModel(ContractModel):
    scheme: SemanticProjectionSchemeScopeModel
    subject_scope: SemanticProjectionSubjectScopeModel
    predicate_profile: SemanticProjectionPredicateProfileModel
    perspective: SemanticProjectionPerspectiveModel
    configuration: SemanticProjectionContextCoordinate
    state: SemanticProjectionContextCoordinate
    quantifier: SemanticProjectionQuantifierModel
    evidence_boundary: SemanticProjectionEvidenceBoundaryModel | SemanticProjectionNotApplicableCoordinateModel
    binding: SemanticProjectionBindingCoordinateModel
    transformations: tuple[SemanticProjectionTransformationCoordinateModel, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def _validate_transformations(self) -> SemanticProjectionFrameModel:
        keys = tuple(
            (item.transformation_id, item.transformation_version, item.transformation_digest)
            for item in self.transformations
        )
        _require_sorted_unique(keys, "projection transformations")
        axes = self.predicate_profile
        if self.configuration.posture != axes.configuration_axis or self.state.posture != axes.state_axis:
            raise ValueError("projection context posture must match the governed predicate profile")
        if axes.transformations_axis == "forbidden" and self.transformations:
            raise ValueError("projection transformations are forbidden by the governed predicate profile")
        for axis_name, coordinate in (("configuration", self.configuration), ("state", self.state)):
            if (
                isinstance(coordinate, SemanticProjectionNotApplicableCoordinateModel)
                and coordinate.basis_ref != f"{axes.predicate_id}-{axis_name}-not-applicable"
            ):
                raise ValueError("not-applicable context posture must use the governed predicate-profile basis")
        return self


class SemanticProjectionBindingObservationModel(ContractModel):
    binding_id: NonEmptyString
    resolution_outcome: Literal[
        "resolved-current",
        "unavailable",
        "stale",
        "ambiguous",
        "superseded",
        "unknown-concept",
        "subject-not-found",
    ]
    relationship_kind: NonEmptyString
    semantic_effect: NonEmptyString
    confidence_posture: NonEmptyString
    approximation_posture: Literal["exact", "approximate", "lossy"]
    loss_details: tuple[NonEmptyString, ...] = ()
    limitations: tuple[NonEmptyString, ...] = Field(min_length=1)
    review_status: NonEmptyString

    @model_validator(mode="after")
    def _validate_binding_details(self) -> SemanticProjectionBindingObservationModel:
        _require_sorted_unique(self.loss_details, "binding loss details")
        _require_sorted_unique(self.limitations, "binding limitations", non_empty=True)
        return self


class SemanticProjectionWitnessModel(ContractModel):
    subject: ExternalConceptSubjectModel
    native_result_id: NonEmptyString
    native_result_digest: PrefixedDigestString
    producer_contract_id: NonEmptyString
    predicate_profile_digest: PrefixedDigestString
    evidence_digests: tuple[PrefixedDigestString, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _validate_evidence(self) -> SemanticProjectionWitnessModel:
        _require_sorted_unique(self.evidence_digests, "witness evidence digests", non_empty=True)
        return self


class SemanticProjectionRowModel(ContractModel):
    concept_id: NonEmptyString
    classification: SemanticProjectionClassification
    bindings: tuple[SemanticProjectionBindingObservationModel, ...] = Field(max_length=4096)
    witnesses: tuple[SemanticProjectionWitnessModel, ...] = Field(max_length=4096)
    reason_codes: tuple[NonEmptyString, ...] = Field(default=(), max_length=128)

    @model_validator(mode="after")
    def _validate_row(self) -> SemanticProjectionRowModel:
        binding_keys = tuple(item.binding_id for item in self.bindings)
        witness_keys = tuple(
            (item.subject.canonical_ref, item.subject.artifact_digest, item.native_result_id, item.native_result_digest)
            for item in self.witnesses
        )
        _require_sorted_unique(binding_keys, "row bindings")
        _require_sorted_unique(witness_keys, "row witnesses")
        _require_sorted_unique(self.reason_codes, "row reason codes")
        if (self.classification == SemanticProjectionClassification.WITNESS) != bool(self.witnesses):
            raise ValueError("only witness rows carry one or more replayable witnesses")
        return self


class SemanticProjectionSummaryModel(ContractModel):
    predicate_id: _PREDICATE_IDS
    predicate_profile_digest: PrefixedDigestString
    frame_digest: PrefixedDigestString
    included_denominator: int = Field(ge=1, le=4096)
    witness_count: int = Field(ge=0, le=4096)
    gap_count: int = Field(ge=0, le=4096)
    unknown_count: int = Field(ge=0, le=4096)
    ambiguous_count: int = Field(ge=0, le=4096)
    excluded_count: int = Field(ge=0, le=4096)
    qualified_fraction: NonEmptyString


def _validate_witness_frame_join(
    frame: SemanticProjectionFrameModel,
    witness: SemanticProjectionWitnessModel,
) -> None:
    subject = witness.subject
    actual_subject = (subject.subject_kind, subject.owning_contract_id, subject.lifecycle_phase)
    expected_subject = (
        frame.subject_scope.subject_kind,
        frame.subject_scope.owning_contract_id,
        frame.subject_scope.lifecycle_phase,
    )
    if actual_subject != expected_subject:
        raise ValueError(_WITNESS_FRAME_JOIN_ERROR)
    if subject.artifact_digest not in frame.subject_scope.artifact_digests:
        raise ValueError(_WITNESS_FRAME_JOIN_ERROR)
    actual_owner = (witness.producer_contract_id, witness.predicate_profile_digest)
    expected_owner = (frame.predicate_profile.producer_contract_id, frame.predicate_profile.profile_digest)
    if actual_owner != expected_owner:
        raise ValueError(_WITNESS_FRAME_JOIN_ERROR)


def _validate_report_rows(
    frame: SemanticProjectionFrameModel,
    rows: tuple[SemanticProjectionRowModel, ...],
) -> tuple[Counter[SemanticProjectionClassification], set[str]]:
    included = set(frame.scheme.included_concept_ids)
    for row in rows:
        is_excluded = row.classification == SemanticProjectionClassification.EXCLUDED
        if (row.concept_id in included) == is_excluded:
            raise ValueError("included concepts cannot be excluded and outside concepts must be excluded")
        for witness in row.witnesses:
            _validate_witness_frame_join(frame, witness)
    return Counter(row.classification for row in rows), included


class SemanticProjectionReportModel(ContractModel):
    schema_version: Literal[SEMANTIC_PROJECTION_REPORT_SCHEMA_VERSION] = SEMANTIC_PROJECTION_REPORT_SCHEMA_VERSION
    frame: SemanticProjectionFrameModel
    frame_digest: PrefixedDigestString
    rows: tuple[SemanticProjectionRowModel, ...] = Field(min_length=1, max_length=8192)
    summary: SemanticProjectionSummaryModel
    diagnostics: tuple[DiagnosticModel, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def _validate_report(self) -> SemanticProjectionReportModel:
        expected_digest = canonical_semantic_projection_frame_digest(self.frame)
        if self.frame_digest != expected_digest or self.summary.frame_digest != expected_digest:
            raise ValueError("semantic projection frame digest does not match the complete embedded frame")
        actual_profile = (self.summary.predicate_id, self.summary.predicate_profile_digest)
        expected_profile = (
            self.frame.predicate_profile.predicate_id,
            self.frame.predicate_profile.profile_digest,
        )
        if actual_profile != expected_profile:
            raise ValueError("projection summary predicate and profile must match the exact frame")
        _require_sorted_unique(tuple(row.concept_id for row in self.rows), "projection rows", non_empty=True)
        counts, included = _validate_report_rows(self.frame, self.rows)
        included_total = sum(
            counts[item]
            for item in SemanticProjectionClassification
            if item != SemanticProjectionClassification.EXCLUDED
        )
        expected = (
            self.summary.witness_count,
            self.summary.gap_count,
            self.summary.unknown_count,
            self.summary.ambiguous_count,
            self.summary.excluded_count,
            self.summary.included_denominator,
        )
        actual = (
            counts[SemanticProjectionClassification.WITNESS],
            counts[SemanticProjectionClassification.GAP],
            counts[SemanticProjectionClassification.UNKNOWN],
            counts[SemanticProjectionClassification.AMBIGUOUS],
            counts[SemanticProjectionClassification.EXCLUDED],
            included_total,
        )
        if expected != actual or included_total != len(included):
            raise ValueError("projection summary counts must exactly reconcile with the row partition")
        fraction = (
            f"{self.summary.predicate_id}:{self.summary.witness_count}/"
            f"{self.summary.included_denominator}@{expected_digest}"
        )
        if self.summary.qualified_fraction != fraction:
            raise ValueError("qualified fraction must name the exact predicate, denominator, and frame digest")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        add_raes_invariant(
            schema,
            "semantic-projection-exact-frame-partition",
            "The complete digest-bound frame selects one native predicate and every explicitly included "
            "concept appears in exactly one structural report partition.",
            validator=_REPORT_VALIDATOR,
            inputs=[{"contract_id": "semantic-projection-report-v1", "instance_path": "#"}],
        )
        add_raes_invariant(
            schema,
            "semantic-projection-evidence-bounded-witnesses",
            "Only witness rows carry digest-stable native results whose subject, producer, and profile join "
            "the embedded frame; contextual evidence admission is validated with referenced authority artifacts.",
            validator=_REPORT_VALIDATOR,
            inputs=[{"contract_id": "semantic-projection-report-v1", "instance_path": "#"}],
        )
        return schema


def canonical_semantic_projection_frame_digest(frame: SemanticProjectionFrameModel) -> str:
    return canonical_json_digest(frame.model_dump(mode="json"))


def canonical_semantic_projection_predicate_profile_digest(
    profile: SemanticProjectionPredicateProfileModel,
) -> str:
    return canonical_json_digest(profile.model_dump(mode="json", exclude={"profile_digest"}))


def governed_semantic_projection_predicate_profile(
    predicate_id: _PREDICATE_IDS,
    *,
    allow_approximate_bindings: bool = False,
    allow_lossy_bindings: bool = False,
) -> SemanticProjectionPredicateProfileModel:
    """Resolve one member of the closed repository-governed predicate-profile registry."""

    posture = binding_posture(allow_approximate_bindings, allow_lossy_bindings)
    adapter_id = f"{predicate_id}-owner-adapter"
    payload = {
        "predicate_id": predicate_id,
        "profile_id": f"semantic-projection-{predicate_id}-{posture}/v1",
        "profile_version": "1",
        "profile_digest": "sha256:" + "0" * 64,
        "producer_contract_id": PROFILE_PRODUCERS[predicate_id],
        "adapter_id": adapter_id,
        "adapter_version": "1",
        "adapter_digest": canonical_json_digest({"adapter_id": adapter_id, "adapter_version": "1"}),
        "allow_approximate_bindings": allow_approximate_bindings,
        "allow_lossy_bindings": allow_lossy_bindings,
        "configuration_axis": "applicable" if predicate_id == "declared" else "not-applicable",
        "state_axis": "applicable" if predicate_id == "observed" else "not-applicable",
        "transformations_axis": "applicable" if predicate_id == "verified" else "forbidden",
    }
    unsealed = SemanticProjectionPredicateProfileModel.model_construct(**payload)
    payload["profile_digest"] = canonical_semantic_projection_predicate_profile_digest(unsealed)
    return SemanticProjectionPredicateProfileModel.model_validate(payload)


__all__ = [
    "SemanticProjectionApplicableCoordinateModel",
    "SemanticProjectionBindingCoordinateModel",
    "SemanticProjectionBindingObservationModel",
    "SemanticProjectionClassification",
    "SemanticProjectionEvidenceBoundaryModel",
    "SemanticProjectionFrameModel",
    "SemanticProjectionNotApplicableCoordinateModel",
    "SemanticProjectionPerspectiveModel",
    "SemanticProjectionPredicateProfileModel",
    "SemanticProjectionQuantifierModel",
    "SemanticProjectionReportModel",
    "SemanticProjectionRowModel",
    "SEMANTIC_PROJECTION_REPORT_SCHEMA_VERSION",
    "SemanticProjectionSchemeScopeModel",
    "SemanticProjectionSubjectScopeModel",
    "SemanticProjectionSummaryModel",
    "SemanticProjectionTransformationCoordinateModel",
    "SemanticProjectionWitnessModel",
    "canonical_semantic_projection_frame_digest",
    "canonical_semantic_projection_predicate_profile_digest",
    "governed_semantic_projection_predicate_profile",
]
