"""Experiment augmentation-disclosure, metric, evaluation-protocol, and apparatus-constraint contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..versions import BACKEND_MANIFEST_V2_SCHEMA_VERSION, PROCESSOR_MANIFEST_V2_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString
from .experiment_artifacts import _validate_unique_experiment_references
from .experiment_manifest_references import (
    ExperimentBackendReferenceModel,
    ExperimentEvidenceRecordReferenceModel,
    ExperimentEvidenceReferenceModel,
    ExperimentManifestReferenceModel,
    ExperimentProcessorReferenceModel,
)
from .experiment_references import ExperimentReferenceModel
from .schema_invariants import _add_raes_invariant
from .validators import _validate_unique_string_values

__all__ = [
    "ExperimentApparatusConstraintModel",
    "ExperimentAugmentationDisclosureModel",
    "ExperimentEvaluationProtocolModel",
    "ExperimentMetricDefinitionModel",
    "ExperimentSplitAndLeakageControlsModel",
]

_SEM_225_PORTABLE_CARRIER_KINDS = frozenset(
    {
        "apparatus-context",
        "capture-spec",
        "derived-measure",
        "evidence-record",
        "manifest",
        "measurement-channel",
        "profile",
        "run",
        "scenario-snapshot",
        "materialization-attestation",
    }
)


def _validate_sem_225_claim_evidence(
    classifications: set[str],
    evidence_refs: list[ExperimentEvidenceRecordReferenceModel],
) -> None:
    if classifications - {"apparatus_only"} and not evidence_refs:
        raise ValueError("environment, participant, or comparability augmentations require evidence_refs")


def _validate_sem_225_environment_visible(disclosure: ExperimentAugmentationDisclosureModel) -> None:
    if disclosure.environment_effect is None:
        raise ValueError("environment_visible augmentation disclosures require environment_effect")
    if not any(ref.ref_kind in _SEM_225_PORTABLE_CARRIER_KINDS for ref in disclosure.carrier_refs):
        raise ValueError("environment_visible augmentation disclosures require a portable carrier_ref")


def _validate_sem_225_participant_visible(disclosure: ExperimentAugmentationDisclosureModel) -> None:
    if disclosure.participant_visibility is None:
        raise ValueError("participant_visible augmentation disclosures require participant_visibility")
    if not disclosure.markings:
        raise ValueError("participant_visible augmentation disclosures require markings")


def _validate_sem_225_comparability_relevant(disclosure: ExperimentAugmentationDisclosureModel) -> None:
    if disclosure.comparability_effect is None:
        raise ValueError("comparability_relevant augmentation disclosures require comparability_effect")
    if disclosure.observer_effect is None:
        raise ValueError("comparability_relevant augmentation disclosures require observer_effect")


class ExperimentAugmentationDisclosureModel(ContractModel):
    """Disclosure for processor/backend augmentation used by a run."""

    augmentation_id: NonEmptyString
    purpose: Literal["evidence", "evaluation", "operational", "comparability", "other"]
    realization_layer: Literal[
        "processor",
        "backend",
        "apparatus",
        "runtime-environment",
        "participant-runtime",
        "measurement-channel",
        "analysis",
        "other",
    ]
    classifications: list[
        Literal["apparatus_only", "environment_visible", "participant_visible", "comparability_relevant"]
    ] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    augmented_by_ref: ExperimentReferenceModel
    carrier_refs: list[ExperimentReferenceModel] = Field(min_length=1)
    affected_refs: list[ExperimentReferenceModel] = Field(default_factory=list)
    evidence_refs: list[ExperimentEvidenceRecordReferenceModel] = Field(default_factory=list)
    disclosure_policy: NonEmptyString
    markings: list[NonEmptyString] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    observer_effect: NonEmptyString | None = None
    environment_effect: NonEmptyString | None = None
    participant_visibility: NonEmptyString | None = None
    comparability_effect: NonEmptyString | None = None
    notes: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_augmentation_disclosure(self) -> ExperimentAugmentationDisclosureModel:
        _validate_unique_string_values("augmentation classifications", self.classifications)
        _validate_unique_string_values("augmentation disclosure markings", self.markings)
        _validate_unique_string_values("augmentation disclosure notes", self.notes)
        _validate_unique_experiment_references("augmentation disclosure carrier_refs", self.carrier_refs)
        _validate_unique_experiment_references("augmentation disclosure affected_refs", self.affected_refs)
        _validate_unique_experiment_references("augmentation disclosure evidence_refs", self.evidence_refs)

        if self.augmented_by_ref.ref_kind not in {"processor", "backend"}:
            raise ValueError("augmentation disclosures must use a processor or backend augmented_by_ref")

        classification_set = set(self.classifications)
        _validate_sem_225_claim_evidence(classification_set, self.evidence_refs)
        if "environment_visible" in classification_set:
            _validate_sem_225_environment_visible(self)
        if "participant_visible" in classification_set:
            _validate_sem_225_participant_visible(self)
        if "comparability_relevant" in classification_set:
            _validate_sem_225_comparability_relevant(self)
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
                    "properties": {
                        "augmented_by_ref": {
                            "required": ["ref_kind"],
                            "properties": {"ref_kind": {"enum": ["processor", "backend"]}},
                        }
                    }
                },
                {
                    "if": {
                        "properties": {"classifications": {"contains": {"const": "environment_visible"}}},
                        "required": ["classifications"],
                    },
                    "then": {
                        "required": ["carrier_refs", "environment_effect", "evidence_refs"],
                        "properties": {
                            "environment_effect": {"type": "string", "minLength": 1},
                            "carrier_refs": {
                                "contains": {
                                    "required": ["ref_kind"],
                                    "properties": {"ref_kind": {"enum": sorted(_SEM_225_PORTABLE_CARRIER_KINDS)}},
                                }
                            },
                            "evidence_refs": {"minItems": 1},
                        },
                    },
                },
                {
                    "if": {
                        "properties": {"classifications": {"contains": {"const": "participant_visible"}}},
                        "required": ["classifications"],
                    },
                    "then": {
                        "required": ["participant_visibility", "markings", "evidence_refs"],
                        "properties": {
                            "participant_visibility": {"type": "string", "minLength": 1},
                            "markings": {"minItems": 1},
                            "evidence_refs": {"minItems": 1},
                        },
                    },
                },
                {
                    "if": {
                        "properties": {"classifications": {"contains": {"const": "comparability_relevant"}}},
                        "required": ["classifications"],
                    },
                    "then": {
                        "required": ["comparability_effect", "observer_effect", "evidence_refs"],
                        "properties": {
                            "comparability_effect": {"type": "string", "minLength": 1},
                            "observer_effect": {"type": "string", "minLength": 1},
                            "evidence_refs": {"minItems": 1},
                        },
                    },
                },
            ]
        )
        _add_raes_invariant(
            json_schema,
            "augmentation-disclosure-semantics-valid",
            "Augmentation disclosures must keep environment-visible, participant-visible, and "
            "comparability-relevant semantics explicit and must use processor/backend authority.",
            validator=(
                "raes_contracts.contracts.ExperimentAugmentationDisclosureModel._validate_augmentation_disclosure"
            ),
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#/augmentation_disclosures"}],
        )
        return json_schema


class ExperimentMetricDefinitionModel(ContractModel):
    """Metric definition bound to a measured construct and unit of analysis."""

    metric_id: NonEmptyString
    metric_version: NonEmptyString
    name: NonEmptyString
    measured_construct: NonEmptyString
    unit_of_analysis: NonEmptyString
    value_kind: Literal["boolean", "integer", "number", "duration", "count", "category", "text"]
    direction: Literal["higher-is-better", "lower-is-better", "target", "descriptive"]
    aggregation: NonEmptyString | None = None
    missingness_policy: NonEmptyString | None = None
    uncertainty_policy: NonEmptyString | None = None
    evidence_requirements: list[ExperimentEvidenceReferenceModel] = Field(min_length=1)


class ExperimentEvaluationProtocolModel(ContractModel):
    """Evaluation protocol that binds metrics and observation requirements."""

    protocol_id: NonEmptyString
    protocol_version: NonEmptyString
    intent: NonEmptyString
    unit_of_analysis: NonEmptyString
    metric_definitions: dict[NonEmptyString, ExperimentMetricDefinitionModel] = Field(min_length=1)
    observation_requirements: list[ExperimentEvidenceReferenceModel] = Field(min_length=1)
    aggregation_policy: NonEmptyString | None = None
    acceptance_policy: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_metric_definition_keys(self) -> ExperimentEvaluationProtocolModel:
        mismatches = [
            metric_key
            for metric_key, definition in self.metric_definitions.items()
            if definition.metric_id != metric_key
        ]
        if mismatches:
            joined = ", ".join(sorted(mismatches))
            raise ValueError(f"metric_definitions keys must match embedded metric_id: {joined}")
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
            "metric-definition-key-matches-metric-id",
            "Every metric_definitions object key must match the embedded metric_id value.",
            validator="raes_contracts.contracts.ExperimentEvaluationProtocolModel._validate_metric_definition_keys",
            inputs=[{"contract_id": "experiment-task-v1", "instance_path": "#/evaluation_protocol"}],
        )
        return json_schema


class ExperimentSplitAndLeakageControlsModel(ContractModel):
    """Controls for data partitioning, hidden material, and leakage risk."""

    partitioning_strategy: NonEmptyString | None = None
    grouping_constraints: list[NonEmptyString] = Field(default_factory=list)
    temporal_availability: NonEmptyString | None = None
    hidden_material_policy: NonEmptyString | None = None
    leakage_checks: list[NonEmptyString] = Field(default_factory=list)
    unresolved_risks: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_disclosure_surface(self) -> ExperimentSplitAndLeakageControlsModel:
        if not any(
            (
                self.partitioning_strategy,
                self.grouping_constraints,
                self.temporal_availability,
                self.hidden_material_policy,
                self.leakage_checks,
                self.unresolved_risks,
            )
        ):
            raise ValueError("split_and_leakage_controls must disclose at least one control, policy, or risk")
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
                {
                    "required": ["partitioning_strategy"],
                    "properties": {"partitioning_strategy": {"not": {"type": "null"}}},
                },
                {
                    "required": ["temporal_availability"],
                    "properties": {"temporal_availability": {"not": {"type": "null"}}},
                },
                {
                    "required": ["hidden_material_policy"],
                    "properties": {"hidden_material_policy": {"not": {"type": "null"}}},
                },
                {"required": ["grouping_constraints"], "properties": {"grouping_constraints": {"minItems": 1}}},
                {"required": ["leakage_checks"], "properties": {"leakage_checks": {"minItems": 1}}},
                {"required": ["unresolved_risks"], "properties": {"unresolved_risks": {"minItems": 1}}},
            ]
        )
        return json_schema


def _expected_manifest_schema_version_for_ref_kind(ref_kind: str) -> str:
    return PROCESSOR_MANIFEST_V2_SCHEMA_VERSION if ref_kind == "processor" else BACKEND_MANIFEST_V2_SCHEMA_VERSION


def _validate_required_manifest_subject_ref(manifest: ExperimentManifestReferenceModel) -> None:
    subject_ref = manifest.subject_ref
    if subject_ref is None or subject_ref.ref_kind not in {"processor", "backend"}:
        return
    expected_manifest_version = _expected_manifest_schema_version_for_ref_kind(subject_ref.ref_kind)
    if manifest.ref_version != expected_manifest_version:
        return
    if manifest.ref_id != subject_ref.ref_id:
        raise ValueError("processor/backend required_manifest_refs ref_id must match subject_ref.ref_id")
    if subject_ref.ref_digest is not None or subject_ref.ref_path is not None:
        raise ValueError("processor/backend required_manifest_refs subject_ref must not carry ref_digest or ref_path")


def _validate_required_manifest_subject_refs(
    required_manifest_refs: list[ExperimentManifestReferenceModel],
) -> None:
    for manifest in required_manifest_refs:
        _validate_required_manifest_subject_ref(manifest)


def _build_required_manifest_keys(
    required_manifest_refs: list[ExperimentManifestReferenceModel],
) -> set[tuple[str, str, str, str]]:
    return {
        (
            manifest.subject_ref.ref_kind,
            manifest.subject_ref.ref_id,
            manifest.subject_ref.ref_version,
            manifest.ref_version,
        )
        for manifest in required_manifest_refs
        if manifest.subject_ref is not None
    }


def _validate_apparatus_constraint_disclosure_surface(model: ExperimentApparatusConstraintModel) -> None:
    if not any(
        (
            model.allowed_processor_refs,
            model.allowed_backend_refs,
            model.required_manifest_refs,
            model.required_capabilities,
            model.notes,
        )
    ):
        raise ValueError("apparatus_constraints must declare at least one apparatus constraint or disclosure note")


def _validate_allowed_processor_refs_resolve(
    allowed_processor_refs: list[ExperimentProcessorReferenceModel],
    required_manifest_keys: set[tuple[str, str, str, str]],
) -> None:
    for ref in allowed_processor_refs:
        if (
            "processor",
            ref.ref_id,
            ref.ref_version,
            PROCESSOR_MANIFEST_V2_SCHEMA_VERSION,
        ) not in required_manifest_keys:
            raise ValueError(
                "allowed_processor_refs entries must have a matching required_manifest_refs "
                f"entry with processor subject_ref='{ref.ref_id}' and "
                f"manifest ref_version='{PROCESSOR_MANIFEST_V2_SCHEMA_VERSION}'"
            )


def _validate_allowed_backend_refs_resolve(
    allowed_backend_refs: list[ExperimentBackendReferenceModel],
    required_manifest_keys: set[tuple[str, str, str, str]],
) -> None:
    for ref in allowed_backend_refs:
        if (
            "backend",
            ref.ref_id,
            ref.ref_version,
            BACKEND_MANIFEST_V2_SCHEMA_VERSION,
        ) not in required_manifest_keys:
            raise ValueError(
                "allowed_backend_refs entries must have a matching required_manifest_refs "
                f"entry with backend subject_ref='{ref.ref_id}' and "
                f"manifest ref_version='{BACKEND_MANIFEST_V2_SCHEMA_VERSION}'"
            )


class ExperimentApparatusConstraintModel(ContractModel):
    """Apparatus compatibility and capability constraints for a task."""

    allowed_processor_refs: list[ExperimentProcessorReferenceModel] = Field(default_factory=list)
    allowed_backend_refs: list[ExperimentBackendReferenceModel] = Field(default_factory=list)
    required_manifest_refs: list[ExperimentManifestReferenceModel] = Field(default_factory=list)
    required_capabilities: list[NonEmptyString] = Field(default_factory=list)
    notes: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_allowed_identity_manifest_refs(self) -> ExperimentApparatusConstraintModel:
        _validate_apparatus_constraint_disclosure_surface(self)
        _validate_required_manifest_subject_refs(self.required_manifest_refs)
        required_manifest_keys = _build_required_manifest_keys(self.required_manifest_refs)
        _validate_allowed_processor_refs_resolve(self.allowed_processor_refs, required_manifest_keys)
        _validate_allowed_backend_refs_resolve(self.allowed_backend_refs, required_manifest_keys)
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
                {"required": ["allowed_processor_refs"], "properties": {"allowed_processor_refs": {"minItems": 1}}},
                {"required": ["allowed_backend_refs"], "properties": {"allowed_backend_refs": {"minItems": 1}}},
                {"required": ["required_manifest_refs"], "properties": {"required_manifest_refs": {"minItems": 1}}},
                {"required": ["required_capabilities"], "properties": {"required_capabilities": {"minItems": 1}}},
                {"required": ["notes"], "properties": {"notes": {"minItems": 1}}},
            ]
        )
        _add_raes_invariant(
            json_schema,
            "apparatus-constraint-identity-manifest-resolves",
            "Every allowed processor/backend identity reference must have a matching required manifest ref_id "
            "with matching manifest id, subject identity, and manifest schema version.",
            validator=(
                "raes_contracts.contracts.ExperimentApparatusConstraintModel._validate_allowed_identity_manifest_refs"
            ),
            inputs=[{"contract_id": "experiment-task-v1", "instance_path": "#/apparatus_constraints"}],
        )
        return json_schema
