"""Helpers for rendering backend manifests as external contract payloads."""

from __future__ import annotations

from typing import Any

from raes_contracts.apparatus import (
    ApparatusIdentity,
    ConceptBinding,
    RealizationObservationCapability,
    RealizationSupportDeclaration,
)
from raes_contracts.contracts import (
    ApparatusIdentityModel,
    BackendCapabilitiesV2Model,
    BackendCompatibilityModel,
    BackendManifestV2Model,
    CleanupCapabilitiesModel,
    ConceptBindingEntryModel,
    EvaluatorCapabilitiesModel,
    OrchestratorCapabilitiesModel,
    ParticipantFeatureSupportModel,
    ParticipantRuntimeCapabilitiesModel,
    RealizationObservationCapabilityModel,
    RealizationSupportDeclarationModel,
    TimeCapabilitiesModel,
)
from raes_contracts.manifest_authority import BACKEND_SUPPORTED_CONTRACT_IDS
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

from .capabilities import (
    BackendCapabilitySet,
    BackendCompatibility,
    BackendManifest,
    CleanupCapabilities,
    EvaluatorCapabilities,
    OrchestratorCapabilities,
    ParticipantFeatureSupport,
    ParticipantRuntimeCapabilities,
    TimeCapabilities,
)
from .observation_manifest import observation_capability_payload, observation_from_model
from .participant_execution_manifest import (
    participant_execution_capability_kwargs,
    participant_execution_capability_payload,
)
from .process_resource_limits import (
    process_resource_limit_capabilities,
    process_resource_limit_models,
)
from .provisioner_manifest import provisioner_capability_payload, provisioner_from_model


class BackendManifestEnvelopeUnsupportedError(ValueError):
    """A backend manifest declares an envelope that cannot be resolved."""


def _evaluator_capability_payload(manifest: BackendManifest) -> dict[str, Any] | None:
    evaluator = manifest.evaluator
    if evaluator is None:
        return None
    payload: dict[str, Any] = {
        "name": evaluator.name,
        "supported_sections": sorted(evaluator.supported_sections),
        "supports_scoring": evaluator.supports_scoring,
        "supports_objectives": evaluator.supports_objectives,
        "constraints": dict(evaluator.constraints),
    }
    if {"propositions", "assertions"}.issubset(evaluator.supported_sections):
        payload.update(
            supported_predicate_families=sorted(evaluator.supported_predicate_families),
            supported_quantifiers=sorted(evaluator.supported_quantifiers),
            supported_truth_outcomes=sorted(evaluator.supported_truth_outcomes),
            supported_evidence_channels=sorted(evaluator.supported_evidence_channels),
            supported_time_domains=sorted(evaluator.supported_time_domains),
            preserves_binding_provenance=evaluator.preserves_binding_provenance,
        )
    return payload


def backend_manifest_v2_model(manifest: BackendManifest) -> BackendManifestV2Model:
    """Render a backend manifest as the authoritative v2 contract model."""
    return BackendManifestV2Model(
        identity=ApparatusIdentityModel(
            name=manifest.identity.name,
            version=manifest.identity.version,
        ),
        supported_contract_versions=[
            contract_id
            for contract_id in BACKEND_SUPPORTED_CONTRACT_IDS
            if contract_id in manifest.supported_contract_versions
        ],
        compatibility=BackendCompatibilityModel(
            processors=sorted(manifest.compatible_processors),
        ),
        realization_support=[
            RealizationSupportDeclarationModel(
                domain=declaration.domain,
                support_mode=declaration.support_mode,
                supported_constraint_kinds=sorted(declaration.supported_constraint_kinds),
                supported_exact_requirement_kinds=sorted(declaration.supported_exact_requirement_kinds),
                disclosure_kinds=sorted(declaration.disclosure_kinds),
                observation_capabilities={
                    concern_kind: RealizationObservationCapabilityModel(
                        verification_scope=capability.verification_scope,
                        observation_strength=capability.observation_strength,
                    )
                    for concern_kind, capability in sorted(declaration.observation_capabilities.items())
                },
                process_resource_limits=process_resource_limit_models(declaration.process_resource_limits),
                artifact_mechanisms=list(declaration.artifact_mechanisms),
                constraints=dict(declaration.constraints),
            )
            for declaration in manifest.realization_support
        ],
        realization_envelope=(
            manifest.realization_envelope.identity.model_dump(mode="json")
            if manifest.realization_envelope is not None
            else None
        ),
        concept_bindings=[
            ConceptBindingEntryModel(scope=binding.scope, family=binding.family)
            for binding in manifest.concept_bindings
        ],
        constraints=dict(manifest.constraints),
        capabilities={
            "provisioner": provisioner_capability_payload(manifest.provisioner),
            "orchestrator": (
                {
                    "name": manifest.orchestrator.name,
                    "supported_sections": sorted(manifest.orchestrator.supported_sections),
                    "supports_workflows": manifest.orchestrator.supports_workflows,
                    "supports_assertion_refs": manifest.orchestrator.supports_assertion_refs,
                    "supports_inject_bindings": manifest.orchestrator.supports_inject_bindings,
                    "supported_workflow_features": sorted(
                        feature for feature in manifest.orchestrator.supported_workflow_features
                    ),
                    "supported_workflow_state_predicates": sorted(
                        feature for feature in manifest.orchestrator.supported_workflow_state_predicates
                    ),
                    "constraints": dict(manifest.orchestrator.constraints),
                }
                if manifest.orchestrator is not None
                else None
            ),
            "evaluator": _evaluator_capability_payload(manifest),
            "participant_runtime": (
                {
                    "name": manifest.participant_runtime.name,
                    "supported_participant_roles": sorted(manifest.participant_runtime.supported_participant_roles),
                    "supported_behavior_features": sorted(manifest.participant_runtime.supported_behavior_features),
                    "supported_interaction_features": sorted(
                        manifest.participant_runtime.supported_interaction_features
                    ),
                    "feature_support": [
                        ParticipantFeatureSupportModel(
                            feature=entry.feature,
                            support_level=entry.support_level,
                            constraint_refs=list(entry.constraint_refs),
                            limitation_refs=list(entry.limitation_refs),
                            disclosure_refs=list(entry.disclosure_refs),
                            evidence_refs=list(entry.evidence_refs),
                        )
                        for entry in manifest.participant_runtime.feature_support
                    ],
                    "supports_autonomous_execution": manifest.participant_runtime.supports_autonomous_execution,
                    "supported_autonomous_selection_strategies": sorted(
                        manifest.participant_runtime.supported_autonomous_selection_strategies
                    ),
                    "supported_autonomous_action_contracts": sorted(
                        manifest.participant_runtime.supported_autonomous_action_contracts
                    ),
                    "supported_autonomous_observation_boundaries": sorted(
                        manifest.participant_runtime.supported_autonomous_observation_boundaries
                    ),
                    "supported_autonomous_target_addresses": sorted(
                        manifest.participant_runtime.supported_autonomous_target_addresses
                    ),
                    "supported_autonomous_policy_profiles": sorted(
                        manifest.participant_runtime.supported_autonomous_policy_profiles
                    ),
                    "supported_autonomous_activity_features": sorted(
                        manifest.participant_runtime.supported_autonomous_activity_features
                    ),
                    "supported_autonomous_random_stream_profiles": sorted(
                        manifest.participant_runtime.supported_autonomous_random_stream_profiles
                    ),
                    "max_autonomous_participants": manifest.participant_runtime.max_autonomous_participants,
                    "max_autonomous_action_attempts": (manifest.participant_runtime.max_autonomous_action_attempts),
                    "max_autonomous_in_flight": manifest.participant_runtime.max_autonomous_in_flight,
                    "max_autonomous_occurrences": manifest.participant_runtime.max_autonomous_occurrences,
                    "max_autonomous_retries_per_occurrence": (
                        manifest.participant_runtime.max_autonomous_retries_per_occurrence
                    ),
                    "max_autonomous_burst_size": manifest.participant_runtime.max_autonomous_burst_size,
                    **participant_execution_capability_payload(manifest.participant_runtime),
                    "constraints": dict(manifest.participant_runtime.constraints),
                }
                if manifest.participant_runtime is not None
                else None
            ),
            "observation": observation_capability_payload(manifest.observation),
            "cleanup": (
                CleanupCapabilitiesModel(
                    name=manifest.cleanup.name,
                    supported_contract_versions=sorted(manifest.cleanup.supported_contract_versions),
                    supported_action_kinds=sorted(manifest.cleanup.supported_action_kinds),
                    supported_verification_methods=sorted(manifest.cleanup.supported_verification_methods),
                    supports_reusable_state=manifest.cleanup.supports_reusable_state,
                    supports_residual_state_disclosure=manifest.cleanup.supports_residual_state_disclosure,
                ).model_dump(mode="json")
                if manifest.cleanup is not None
                else None
            ),
            "time": (
                TimeCapabilitiesModel(
                    name=manifest.time.name,
                    supported_contract_versions=sorted(manifest.time.supported_contract_versions),
                    supported_domain_kinds=sorted(manifest.time.supported_domain_kinds),
                    supported_authority_kinds=sorted(manifest.time.supported_authority_kinds),
                    supported_advancement_modes=sorted(manifest.time.supported_advancement_modes),
                    supported_synchronization_modes=sorted(manifest.time.supported_synchronization_modes),
                    supported_mapping_kinds=sorted(manifest.time.supported_mapping_kinds),
                    supported_constraint_kinds=sorted(manifest.time.supported_constraint_kinds),
                    supported_reset_behaviors=sorted(manifest.time.supported_reset_behaviors),
                    supported_replay_behaviors=sorted(manifest.time.supported_replay_behaviors),
                    max_time_domains=manifest.time.max_time_domains,
                    max_clocks=manifest.time.max_clocks,
                    supports_pause=manifest.time.supports_pause,
                    supports_jump=manifest.time.supports_jump,
                    supports_exact_rational_mappings=manifest.time.supports_exact_rational_mappings,
                    supports_append_only_history=manifest.time.supports_append_only_history,
                    supports_run_provenance=manifest.time.supports_run_provenance,
                    supports_coordinated_participant_reset=(manifest.time.supports_coordinated_participant_reset),
                    constraints=dict(manifest.time.constraints),
                ).model_dump(mode="json")
                if manifest.time is not None
                else None
            ),
        },
    )


def backend_manifest_payload(manifest: BackendManifest) -> dict[str, Any]:
    """Render a backend manifest as JSON-ready data."""

    payload = backend_manifest_v2_model(manifest).model_dump(mode="json")
    if payload.get("realization_envelope") is None:
        payload.pop("realization_envelope", None)
    if payload["capabilities"].get("time") is None:
        payload["capabilities"].pop("time", None)
    return payload


def _realization_support_from_model(model: RealizationSupportDeclarationModel) -> RealizationSupportDeclaration:
    return RealizationSupportDeclaration(
        domain=model.domain,
        support_mode=model.support_mode,
        supported_constraint_kinds=frozenset(model.supported_constraint_kinds),
        supported_exact_requirement_kinds=frozenset(model.supported_exact_requirement_kinds),
        disclosure_kinds=frozenset(model.disclosure_kinds),
        observation_capabilities={
            concern_kind: RealizationObservationCapability(
                verification_scope=capability.verification_scope,
                observation_strength=capability.observation_strength,
            )
            for concern_kind, capability in model.observation_capabilities.items()
        },
        process_resource_limits=process_resource_limit_capabilities(model.process_resource_limits),
        artifact_mechanisms=tuple(model.artifact_mechanisms),
        constraints=dict(model.constraints),
    )


def _orchestrator_from_model(model: OrchestratorCapabilitiesModel | None) -> OrchestratorCapabilities | None:
    if model is None:
        return None
    return OrchestratorCapabilities(
        name=model.name,
        supported_sections=frozenset(model.supported_sections),
        supports_workflows=model.supports_workflows,
        supports_assertion_refs=model.supports_assertion_refs,
        supports_inject_bindings=model.supports_inject_bindings,
        supported_workflow_features=frozenset(model.supported_workflow_features),
        supported_workflow_state_predicates=frozenset(model.supported_workflow_state_predicates),
        constraints=dict(model.constraints),
    )


def _evaluator_from_model(model: EvaluatorCapabilitiesModel | None) -> EvaluatorCapabilities | None:
    if model is None:
        return None
    return EvaluatorCapabilities(
        name=model.name,
        supported_sections=frozenset(model.supported_sections),
        supports_scoring=model.supports_scoring,
        supports_objectives=model.supports_objectives,
        supported_predicate_families=frozenset(model.supported_predicate_families),
        supported_quantifiers=frozenset(model.supported_quantifiers),
        supported_truth_outcomes=frozenset(model.supported_truth_outcomes),
        supported_evidence_channels=frozenset(model.supported_evidence_channels),
        supported_time_domains=frozenset(model.supported_time_domains),
        preserves_binding_provenance=model.preserves_binding_provenance,
        constraints=dict(model.constraints),
    )


def _participant_feature_support_from_model(model: ParticipantFeatureSupportModel) -> ParticipantFeatureSupport:
    return ParticipantFeatureSupport(
        feature=model.feature,
        support_level=model.support_level,
        constraint_refs=tuple(model.constraint_refs),
        limitation_refs=tuple(model.limitation_refs),
        disclosure_refs=tuple(model.disclosure_refs),
        evidence_refs=tuple(model.evidence_refs),
    )


def _participant_runtime_from_model(
    model: ParticipantRuntimeCapabilitiesModel | None,
) -> ParticipantRuntimeCapabilities | None:
    if model is None:
        return None
    return ParticipantRuntimeCapabilities(
        name=model.name,
        supported_participant_roles=frozenset(model.supported_participant_roles),
        supported_behavior_features=frozenset(model.supported_behavior_features),
        supported_interaction_features=frozenset(model.supported_interaction_features),
        feature_support=tuple(_participant_feature_support_from_model(entry) for entry in model.feature_support),
        supports_autonomous_execution=model.supports_autonomous_execution,
        supported_autonomous_selection_strategies=frozenset(model.supported_autonomous_selection_strategies),
        supported_autonomous_action_contracts=frozenset(model.supported_autonomous_action_contracts),
        supported_autonomous_observation_boundaries=frozenset(model.supported_autonomous_observation_boundaries),
        supported_autonomous_target_addresses=frozenset(model.supported_autonomous_target_addresses),
        supported_autonomous_policy_profiles=frozenset(model.supported_autonomous_policy_profiles),
        supported_autonomous_activity_features=frozenset(model.supported_autonomous_activity_features),
        supported_autonomous_random_stream_profiles=frozenset(model.supported_autonomous_random_stream_profiles),
        max_autonomous_participants=model.max_autonomous_participants,
        max_autonomous_action_attempts=model.max_autonomous_action_attempts,
        max_autonomous_in_flight=model.max_autonomous_in_flight,
        max_autonomous_occurrences=model.max_autonomous_occurrences,
        max_autonomous_retries_per_occurrence=model.max_autonomous_retries_per_occurrence,
        max_autonomous_burst_size=model.max_autonomous_burst_size,
        **participant_execution_capability_kwargs(model),
        constraints=dict(model.constraints),
    )


def _cleanup_from_model(model: CleanupCapabilitiesModel | None) -> CleanupCapabilities | None:
    if model is None:
        return None
    return CleanupCapabilities(
        name=model.name,
        supported_contract_versions=frozenset(model.supported_contract_versions),
        supported_action_kinds=frozenset(model.supported_action_kinds),
        supported_verification_methods=frozenset(model.supported_verification_methods),
        supports_reusable_state=model.supports_reusable_state,
        supports_residual_state_disclosure=model.supports_residual_state_disclosure,
    )


def _time_from_model(model: TimeCapabilitiesModel | None) -> TimeCapabilities | None:
    if model is None:
        return None
    return TimeCapabilities(
        name=model.name,
        supported_contract_versions=frozenset(model.supported_contract_versions),
        supported_domain_kinds=frozenset(model.supported_domain_kinds),
        supported_authority_kinds=frozenset(model.supported_authority_kinds),
        supported_advancement_modes=frozenset(model.supported_advancement_modes),
        supported_synchronization_modes=frozenset(model.supported_synchronization_modes),
        supported_mapping_kinds=frozenset(model.supported_mapping_kinds),
        supported_constraint_kinds=frozenset(model.supported_constraint_kinds),
        supported_reset_behaviors=frozenset(model.supported_reset_behaviors),
        supported_replay_behaviors=frozenset(model.supported_replay_behaviors),
        max_time_domains=model.max_time_domains,
        max_clocks=model.max_clocks,
        supports_pause=model.supports_pause,
        supports_jump=model.supports_jump,
        supports_exact_rational_mappings=model.supports_exact_rational_mappings,
        supports_append_only_history=model.supports_append_only_history,
        supports_run_provenance=model.supports_run_provenance,
        supports_coordinated_participant_reset=model.supports_coordinated_participant_reset,
        constraints=dict(model.constraints),
    )


def _capability_set_from_model(model: BackendCapabilitiesV2Model) -> BackendCapabilitySet:
    return BackendCapabilitySet(
        provisioner=provisioner_from_model(model.provisioner),
        orchestrator=_orchestrator_from_model(model.orchestrator),
        evaluator=_evaluator_from_model(model.evaluator),
        participant_runtime=_participant_runtime_from_model(model.participant_runtime),
        observation=observation_from_model(model.observation),
        cleanup=_cleanup_from_model(model.cleanup),
        time=_time_from_model(model.time),
    )


def backend_manifest_from_v2_model(model: BackendManifestV2Model) -> BackendManifest:
    """Reconstruct the internal typed ``BackendManifest`` from its v2 contract model.

    Inverse of :func:`backend_manifest_v2_model`. Constructing ``BackendManifest``
    re-runs the internal capability, controlled-vocabulary, compatibility, and
    contract-authority validators, so a payload that merely passed
    ``BackendManifestV2Model`` schema validation still cannot smuggle in an
    inconsistent internal manifest.

    Fails closed on realization-envelope-bearing manifests: a
    ``backend-manifest-v2`` payload carries only the realization-envelope
    *identity*, not the full digest-checked declaration the planner needs for
    envelope-membership checks. Such a manifest is insufficient for planning, so
    the caller must supply an envelope-free manifest (or use the default).
    """

    if model.realization_envelope is not None or "realization-envelope-v1" in model.supported_contract_versions:
        raise BackendManifestEnvelopeUnsupportedError(
            "backend manifest declares a realization envelope, but a backend-manifest-v2 payload "
            "carries only the envelope identity, not the full digest-checked declaration the planner "
            "requires. Supply an envelope-free manifest or omit it to use the default reference "
            "dry-run manifest."
        )
    return _backend_manifest_from_v2_model(model, realization_envelope=None)


def backend_manifest_from_v2_model_with_envelope(
    model: BackendManifestV2Model,
    realization_envelope: BackendRealizationEnvelopeModel,
) -> BackendManifest:
    """Reconstruct a runtime manifest after joining its full pinned envelope."""

    if model.realization_envelope != realization_envelope.identity:
        raise BackendManifestEnvelopeUnsupportedError(
            "backend manifest realization-envelope identity does not match the supplied declaration"
        )
    return _backend_manifest_from_v2_model(model, realization_envelope=realization_envelope)


def _backend_manifest_from_v2_model(
    model: BackendManifestV2Model,
    *,
    realization_envelope: BackendRealizationEnvelopeModel | None,
) -> BackendManifest:
    return BackendManifest(
        identity=ApparatusIdentity(name=model.identity.name, version=model.identity.version),
        supported_contract_versions=frozenset(model.supported_contract_versions),
        compatibility=BackendCompatibility(processors=frozenset(model.compatibility.processors)),
        realization_support=tuple(
            _realization_support_from_model(declaration) for declaration in model.realization_support
        ),
        concept_bindings=tuple(
            ConceptBinding(scope=binding.scope, family=binding.family) for binding in model.concept_bindings
        ),
        constraints=dict(model.constraints),
        capabilities=_capability_set_from_model(model.capabilities),
        realization_envelope=realization_envelope,
    )
