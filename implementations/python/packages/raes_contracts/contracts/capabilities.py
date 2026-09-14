"""Provisioner/orchestrator/evaluator capability and realization-support contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..artifact_requirements import ArtifactMechanismCapability
from ..domain_profiles import DomainProfileCoordinateModel
from ..operating_systems import OS_VERSION_PATTERN, validate_operating_system_pair
from ..vocabulary import (
    GeneratedArtifactDeliveryMode,
    GeneratedArtifactKind,
    ObservationStrength,
    ProcessResourceLimitKind,
    ProcessResourceLimitScope,
    RealizationSupportMode,
    RealizationVerificationScope,
    WorkflowFeature,
    WorkflowStatePredicateFeature,
)
from .base import ContractModel, NonEmptyString
from .validators import _validate_controlled_vocabulary_terms

OSReleaseString = Annotated[str, Field(min_length=1, max_length=128, pattern=OS_VERSION_PATTERN)]


class OperatingSystemCompatibilityModel(ContractModel):
    """One portable, coupled OS family/distribution/release capability row."""

    family: NonEmptyString
    distribution: NonEmptyString
    versions: list[OSReleaseString] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_terms(self) -> OperatingSystemCompatibilityModel:
        _validate_controlled_vocabulary_terms(
            "capabilities.provisioner.supported_os_families",
            [self.family],
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.provisioner.operating_systems.distribution",
            [self.distribution],
        )
        validate_operating_system_pair(self.family, self.distribution)
        if len(self.versions) != len(set(self.versions)):
            raise ValueError("versions must not contain duplicates")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema["properties"]["versions"]["uniqueItems"] = True
        return json_schema


def _validate_operating_system_rows(model: ProvisionerCapabilitiesModel) -> None:
    os_keys = [(entry.family, entry.distribution) for entry in model.operating_systems]
    if len(os_keys) != len(set(os_keys)):
        raise ValueError("operating_systems must not contain duplicate family/distribution rows")
    undeclared_families = {
        entry.family for entry in model.operating_systems if entry.family not in model.supported_os_families
    }
    if undeclared_families:
        raise ValueError(
            "operating_systems families must be present in supported_os_families: "
            + ", ".join(sorted(undeclared_families))
        )


def _validate_account_feature_coupling(model: ProvisionerCapabilitiesModel) -> None:
    if model.supports_accounts and not model.supported_account_features:
        raise ValueError("provisioners that support accounts must declare supported_account_features")
    if not model.supports_accounts and model.supported_account_features:
        raise ValueError("supported_account_features require supports_accounts=true")


def _validate_generated_artifact_kind_coupling(model: ProvisionerCapabilitiesModel) -> None:
    if len(model.supported_generated_artifact_kinds) != len(set(model.supported_generated_artifact_kinds)):
        raise ValueError("supported_generated_artifact_kinds must not contain duplicates")
    if model.supports_generated_artifacts and not model.supported_generated_artifact_kinds:
        raise ValueError(
            "provisioners that support generated artifacts must declare supported_generated_artifact_kinds"
        )
    if not model.supports_generated_artifacts and model.supported_generated_artifact_kinds:
        raise ValueError("supported_generated_artifact_kinds require supports_generated_artifacts=true")


def _validate_generated_artifact_delivery_coupling(model: ProvisionerCapabilitiesModel) -> None:
    if len(model.supported_generated_artifact_delivery_modes) != len(
        set(model.supported_generated_artifact_delivery_modes)
    ):
        raise ValueError("supported_generated_artifact_delivery_modes must not contain duplicates")
    if not model.supports_generated_artifacts and model.supported_generated_artifact_delivery_modes:
        raise ValueError("supported_generated_artifact_delivery_modes require supports_generated_artifacts=true")


def _validate_feature_coupling(model: ProvisionerCapabilitiesModel) -> None:
    _validate_account_feature_coupling(model)
    _validate_generated_artifact_kind_coupling(model)
    _validate_generated_artifact_delivery_coupling(model)


class ProvisionerCapabilitiesModel(ContractModel):
    name: NonEmptyString
    supported_node_types: list[NonEmptyString] = Field(min_length=1)
    supported_os_families: list[NonEmptyString] = Field(min_length=1)
    operating_systems: list[OperatingSystemCompatibilityModel] = Field(default_factory=list)
    supported_node_architectures: list[NonEmptyString] = Field(default_factory=list)
    supported_content_types: list[NonEmptyString] = Field(default_factory=list)
    supported_account_features: list[NonEmptyString] = Field(default_factory=list)
    supported_domain_profiles: list[NonEmptyString | DomainProfileCoordinateModel] = Field(default_factory=list)
    supported_service_materialization_profiles: list[NonEmptyString | DomainProfileCoordinateModel] = Field(
        default_factory=list
    )
    max_total_nodes: int | None = Field(default=None, gt=0)
    supports_acls: bool = False
    supports_accounts: bool = False
    supports_generated_artifacts: bool = False
    supported_generated_artifact_kinds: list[GeneratedArtifactKind | DomainProfileCoordinateModel] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    supported_generated_artifact_delivery_modes: list[GeneratedArtifactDeliveryMode] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    supports_persistent_volumes: bool = False
    constraints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_account_support(self) -> ProvisionerCapabilitiesModel:
        _validate_controlled_vocabulary_terms(
            "capabilities.provisioner.supported_node_types",
            self.supported_node_types,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.provisioner.supported_os_families",
            self.supported_os_families,
        )
        _validate_operating_system_rows(self)
        _validate_controlled_vocabulary_terms(
            "capabilities.provisioner.supported_node_architectures",
            self.supported_node_architectures,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.provisioner.supported_content_types",
            self.supported_content_types,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.provisioner.supported_account_features",
            self.supported_account_features,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.provisioner.supported_domain_profiles",
            [value for value in self.supported_domain_profiles if isinstance(value, str)],
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.provisioner.supported_service_materialization_profiles",
            [value for value in self.supported_service_materialization_profiles if isinstance(value, str)],
        )
        _validate_feature_coupling(self)
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["properties"]["operating_systems"]["uniqueItems"] = True
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"supports_accounts": {"const": True}},
                        "required": ["supports_accounts"],
                    },
                    "then": {
                        "required": ["supported_account_features"],
                        "properties": {"supported_account_features": {"minItems": 1}},
                    },
                },
                {
                    "if": {
                        "properties": {"supported_account_features": {"minItems": 1}},
                        "required": ["supported_account_features"],
                    },
                    "then": {
                        "required": ["supports_accounts"],
                        "properties": {"supports_accounts": {"const": True}},
                    },
                },
                {
                    "if": {
                        "properties": {"supports_generated_artifacts": {"const": True}},
                        "required": ["supports_generated_artifacts"],
                    },
                    "then": {
                        "required": ["supported_generated_artifact_kinds"],
                        "properties": {"supported_generated_artifact_kinds": {"minItems": 1}},
                    },
                },
                {
                    "if": {
                        "properties": {"supported_generated_artifact_kinds": {"minItems": 1}},
                        "required": ["supported_generated_artifact_kinds"],
                    },
                    "then": {
                        "required": ["supports_generated_artifacts"],
                        "properties": {"supports_generated_artifacts": {"const": True}},
                    },
                },
            ]
        )
        return json_schema


class OrchestratorCapabilitiesModel(ContractModel):
    name: NonEmptyString
    supported_sections: list[NonEmptyString] = Field(min_length=1)
    supports_workflows: bool = False
    supports_assertion_refs: bool = True
    supports_inject_bindings: bool = True
    supported_workflow_features: list[WorkflowFeature] = Field(default_factory=list)
    supported_workflow_state_predicates: list[WorkflowStatePredicateFeature] = Field(default_factory=list)
    constraints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_workflow_support(self) -> OrchestratorCapabilitiesModel:
        _validate_controlled_vocabulary_terms(
            "capabilities.orchestrator.supported_sections",
            self.supported_sections,
        )
        if self.supports_workflows:
            if "workflows" not in self.supported_sections:
                raise ValueError("orchestrators that support workflows must include 'workflows' in supported_sections")
            if not self.supported_workflow_features:
                raise ValueError("orchestrators that support workflows must declare supported_workflow_features")
        else:
            if "workflows" in self.supported_sections:
                raise ValueError("'workflows' in supported_sections requires supports_workflows=true")
            if self.supported_workflow_features:
                raise ValueError("supported_workflow_features require supports_workflows=true")
            if self.supported_workflow_state_predicates:
                raise ValueError("supported_workflow_state_predicates require supports_workflows=true")
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
                    "if": {
                        "properties": {"supports_workflows": {"const": True}},
                        "required": ["supports_workflows"],
                    },
                    "then": {
                        "required": ["supported_workflow_features", "supported_sections"],
                        "properties": {
                            "supported_workflow_features": {"minItems": 1},
                            "supported_sections": {"contains": {"const": "workflows"}},
                        },
                    },
                },
                {
                    "if": {
                        "properties": {"supports_workflows": {"const": False}},
                        "required": ["supports_workflows"],
                    },
                    "then": {
                        "properties": {
                            "supported_workflow_features": {"maxItems": 0},
                            "supported_workflow_state_predicates": {"maxItems": 0},
                            "supported_sections": {"not": {"contains": {"const": "workflows"}}},
                        },
                    },
                },
            ]
        )
        return json_schema


class EvaluatorCapabilitiesModel(ContractModel):
    name: NonEmptyString
    supported_sections: list[NonEmptyString] = Field(min_length=1)
    supports_scoring: bool = True
    supports_objectives: bool = True
    supported_predicate_families: list[NonEmptyString] = Field(default_factory=list)
    supported_quantifiers: list[NonEmptyString] = Field(default_factory=list)
    supported_truth_outcomes: list[NonEmptyString] = Field(default_factory=list)
    supported_evidence_channels: list[NonEmptyString] = Field(default_factory=list)
    supported_time_domains: list[NonEmptyString] = Field(default_factory=list)
    preserves_binding_provenance: bool = False
    constraints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_evaluator_support(self) -> EvaluatorCapabilitiesModel:
        _validate_controlled_vocabulary_terms(
            "capabilities.evaluator.supported_sections",
            self.supported_sections,
        )
        if not self.supports_scoring and not self.supports_objectives:
            raise ValueError("evaluators must support scoring, objectives, or both")
        for field_name in (
            "supported_predicate_families",
            "supported_quantifiers",
            "supported_truth_outcomes",
            "supported_evidence_channels",
            "supported_time_domains",
        ):
            values = getattr(self, field_name)
            if len(set(values)) != len(values):
                raise ValueError(f"evaluator {field_name} must be unique")
        proposition_sections = {"propositions", "assertions"}
        if proposition_sections.intersection(self.supported_sections):
            if not proposition_sections.issubset(self.supported_sections):
                raise ValueError("evaluator proposition support requires propositions and assertions")
            if set(self.supported_truth_outcomes) != {"true", "false", "unknown", "unsupported"}:
                raise ValueError("evaluator proposition support requires all portable truth outcomes")
            if not all(
                (
                    self.supported_predicate_families,
                    self.supported_quantifiers,
                    self.supported_evidence_channels,
                    self.supported_time_domains,
                )
            ):
                raise ValueError("evaluator proposition support requires typed capability dimensions")
            if not self.preserves_binding_provenance:
                raise ValueError("evaluator proposition support requires binding provenance")
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
                "not": {
                    "allOf": [
                        {
                            "properties": {"supports_scoring": {"const": False}},
                            "required": ["supports_scoring"],
                        },
                        {
                            "properties": {"supports_objectives": {"const": False}},
                            "required": ["supports_objectives"],
                        },
                    ]
                }
            }
        )
        return json_schema


class ApparatusIdentityModel(ContractModel):
    name: NonEmptyString
    version: NonEmptyString


class BackendCompatibilityModel(ContractModel):
    processors: list[NonEmptyString] = Field(min_length=1)


class ProcessorCompatibilityModel(ContractModel):
    backends: list[NonEmptyString] = Field(min_length=1)


class RealizationObservationCapabilityModel(ContractModel):
    """Concern-specific scope and source of backend corroboration."""

    verification_scope: RealizationVerificationScope
    observation_strength: ObservationStrength = Field(json_schema_extra={"not": {"const": "none"}})

    @model_validator(mode="after")
    def _require_evidence(self) -> RealizationObservationCapabilityModel:
        if self.observation_strength is ObservationStrength.NONE:
            raise ValueError("realization observation capability must provide non-none evidence")
        return self


class ProcessResourceLimitCapabilityModel(ContractModel):
    """Published typed apparatus domain for portable process limits."""

    resource: ProcessResourceLimitKind
    scopes: list[ProcessResourceLimitScope] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    minimum: int = Field(default=0, ge=0)
    maximum: int | None = Field(default=None, ge=0)
    supports_unlimited: bool = False

    @model_validator(mode="after")
    def _validate_domain(self) -> ProcessResourceLimitCapabilityModel:
        if len(self.scopes) != len(set(self.scopes)):
            raise ValueError("process resource limit capability scopes must not contain duplicates")
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("process resource limit capability maximum must not be less than minimum")
        return self


class RealizationSupportDeclarationModel(ContractModel):
    domain: NonEmptyString
    support_mode: RealizationSupportMode
    supported_constraint_kinds: list[NonEmptyString] = Field(default_factory=list)
    supported_exact_requirement_kinds: list[NonEmptyString] = Field(default_factory=list)
    disclosure_kinds: list[NonEmptyString] = Field(min_length=1)
    observation_capabilities: dict[NonEmptyString, RealizationObservationCapabilityModel] = Field(default_factory=dict)
    process_resource_limits: list[ProcessResourceLimitCapabilityModel] = Field(default_factory=list)
    artifact_mechanisms: list[ArtifactMechanismCapability] = Field(default_factory=list)
    constraints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_realization_support(self) -> RealizationSupportDeclarationModel:
        if not self.supported_constraint_kinds and not self.supported_exact_requirement_kinds:
            raise ValueError(
                "realization_support declarations must declare supported_constraint_kinds "
                "or supported_exact_requirement_kinds"
            )
        if self.support_mode == RealizationSupportMode.EXACT_ONLY and self.supported_constraint_kinds:
            raise ValueError("exact-only realization support must not declare supported_constraint_kinds")
        resources = [capability.resource for capability in self.process_resource_limits]
        if len(resources) != len(set(resources)):
            raise ValueError("process_resource_limits must not contain duplicate resource terms")
        identities = [
            (
                capability.mechanism.mechanism,
                capability.mechanism.profile,
                capability.mechanism.version,
                capability.mechanism.digest,
            )
            for capability in self.artifact_mechanisms
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("artifact_mechanisms must not contain duplicate mechanism profiles")
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
                    "anyOf": [
                        {
                            "required": ["supported_constraint_kinds"],
                            "properties": {"supported_constraint_kinds": {"minItems": 1}},
                        },
                        {
                            "required": ["supported_exact_requirement_kinds"],
                            "properties": {"supported_exact_requirement_kinds": {"minItems": 1}},
                        },
                    ]
                },
                {
                    "if": {
                        "properties": {"support_mode": {"const": RealizationSupportMode.EXACT_ONLY.value}},
                        "required": ["support_mode"],
                    },
                    "then": {
                        "required": ["supported_exact_requirement_kinds"],
                        "properties": {
                            "supported_exact_requirement_kinds": {"minItems": 1},
                            "supported_constraint_kinds": {"maxItems": 0},
                        },
                    },
                },
            ]
        )
        return json_schema
