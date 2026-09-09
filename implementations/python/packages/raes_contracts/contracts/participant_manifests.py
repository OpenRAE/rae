"""Backend-manifest and participant-implementation manifest contracts."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, GetJsonSchemaHandler, SerializerFunctionWrapHandler, model_serializer, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..manifest_authority import (
    BACKEND_SUPPORTED_CONTRACT_IDS,
    PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS,
    PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    validate_backend_supported_contract_versions,
    validate_participant_implementation_supported_contract_versions,
    validate_participant_supported_contract_versions,
)
from ..versions import (
    BACKEND_MANIFEST_V2_SCHEMA_VERSION,
    PARTICIPANT_IMPLEMENTATION_MANIFEST_V1_SCHEMA_VERSION,
    PARTICIPANT_IMPLEMENTATION_PROVENANCE_V1_SCHEMA_VERSION,
)
from .base import (
    _BACKEND_CONCEPT_BINDING_SCOPES,
    _PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES,
    ContractModel,
    NonEmptyString,
)
from .capabilities import (
    ApparatusIdentityModel,
    BackendCompatibilityModel,
    RealizationSupportDeclarationModel,
)
from .experiment_bindings import ConfigurationTargetRegistryModel
from .manifests import BackendCapabilitiesV2Model, ConceptBindingEntryModel
from .realization_plans import RealizationEnvelopeIdentityModel
from .validators import (
    _validate_canonical_concept_bindings,
    _validate_controlled_vocabulary_terms,
    _validate_unique_string_values,
)


class BackendManifestV2Model(ContractModel):
    schema_version: Literal[BACKEND_MANIFEST_V2_SCHEMA_VERSION] = BACKEND_MANIFEST_V2_SCHEMA_VERSION
    identity: ApparatusIdentityModel
    supported_contract_versions: list[NonEmptyString] = Field(min_length=1)
    compatibility: BackendCompatibilityModel
    realization_support: list[RealizationSupportDeclarationModel] = Field(min_length=1)
    realization_envelope: RealizationEnvelopeIdentityModel | None = None
    concept_bindings: list[ConceptBindingEntryModel] = Field(min_length=1)
    constraints: dict[str, str] = Field(default_factory=dict)
    capabilities: BackendCapabilitiesV2Model
    configuration_registry: ConfigurationTargetRegistryModel | None = None

    @model_validator(mode="after")
    def _validate_unique_binding_scopes(self) -> BackendManifestV2Model:
        validate_backend_supported_contract_versions(self.supported_contract_versions)
        if (
            self.configuration_registry is not None
            and "experiment-binding-descriptors-v1" not in self.supported_contract_versions
        ):
            raise ValueError("configuration_registry requires experiment-binding-descriptors-v1 support")
        self._validate_realization_envelope_contract()
        self._validate_cleanup_contracts()
        self._validate_time_contracts()
        self._validate_observation_capture_offers()
        self._validate_participant_policy_contracts()
        self._validate_concept_bindings()
        return self

    def _validate_observation_capture_offers(self) -> None:
        observation = self.capabilities.observation
        if observation is None:
            return
        declared_contracts = set(self.supported_contract_versions)
        missing = sorted({offer.output_contract for offer in observation.capture_offers} - declared_contracts)
        if missing:
            raise ValueError(
                "observation capture offers require output contracts in supported_contract_versions: "
                + ", ".join(missing)
            )

    def _validate_participant_policy_contracts(self) -> None:
        participant_runtime = self.capabilities.participant_runtime
        if participant_runtime is None:
            return
        declared_contracts = set(self.supported_contract_versions)
        required_by_feature = PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[
            PARTICIPANT_RUNTIME_BEHAVIOR_FEATURE_SCOPE
        ]
        for entry in participant_runtime.feature_support:
            if (
                entry.feature not in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES
                or entry.support_level.value == "unsupported"
            ):
                continue
            missing = sorted(required_by_feature[entry.feature] - declared_contracts)
            if missing:
                raise ValueError(
                    f"feature_support entry '{entry.feature}' is missing required contracts: {', '.join(missing)}"
                )

    def _validate_realization_envelope_contract(self) -> None:
        envelope_contract_declared = "realization-envelope-v1" in self.supported_contract_versions
        if self.realization_envelope is not None and not envelope_contract_declared:
            raise ValueError("realization_envelope requires realization-envelope-v1 support")
        if envelope_contract_declared and self.realization_envelope is None:
            raise ValueError("realization-envelope-v1 support requires realization_envelope identity")

    def _validate_cleanup_contracts(self) -> None:
        cleanup_contracts = {"trial-cleanup-plan-v1", "trial-cleanup-receipt-v1"}
        declared_cleanup_contracts = cleanup_contracts.intersection(self.supported_contract_versions)
        if self.capabilities.cleanup is not None and declared_cleanup_contracts != cleanup_contracts:
            raise ValueError(
                "cleanup capabilities require both cleanup contract versions in supported_contract_versions"
            )
        if declared_cleanup_contracts and self.capabilities.cleanup is None:
            raise ValueError("cleanup contract support requires capabilities.cleanup")

    def _validate_time_contracts(self) -> None:
        time_contracts = {
            "time-model-v1",
            "time-runtime-state-v1",
            "realized-time-model-v1",
            "runtime-snapshot-v1",
            "experiment-run-v1",
        }
        declared_time_contracts = time_contracts.intersection(self.supported_contract_versions)
        if self.capabilities.time is not None and declared_time_contracts != time_contracts:
            raise ValueError("time capabilities require the complete time contract family")
        portable_time_contracts = {"time-model-v1", "time-runtime-state-v1", "realized-time-model-v1"}
        if declared_time_contracts.intersection(portable_time_contracts) and self.capabilities.time is None:
            raise ValueError("time contract support requires capabilities.time")
        if (
            self.capabilities.time is not None
            and self.capabilities.time.supports_coordinated_participant_reset
            and self.capabilities.participant_runtime is None
        ):
            raise ValueError("coordinated participant reset support requires participant runtime capabilities")

    def _validate_concept_bindings(self) -> None:
        scopes = [binding.scope for binding in self.concept_bindings]
        if len(scopes) != len(set(scopes)):
            raise ValueError("concept_bindings must not contain duplicate scopes")
        _validate_canonical_concept_bindings(self, allowed_scopes=_BACKEND_CONCEPT_BINDING_SCOPES)

    @model_serializer(mode="wrap")
    def _serialize_optional_configuration_registry(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        payload = handler(self)
        if self.configuration_registry is None:
            payload.pop("configuration_registry", None)
        return payload

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["properties"]["supported_contract_versions"]["items"]["enum"] = list(BACKEND_SUPPORTED_CONTRACT_IDS)
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"realization_envelope": {"not": {"type": "null"}}},
                        "required": ["realization_envelope"],
                    },
                    "then": {
                        "properties": {
                            "supported_contract_versions": {"contains": {"const": "realization-envelope-v1"}}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "supported_contract_versions": {"contains": {"const": "realization-envelope-v1"}}
                        },
                        "required": ["supported_contract_versions"],
                    },
                    "then": {
                        "properties": {"realization_envelope": {"not": {"type": "null"}}},
                        "required": ["realization_envelope"],
                    },
                },
                {
                    "if": {
                        "properties": {"supported_contract_versions": {"contains": {"const": "trial-cleanup-plan-v1"}}},
                        "required": ["supported_contract_versions"],
                    },
                    "then": {
                        "properties": {"capabilities": {"required": ["cleanup"]}},
                    },
                },
                {
                    "if": {
                        "properties": {"supported_contract_versions": {"contains": {"const": "time-model-v1"}}},
                        "required": ["supported_contract_versions"],
                    },
                    "then": {
                        "properties": {"capabilities": {"required": ["time"]}},
                    },
                },
            ]
        )
        return json_schema


class ParticipantImplementationCompatibilityModel(ContractModel):
    participant_runtimes: list[NonEmptyString] = Field(default_factory=list)
    processors: list[NonEmptyString] = Field(default_factory=list)
    backends: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_non_empty_compatibility(self) -> ParticipantImplementationCompatibilityModel:
        _validate_unique_string_values("participant_runtimes", self.participant_runtimes)
        _validate_unique_string_values("processors", self.processors)
        _validate_unique_string_values("backends", self.backends)
        if not (self.participant_runtimes or self.processors or self.backends):
            raise ValueError(
                "compatibility must declare at least one participant runtime, processor, or backend surface"
            )
        return self


class ParticipantImplementationCapabilitiesModel(ContractModel):
    supported_participant_contracts: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    supported_decision_surface_modes: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    tool_affordance_expectations: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    exposure_policy_kinds: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def _validate_participant_implementation_capabilities(self) -> ParticipantImplementationCapabilitiesModel:
        _validate_unique_string_values("supported_participant_contracts", self.supported_participant_contracts)
        _validate_unique_string_values("supported_decision_surface_modes", self.supported_decision_surface_modes)
        _validate_unique_string_values("tool_affordance_expectations", self.tool_affordance_expectations)
        _validate_unique_string_values("exposure_policy_kinds", self.exposure_policy_kinds)
        validate_participant_supported_contract_versions(self.supported_participant_contracts)
        _validate_controlled_vocabulary_terms(
            "capabilities.supported_participant_contracts",
            self.supported_participant_contracts,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.supported_decision_surface_modes",
            self.supported_decision_surface_modes,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.tool_affordance_expectations",
            self.tool_affordance_expectations,
        )
        _validate_controlled_vocabulary_terms("capabilities.exposure_policy_kinds", self.exposure_policy_kinds)
        return self


class ParticipantImplementationManifestModel(ContractModel):
    schema_version: Literal[PARTICIPANT_IMPLEMENTATION_MANIFEST_V1_SCHEMA_VERSION] = (
        PARTICIPANT_IMPLEMENTATION_MANIFEST_V1_SCHEMA_VERSION
    )
    identity: ApparatusIdentityModel
    implementation_kind: NonEmptyString
    supported_contract_versions: list[NonEmptyString] = Field(min_length=1)
    compatibility: ParticipantImplementationCompatibilityModel
    concept_bindings: list[ConceptBindingEntryModel] = Field(min_length=1)
    constraints: dict[str, str] = Field(default_factory=dict)
    capabilities: ParticipantImplementationCapabilitiesModel
    configuration_registry: ConfigurationTargetRegistryModel | None = None

    @model_validator(mode="after")
    def _validate_participant_implementation_manifest(self) -> ParticipantImplementationManifestModel:
        validate_participant_implementation_supported_contract_versions(self.supported_contract_versions)
        _validate_unique_string_values("supported_contract_versions", self.supported_contract_versions)
        _validate_controlled_vocabulary_terms("implementation_kind", [self.implementation_kind])
        unsupported = sorted(
            set(self.capabilities.supported_participant_contracts) - set(self.supported_contract_versions)
        )
        if unsupported:
            joined = ", ".join(unsupported)
            raise ValueError(
                "supported_participant_contracts must be declared in supported_contract_versions: " + joined
            )
        if self.configuration_registry is not None:
            required_configuration_contracts = {
                "experiment-binding-descriptors-v1",
                "participant-configuration-result-v1",
            }
            missing = sorted(required_configuration_contracts - set(self.supported_contract_versions))
            if missing:
                raise ValueError("configuration_registry requires supported_contract_versions: " + ", ".join(missing))
        scopes = [binding.scope for binding in self.concept_bindings]
        if len(scopes) != len(set(scopes)):
            raise ValueError("concept_bindings must not contain duplicate scopes")
        _validate_canonical_concept_bindings(
            self,
            allowed_scopes=_PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES,
        )
        return self

    @model_serializer(mode="wrap")
    def _serialize_optional_configuration_registry(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        payload = handler(self)
        if self.configuration_registry is None:
            payload.pop("configuration_registry", None)
        return payload

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["properties"]["supported_contract_versions"]["items"]["enum"] = list(
            PARTICIPANT_IMPLEMENTATION_SUPPORTED_CONTRACT_IDS
        )
        return json_schema


DigestString = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


class ParticipantExposurePolicyModel(ContractModel):
    policy_id: NonEmptyString
    policy_version: NonEmptyString | None = None
    policy_digest: DigestString | None = None
    exposure_policy_kinds: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    disclosed_refs: list[NonEmptyString] = Field(default_factory=list)
    withheld_refs: list[NonEmptyString] = Field(default_factory=list)
    tool_affordance_refs: list[NonEmptyString] = Field(default_factory=list)
    visibility_scope_refs: list[NonEmptyString] = Field(default_factory=list)
    constraints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_exposure_policy(self) -> ParticipantExposurePolicyModel:
        _validate_unique_string_values("exposure_policy_kinds", self.exposure_policy_kinds)
        _validate_unique_string_values("disclosed_refs", self.disclosed_refs)
        _validate_unique_string_values("withheld_refs", self.withheld_refs)
        _validate_unique_string_values("tool_affordance_refs", self.tool_affordance_refs)
        _validate_unique_string_values("visibility_scope_refs", self.visibility_scope_refs)
        _validate_controlled_vocabulary_terms("capabilities.exposure_policy_kinds", self.exposure_policy_kinds)
        if not (self.disclosed_refs or self.withheld_refs or self.tool_affordance_refs or self.visibility_scope_refs):
            raise ValueError(
                "exposure policy must declare disclosed_refs, withheld_refs, "
                "tool_affordance_refs, or visibility_scope_refs"
            )
        return self


class ParticipantImplementationSelectionModel(ContractModel):
    participant_address: NonEmptyString
    implementation_identity: ApparatusIdentityModel
    manifest_ref: NonEmptyString
    manifest_digest: DigestString
    configuration_ref: NonEmptyString | None = None
    configuration_digest: DigestString | None = None
    selected_decision_surface_mode: NonEmptyString
    participant_contract_versions: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    exposure_policy: ParticipantExposurePolicyModel

    @model_validator(mode="after")
    def _validate_participant_implementation_selection(self) -> ParticipantImplementationSelectionModel:
        if (self.configuration_ref is None) != (self.configuration_digest is None):
            raise ValueError("configuration_ref and configuration_digest must be supplied together")
        _validate_unique_string_values("participant_contract_versions", self.participant_contract_versions)
        validate_participant_supported_contract_versions(self.participant_contract_versions)
        _validate_controlled_vocabulary_terms(
            "capabilities.supported_decision_surface_modes",
            [self.selected_decision_surface_mode],
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
        json_schema.setdefault("oneOf", []).extend(
            [
                {
                    "required": ["configuration_ref", "configuration_digest"],
                    "properties": {
                        "configuration_ref": {"not": {"type": "null"}},
                        "configuration_digest": {"not": {"type": "null"}},
                    },
                },
                {
                    "properties": {
                        "configuration_ref": {"type": "null"},
                        "configuration_digest": {"type": "null"},
                    }
                },
            ]
        )
        return json_schema


class ParticipantImplementationProvenanceModel(ContractModel):
    schema_version: Literal[PARTICIPANT_IMPLEMENTATION_PROVENANCE_V1_SCHEMA_VERSION] = (
        PARTICIPANT_IMPLEMENTATION_PROVENANCE_V1_SCHEMA_VERSION
    )
    run_id: NonEmptyString
    participant_implementations: list[ParticipantImplementationSelectionModel] = Field(min_length=1)
    processor_manifest_ref: NonEmptyString | None = None
    backend_manifest_ref: NonEmptyString | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_unique_participant_addresses(self) -> ParticipantImplementationProvenanceModel:
        addresses = [selection.participant_address for selection in self.participant_implementations]
        _validate_unique_string_values("participant_address", addresses)
        return self
