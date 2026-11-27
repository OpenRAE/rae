"""Atomic realization of manifest-declared participant configuration."""

from __future__ import annotations

from typing import Protocol

from pydantic import Field

from raes_contracts.canonical import canonical_contract_digest

from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .experiment_bindings import (
    BindingValue,
    ConfigurationTargetDeclarationModel,
    ParticipantConfigurationModel,
    ParticipantConfigurationResultModel,
    ParticipantControlContextConfigurationSelectionModel,
    RealizedConfigurationValueModel,
)
from .participant_manifests import (
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)


class ConfigurationOverrideModel(ContractModel):
    """One author-supplied override using a canonical target id or declared alias."""

    target_id: NonEmptyString
    value: BindingValue = Field(discriminator="kind")


class ParticipantConfigurationValidator(Protocol):
    """Trusted owner hook for complete same-type normalization and validation."""

    def validate_and_normalize(
        self,
        configuration: ParticipantConfigurationModel,
    ) -> ParticipantConfigurationModel: ...


def realize_participant_configuration(
    *,
    participant_address: str,
    manifest: ParticipantImplementationManifestModel,
    manifest_ref: str,
    manifest_digest: PrefixedDigestString,
    overrides: list[ConfigurationOverrideModel],
    validator: ParticipantConfigurationValidator | None = None,
) -> ParticipantConfigurationResultModel:
    """Validate a complete configuration and return one atomic normalized result."""

    registry = manifest.configuration_registry
    if registry is None:
        raise ValueError("participant implementation manifest has no configuration target registry")

    overrides_by_target: dict[str, ConfigurationOverrideModel] = {}
    for override in overrides:
        declaration = registry.resolve(override.target_id)
        canonical_target = declaration.target_id
        if canonical_target in overrides_by_target:
            raise ValueError(f"duplicate canonical target {canonical_target!r} in configuration overrides")
        declaration.validate_value(override.value)
        overrides_by_target[canonical_target] = override

    realized_values: list[RealizedConfigurationValueModel] = []
    for target_id in sorted(registry.targets):
        declaration = registry.targets[target_id]
        override = overrides_by_target.get(target_id)
        if override is not None:
            value = override.value
            origin = "override"
        elif declaration.default is not None:
            value = declaration.default
            origin = "default"
        else:
            raise ValueError(f"required configuration target {target_id!r} has no override")
        declaration.validate_value(value)
        realized_values.append(
            RealizedConfigurationValueModel(
                target_id=target_id,
                value_type=declaration.value_type,
                origin=origin,
                value=value,
                control_context_selection=_context_selection(participant_address, declaration, value, validator),
            )
        )

    configuration = ParticipantConfigurationModel(
        implementation_identity=manifest.identity,
        manifest_version=manifest.schema_version,
        owner=registry.owner,
        values=realized_values,
    )
    if validator is not None:
        original = configuration.model_copy(deep=True)
        normalized = validator.validate_and_normalize(configuration)
        configuration = _validate_owner_normalization(original, normalized, registry.targets)

    digest = canonical_contract_digest(configuration)
    return ParticipantConfigurationResultModel(
        participant_address=participant_address,
        manifest_ref=manifest_ref,
        manifest_digest=manifest_digest,
        configuration=configuration,
        configuration_digest=digest,
    )


def _context_selection(
    participant_address: str,
    declaration: ConfigurationTargetDeclarationModel,
    value: BindingValue,
    validator: ParticipantConfigurationValidator | None,
) -> ParticipantControlContextConfigurationSelectionModel | None:
    domain = declaration.control_context
    if domain is None:
        return None
    contextual = getattr(validator, "validate_control_context_reference", None)
    if not callable(contextual):
        raise ValueError("control-context owner validation is required")
    selection = ParticipantControlContextConfigurationSelectionModel(
        slot_id=domain.slot_id,
        declaration_ref=value.value,
        asset_ref=domain.references[value.value].model_copy(deep=True),
    )
    original = selection.model_copy(deep=True)
    contextual(participant_address, selection)
    if selection != original:
        raise ValueError("control-context owner must preserve the exact selection")
    return selection


def _validate_owner_normalization(
    original: ParticipantConfigurationModel,
    normalized: ParticipantConfigurationModel,
    declarations: dict[str, ConfigurationTargetDeclarationModel],
) -> ParticipantConfigurationModel:
    if (
        normalized.implementation_identity != original.implementation_identity
        or normalized.manifest_version != original.manifest_version
        or normalized.owner != original.owner
    ):
        raise ValueError("participant configuration validator must preserve owner and manifest identity")
    if [entry.target_id for entry in normalized.values] != [entry.target_id for entry in original.values]:
        raise ValueError("participant configuration validator must preserve the complete canonical target set")
    original_by_target = {entry.target_id: entry for entry in original.values}
    for entry in normalized.values:
        _validate_normalized_entry(
            entry,
            original_by_target[entry.target_id],
            declarations[entry.target_id],
        )
    return normalized


def _validate_normalized_entry(
    entry: RealizedConfigurationValueModel,
    original_entry: RealizedConfigurationValueModel,
    declaration: ConfigurationTargetDeclarationModel,
) -> None:
    if entry.control_context_selection != original_entry.control_context_selection or (
        entry.control_context_selection is not None and entry.value != original_entry.value
    ):
        raise ValueError("participant configuration validator must preserve exact control-context selection")
    if entry.origin != original_entry.origin:
        raise ValueError("participant configuration validator must preserve default/override origin")
    if entry.value_type != declaration.value_type:
        raise ValueError("participant configuration validator must preserve declared value types")
    if entry.value.kind != original_entry.value.kind:
        raise ValueError("participant configuration validator must preserve literal/secret-reference disposition")
    if entry.value.kind == "secret-reference" and entry.value != original_entry.value:
        raise ValueError("participant configuration validator must preserve secret-reference identity")
    declaration.validate_value(entry.value)


def validate_participant_configuration_selection(
    selection: ParticipantImplementationSelectionModel,
    result: ParticipantConfigurationResultModel,
) -> None:
    """Verify that a participant selection names one authoritative configuration result."""

    if selection.participant_address != result.participant_address:
        raise ValueError("participant selection address does not match configuration result")
    if selection.implementation_identity != result.configuration.implementation_identity:
        raise ValueError("participant selection implementation identity does not match configuration result")
    if selection.manifest_ref != result.manifest_ref or selection.manifest_digest != result.manifest_digest:
        raise ValueError("participant selection manifest identity does not match configuration result")
    if selection.configuration_digest != result.configuration_digest:
        raise ValueError("participant selection configuration digest does not match authoritative result")


__all__ = [
    "ConfigurationOverrideModel",
    "ParticipantConfigurationValidator",
    "realize_participant_configuration",
    "validate_participant_configuration_selection",
]
