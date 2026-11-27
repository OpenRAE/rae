"""Scopes where manifests may bind canonical concepts (ADR-012).

The controlled vocabulary catalog governs these scopes, and the backend,
processor and participant implementation manifests check their bindings
against them.
"""

from __future__ import annotations

BACKEND_CONCEPT_BINDING_SCOPES = frozenset(
    {
        "capabilities.provisioner.supported_node_types",
        "capabilities.provisioner.supported_os_families",
        "capabilities.provisioner.operating_systems.distribution",
        "capabilities.provisioner.supported_node_architectures",
        "capabilities.provisioner.supported_content_types",
        "capabilities.provisioner.supported_account_features",
        "capabilities.provisioner.supported_domain_profiles",
        "capabilities.provisioner.supported_service_materialization_profiles",
        "capabilities.orchestrator.supported_sections",
        "capabilities.evaluator.supported_sections",
        "capabilities.observation.supported_capture_kinds",
        "capabilities.observation.supported_channel_kinds",
        "capabilities.observation.supported_sealing_modes",
        "capabilities.participant_runtime.supported_participant_roles",
        "capabilities.participant_runtime.supported_behavior_features",
        "capabilities.participant_runtime.supported_interaction_features",
        "capabilities.time.supported_domain_kinds",
        "capabilities.time.supported_authority_kinds",
        "capabilities.time.supported_advancement_modes",
        "capabilities.time.supported_synchronization_modes",
        "capabilities.time.supported_constraint_kinds",
    }
)


PROCESSOR_CONCEPT_BINDING_SCOPES = frozenset(
    {
        "capabilities.supported_sdl_versions",
        "capabilities.supported_features",
    }
)


PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES = frozenset(
    {
        "implementation_kind",
        "capabilities.supported_participant_contracts",
        "capabilities.supported_decision_surface_modes",
        "capabilities.tool_affordance_expectations",
        "capabilities.exposure_policy_kinds",
    }
)


__all__ = [
    "BACKEND_CONCEPT_BINDING_SCOPES",
    "PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES",
    "PROCESSOR_CONCEPT_BINDING_SCOPES",
]
