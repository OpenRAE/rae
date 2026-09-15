"""Closed portable contracts for governed semantic comparison and impact analysis."""

from __future__ import annotations

from enum import Enum
from importlib import import_module
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .canonical import canonical_json_digest
from .contracts.base import ContractModel, PrefixedDigestString
from .contracts.schema_invariants import _add_raes_invariant
from .json_ingress import parse_bounded_json_object
from .versions import (
    EXPERIMENT_CAPTURE_SPEC_SCHEMA_VERSION,
    EXPERIMENT_RUN_SCHEMA_VERSION,
    EXPERIMENT_STUDY_SCHEMA_VERSION,
    EXPERIMENT_TASK_SCHEMA_VERSION,
    EXTERNAL_CONCEPT_BINDINGS_SCHEMA_VERSION,
    SEMANTIC_COMPARISON_REQUEST_SCHEMA_VERSION,
)

_IDENTITY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:@/-]*$"


class ArtifactKind(str, Enum):
    SCENARIO = "scenario"
    MODULE = "module"
    TASK = "task"
    RUN = "run"
    EVIDENCE_SPECIFICATION = "evidence-specification"
    STUDY = "study"
    EXTERNAL_CONCEPT_BINDINGS = "external-concept-bindings"


class IdentityRelation(str, Enum):
    SAME = "same"
    ADDED = "added"
    REMOVED = "removed"
    RENAMED = "renamed"
    INDETERMINATE = "indeterminate"


class RelationStatus(str, Enum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNKNOWN = "unknown"
    INCOMPARABLE = "incomparable"
    NOT_APPLICABLE = "not-applicable"


class DependencyResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    WITHHELD = "withheld"


class DependencyRelation(str, Enum):
    UNCHANGED = "unchanged"
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


class ImpactClosureStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    REDACTED = "redacted"
    UNVERIFIED = "unverified"


class ComparisonCompleteness(str, Enum):
    COMPLETE = "complete"
    BOUNDED = "bounded"
    INDETERMINATE = "indeterminate"


class ComparisonReason(str, Enum):
    REPRESENTATION_EVIDENCE_MISSING = "representation-evidence-missing"
    VERSION_PAIR_INCOMPARABLE = "version-pair-incomparable"
    IMPACT_SCOPE_PARTIAL = "impact-scope-partial"
    IMPACT_SCOPE_REDACTED = "impact-scope-redacted"
    IMPACT_SCOPE_UNVERIFIED = "impact-scope-unverified"
    SUBJECT_BOUND_EXHAUSTED = "subject-bound-exhausted"
    DEPENDENCY_EDGE_BOUND_EXHAUSTED = "dependency-edge-bound-exhausted"
    IMPACT_PATH_DEPTH_EXHAUSTED = "impact-path-depth-exhausted"
    IMPACT_PATH_BOUND_EXHAUSTED = "impact-path-bound-exhausted"
    UNRESOLVED_REFERENCE = "unresolved-reference"
    AMBIGUOUS_REFERENCE = "ambiguous-reference"
    WITHHELD_REFERENCE = "withheld-reference"
    TRANSFORMATION_EVIDENCE_NOT_SUCCESSFUL = "transformation-evidence-not-successful"
    TRANSFORMATION_EVIDENCE_DIGEST_MISMATCH = "transformation-evidence-digest-mismatch"
    TRANSFORMATION_EVIDENCE_PROFILE_MISMATCH = "transformation-evidence-profile-mismatch"
    TRANSFORMATION_EVIDENCE_LOSSY = "transformation-evidence-lossy"


class ExactRepresentationModel(ContractModel):
    """Digest-only evidence for one exact representation, never a host path."""

    profile: Literal["utf8-json/v1", "utf8-yaml/v1"]
    media_type: Literal["application/json", "application/yaml"]
    byte_digest: PrefixedDigestString


class _CoordinateBase(ContractModel):
    canonical_identity: str = Field(pattern=_IDENTITY_PATTERN, max_length=512)
    canonicalization_profile: str = Field(pattern=r"^[a-z0-9-]+/v[1-9][0-9]*$", max_length=128)
    canonical_digest: PrefixedDigestString
    exact_representation: ExactRepresentationModel | None = None


class ScenarioCoordinateModel(_CoordinateBase):
    artifact_kind: Literal[ArtifactKind.SCENARIO] = ArtifactKind.SCENARIO
    lifecycle_phase: Literal["normalized-authoring"] = "normalized-authoring"
    source_profile: Literal["sdl-normalized-authoring/v1"] = "sdl-normalized-authoring/v1"
    scenario_id: str = Field(min_length=1, max_length=256)
    scenario_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_identity(self) -> ScenarioCoordinateModel:
        _require_coordinate_identity(self.canonical_identity, "scenario", self.scenario_id)
        return self


class ModuleCoordinateModel(_CoordinateBase):
    artifact_kind: Literal[ArtifactKind.MODULE] = ArtifactKind.MODULE
    lifecycle_phase: Literal["resolved-import"] = "resolved-import"
    provenance_profile: Literal["resolved-import-provenance/v1"] = "resolved-import-provenance/v1"
    module_id: str = Field(min_length=1, max_length=256)
    module_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_identity(self) -> ModuleCoordinateModel:
        _require_coordinate_identity(self.canonical_identity, "module", self.module_id)
        return self


class TaskCoordinateModel(_CoordinateBase):
    artifact_kind: Literal[ArtifactKind.TASK] = ArtifactKind.TASK
    lifecycle_phase: Literal["portable-contract"] = "portable-contract"
    schema_version: Literal[EXPERIMENT_TASK_SCHEMA_VERSION] = EXPERIMENT_TASK_SCHEMA_VERSION
    task_id: str = Field(min_length=1, max_length=256)
    task_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_identity(self) -> TaskCoordinateModel:
        _require_coordinate_identity(self.canonical_identity, "task", self.task_id)
        return self


class RunCoordinateModel(_CoordinateBase):
    artifact_kind: Literal[ArtifactKind.RUN] = ArtifactKind.RUN
    lifecycle_phase: Literal["portable-contract"] = "portable-contract"
    schema_version: Literal[EXPERIMENT_RUN_SCHEMA_VERSION] = EXPERIMENT_RUN_SCHEMA_VERSION
    run_id: str = Field(min_length=1, max_length=256)
    run_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_identity(self) -> RunCoordinateModel:
        _require_coordinate_identity(self.canonical_identity, "run", self.run_id)
        return self


class EvidenceSpecificationCoordinateModel(_CoordinateBase):
    artifact_kind: Literal[ArtifactKind.EVIDENCE_SPECIFICATION] = ArtifactKind.EVIDENCE_SPECIFICATION
    lifecycle_phase: Literal["portable-contract"] = "portable-contract"
    schema_version: Literal[EXPERIMENT_CAPTURE_SPEC_SCHEMA_VERSION] = EXPERIMENT_CAPTURE_SPEC_SCHEMA_VERSION
    capture_spec_id: str = Field(min_length=1, max_length=256)
    spec_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_identity(self) -> EvidenceSpecificationCoordinateModel:
        _require_coordinate_identity(self.canonical_identity, "capture-spec", self.capture_spec_id)
        return self


class StudyCoordinateModel(_CoordinateBase):
    artifact_kind: Literal[ArtifactKind.STUDY] = ArtifactKind.STUDY
    lifecycle_phase: Literal["portable-contract"] = "portable-contract"
    schema_version: Literal[EXPERIMENT_STUDY_SCHEMA_VERSION] = EXPERIMENT_STUDY_SCHEMA_VERSION
    study_id: str = Field(min_length=1, max_length=256)
    study_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_identity(self) -> StudyCoordinateModel:
        _require_coordinate_identity(self.canonical_identity, "study", self.study_id)
        return self


class ExternalConceptBindingsCoordinateModel(_CoordinateBase):
    artifact_kind: Literal[ArtifactKind.EXTERNAL_CONCEPT_BINDINGS] = ArtifactKind.EXTERNAL_CONCEPT_BINDINGS
    lifecycle_phase: Literal["portable-contract"] = "portable-contract"
    schema_version: Literal[EXTERNAL_CONCEPT_BINDINGS_SCHEMA_VERSION] = EXTERNAL_CONCEPT_BINDINGS_SCHEMA_VERSION
    binding_set_id: str = Field(min_length=1, max_length=256)
    binding_set_version: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_identity(self) -> ExternalConceptBindingsCoordinateModel:
        _require_coordinate_identity(
            self.canonical_identity,
            "external-concept-bindings",
            self.binding_set_id,
        )
        return self


ArtifactCoordinate = Annotated[
    ScenarioCoordinateModel
    | ModuleCoordinateModel
    | TaskCoordinateModel
    | RunCoordinateModel
    | EvidenceSpecificationCoordinateModel
    | StudyCoordinateModel
    | ExternalConceptBindingsCoordinateModel,
    Field(discriminator="artifact_kind"),
]


class ComparisonLimitsModel(ContractModel):
    max_subjects: int = Field(default=4096, ge=1, le=4096)
    max_dependency_edges: int = Field(default=8192, ge=0, le=8192)
    max_path_depth: int = Field(default=8, ge=0, le=32)
    max_paths: int = Field(default=1024, ge=0, le=4096)
    max_diagnostics: int = Field(default=64, ge=0, le=64)


class SemanticComparisonProfileModel(ContractModel):
    """Governed portable meaning of the v1 comparison operation."""

    profile_id: Literal["raes-semantic-comparison/v1"] = "raes-semantic-comparison/v1"
    analyzer_profile: Literal["raes-reference-semantic-comparator/v1"]
    projection_profile: Literal["owner-specific-admitted-artifact-projection/v1"]
    impact_closure_policy: Literal["declared-exact-artifact-set/v1"]
    identity_axis: Literal["canonical-owner-identity/v1"]
    textual_axis: Literal["exact-representation-digest/v1"]
    structural_axis: Literal["owner-shape-projection/v1"]
    semantic_axis: Literal["owner-semantic-projection/v1"]
    dependency_rule_versions: dict[str, Literal["1"]]
    owner_projection_versions: dict[ArtifactKind, Literal["1", "2"]]
    limits: ComparisonLimitsModel = ComparisonLimitsModel()

    @model_validator(mode="after")
    def _validate_rules(self) -> SemanticComparisonProfileModel:
        expected = {
            "scenario-import",
            "experiment-task-scenario-reference",
            "experiment-run-task-reference",
            "experiment-run-scenario-snapshot-reference",
            "experiment-capture-scope-reference",
            "experiment-study-membership",
            "external-concept-subject",
        }
        if set(self.dependency_rule_versions) != expected:
            raise ValueError("comparison profile must declare the complete closed dependency rule set")
        if set(self.owner_projection_versions) != set(ArtifactKind):
            raise ValueError("comparison profile must declare every owner projection version")
        if any(
            kind not in {ArtifactKind.SCENARIO, ArtifactKind.TASK} and version != "1"
            for kind, version in self.owner_projection_versions.items()
        ):
            raise ValueError("only scenario and task owners support projection revision 2")
        return self


class ImpactScopeModel(ContractModel):
    """Exact two-sided artifact universe relative to which impact is reported."""

    scope_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)
    closure_policy: Literal["declared-exact-artifact-set/v1"] = "declared-exact-artifact-set/v1"
    closure_status: ImpactClosureStatus
    traversal_roots: tuple[str, ...] = Field(min_length=1, max_length=4096)
    before_artifacts: tuple[ArtifactCoordinate, ...] = Field(min_length=1, max_length=4096)
    after_artifacts: tuple[ArtifactCoordinate, ...] = Field(min_length=1, max_length=4096)
    scope_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _validate_scope(self) -> ImpactScopeModel:
        _require_sorted_unique(self.traversal_roots, "impact traversal_roots")
        _require_sorted_unique(tuple(_coordinate_key(item) for item in self.before_artifacts), "before artifacts")
        _require_sorted_unique(tuple(_coordinate_key(item) for item in self.after_artifacts), "after artifacts")
        if self.scope_digest != canonical_impact_scope_digest(self):
            raise ValueError("impact scope digest does not match the declared artifact scope")
        return self


class SemanticComparisonRequestModel(ContractModel):
    schema_version: Literal[SEMANTIC_COMPARISON_REQUEST_SCHEMA_VERSION] = SEMANTIC_COMPARISON_REQUEST_SCHEMA_VERSION
    comparison_profile: Literal["raes-semantic-comparison/v1"]
    comparison_profile_digest: PrefixedDigestString
    analyzer_profile: Literal["raes-reference-semantic-comparator/v1"]
    before: ArtifactCoordinate
    after: ArtifactCoordinate
    impact_scope: ImpactScopeModel
    limits: ComparisonLimitsModel = ComparisonLimitsModel()

    @model_validator(mode="after")
    def _validate_request(self) -> SemanticComparisonRequestModel:
        if self.before.artifact_kind != self.after.artifact_kind:
            raise ValueError("semantic comparison operands must have the same artifact_kind")
        before_keys = {_coordinate_key(item) for item in self.impact_scope.before_artifacts}
        after_keys = {_coordinate_key(item) for item in self.impact_scope.after_artifacts}
        if _coordinate_key(self.before) not in before_keys or _coordinate_key(self.after) not in after_keys:
            raise ValueError("semantic comparison operands must be members of their impact scope sides")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        _add_raes_invariant(
            schema,
            "semantic-comparison-governed-scope",
            "Operands use one owner-specific family and are members of a digest-bound two-sided impact scope.",
            validator="raes_contracts.semantic_comparison.SemanticComparisonRequestModel.model_validate",
            inputs=[{"contract_id": "semantic-comparison-request-v1", "instance_path": "#"}],
        )
        return schema


def canonical_impact_scope_digest(scope: ImpactScopeModel) -> str:
    return canonical_json_digest(scope.model_dump(mode="json", exclude={"scope_digest"}))


def canonical_semantic_comparison_profile_digest(profile: SemanticComparisonProfileModel) -> str:
    return canonical_json_digest(profile.model_dump(mode="json"))


def canonical_semantic_comparison_request_digest(request: SemanticComparisonRequestModel) -> str:
    return canonical_json_digest(request.model_dump(mode="json"))


def canonical_semantic_comparison_result_digest(result: SemanticComparisonResultModel) -> str:
    return canonical_json_digest(result.model_dump(mode="json"))


def parse_semantic_comparison_request(
    source: str | bytes | bytearray,
    *,
    max_bytes: int = 1_048_576,
) -> SemanticComparisonRequestModel:
    payload = parse_bounded_json_object(source, max_bytes=max_bytes)
    return SemanticComparisonRequestModel.model_validate(payload)


def _coordinate_key(coordinate: ArtifactCoordinate) -> tuple[str, str, str]:
    return (coordinate.artifact_kind.value, coordinate.canonical_identity, coordinate.canonical_digest)


def _require_coordinate_identity(actual: str, prefix: str, owner_id: str) -> None:
    if actual != f"{prefix}:{owner_id}":
        raise ValueError("owner-specific canonical identity does not match its declared owner id")


def _require_sorted_unique(values: tuple[object, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be sorted and unique")


_results = import_module(".semantic_comparison_results", __package__)
DependencyChangeModel = _results.DependencyChangeModel
DependencyStateModel = _results.DependencyStateModel
ImpactPathModel = _results.ImpactPathModel
ImpactPathStepModel = _results.ImpactPathStepModel
SemanticChangeModel = _results.SemanticChangeModel
SemanticComparisonContextModel = _results.SemanticComparisonContextModel
SemanticComparisonResultModel = _results.SemanticComparisonResultModel

__all__ = [
    "ArtifactCoordinate",
    "ArtifactKind",
    "ComparisonCompleteness",
    "ComparisonLimitsModel",
    "ComparisonReason",
    "DependencyChangeModel",
    "DependencyRelation",
    "DependencyResolutionStatus",
    "DependencyStateModel",
    "EvidenceSpecificationCoordinateModel",
    "ExactRepresentationModel",
    "ExternalConceptBindingsCoordinateModel",
    "IdentityRelation",
    "ImpactClosureStatus",
    "ImpactPathModel",
    "ImpactPathStepModel",
    "ImpactScopeModel",
    "ModuleCoordinateModel",
    "RelationStatus",
    "RunCoordinateModel",
    "ScenarioCoordinateModel",
    "SemanticChangeModel",
    "SemanticComparisonContextModel",
    "SemanticComparisonProfileModel",
    "SemanticComparisonRequestModel",
    "SemanticComparisonResultModel",
    "StudyCoordinateModel",
    "TaskCoordinateModel",
    "canonical_impact_scope_digest",
    "canonical_semantic_comparison_profile_digest",
    "canonical_semantic_comparison_request_digest",
    "canonical_semantic_comparison_result_digest",
    "parse_semantic_comparison_request",
]
