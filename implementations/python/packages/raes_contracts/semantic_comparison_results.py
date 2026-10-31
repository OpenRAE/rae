"""Result-side DTOs for semantic comparison and impact analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from .contracts.artifact_transformations import ArtifactTransformationReportModel
from .contracts.base import ContractModel, PrefixedDigestString
from .contracts.schema_invariants import _add_raes_invariant
from .diagnostics import DiagnosticModel
from .semantic_comparison import (
    _IDENTITY_PATTERN,
    ArtifactCoordinate,
    ComparisonCompleteness,
    ComparisonReason,
    DependencyRelation,
    DependencyResolutionStatus,
    IdentityRelation,
    ImpactScopeModel,
    RelationStatus,
    _require_sorted_unique,
)
from .versions import SEMANTIC_COMPARISON_RESULT_SCHEMA_VERSION


class SemanticComparisonContextModel(ContractModel):
    transformation_report: ArtifactTransformationReportModel | None = None
    evidence_digests: tuple[PrefixedDigestString, ...] = ()

    @model_validator(mode="after")
    def _validate_context(self) -> SemanticComparisonContextModel:
        _require_sorted_unique(self.evidence_digests, "context evidence_digests")
        return self


class SemanticChangeModel(ContractModel):
    identity: str = Field(pattern=_IDENTITY_PATTERN, max_length=512)
    before_identity: str | None = Field(default=None, pattern=_IDENTITY_PATTERN, max_length=512)
    after_identity: str | None = Field(default=None, pattern=_IDENTITY_PATTERN, max_length=512)
    identity_relation: IdentityRelation
    textual_relation: RelationStatus
    structural_relation: RelationStatus
    semantic_relation: RelationStatus
    reason_codes: tuple[ComparisonReason, ...] = ()

    @model_validator(mode="after")
    def _validate_change(self) -> SemanticChangeModel:
        _require_sorted_unique(self.reason_codes, "change reason_codes")
        if self.identity_relation == IdentityRelation.ADDED and (
            self.before_identity is not None or self.after_identity is None
        ):
            raise ValueError("added changes require only after_identity")
        if self.identity_relation == IdentityRelation.REMOVED and (
            self.before_identity is None or self.after_identity is not None
        ):
            raise ValueError("removed changes require only before_identity")
        if self.identity_relation in {IdentityRelation.SAME, IdentityRelation.RENAMED} and (
            self.before_identity is None or self.after_identity is None
        ):
            raise ValueError("same and renamed changes require both identities")
        return self


class DependencyStateModel(ContractModel):
    dependency_identity: str = Field(pattern=_IDENTITY_PATTERN, max_length=512)
    resolution_status: DependencyResolutionStatus
    provenance_digests: tuple[PrefixedDigestString, ...] = ()
    reason_codes: tuple[ComparisonReason, ...] = ()

    @model_validator(mode="after")
    def _validate_state(self) -> DependencyStateModel:
        _require_sorted_unique(self.provenance_digests, "dependency provenance_digests")
        _require_sorted_unique(self.reason_codes, "dependency reason_codes")
        if self.resolution_status == DependencyResolutionStatus.RESOLVED and self.reason_codes:
            raise ValueError("resolved dependency states cannot carry reason codes")
        if self.resolution_status != DependencyResolutionStatus.RESOLVED and not self.reason_codes:
            raise ValueError("unresolved dependency states require a reason code")
        return self


class DependencyChangeModel(ContractModel):
    dependent_identity: str = Field(pattern=_IDENTITY_PATTERN, max_length=512)
    rule_id: Literal[
        "scenario-import",
        "experiment-task-scenario-reference",
        "experiment-run-task-reference",
        "experiment-run-scenario-snapshot-reference",
        "experiment-capture-scope-reference",
        "experiment-study-membership",
        "external-concept-subject",
    ]
    rule_version: Literal["1"] = "1"
    relation: DependencyRelation
    before: DependencyStateModel | None = None
    after: DependencyStateModel | None = None

    @model_validator(mode="after")
    def _validate_sides(self) -> DependencyChangeModel:
        error = _dependency_sides_error(self.relation, self.before, self.after)
        if error is not None:
            raise ValueError(error)
        return self


class ImpactPathStepModel(ContractModel):
    dependent_identity: str = Field(pattern=_IDENTITY_PATTERN, max_length=512)
    dependency_identity: str = Field(pattern=_IDENTITY_PATTERN, max_length=512)
    rule_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)
    rule_version: Literal["1"] = "1"
    evidence_side: Literal["before", "after"]


class ImpactPathModel(ContractModel):
    source_identity: str = Field(pattern=_IDENTITY_PATTERN, max_length=512)
    affected_identity: str = Field(pattern=_IDENTITY_PATTERN, max_length=512)
    steps: tuple[ImpactPathStepModel, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _validate_path(self) -> ImpactPathModel:
        current = self.source_identity
        for step in self.steps:
            if step.dependency_identity != current:
                raise ValueError("impact path steps must form a dependency-to-dependent chain")
            current = step.dependent_identity
        if current != self.affected_identity:
            raise ValueError("impact path affected_identity must match the final dependent")
        return self


class SemanticComparisonResultModel(ContractModel):
    schema_version: Literal[SEMANTIC_COMPARISON_RESULT_SCHEMA_VERSION] = SEMANTIC_COMPARISON_RESULT_SCHEMA_VERSION
    comparison_profile: Literal["raes-semantic-comparison/v1"]
    comparison_profile_digest: PrefixedDigestString
    analyzer_profile: Literal["raes-reference-semantic-comparator/v1"]
    request_digest: PrefixedDigestString
    before: ArtifactCoordinate
    after: ArtifactCoordinate
    impact_scope: ImpactScopeModel
    impact_scope_digest: PrefixedDigestString
    changes: tuple[SemanticChangeModel, ...] = Field(max_length=4096)
    dependencies: tuple[DependencyChangeModel, ...] = Field(max_length=8192)
    impact_paths: tuple[ImpactPathModel, ...] = Field(max_length=4096)
    completeness: ComparisonCompleteness
    reason_codes: tuple[ComparisonReason, ...] = Field(default=(), max_length=128)
    context_digests: tuple[PrefixedDigestString, ...] = Field(default=(), max_length=128)
    diagnostics: tuple[DiagnosticModel, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def _validate_result(self) -> SemanticComparisonResultModel:
        if self.impact_scope_digest != self.impact_scope.scope_digest:
            raise ValueError("result impact scope digest does not match the embedded scope digest")
        _require_sorted_unique(tuple(_change_key(item) for item in self.changes), "changes")
        _require_sorted_unique(tuple(_dependency_key(item) for item in self.dependencies), "dependencies")
        _require_sorted_unique(tuple(_path_key(item) for item in self.impact_paths), "impact paths")
        _require_sorted_unique(self.reason_codes, "result reason_codes")
        _require_sorted_unique(self.context_digests, "result context_digests")
        child_reasons = {reason for change in self.changes for reason in change.reason_codes}
        for dependency in self.dependencies:
            for state in (dependency.before, dependency.after):
                if state is not None:
                    child_reasons.update(state.reason_codes)
        if not child_reasons.issubset(set(self.reason_codes)):
            raise ValueError("result reason_codes must include every child reason")
        if self.completeness == ComparisonCompleteness.COMPLETE and self.reason_codes:
            raise ValueError("complete results cannot carry indeterminate reasons")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        _add_raes_invariant(
            schema,
            "semantic-comparison-independent-change-axes",
            "Identity, exact representation, structure, and semantic relations remain independent.",
            inputs=[{"contract_id": "semantic-comparison-result-v1", "instance_path": "#"}],
        )
        return schema


def _change_key(change: SemanticChangeModel) -> tuple[str, str, str]:
    return (change.identity, change.before_identity or "", change.after_identity or "")


def _has_only_after(before: DependencyStateModel | None, after: DependencyStateModel | None) -> bool:
    return before is None and after is not None


def _has_only_before(before: DependencyStateModel | None, after: DependencyStateModel | None) -> bool:
    return before is not None and after is None


def _has_both_sides(before: DependencyStateModel | None, after: DependencyStateModel | None) -> bool:
    return before is not None and after is not None


def _dependency_sides_error(
    relation: DependencyRelation,
    before: DependencyStateModel | None,
    after: DependencyStateModel | None,
) -> str | None:
    validators = {
        DependencyRelation.ADDED: _added_sides_error,
        DependencyRelation.REMOVED: _removed_sides_error,
        DependencyRelation.UNCHANGED: _unchanged_sides_error,
        DependencyRelation.CHANGED: _changed_sides_error,
    }
    return validators[relation](before, after)


def _added_sides_error(before: DependencyStateModel | None, after: DependencyStateModel | None) -> str | None:
    return None if _has_only_after(before, after) else "added dependencies require only an after state"


def _removed_sides_error(before: DependencyStateModel | None, after: DependencyStateModel | None) -> str | None:
    return None if _has_only_before(before, after) else "removed dependencies require only a before state"


def _unchanged_sides_error(before: DependencyStateModel | None, after: DependencyStateModel | None) -> str | None:
    valid = _has_both_sides(before, after) and before == after
    return None if valid else "unchanged dependencies require equal before and after states"


def _changed_sides_error(before: DependencyStateModel | None, after: DependencyStateModel | None) -> str | None:
    valid = _has_both_sides(before, after) and before != after
    return None if valid else "changed dependencies require distinct before and after states"


def _dependency_key(change: DependencyChangeModel) -> tuple[str, str, str, str]:
    before = change.before.dependency_identity if change.before else ""
    after = change.after.dependency_identity if change.after else ""
    return (change.dependent_identity, change.rule_id, before, after)


def _path_key(path: ImpactPathModel) -> tuple[str, str, tuple[tuple[str, str, str], ...]]:
    return (
        path.source_identity,
        path.affected_identity,
        tuple((step.dependency_identity, step.dependent_identity, step.rule_id) for step in path.steps),
    )


__all__ = [
    "DependencyChangeModel",
    "DependencyStateModel",
    "ImpactPathModel",
    "ImpactPathStepModel",
    "SemanticChangeModel",
    "SemanticComparisonContextModel",
    "SemanticComparisonResultModel",
]
