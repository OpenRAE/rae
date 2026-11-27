"""API-414 capability comparison shared by planning and selected trial admission."""

from collections import Counter

from pydantic import ValidationError
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_backend_protocols.participant_feature_admission import participant_feature_support_gaps
from raes_contracts.contracts import BackendManifestV2Model, ProcessorManifestV2Model
from raes_contracts.contracts.participant_tool_support import TOOL_PROFILE_SEMANTICS, ParticipantToolProfilesModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.manifest_authority import (
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
)
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel, ProcessorFeature

from .manifest import reference_processor_manifest_v2_model
from .models import RuntimeModel


def _required_features(model: RuntimeModel) -> tuple[set[str], set[str]]:
    tool_features = {"tool_affordances"}
    backend_features = {"action_contracts", "observation_boundaries"}
    for binding in model.tool_affordances.values():
        if binding.participant_refs or binding.participant_role_refs:
            tool_features.add("scoped_tool_affordances")
        for address in binding.action_contract_addresses:
            action = model.action_contracts[address]
            for feature, used in (
                ("preconditions", action.precondition_classes),
                ("effects", action.effect_classes),
                ("failure_classes", action.failure_classes),
                ("temporal_contracts", action.temporal_contract_ids),
            ):
                if used:
                    backend_features.add(feature)
            backend_features.update(action.interaction_classes)
    return tool_features, backend_features


def _capacity_exceeded(model: RuntimeModel, profiles: ParticipantToolProfilesModel) -> bool:
    counts = Counter(binding.behavior_specification_address for binding in model.tool_affordances.values())
    if profiles.max_bindings_per_profile is not None and max(counts.values()) > profiles.max_bindings_per_profile:
        return True
    return profiles.max_participants_per_binding is not None and any(
        len(binding.participant_addresses) > profiles.max_participants_per_binding
        for binding in model.tool_affordances.values()
    )


def _processor_supports(model: RuntimeModel, processor: ProcessorManifestV2Model, required: set[str]) -> bool:
    capabilities = processor.capabilities
    tools = capabilities.participant_tools
    if tools is None:
        return False
    coordinates_supported = all(
        (
            TOOL_PROFILE_SEMANTICS in tools.semantic_versions,
            "sdl-authoring-input-v1" in capabilities.supported_sdl_versions,
            {ProcessorFeature.COMPILATION, ProcessorFeature.PLANNING}.issubset(capabilities.supported_features),
        )
    )
    support = {entry.feature: entry for entry in tools.feature_support}
    features_supported = all(
        feature in support and support[feature].support_level in {"exact", "bounded"} for feature in required
    )
    return coordinates_supported and not _capacity_exceeded(model, tools) and features_supported


def _backend_supports(
    model: RuntimeModel, backend: BackendManifest, tool_features: set[str], backend_features: set[str]
) -> bool:
    # Revalidate nested caller-owned values rather than retaining a trusted cache.
    try:
        wire = BackendManifestV2Model.model_validate(backend_manifest_v2_model(backend).model_dump(mode="json"))
    except ValidationError:
        return False
    capability = wire.capabilities.participant_runtime
    if capability is None or capability.tool_profiles is None:
        return False
    profiles = capability.tool_profiles
    required_roles = {
        model.participant_behaviors[address].role
        for binding in model.tool_affordances.values()
        for address in binding.participant_addresses
        if model.participant_behaviors[address].role
    }
    required_contracts = set().union(
        *(
            mapping.get(feature, frozenset())
            for mapping in PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS.values()
            for feature in tool_features | backend_features
        )
    )
    # Bounded tool support has exact semantics within the evaluated capacity.
    return all(
        (
            TOOL_PROFILE_SEMANTICS in profiles.semantic_versions,
            required_roles.issubset(capability.supported_participant_roles),
            not _capacity_exceeded(model, profiles),
            not participant_feature_support_gaps(
                backend, tool_features, required_level=ParticipantFeatureSupportLevel.BOUNDED
            ),
            not participant_feature_support_gaps(backend, backend_features),
            required_contracts.issubset(backend.supported_contract_versions),
        )
    )


def participant_tool_support_diagnostics(
    model: RuntimeModel,
    backend: BackendManifest,
    processor_manifest: ProcessorManifestV2Model | None = None,
) -> list[Diagnostic]:
    """Fail closed before dispatch; never infer requirements from author promises."""

    if not model.tool_affordances:
        return []
    tool_features, backend_features = _required_features(model)
    diagnostics: list[Diagnostic] = []
    processor = processor_manifest or reference_processor_manifest_v2_model()
    try:
        # Revalidate the caller-owned manifest; a contract refusal means no support.
        processor = ProcessorManifestV2Model.model_validate(processor.model_dump(mode="json"))
    except ValidationError:
        processor_supported = False
    else:
        processor_supported = _processor_supports(model, processor, tool_features)
    if not processor_supported:
        diagnostics.append(
            Diagnostic(
                code="processor.tool-support-insufficient",
                domain="participant",
                address="participant.tool-profiles",
                message="Selected processor lacks required tool-profile semantics, strength, or capacity.",
            )
        )
    backend_supported = _backend_supports(model, backend, tool_features, backend_features)
    if not backend_supported:
        diagnostics.append(
            Diagnostic(
                code="participant.tool-support-insufficient",
                domain="participant",
                address="participant.tool-profiles",
                message="Selected backend lacks required tool-profile semantics, strength, contracts, or capacity.",
            )
        )
    return diagnostics


__all__ = ["participant_tool_support_diagnostics"]
