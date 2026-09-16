"""Portable finite-vector contracts for authoring-path consistency (ASR-516)."""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes.identifiers import PortableIdentifier

from .canonical import canonical_json_digest
from .contracts.base import ContractModel, PrefixedDigestString
from .contracts.schema_invariants import _add_raes_invariant
from .json_ingress import parse_bounded_json_object
from .semantic_comparison import ScenarioCoordinateModel

CaseId = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)]
Relation = Literal["equivalent", "different", "incomparable", "not-applicable"]
Reason = Literal[
    "left-input-mismatch",
    "right-input-mismatch",
    "left-invalid",
    "right-invalid",
    "left-unexpected",
    "right-unexpected",
    "outcomes-differ",
    "artifacts-differ",
    "diagnostics-differ",
    "provenance-differs",
    "semantics-differ",
    "semantic-context-incomplete",
]


class AuthoringAdapterProfileModel(ContractModel):
    """Fixed meaning and resource ceilings of the first, source-only profile."""

    profile_id: Literal["raes-authoring-adapter-conformance/v1"] = "raes-authoring-adapter-conformance/v1"
    source_profile: Literal["sdl-yaml/v1"] = "sdl-yaml/v1"
    migration_policy: Literal["reject"] = "reject"
    canonicalization_profile: Literal["raes-sdl-semantic/v2"] = "raes-sdl-semantic/v2"
    diagnostic_profile: Literal["authoring-diagnostic-semantics/v1"] = "authoring-diagnostic-semantics/v1"
    semantic_profile_digest: PrefixedDigestString
    max_source_bytes: Literal[65536] = 65536
    max_diagnostics: Literal[64] = 64
    max_cases: Literal[32] = 32


class AuthoringOperationModel(ContractModel):
    profile: Literal["validate-sdl/v1", "rename-sdl-declaration/v1"]
    target_address: str | None = Field(default=None, min_length=1, max_length=4096)
    new_local_name: PortableIdentifier | None = None

    @model_validator(mode="after")
    def _require_operation_fields(self) -> AuthoringOperationModel:
        rename = self.profile == "rename-sdl-declaration/v1"
        if rename != (self.target_address is not None) or rename != (self.new_local_name is not None):
            raise ValueError("only rename requires target_address and new_local_name")
        return self


class AuthoringObservationModel(ContractModel):
    """Derived evidence; consumers must retain the original diagnostic/report carriers."""

    outcome: Literal["success", "refused"]
    artifact_coordinate: ScenarioCoordinateModel | None
    canonical_artifact_digest: PrefixedDigestString | None
    diagnostics_digest: PrefixedDigestString
    transformation_digest: PrefixedDigestString | None

    @model_validator(mode="after")
    def _require_artifact(self) -> AuthoringObservationModel:
        success = self.outcome == "success"
        if success != (self.artifact_coordinate is not None) or success != (self.canonical_artifact_digest is not None):
            raise ValueError("success requires an artifact; refusal must not carry one")
        return self


class AuthoringContrastModel(ContractModel):
    """Fixed negative witness: one alternative emitted artifact and its dispositions."""

    output_source: str = Field(min_length=1, max_length=65536)
    artifact_relation: Literal["different"]
    semantic_relation: Literal["equivalent", "different"]


class AuthoringAdapterVectorModel(ContractModel):
    schema_version: Literal["authoring-adapter-vector/v1"] = "authoring-adapter-vector/v1"
    case_id: CaseId
    profile_digest: PrefixedDigestString
    input_source: str = Field(min_length=1, max_length=65536)
    input_digest: PrefixedDigestString
    operation: AuthoringOperationModel
    operation_digest: PrefixedDigestString
    expected: AuthoringObservationModel
    contrast: AuthoringContrastModel | None = None

    @model_validator(mode="after")
    def _require_bound_inputs(self) -> AuthoringAdapterVectorModel:
        encoded = self.input_source.encode("utf-8")
        if len(encoded) > 65536:
            raise ValueError("source exceeds the byte limit")
        if self.contrast is not None and len(self.contrast.output_source.encode("utf-8")) > 65536:
            raise ValueError("contrast source exceeds the byte limit")
        if self.input_digest != "sha256:" + hashlib.sha256(encoded).hexdigest():
            raise ValueError("input digest does not bind the exact source bytes")
        if self.operation_digest != canonical_json_digest(self.operation.model_dump(mode="json")):
            raise ValueError("operation digest does not bind the complete operation")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        _add_raes_invariant(
            schema,
            "authoring-vector-bound-inputs",
            "Exact UTF-8 source and closed operation digests must match; outcomes must bind artifacts.",
            validator="raes_contracts.authoring_adapters.AuthoringAdapterVectorModel.model_validate",
            inputs=[{"contract_id": "authoring-adapter-vector-v1", "instance_path": "#"}],
        )
        return schema


class AuthoringAdapterComparisonModel(ContractModel):
    """Four independent dispositions with a separately retained semantic result."""

    schema_version: Literal["authoring-adapter-comparison/v1"] = "authoring-adapter-comparison/v1"
    case_id: CaseId
    vector_digest: PrefixedDigestString
    left_path: CaseId
    right_path: CaseId
    left: AuthoringObservationModel | None
    right: AuthoringObservationModel | None
    left_matches_expected: bool
    right_matches_expected: bool
    artifact_relation: Relation
    diagnostic_relation: Relation
    provenance_relation: Relation
    semantic_relation: Relation
    semantic_result_digest: PrefixedDigestString | None
    reason_codes: tuple[Reason, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def _require_evidence(self) -> AuthoringAdapterComparisonModel:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("reason_codes must be sorted and unique")
        if (self.left is None and self.left_matches_expected) or (self.right is None and self.right_matches_expected):
            raise ValueError("missing observations cannot match the vector")
        comparable = self.left is not None and self.right is not None
        if not comparable and any(relation != "incomparable" for relation in self.relations):
            raise ValueError("missing observations require incomparable axes")
        has_artifacts = comparable and self.left.outcome == self.right.outcome == "success"
        if has_artifacts != (self.semantic_result_digest is not None):
            raise ValueError("two successful observations require semantic evidence")
        if has_artifacts and self.semantic_relation == "not-applicable":
            raise ValueError("two artifacts require an applicable semantic relation")
        if comparable:
            self._require_applicability(has_artifacts)
        return self

    def _require_applicability(self, has_artifacts: bool) -> None:
        no_artifacts = self.left.outcome == self.right.outcome == "refused"
        if no_artifacts != (self.artifact_relation == "not-applicable"):
            raise ValueError("artifact applicability must match the observed outcomes")
        if self.diagnostic_relation == "not-applicable":
            raise ValueError("diagnostics are always applicable to admitted observations")
        no_provenance = self.left.transformation_digest is None and self.right.transformation_digest is None
        if no_provenance != (self.provenance_relation == "not-applicable"):
            raise ValueError("provenance applicability must match the observed evidence")
        if not has_artifacts and self.semantic_relation != "not-applicable":
            raise ValueError("semantic comparison requires two artifacts")

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        _add_raes_invariant(
            schema,
            "authoring-comparison-evidence-shape",
            "Axes must remain applicable to their evidence; success requires semantic companion evidence.",
            validator="raes_contracts.authoring_adapters.AuthoringAdapterComparisonModel.model_validate",
            inputs=[{"contract_id": "authoring-adapter-comparison-v1", "instance_path": "#"}],
        )
        return schema

    @property
    def relations(self) -> tuple[Relation, ...]:
        return self.artifact_relation, self.diagnostic_relation, self.provenance_relation, self.semantic_relation

    @property
    def conformant(self) -> bool:
        return (
            self.left_matches_expected
            and self.right_matches_expected
            and all(relation in {"equivalent", "not-applicable"} for relation in self.relations)
        )


def parse_authoring_vector(source: str | bytes) -> AuthoringAdapterVectorModel:
    """Admit a bounded descriptor before resolving its pinned profiles."""
    return AuthoringAdapterVectorModel.model_validate(parse_bounded_json_object(source, max_bytes=128 * 1024))


def parse_authoring_comparison(source: str | bytes) -> AuthoringAdapterComparisonModel:
    """Admit a bounded portable report without trusting a caller's result shape."""
    return AuthoringAdapterComparisonModel.model_validate(parse_bounded_json_object(source, max_bytes=65536))


__all__ = [
    "AuthoringAdapterComparisonModel",
    "AuthoringAdapterProfileModel",
    "AuthoringAdapterVectorModel",
    "AuthoringContrastModel",
    "AuthoringObservationModel",
    "AuthoringOperationModel",
    "parse_authoring_comparison",
    "parse_authoring_vector",
]
