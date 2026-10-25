"""Portable contracts for authoritative cross-plane experiment bindings."""

from __future__ import annotations

import math
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    Field,
    GetJsonSchemaHandler,
    SerializerFunctionWrapHandler,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_serializer,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..secret_references import SecretReferenceId
from ..versions import (
    EXPERIMENT_BINDING_DESCRIPTORS_V1_SCHEMA_VERSION,
    PARTICIPANT_CONFIGURATION_RESULT_V1_SCHEMA_VERSION,
)
from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .capabilities import ApparatusIdentityModel
from .schema_invariants import _add_raes_invariant


class BindingScalarType(str, Enum):
    """Exact JSON scalar type declared by a binding owner."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    NULL = "null"


BindingScalar = StrictBool | StrictInt | StrictFloat | StrictStr | None


class LiteralBindingValueModel(ContractModel):
    """Portable literal value; strict type validation occurs at its descriptor."""

    kind: Literal["literal"]
    value: BindingScalar


class SecretReferenceBindingValueModel(ContractModel):
    """Non-sensitive identity of a secret resolved only at an authorized sink."""

    kind: Literal["secret-reference"]
    reference_id: SecretReferenceId


BindingValue = Annotated[
    LiteralBindingValueModel | SecretReferenceBindingValueModel,
    Field(discriminator="kind"),
]


class ScenarioBindingTargetModel(ContractModel):
    """Canonical target owned by a composed SDL scenario family."""

    plane: Literal["scenario"]
    scenario_family_id: NonEmptyString
    variation_point_id: NonEmptyString
    target_id: NonEmptyString

    def canonical_key(self) -> tuple[str, ...]:
        return (
            self.plane,
            self.scenario_family_id,
            self.variation_point_id,
            self.target_id,
        )


class ParticipantImplementationBindingTargetModel(ContractModel):
    """Canonical target declared by one selected participant implementation."""

    plane: Literal["participant-implementation"]
    participant_address: NonEmptyString
    implementation_name: NonEmptyString
    implementation_version: NonEmptyString
    manifest_version: NonEmptyString
    target_id: NonEmptyString

    def canonical_key(self) -> tuple[str, ...]:
        return (
            self.plane,
            self.participant_address,
            self.implementation_name,
            self.implementation_version,
            self.manifest_version,
            self.target_id,
        )


class ApparatusBindingTargetModel(ContractModel):
    """Canonical target declared by a selected portable apparatus manifest."""

    plane: Literal["apparatus"]
    component_kind: Literal["processor", "backend", "participant-runtime", "other"]
    component_name: NonEmptyString
    component_version: NonEmptyString
    manifest_version: NonEmptyString
    target_id: NonEmptyString

    def canonical_key(self) -> tuple[str, ...]:
        return (
            self.plane,
            self.component_kind,
            self.component_name,
            self.component_version,
            self.manifest_version,
            self.target_id,
        )


BindingTarget = Annotated[
    ScenarioBindingTargetModel | ParticipantImplementationBindingTargetModel | ApparatusBindingTargetModel,
    Field(discriminator="plane"),
]


class BindingOwnerModel(ContractModel):
    """Governed contract and validator profile that owns one binding."""

    contract_id: NonEmptyString
    contract_version: NonEmptyString
    validator_id: NonEmptyString
    validator_version: NonEmptyString


class ConfigurationTargetDeclarationModel(ContractModel):
    """One scalar target admitted by an owning portable manifest."""

    target_id: NonEmptyString
    value_type: BindingScalarType
    aliases: list[NonEmptyString] = Field(default_factory=list)
    allowed_value_kinds: list[Literal["literal", "secret-reference"]] = Field(min_length=1)
    sensitivity: Literal["public", "internal", "restricted", "secret"]
    default: LiteralBindingValueModel | None = None

    @model_validator(mode="after")
    def _validate_target_declaration(self) -> ConfigurationTargetDeclarationModel:
        if len(self.aliases) != len(set(self.aliases)):
            raise ValueError("configuration target aliases must be unique")
        if self.target_id in self.aliases:
            raise ValueError("configuration target aliases must not repeat the canonical target id")
        if len(self.allowed_value_kinds) != len(set(self.allowed_value_kinds)):
            raise ValueError("allowed_value_kinds must be unique")
        if self.sensitivity == "secret" and self.allowed_value_kinds != ["secret-reference"]:
            raise ValueError("secret configuration targets admit only secret-reference values")
        if self.default is not None:
            if self.sensitivity == "secret":
                raise ValueError("secret configuration targets must not declare portable defaults")
            if "literal" not in self.allowed_value_kinds:
                raise ValueError("a literal default requires literal values to be allowed")
            self.validate_value(self.default)
        return self

    @model_serializer(mode="wrap")
    def _serialize_optional_default(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        payload = handler(self)
        if self.default is None:
            payload.pop("default", None)
        return payload

    def validate_value(self, value: BindingValue) -> None:
        if value.kind not in self.allowed_value_kinds:
            raise ValueError(f"configuration target {self.target_id!r} rejects value kind {value.kind!r}")
        if isinstance(value, LiteralBindingValueModel):
            if not _binding_value_matches_type(value.value, self.value_type):
                raise ValueError(f"configuration target {self.target_id!r} value does not match value_type")
            if isinstance(value.value, float) and not math.isfinite(value.value):
                raise ValueError(f"configuration target {self.target_id!r} number must be finite")
        elif self.value_type == BindingScalarType.NULL:
            raise ValueError(f"configuration target {self.target_id!r} null type cannot admit a secret reference")


class ConfigurationTargetRegistryModel(ContractModel):
    """Collision-free target registry published by one manifest owner."""

    owner: BindingOwnerModel
    targets: dict[NonEmptyString, ConfigurationTargetDeclarationModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_registry(self) -> ConfigurationTargetRegistryModel:
        claimed_names: dict[str, str] = {}
        for key, declaration in self.targets.items():
            if key != declaration.target_id:
                raise ValueError("configuration target map key must match embedded target_id")
            for name in (declaration.target_id, *declaration.aliases):
                prior = claimed_names.get(name)
                if prior is not None:
                    raise ValueError(f"configuration target alias or id {name!r} collides with target {prior!r}")
                claimed_names[name] = declaration.target_id
        return self

    def resolve(self, supplied_id: str) -> ConfigurationTargetDeclarationModel:
        direct = self.targets.get(supplied_id)
        if direct is not None:
            return direct
        matches = [target for target in self.targets.values() if supplied_id in target.aliases]
        if len(matches) != 1:
            raise ValueError(f"unknown configuration target {supplied_id!r}")
        return matches[0]


class ExperimentBindingDescriptorModel(ContractModel):
    """One explicit factor/condition value bound to one authoritative target."""

    binding_id: NonEmptyString
    source_factor_id: NonEmptyString
    source_factor_level_id: NonEmptyString
    source_condition_id: NonEmptyString
    target: BindingTarget
    value_type: BindingScalarType
    value: BindingValue
    owner: BindingOwnerModel

    def realization_payload(self) -> dict[str, object]:
        """Owner/target/value meaning, independent of design-axis labels."""
        return self.model_dump(
            mode="json", exclude={"binding_id", "source_factor_id", "source_factor_level_id", "source_condition_id"}
        )

    @model_validator(mode="after")
    def _validate_declared_value_type(self) -> ExperimentBindingDescriptorModel:
        if isinstance(self.value, SecretReferenceBindingValueModel):
            if self.value_type == BindingScalarType.NULL:
                raise ValueError("secret references cannot use value_type null")
            return self
        if not _binding_value_matches_type(self.value.value, self.value_type):
            raise ValueError("literal binding value does not match declared value_type")
        if isinstance(self.value.value, float) and not math.isfinite(self.value.value):
            raise ValueError("literal number must be finite")
        return self


class ExperimentBindingDescriptorSetModel(ContractModel):
    """Versioned, collision-free set of authoritative experiment bindings."""

    schema_version: Literal[EXPERIMENT_BINDING_DESCRIPTORS_V1_SCHEMA_VERSION] = (
        EXPERIMENT_BINDING_DESCRIPTORS_V1_SCHEMA_VERSION
    )
    descriptors: list[ExperimentBindingDescriptorModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_unique_bindings_and_targets(self) -> ExperimentBindingDescriptorSetModel:
        binding_ids = [descriptor.binding_id for descriptor in self.descriptors]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("binding_id values must be unique")
        canonical_targets = [
            (descriptor.source_condition_id, *descriptor.target.canonical_key()) for descriptor in self.descriptors
        ]
        if len(canonical_targets) != len(set(canonical_targets)):
            raise ValueError("binding descriptors must not contain a duplicate canonical target")
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
            "binding-descriptors-canonical-targets-injective",
            "Binding ids must be unique and target resolution must be injective within each source condition.",
            validator=(
                "raes_contracts.contracts.ExperimentBindingDescriptorSetModel._validate_unique_bindings_and_targets"
            ),
            inputs=[{"contract_id": "experiment-binding-descriptors-v1", "instance_path": "#"}],
        )
        return json_schema


class RealizedBindingProvenanceModel(ContractModel):
    """Portable provenance for one binding actually realized by its owner."""

    descriptor: ExperimentBindingDescriptorModel
    origin: Literal["selection", "default", "override"]
    configuration_digest: PrefixedDigestString | None = None

    @model_validator(mode="after")
    def _validate_configuration_digest_scope(self) -> RealizedBindingProvenanceModel:
        if self.descriptor.target.plane != "scenario" and self.configuration_digest is None:
            raise ValueError("participant and apparatus realized bindings require configuration_digest")
        return self


class RealizedConfigurationValueModel(ContractModel):
    """One normalized value in a complete participant configuration."""

    target_id: NonEmptyString
    value_type: BindingScalarType
    origin: Literal["default", "override"]
    value: BindingValue

    @model_validator(mode="after")
    def _validate_value_type(self) -> RealizedConfigurationValueModel:
        if isinstance(self.value, LiteralBindingValueModel):
            if not _binding_value_matches_type(self.value.value, self.value_type):
                raise ValueError("realized configuration value does not match value_type")
            if isinstance(self.value.value, float) and not math.isfinite(self.value.value):
                raise ValueError("realized configuration number must be finite")
        elif self.value_type == BindingScalarType.NULL:
            raise ValueError("null configuration values cannot be secret references")
        return self


class ParticipantConfigurationModel(ContractModel):
    """Canonical digest payload for one complete participant configuration."""

    implementation_identity: ApparatusIdentityModel
    manifest_version: NonEmptyString
    owner: BindingOwnerModel
    values: list[RealizedConfigurationValueModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_canonical_values(self) -> ParticipantConfigurationModel:
        target_ids = [entry.target_id for entry in self.values]
        if target_ids != sorted(target_ids):
            raise ValueError("participant configuration values must be ordered by canonical target id")
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("participant configuration values must have unique canonical target ids")
        return self


class ParticipantConfigurationResultModel(ContractModel):
    """Portable result of one complete, atomic participant configuration validation."""

    schema_version: Literal[PARTICIPANT_CONFIGURATION_RESULT_V1_SCHEMA_VERSION] = (
        PARTICIPANT_CONFIGURATION_RESULT_V1_SCHEMA_VERSION
    )
    participant_address: NonEmptyString
    manifest_ref: NonEmptyString
    manifest_digest: PrefixedDigestString
    configuration: ParticipantConfigurationModel
    configuration_digest: PrefixedDigestString

    @model_validator(mode="after")
    def _validate_configuration_digest(self) -> ParticipantConfigurationResultModel:
        from ..satisfiability import canonical_contract_digest

        if self.configuration_digest != canonical_contract_digest(self.configuration):
            raise ValueError("configuration_digest must match the canonical normalized configuration")
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
            "participant-configuration-digest-valid",
            "The configuration digest must be the RFC 8785/JCS digest of the complete normalized configuration.",
            validator=("raes_contracts.contracts.ParticipantConfigurationResultModel._validate_configuration_digest"),
            inputs=[{"contract_id": "participant-configuration-result-v1", "instance_path": "#"}],
        )
        return json_schema


def _binding_value_matches_type(value: BindingScalar, value_type: BindingScalarType) -> bool:
    if value_type == BindingScalarType.NULL:
        matches = value is None
    elif value_type == BindingScalarType.BOOLEAN:
        matches = isinstance(value, bool)
    elif value_type == BindingScalarType.INTEGER:
        matches = isinstance(value, int) and not isinstance(value, bool)
    elif value_type == BindingScalarType.NUMBER:
        matches = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif value_type == BindingScalarType.STRING:
        matches = isinstance(value, str)
    else:
        matches = False
    return matches


def _validate_realized_bindings(bindings: list[RealizedBindingProvenanceModel]) -> None:
    binding_ids = [binding.descriptor.binding_id for binding in bindings]
    if len(binding_ids) != len(set(binding_ids)):
        raise ValueError("realized binding ids must be unique")
    canonical_targets = [
        (binding.descriptor.source_condition_id, *binding.descriptor.target.canonical_key()) for binding in bindings
    ]
    if len(canonical_targets) != len(set(canonical_targets)):
        raise ValueError("realized bindings must not contain duplicate canonical targets")


__all__ = [
    "ApparatusBindingTargetModel",
    "BindingOwnerModel",
    "BindingScalar",
    "BindingScalarType",
    "BindingTarget",
    "BindingValue",
    "ConfigurationTargetDeclarationModel",
    "ConfigurationTargetRegistryModel",
    "EXPERIMENT_BINDING_DESCRIPTORS_V1_SCHEMA_VERSION",
    "ExperimentBindingDescriptorModel",
    "ExperimentBindingDescriptorSetModel",
    "LiteralBindingValueModel",
    "PARTICIPANT_CONFIGURATION_RESULT_V1_SCHEMA_VERSION",
    "ParticipantConfigurationModel",
    "ParticipantConfigurationResultModel",
    "ParticipantImplementationBindingTargetModel",
    "RealizedBindingProvenanceModel",
    "RealizedConfigurationValueModel",
    "ScenarioBindingTargetModel",
    "SecretReferenceBindingValueModel",
]
