"""Concept-binding, capability-v2, and processor-manifest contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, GetJsonSchemaHandler, SerializerFunctionWrapHandler, model_serializer, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..addressing import require_compiled_address
from ..manifest_authority import (
    PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    PROCESSOR_SUPPORTED_CONTRACT_IDS,
    PROCESSOR_SUPPORTED_SDL_VERSION_IDS,
    validate_backend_supported_contract_versions,
    validate_processor_supported_contract_versions,
    validate_processor_supported_sdl_versions,
)
from ..versions import PROCESSOR_MANIFEST_V2_SCHEMA_VERSION
from ..vocabulary import ConceptFamilyId, ParticipantFeatureSupportLevel, ProcessorFeature
from .base import _PROCESSOR_CONCEPT_BINDING_SCOPES, ContractModel, NonEmptyString
from .capabilities import (
    ApparatusIdentityModel,
    EvaluatorCapabilitiesModel,
    OrchestratorCapabilitiesModel,
    ProcessorCompatibilityModel,
    ProvisionerCapabilitiesModel,
)
from .experiment_bindings import ConfigurationTargetRegistryModel
from .feature_support import ParticipantFeatureSupportModel
from .observation_capture import ObservationCaptureOfferModel
from .participant_execution import ParticipantExecutionBindingModel
from .participant_resource_budgets import ParticipantResourceBudgetCapabilitiesModel
from .time_manifest_capabilities import TimeCapabilitiesModel
from .trial_cleanup import CleanupActionKind
from .validators import (
    _validate_canonical_concept_bindings,
    _validate_controlled_vocabulary_terms,
    _validate_unique_string_values,
)


class ConceptBindingEntryModel(ContractModel):
    """Binds a vocabulary surface in an artifact to a canonical concept family."""

    scope: NonEmptyString = Field(
        ...,
        pattern=r"^[a-z_][a-z0-9_.]*[a-z0-9_]$",
    )
    family: ConceptFamilyId


class ProcessorCapabilitiesV2Model(ContractModel):
    supported_sdl_versions: list[NonEmptyString] = Field(min_length=1)
    supported_features: list[ProcessorFeature] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_declared_authority(self) -> ProcessorCapabilitiesV2Model:
        validate_processor_supported_sdl_versions(self.supported_sdl_versions)
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["properties"]["supported_sdl_versions"]["items"]["enum"] = list(PROCESSOR_SUPPORTED_SDL_VERSION_IDS)
        return json_schema


class ParticipantRuntimeCapabilitiesModel(ContractModel):
    """Participant-episode lifecycle capability block (RUN-311).

    A backend that declares this block advertises that it implements
    the full participant episode control surface on the
    ``ParticipantRuntime`` protocol: ``initialize`` / ``reset`` /
    ``restart`` / ``terminate`` plus ``status`` / ``results`` /
    ``history``. Consumers of the manifest can infer the
    ``FULL_REMOTE_CONTROL_PLANE`` conformance profile from this block.

    API-405 support dimensions live here because they are backend apparatus
    claims: which participant roles, behavior features, and interaction
    features this participant runtime can actually realize.
    """

    name: NonEmptyString
    supported_participant_roles: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    supported_behavior_features: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    supported_interaction_features: list[NonEmptyString] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    feature_support: list[ParticipantFeatureSupportModel] = Field(default_factory=list)
    supports_autonomous_execution: bool = False
    supported_autonomous_selection_strategies: list[Literal["ordered_cycle", "weighted"]] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    supported_autonomous_action_contracts: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    supported_autonomous_observation_boundaries: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    supported_autonomous_target_addresses: list[NonEmptyString] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    supported_autonomous_policy_profiles: list[
        Literal[
            "participant-autonomous-execution/v1",
            "participant-autonomous-execution/v2",
            "participant-autonomous-execution/v3",
        ]
    ] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    supported_autonomous_activity_features: list[
        Literal[
            "work-windows",
            "timing-variation",
            "weighted-selection",
            "dependencies",
            "bounded-retries",
            "cooldowns",
            "limited-bursts",
            "occurrence-provenance",
        ]
    ] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    supported_autonomous_random_stream_profiles: list[Literal["blake3-xof-participant-v1"]] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    max_autonomous_participants: int | None = Field(default=None, ge=1)
    max_autonomous_action_attempts: int | None = Field(default=None, ge=1)
    max_autonomous_in_flight: int | None = Field(default=None, ge=1)
    max_autonomous_occurrences: int | None = Field(default=None, ge=1)
    max_autonomous_retries_per_occurrence: int | None = Field(default=None, ge=1)
    max_autonomous_burst_size: int | None = Field(default=None, ge=1)
    execution_bindings: list[ParticipantExecutionBindingModel] = Field(default_factory=list)
    supports_execution_control: bool = False
    supported_execution_control_actions: list[Literal["start", "pause", "resume", "drain", "reset", "teardown"]] = (
        Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    )
    supports_bounded_concurrency: bool = False
    max_execution_services: int | None = Field(default=None, ge=1)
    max_concurrent_actions: int | None = Field(default=None, ge=2)
    resource_budgets: ParticipantResourceBudgetCapabilitiesModel | None = None
    constraints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_api_405_declarations(self) -> ParticipantRuntimeCapabilitiesModel:
        _validate_unique_string_values("supported_participant_roles", self.supported_participant_roles)
        _validate_unique_string_values("supported_behavior_features", self.supported_behavior_features)
        _validate_unique_string_values("supported_interaction_features", self.supported_interaction_features)
        _validate_controlled_vocabulary_terms(
            "capabilities.participant_runtime.supported_participant_roles",
            self.supported_participant_roles,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.participant_runtime.supported_behavior_features",
            self.supported_behavior_features,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.participant_runtime.supported_interaction_features",
            self.supported_interaction_features,
        )
        return self

    @model_validator(mode="after")
    def _validate_api_407_feature_support(self) -> ParticipantRuntimeCapabilitiesModel:
        _validate_unique_string_values("feature_support", [entry.feature for entry in self.feature_support])
        self._validate_supported_feature_levels()
        self._validate_autonomous_configuration()
        self._validate_autonomous_addresses()
        self._validate_execution_control()
        return self

    def _validate_supported_feature_levels(self) -> None:
        supported_features = set(self.supported_behavior_features) | set(self.supported_interaction_features)
        declared_features = {entry.feature for entry in self.feature_support}
        missing_policy_declarations = sorted(
            (supported_features & PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES) - declared_features
        )
        if missing_policy_declarations:
            raise ValueError(
                "supported participant policy features require explicit feature_support declarations: "
                + ", ".join(missing_policy_declarations)
            )
        for entry in self.feature_support:
            declared_unsupported = entry.support_level == ParticipantFeatureSupportLevel.UNSUPPORTED
            if declared_unsupported and entry.feature in supported_features:
                raise ValueError(
                    f"feature_support entry '{entry.feature}' declares support_level 'unsupported' but the "
                    "feature is declared in supported_behavior_features or supported_interaction_features"
                )
            if (
                entry.feature in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES
                and not declared_unsupported
                and entry.feature not in supported_features
            ):
                raise ValueError(
                    f"feature_support entry '{entry.feature}' declares positive support but the feature "
                    "is absent from supported_behavior_features"
                )

    def _validate_autonomous_configuration(self) -> None:
        declares_autonomous = "autonomous_execution" in self.supported_behavior_features
        if declares_autonomous != self.supports_autonomous_execution:
            raise ValueError("autonomous_execution feature and support flag must agree")
        if self.supports_autonomous_execution:
            self._validate_enabled_autonomous_configuration()
        elif self._has_any_autonomous_configuration():
            raise ValueError("autonomous execution limits require autonomous execution support")

    def _validate_enabled_autonomous_configuration(self) -> None:
        if not self._has_complete_autonomous_configuration():
            raise ValueError(
                "autonomous execution requires selection strategies, exact action, observation, and policy-profile "
                "support, and finite limits"
            )
        self._validate_activity_profile_configuration()

    def _validate_activity_profile_configuration(self) -> None:
        activity_profiles = {
            "participant-autonomous-execution/v2",
            "participant-autonomous-execution/v3",
        }.intersection(self.supported_autonomous_policy_profiles)
        missing_activity_support = (
            not self.supported_autonomous_activity_features or not self.supported_autonomous_random_stream_profiles
        )
        if activity_profiles and missing_activity_support:
            raise ValueError(
                "autonomous execution v2 requires exact activity-feature and random-stream-profile support"
            )
        if (
            "participant-autonomous-execution/v3" in self.supported_autonomous_policy_profiles
            and self.resource_budgets is None
        ):
            raise ValueError("autonomous execution v3 requires participant resource-budget capabilities")

    def _has_complete_autonomous_configuration(self) -> bool:
        return bool(
            self.supported_autonomous_selection_strategies
            and self.supported_autonomous_action_contracts
            and self.supported_autonomous_observation_boundaries
            and self.supported_autonomous_policy_profiles
            and all(value is not None for value in self._autonomous_limits())
            and self.execution_bindings
            and self.supports_execution_control
            and self.supports_bounded_concurrency
            and self.max_execution_services is not None
            and self.max_concurrent_actions is not None
        )

    def _has_any_autonomous_configuration(self) -> bool:
        limits_configured = any(value is not None for value in self._autonomous_limits())
        return any(
            (
                self.supported_autonomous_selection_strategies,
                self.supported_autonomous_action_contracts,
                self.supported_autonomous_observation_boundaries,
                self.supported_autonomous_target_addresses,
                self.supported_autonomous_policy_profiles,
                self.supported_autonomous_activity_features,
                self.supported_autonomous_random_stream_profiles,
                limits_configured,
                self.execution_bindings,
                self.supports_execution_control,
                self.supported_execution_control_actions,
                self.supports_bounded_concurrency,
                self.max_execution_services is not None,
                self.max_concurrent_actions is not None,
                self.resource_budgets is not None,
            )
        )

    def _validate_execution_control(self) -> None:
        if not self.supports_autonomous_execution:
            return
        required_actions = {"start", "pause", "resume", "drain", "reset", "teardown"}
        missing = required_actions - set(self.supported_execution_control_actions)
        if missing:
            raise ValueError("execution control is missing required actions: " + ", ".join(sorted(missing)))
        binding_ids = [binding.binding_id for binding in self.execution_bindings]
        _validate_unique_string_values("execution_bindings", binding_ids)
        supported_actions = set(self.supported_autonomous_action_contracts)
        supported_targets = set(self.supported_autonomous_target_addresses)
        for binding in self.execution_bindings:
            if binding.action_contract_address not in supported_actions:
                raise ValueError("execution binding action is not declared supported")
            if not set(binding.target_addresses).issubset(supported_targets):
                raise ValueError("execution binding target is not declared supported")
            if self.max_concurrent_actions is not None and binding.max_in_flight > self.max_concurrent_actions:
                raise ValueError("execution binding exceeds max_concurrent_actions")

    def _autonomous_limits(self) -> tuple[int | None, ...]:
        return (
            self.max_autonomous_participants,
            self.max_autonomous_action_attempts,
            self.max_autonomous_in_flight,
            self.max_autonomous_occurrences,
            self.max_autonomous_retries_per_occurrence,
            self.max_autonomous_burst_size,
        )

    def _validate_autonomous_addresses(self) -> None:
        for field_name in (
            "supported_autonomous_action_contracts",
            "supported_autonomous_observation_boundaries",
            "supported_autonomous_target_addresses",
        ):
            values = getattr(self, field_name)
            _validate_unique_string_values(field_name, values)
            for address in values:
                try:
                    require_compiled_address(address, field_name=field_name)
                except (TypeError, ValueError) as exc:
                    raise ValueError(str(exc)) from exc


class ObservationCapabilitiesModel(ContractModel):
    """EXP-715 backend observation and evidence-collection capability declaration."""

    name: NonEmptyString
    supported_capture_kinds: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_channel_kinds: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_evidence_contracts: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_media_types: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_sealing_modes: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supports_redaction: bool = False
    supports_loss_disclosure: bool = False
    supports_chain_of_custody: bool = False
    capture_offers: list[ObservationCaptureOfferModel] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    constraints: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_observation_capability(self) -> ObservationCapabilitiesModel:
        _validate_unique_string_values("supported_capture_kinds", self.supported_capture_kinds)
        _validate_unique_string_values("supported_channel_kinds", self.supported_channel_kinds)
        _validate_unique_string_values("supported_evidence_contracts", self.supported_evidence_contracts)
        _validate_unique_string_values("supported_media_types", self.supported_media_types)
        _validate_unique_string_values("supported_sealing_modes", self.supported_sealing_modes)
        _validate_unique_string_values("capture offer ids", [offer.offer_id for offer in self.capture_offers])
        _validate_controlled_vocabulary_terms(
            "capabilities.observation.supported_capture_kinds",
            self.supported_capture_kinds,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.observation.supported_channel_kinds",
            self.supported_channel_kinds,
        )
        _validate_controlled_vocabulary_terms(
            "capabilities.observation.supported_sealing_modes",
            self.supported_sealing_modes,
        )
        validate_backend_supported_contract_versions(self.supported_evidence_contracts)
        for contract_id in self.supported_evidence_contracts:
            if not contract_id.startswith("experiment-"):
                raise ValueError("observation supported_evidence_contracts must be experiment contract ids")
        for offer in self.capture_offers:
            if offer.capture_kind not in self.supported_capture_kinds:
                raise ValueError("capture offer capture_kind must appear in supported_capture_kinds")
            if not set(offer.channel_kinds).issubset(self.supported_channel_kinds):
                raise ValueError("capture offer channel_kinds must appear in supported_channel_kinds")
            if not set(offer.media_types).issubset(self.supported_media_types):
                raise ValueError("capture offer media_types must appear in supported_media_types")
        return self


class CleanupCapabilitiesModel(ContractModel):
    """Backend support for the portable SCE-007 cleanup contract family."""

    name: NonEmptyString
    supported_contract_versions: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_action_kinds: list[CleanupActionKind] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supported_verification_methods: list[NonEmptyString] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    supports_reusable_state: bool = False
    supports_residual_state_disclosure: bool = False

    @model_validator(mode="after")
    def _validate_cleanup_capability(self) -> CleanupCapabilitiesModel:
        _validate_unique_string_values("cleanup supported_contract_versions", self.supported_contract_versions)
        _validate_unique_string_values("cleanup supported_action_kinds", self.supported_action_kinds)
        _validate_unique_string_values("cleanup supported_verification_methods", self.supported_verification_methods)
        required = {"trial-cleanup-plan-v1", "trial-cleanup-receipt-v1"}
        if set(self.supported_contract_versions) != required:
            raise ValueError(
                "cleanup capabilities require contract versions trial-cleanup-plan-v1 and trial-cleanup-receipt-v1"
            )
        validate_backend_supported_contract_versions(self.supported_contract_versions)
        if self.supports_reusable_state and not self.supports_residual_state_disclosure:
            raise ValueError("reusable-state support requires residual-state disclosure")
        return self


class BackendCapabilitiesV2Model(ContractModel):
    provisioner: ProvisionerCapabilitiesModel
    orchestrator: OrchestratorCapabilitiesModel | None = None
    evaluator: EvaluatorCapabilitiesModel | None = None
    participant_runtime: ParticipantRuntimeCapabilitiesModel | None = None
    observation: ObservationCapabilitiesModel | None = None
    cleanup: CleanupCapabilitiesModel | None = None
    time: TimeCapabilitiesModel | None = None


class ProcessorManifestV2Model(ContractModel):
    schema_version: Literal[PROCESSOR_MANIFEST_V2_SCHEMA_VERSION] = PROCESSOR_MANIFEST_V2_SCHEMA_VERSION
    identity: ApparatusIdentityModel
    supported_contract_versions: list[NonEmptyString] = Field(min_length=1)
    compatibility: ProcessorCompatibilityModel
    concept_bindings: list[ConceptBindingEntryModel] = Field(min_length=1)
    constraints: dict[str, str] = Field(default_factory=dict)
    capabilities: ProcessorCapabilitiesV2Model
    configuration_registry: ConfigurationTargetRegistryModel | None = None

    @model_validator(mode="after")
    def _validate_unique_binding_scopes(self) -> ProcessorManifestV2Model:
        validate_processor_supported_contract_versions(self.supported_contract_versions)
        if (
            self.configuration_registry is not None
            and "experiment-binding-descriptors-v1" not in self.supported_contract_versions
        ):
            raise ValueError("configuration_registry requires experiment-binding-descriptors-v1 support")
        scopes = [binding.scope for binding in self.concept_bindings]
        if len(scopes) != len(set(scopes)):
            raise ValueError("concept_bindings must not contain duplicate scopes")
        _validate_canonical_concept_bindings(self, allowed_scopes=_PROCESSOR_CONCEPT_BINDING_SCOPES)
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
            PROCESSOR_SUPPORTED_CONTRACT_IDS
        )
        return json_schema
