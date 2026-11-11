"""Cross-artifact admission for authoritative experiment binding targets.

A target that does not resolve through its plane owner raises
``ExperimentBindingTargetError`` (ADR-116).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Protocol

from pydantic import ValidationError

from .contracts.base import ContractModel, NonEmptyString
from .contracts.experiment_bindings import (
    ApparatusBindingTargetModel,
    BindingOwnerModel,
    BindingScalarType,
    ConfigurationTargetDeclarationModel,
    ConfigurationTargetRegistryModel,
    ExperimentBindingDescriptorModel,
    ExperimentBindingDescriptorSetModel,
    ParticipantImplementationBindingTargetModel,
    ScenarioBindingTargetModel,
)
from .contracts.manifests import ProcessorManifestV2Model
from .contracts.participant_manifests import (
    BackendManifestV2Model,
    ParticipantImplementationManifestModel,
)
from .errors import InvalidInputError

ParticipantManifestKey = tuple[str, str, str, str]
ApparatusManifestKey = tuple[str, str, str, str]
ApparatusManifest = ProcessorManifestV2Model | BackendManifestV2Model


class ExperimentBindingTargetError(InvalidInputError):
    """A binding descriptor target does not resolve through its plane owner."""


class ScenarioBindingResolution(ContractModel):
    """Canonical SDL target result returned by the public variation authority."""

    canonical_target_id: NonEmptyString
    value_type: BindingScalarType
    allowed_value_kinds: list[Literal["literal", "secret-reference"]]
    sensitivity: Literal["public", "internal", "restricted", "secret"]
    owner: BindingOwnerModel


class ScenarioBindingTargetResolver(Protocol):
    """Public SDL variation-target resolution seam used during admission.

    ``resolve`` raises ``ExperimentBindingTargetError`` for a target that does not resolve.
    """

    def resolve(
        self,
        scenario_family_id: str,
        variation_point_id: str,
        supplied_target_id: str,
    ) -> ScenarioBindingResolution: ...


def validate_experiment_binding_targets(
    descriptors: ExperimentBindingDescriptorSetModel,
    *,
    scenario_resolver: ScenarioBindingTargetResolver,
    participant_manifests: Mapping[ParticipantManifestKey, ParticipantImplementationManifestModel],
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest],
) -> ExperimentBindingDescriptorSetModel:
    """Resolve every descriptor through exactly one plane owner before admission."""

    admitted: list[ExperimentBindingDescriptorModel] = []
    for descriptor in descriptors.descriptors:
        target = descriptor.target
        if isinstance(target, ScenarioBindingTargetModel):
            canonical_target = _resolve_scenario_target(descriptor, target, scenario_resolver)
        elif isinstance(target, ParticipantImplementationBindingTargetModel):
            canonical_target = _resolve_participant_target(descriptor, target, participant_manifests)
        elif isinstance(target, ApparatusBindingTargetModel):
            canonical_target = _resolve_apparatus_target(descriptor, target, apparatus_manifests)
        # The discriminated union is closed before dispatch.
        else:
            raise ValueError("unknown binding plane")
        admitted.append(descriptor.model_copy(update={"target": canonical_target}))
    try:
        return ExperimentBindingDescriptorSetModel(
            schema_version=descriptors.schema_version,
            descriptors=admitted,
        )
    except ValidationError as exc:
        # An alias and its canonical target can resolve to the same target, which the set refuses.
        raise ExperimentBindingTargetError("binding descriptors must not contain a duplicate canonical target") from exc


def _resolve_scenario_target(
    descriptor: ExperimentBindingDescriptorModel,
    target: ScenarioBindingTargetModel,
    resolver: ScenarioBindingTargetResolver,
) -> ScenarioBindingTargetModel:
    resolution = resolver.resolve(
        target.scenario_family_id,
        target.variation_point_id,
        target.target_id,
    )
    if resolution.value_type != descriptor.value_type:
        raise ExperimentBindingTargetError("scenario target value_type does not match binding descriptor")
    if resolution.owner != descriptor.owner:
        raise ExperimentBindingTargetError("scenario target owner does not match binding descriptor")
    if descriptor.value.kind not in resolution.allowed_value_kinds:
        raise ExperimentBindingTargetError("scenario target rejects the binding value kind")
    if resolution.sensitivity == "secret" and descriptor.value.kind != "secret-reference":
        raise ExperimentBindingTargetError("secret scenario targets admit only secret-reference values")
    return target.model_copy(update={"target_id": resolution.canonical_target_id})


def _resolve_participant_target(
    descriptor: ExperimentBindingDescriptorModel,
    target: ParticipantImplementationBindingTargetModel,
    manifests: Mapping[ParticipantManifestKey, ParticipantImplementationManifestModel],
) -> ParticipantImplementationBindingTargetModel:
    key = (
        target.participant_address,
        target.implementation_name,
        target.implementation_version,
        target.manifest_version,
    )
    manifest = manifests.get(key)
    if manifest is None:
        raise ExperimentBindingTargetError("participant binding target owner must resolve to the selected manifest")
    if (
        manifest.identity.name != target.implementation_name
        or manifest.identity.version != target.implementation_version
        or manifest.schema_version != target.manifest_version
    ):
        raise ExperimentBindingTargetError("participant binding target identity must match the resolved manifest")
    registry = manifest.configuration_registry
    if registry is None:
        raise ExperimentBindingTargetError("selected participant manifest has no configuration target registry")
    declaration = _declared_target(registry, target.target_id)
    _validate_declared_target(descriptor, declaration, registry.owner)
    return target.model_copy(update={"target_id": declaration.target_id})


def _resolve_apparatus_target(
    descriptor: ExperimentBindingDescriptorModel,
    target: ApparatusBindingTargetModel,
    manifests: Mapping[ApparatusManifestKey, ApparatusManifest],
) -> ApparatusBindingTargetModel:
    key = (
        target.component_kind,
        target.component_name,
        target.component_version,
        target.manifest_version,
    )
    manifest = manifests.get(key)
    if manifest is None:
        raise ExperimentBindingTargetError("apparatus binding target owner must resolve to the selected manifest")
    manifest_kind = "processor" if isinstance(manifest, ProcessorManifestV2Model) else "backend"
    if (
        target.component_kind != manifest_kind
        or manifest.identity.name != target.component_name
        or manifest.identity.version != target.component_version
        or manifest.schema_version != target.manifest_version
    ):
        raise ExperimentBindingTargetError(
            "apparatus binding target identity and kind must match the resolved manifest"
        )
    registry = manifest.configuration_registry
    if registry is None:
        raise ExperimentBindingTargetError("selected apparatus manifest has no configuration target registry")
    declaration = _declared_target(registry, target.target_id)
    _validate_declared_target(descriptor, declaration, registry.owner)
    return target.model_copy(update={"target_id": declaration.target_id})


def _declared_target(registry: ConfigurationTargetRegistryModel, target_id: str) -> ConfigurationTargetDeclarationModel:
    try:
        return registry.resolve(target_id)
    except ValueError as exc:
        # The registry is a value object, so it refuses an unknown id with ValueError (rule E3).
        raise ExperimentBindingTargetError("unknown configuration target in the selected manifest registry") from exc


def _validate_declared_target(
    descriptor: ExperimentBindingDescriptorModel,
    declaration: ConfigurationTargetDeclarationModel,
    owner: BindingOwnerModel,
) -> None:
    if descriptor.owner != owner:
        raise ExperimentBindingTargetError("configuration target owner does not match binding descriptor")
    if descriptor.value_type != declaration.value_type:
        raise ExperimentBindingTargetError("configuration target value_type does not match binding descriptor")
    try:
        declaration.validate_value(descriptor.value)
    except ValueError as exc:
        # The declaration is a value object, so it refuses an out-of-domain value with ValueError (rule E3).
        raise ExperimentBindingTargetError(
            "binding descriptor value is outside the configuration target domain"
        ) from exc


__all__ = [
    "ApparatusManifest",
    "ApparatusManifestKey",
    "ExperimentBindingTargetError",
    "ParticipantManifestKey",
    "ScenarioBindingResolution",
    "ScenarioBindingTargetResolver",
    "validate_experiment_binding_targets",
]
