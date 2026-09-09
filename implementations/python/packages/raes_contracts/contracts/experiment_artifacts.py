"""Experiment reference helpers and checksum/artifact-ref contracts."""

from __future__ import annotations

import re
from typing import Any, ClassVar, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .base import (
    _CHECKSUM_VALUE_PATTERNS,
    ContractModel,
    HexDigestString,
    NonEmptyString,
    NonNegativeInteger,
    Rfc3339DateTimeString,
    _canonical_digest,
    _parse_rfc3339_datetime,
)
from .capabilities import ApparatusIdentityModel
from .experiment_manifest_references import (
    ExperimentEvidenceSatisfactionReferenceModel,
    ExperimentManifestReferenceModel,
)
from .experiment_references import ExperimentReferenceModel, PrunedReferenceFieldsMixin


class ExperimentDerivedMeasureReferenceModel(PrunedReferenceFieldsMixin, ExperimentReferenceModel):
    """Reference constrained to a derived measure or analysis output."""

    ref_kind: Literal["derived-measure"]
    _PRUNED_REF_FIELDS: ClassVar[tuple[str, ...]] = ("ref_digest", "ref_path")

    @model_validator(mode="after")
    def _validate_derived_measure_reference_scope(self) -> ExperimentDerivedMeasureReferenceModel:
        if "ref_digest" in self.model_fields_set or "ref_path" in self.model_fields_set:
            raise ValueError("derived-measure references must not carry ref_digest or ref_path")
        return self


class ExperimentMeasurementChannelReferenceModel(PrunedReferenceFieldsMixin, ExperimentReferenceModel):
    """Reference constrained to a declared measurement channel."""

    ref_kind: Literal["measurement-channel"]
    _PRUNED_REF_FIELDS: ClassVar[tuple[str, ...]] = ("ref_digest", "ref_path")

    @model_validator(mode="after")
    def _validate_measurement_channel_reference_scope(self) -> ExperimentMeasurementChannelReferenceModel:
        if "ref_digest" in self.model_fields_set or "ref_path" in self.model_fields_set:
            raise ValueError("measurement-channel references must not carry ref_digest or ref_path")
        return self


class ExperimentApparatusCompatibilityReferenceModel(PrunedReferenceFieldsMixin, ExperimentReferenceModel):
    """Profile or capability reference declared by apparatus compatibility metadata."""

    ref_kind: Literal["profile", "capability"]
    _PRUNED_REF_FIELDS: ClassVar[tuple[str, ...]] = ("ref_digest", "ref_path")

    @model_validator(mode="after")
    def _validate_compatibility_reference_scope(self) -> ExperimentApparatusCompatibilityReferenceModel:
        if "ref_digest" in self.model_fields_set or "ref_path" in self.model_fields_set:
            raise ValueError("apparatus compatibility references must not carry ref_digest or ref_path")
        return self


class ExperimentConditionAssignmentReferenceModel(ExperimentReferenceModel):
    """Auditable run-level reference that can ground a study condition assignment."""

    ref_kind: Literal[
        "processor",
        "backend",
        "participant-implementation",
        "scenario-snapshot",
        "task",
        "apparatus-context",
        "manifest",
        "profile",
        "capability",
        "measurement-channel",
        "evidence",
    ]

    @model_validator(mode="after")
    def _validate_condition_reference_scope(self) -> ExperimentConditionAssignmentReferenceModel:
        if self.ref_digest is not None or self.ref_path is not None:
            raise ValueError(
                "condition assignment references are run-level criteria and must not carry ref_digest or ref_path; "
                "use task evidence requirements or validated apparatus manifest refs for digest/path-bound evidence"
            )
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).append(
            {
                "properties": {
                    "ref_digest": {"type": "null"},
                    "ref_path": {"type": "null"},
                },
            }
        )
        return json_schema


def _manifest_reference_key(
    reference: ExperimentManifestReferenceModel,
) -> tuple[
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    subject_ref = reference.subject_ref
    return (
        reference.ref_id,
        reference.ref_version,
        _canonical_digest(reference.ref_digest),
        reference.ref_path,
        subject_ref.ref_kind if subject_ref is not None else None,
        subject_ref.ref_id if subject_ref is not None else None,
        subject_ref.ref_version if subject_ref is not None else None,
        _canonical_digest(subject_ref.ref_digest) if subject_ref is not None else None,
        subject_ref.ref_path if subject_ref is not None else None,
    )


def _reference_scalar_fields_mismatch(
    candidate: ExperimentReferenceModel, requirement: ExperimentReferenceModel
) -> bool:
    kind_or_id_mismatch = candidate.ref_kind != requirement.ref_kind or candidate.ref_id != requirement.ref_id
    version_mismatch = requirement.ref_version is not None and candidate.ref_version != requirement.ref_version
    digest_mismatch = requirement.ref_digest is not None and _canonical_digest(
        candidate.ref_digest
    ) != _canonical_digest(requirement.ref_digest)
    path_mismatch = requirement.ref_path is not None and candidate.ref_path != requirement.ref_path
    return kind_or_id_mismatch or version_mismatch or digest_mismatch or path_mismatch


def _reference_subject_satisfies_requirement(
    candidate: ExperimentReferenceModel, requirement: ExperimentReferenceModel
) -> bool:
    requirement_subject = getattr(requirement, "subject_ref", None)
    if requirement_subject is None:
        return True
    candidate_subject = getattr(candidate, "subject_ref", None)
    if candidate_subject is None:
        return False
    return _reference_satisfies_requirement(candidate_subject, requirement_subject)


def _reference_satisfies_requirement(
    candidate: ExperimentReferenceModel, requirement: ExperimentReferenceModel
) -> bool:
    if _reference_scalar_fields_mismatch(candidate, requirement):
        return False
    return _reference_subject_satisfies_requirement(candidate, requirement)


def _reference_identity_scalar_fields_mismatch(
    candidate: ExperimentReferenceModel, requirement: ExperimentReferenceModel
) -> bool:
    kind_or_id_mismatch = candidate.ref_kind != requirement.ref_kind or candidate.ref_id != requirement.ref_id
    version_mismatch = requirement.ref_version is not None and candidate.ref_version != requirement.ref_version
    return kind_or_id_mismatch or version_mismatch


def _reference_identity_subject_satisfies_requirement(
    candidate: ExperimentReferenceModel, requirement: ExperimentReferenceModel
) -> bool:
    requirement_subject = getattr(requirement, "subject_ref", None)
    if requirement_subject is None:
        return True
    candidate_subject = getattr(candidate, "subject_ref", None)
    if candidate_subject is None:
        return False
    return _reference_identity_satisfies_requirement(candidate_subject, requirement_subject)


def _reference_identity_satisfies_requirement(
    candidate: ExperimentReferenceModel, requirement: ExperimentReferenceModel
) -> bool:
    if _reference_identity_scalar_fields_mismatch(candidate, requirement):
        return False
    return _reference_identity_subject_satisfies_requirement(candidate, requirement)


def _experiment_reference_key(
    reference: ExperimentReferenceModel,
) -> tuple[Any, ...]:
    subject_ref = getattr(reference, "subject_ref", None)
    return (
        reference.ref_kind,
        reference.ref_id,
        reference.ref_version,
        _canonical_digest(getattr(reference, "ref_digest", None)),
        getattr(reference, "ref_path", None),
        _experiment_reference_key(subject_ref) if subject_ref is not None else None,
    )


def _validate_unique_experiment_references(
    field_name: str,
    references: list[ExperimentReferenceModel],
) -> None:
    seen: set[tuple[Any, ...]] = set()
    duplicates: list[str] = []
    for reference in references:
        key = _experiment_reference_key(reference)
        if key in seen:
            duplicates.append(_format_reference(reference))
        seen.add(key)
    if duplicates:
        joined = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"{field_name} must not contain duplicates: {joined}")


def _identity_matches_reference(identity: ApparatusIdentityModel, reference: ExperimentReferenceModel) -> bool:
    if reference.ref_digest is not None or reference.ref_path is not None:
        return False
    if identity.name != reference.ref_id:
        return False
    return reference.ref_version is None or identity.version == reference.ref_version


def _format_reference(reference: ExperimentReferenceModel) -> str:
    if reference.ref_version is None:
        return f"{reference.ref_kind}:{reference.ref_id}"
    return f"{reference.ref_kind}:{reference.ref_id}@{reference.ref_version}"


class ExperimentChecksumModel(ContractModel):
    """Checksum metadata for an experiment-core artifact reference."""

    algorithm: Literal["sha256", "sha384", "sha512", "blake3"]
    value: HexDigestString

    @model_validator(mode="after")
    def _validate_checksum_length(self) -> ExperimentChecksumModel:
        if re.fullmatch(_CHECKSUM_VALUE_PATTERNS[self.algorithm], self.value) is None:
            raise ValueError(f"checksum value must match {self.algorithm} hex digest length")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {"properties": {"algorithm": {"const": algorithm}}, "required": ["algorithm"]},
                    "then": {"properties": {"value": {"pattern": pattern}}},
                }
                for algorithm, pattern in _CHECKSUM_VALUE_PATTERNS.items()
            ]
        )
        return json_schema


class ExperimentArtifactRefModel(ContractModel):
    """Reference to an artifact that supports a task, run, apparatus, or study."""

    artifact_id: NonEmptyString
    role: Literal[
        "protocol",
        "metric-definition",
        "scenario-snapshot",
        "manifest",
        "apparatus-evidence",
        "observation",
        "result",
        "analysis",
        "report",
        "export",
        "starter-file",
        "evaluator",
        "subtask",
        "gold-step",
        "milestone",
        "human-assistance",
        "scaffold",
        "baseline",
        "cost-resource-trace",
        "documentation",
        "operator-guide",
        "configuration",
        "profile",
        "dataset",
        "other",
    ]
    media_type: NonEmptyString
    uri: NonEmptyString
    checksum: ExperimentChecksumModel
    size_bytes: NonNegativeInteger
    created_at: Rfc3339DateTimeString
    source: NonEmptyString
    satisfies_refs: list[ExperimentEvidenceSatisfactionReferenceModel] = Field(default_factory=list)
    sensitivity: Literal["public", "internal", "restricted", "redacted"]
    description: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_artifact_created_at(self) -> ExperimentArtifactRefModel:
        _parse_rfc3339_datetime("created_at", self.created_at)
        return self
