"""Experiment evidence-record, derived-measure, and realized-form contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..versions import (
    EXPERIMENT_DERIVED_MEASURE_SCHEMA_VERSION,
    EXPERIMENT_EVIDENCE_RECORD_SCHEMA_VERSION,
)
from .base import ContractModel, NonEmptyString, Rfc3339DateTimeString, _parse_rfc3339_datetime
from .experiment_artifacts import (
    ExperimentDerivedMeasureReferenceModel,
    _validate_unique_experiment_references,
)
from .experiment_capture import ExperimentRawEvidenceContentModel
from .experiment_manifest_references import (
    ExperimentCaptureSpecReferenceModel,
    ExperimentEvidenceRecordReferenceModel,
)
from .experiment_references import (
    ExperimentParameterModel,
    ExperimentReferenceModel,
    ExperimentTaskReferenceModel,
)
from .schema_invariants import (
    _add_raes_invariant,
    _add_raes_plane,
    _extend_reported_value_status_schema,
    _validate_reported_value_status,
)


class ExperimentEvidenceRecordModel(ContractModel):
    """Raw captured EXP-708 evidence record, distinct from derived measures."""

    schema_version: Literal[EXPERIMENT_EVIDENCE_RECORD_SCHEMA_VERSION]
    evidence_record_id: NonEmptyString
    record_version: NonEmptyString
    capture_spec_ref: ExperimentCaptureSpecReferenceModel
    capture_requirement_ref: NonEmptyString
    output_contract: NonEmptyString
    run_ref: ExperimentReferenceModel
    task_ref: ExperimentTaskReferenceModel | None = None
    apparatus_context_ref: ExperimentReferenceModel | None = None
    source_refs: list[ExperimentReferenceModel] = Field(min_length=1)
    evidence_kind: Literal["artifact", "observation", "trace", "telemetry", "log", "packet-capture", "other"]
    captured_at: Rfc3339DateTimeString
    capture_window_ref: NonEmptyString
    raw_content: ExperimentRawEvidenceContentModel
    sensitivity: Literal["public", "internal", "restricted", "redacted"]
    redaction_state: Literal["none", "redacted", "withheld"]
    redaction_policy: NonEmptyString | None = None
    provenance_refs: list[ExperimentReferenceModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_evidence_record(self) -> ExperimentEvidenceRecordModel:
        _parse_rfc3339_datetime("captured_at", self.captured_at)
        if self.redaction_state != "none" and self.raw_content.loss_disclosure is None:
            raise ValueError("redacted or withheld evidence records must include raw_content.loss_disclosure")
        if (self.redaction_state == "none") != (self.redaction_policy is None):
            raise ValueError("redacted or withheld evidence records require exactly one redaction_policy")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "evidence-record-raw-content-present",
            "Evidence records must carry raw content as an artifact reference, content URI with checksum, or bounded "
            "payload summary; redacted/withheld records must disclose loss.",
            validator="raes_contracts.contracts.ExperimentEvidenceRecordModel._validate_evidence_record",
            inputs=[{"contract_id": "experiment-evidence-record-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "evidence-record-captured-at-valid",
            "captured_at must be a valid RFC 3339 date-time.",
            validator="raes_contracts.contracts.ExperimentEvidenceRecordModel._validate_evidence_record",
            inputs=[{"contract_id": "experiment-evidence-record-v1", "instance_path": "#/captured_at"}],
        )
        # SEM-216 B4: redacted or withheld evidence records must disclose redaction/loss at the
        # evidence boundary. Publish the model rule as a portable schema constraint so any
        # consumer validating against the JSON Schema enforces the disclosure, not just the model.
        json_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"redaction_state": {"enum": ["redacted", "withheld"]}},
                    "required": ["redaction_state"],
                },
                "then": {
                    "required": ["raw_content"],
                    "properties": {
                        "raw_content": {
                            "required": ["loss_disclosure"],
                            "properties": {"loss_disclosure": {"type": "string", "minLength": 1}},
                        }
                    },
                },
            }
        )
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {"properties": {"redaction_state": {"const": "none"}}, "required": ["redaction_state"]},
                    "then": {"properties": {"redaction_policy": {"type": "null"}}},
                },
                {
                    "if": {
                        "properties": {"redaction_state": {"enum": ["redacted", "withheld"]}},
                        "required": ["redaction_state"],
                    },
                    "then": {
                        "required": ["redaction_policy"],
                        "properties": {"redaction_policy": {"type": "string", "minLength": 1}},
                    },
                },
            ]
        )
        _add_raes_plane(json_schema, "experiment-evidence-record-v1")
        return json_schema


class ExperimentDerivedMeasureMethodModel(ContractModel):
    """Method metadata for deriving measures from raw evidence."""

    method_id: NonEmptyString
    method_version: NonEmptyString
    name: NonEmptyString
    description: NonEmptyString | None = None
    parameters: list[ExperimentParameterModel] = Field(default_factory=list)


class ExperimentDerivedMeasureModel(ContractModel):
    """EXP-709 derived measure/evaluation output computed from raw evidence."""

    schema_version: Literal[EXPERIMENT_DERIVED_MEASURE_SCHEMA_VERSION]
    derived_measure_id: NonEmptyString
    measure_version: NonEmptyString
    measure_kind: Literal["metric", "evaluation", "score", "summary", "analysis-output", "other"]
    metric_ref: ExperimentReferenceModel
    method: ExperimentDerivedMeasureMethodModel
    source_evidence_refs: list[ExperimentEvidenceRecordReferenceModel] = Field(min_length=1)
    generated_at: Rfc3339DateTimeString
    value_status: Literal["reported", "missing", "withheld", "not-applicable"]
    value: str | int | float | bool | None = None
    uncertainty: NonEmptyString | None = None
    limitations: list[NonEmptyString] = Field(default_factory=list)
    provenance_refs: list[ExperimentReferenceModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_derived_measure(self) -> ExperimentDerivedMeasureModel:
        _parse_rfc3339_datetime("generated_at", self.generated_at)
        _validate_reported_value_status(
            self.value_status,
            self.value,
            reported_message="reported derived measures must include value",
            non_reported_message="non-reported derived measures must not include value",
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
        _extend_reported_value_status_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "derived-measure-reported-value-present",
            "Reported derived measures must include a value; missing/withheld/not-applicable measures must not.",
            validator="raes_contracts.contracts.ExperimentDerivedMeasureModel._validate_derived_measure",
            inputs=[{"contract_id": "experiment-derived-measure-v1", "instance_path": "#"}],
        )
        _add_raes_invariant(
            json_schema,
            "derived-measure-generated-at-valid",
            "generated_at must be a valid RFC 3339 date-time.",
            validator="raes_contracts.contracts.ExperimentDerivedMeasureModel._validate_derived_measure",
            inputs=[{"contract_id": "experiment-derived-measure-v1", "instance_path": "#/generated_at"}],
        )
        _add_raes_plane(json_schema, "experiment-derived-measure-v1")
        return json_schema


class ExperimentRunTraceabilityModel(ContractModel):
    """Canonical run provenance links across capture, evidence, measures, and claims."""

    capture_spec_refs: list[ExperimentCaptureSpecReferenceModel] = Field(min_length=1)
    evidence_record_refs: list[ExperimentEvidenceRecordReferenceModel] = Field(min_length=1)
    derived_measure_refs: list[ExperimentDerivedMeasureReferenceModel] = Field(default_factory=list)
    claim_refs: list[ExperimentReferenceModel] = Field(default_factory=list)
    notes: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_run_traceability(self) -> ExperimentRunTraceabilityModel:
        _validate_unique_experiment_references("traceability capture_spec_refs", self.capture_spec_refs)
        _validate_unique_experiment_references("traceability evidence_record_refs", self.evidence_record_refs)
        _validate_unique_experiment_references("traceability derived_measure_refs", self.derived_measure_refs)
        _validate_unique_experiment_references("traceability claim_refs", self.claim_refs)
        if self.claim_refs and not self.derived_measure_refs:
            raise ValueError("traceability claim_refs require at least one derived_measure_refs entry")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "run-traceability-refs-unique",
            "Run provenance traceability references must be duplicate-free, and claim refs must be grounded by "
            "at least one derived measure ref.",
            validator="raes_contracts.contracts.ExperimentRunTraceabilityModel._validate_run_traceability",
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#/traceability"}],
        )
        return json_schema


class ExperimentRealizedFormDisclosureModel(ContractModel):
    """Disclosure of one realized form chosen for an underspecified run concern."""

    concern_id: NonEmptyString
    concern_kind: Literal[
        "scenario-module",
        "processor-selection",
        "backend-selection",
        "participant-implementation",
        "apparatus-configuration",
        "parameter-default",
        "stochastic-control",
        "measurement-channel",
        "capture-window",
        "other",
    ]
    basis: Literal["author-declared", "processor-realized", "backend-realized", "operator-supplied", "observed"]
    realized_by_ref: ExperimentReferenceModel
    authored_ref: ExperimentReferenceModel | None = None
    realized_ref: ExperimentReferenceModel | None = None
    realized_value_summary: NonEmptyString | None = None
    disclosure: NonEmptyString
    evidence_refs: list[ExperimentEvidenceRecordReferenceModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_realized_form_disclosure(self) -> ExperimentRealizedFormDisclosureModel:
        if self.realized_ref is None and self.realized_value_summary is None:
            raise ValueError("realized form disclosures must include realized_ref or realized_value_summary")
        if self.basis == "processor-realized" and self.realized_by_ref.ref_kind != "processor":
            raise ValueError("processor-realized disclosures must use a processor realized_by_ref")
        if self.basis == "backend-realized" and self.realized_by_ref.ref_kind != "backend":
            raise ValueError("backend-realized disclosures must use a backend realized_by_ref")
        _validate_unique_experiment_references("realized form disclosure evidence_refs", self.evidence_refs)
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("anyOf", []).extend(
            [
                {"required": ["realized_ref"], "properties": {"realized_ref": {"not": {"type": "null"}}}},
                {
                    "required": ["realized_value_summary"],
                    "properties": {"realized_value_summary": {"not": {"type": "null"}}},
                },
            ]
        )
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {"properties": {"basis": {"const": "processor-realized"}}, "required": ["basis"]},
                    "then": {
                        "properties": {
                            "realized_by_ref": {
                                "required": ["ref_kind"],
                                "properties": {"ref_kind": {"const": "processor"}},
                            }
                        }
                    },
                },
                {
                    "if": {"properties": {"basis": {"const": "backend-realized"}}, "required": ["basis"]},
                    "then": {
                        "properties": {
                            "realized_by_ref": {
                                "required": ["ref_kind"],
                                "properties": {"ref_kind": {"const": "backend"}},
                            }
                        }
                    },
                },
            ]
        )
        _add_raes_invariant(
            json_schema,
            "realized-form-disclosure-substantive",
            "Every realized-form disclosure must name a realized reference or value summary and use the right "
            "processor/backend realization authority for processor-realized and backend-realized concerns.",
            validator=(
                "raes_contracts.contracts.ExperimentRealizedFormDisclosureModel._validate_realized_form_disclosure"
            ),
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#/realized_form_disclosures"}],
        )
        return json_schema
