"""Manifest payloads and conversions for operational capability blocks.

Cleanup, time, crash-recovery observation and operation supervision are
declared independently of the provisioning, orchestration and evaluation
surfaces, and are rendered and reconstructed together here.
"""

from __future__ import annotations

from typing import Any

from raes_contracts.contracts import (
    BackendCapabilitiesV2Model,
    CleanupCapabilitiesModel,
    OperationSupervisionCapabilitiesModel,
    RecoveryObservationCapabilitiesModel,
    TimeCapabilitiesModel,
)

from .capabilities import (
    BackendManifest,
    CleanupCapabilities,
    OperationSupervisionCapabilities,
    RecoveryObservationCapabilities,
    TimeCapabilities,
)


def operational_capability_payloads(manifest: BackendManifest) -> dict[str, Any]:
    """Render the operational capability blocks of a v2 manifest payload."""

    return {
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
        "recovery_observation": (
            RecoveryObservationCapabilitiesModel(
                name=manifest.recovery_observation.name,
                supported_operation_kinds=sorted(
                    manifest.recovery_observation.supported_operation_kinds,
                    key=lambda kind: kind.value,
                ),
            ).model_dump(mode="json")
            if manifest.recovery_observation is not None
            else None
        ),
        "operation_supervision": (
            OperationSupervisionCapabilitiesModel(
                name=manifest.operation_supervision.name,
                guarantees=sorted(manifest.operation_supervision.guarantees),
            ).model_dump(mode="json")
            if manifest.operation_supervision is not None
            else None
        ),
    }


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


def _recovery_observation_from_model(
    model: RecoveryObservationCapabilitiesModel | None,
) -> RecoveryObservationCapabilities | None:
    if model is None:
        return None
    return RecoveryObservationCapabilities(
        name=model.name,
        supported_operation_kinds=frozenset(model.supported_operation_kinds),
    )


def _operation_supervision_from_model(
    model: OperationSupervisionCapabilitiesModel | None,
) -> OperationSupervisionCapabilities | None:
    if model is None:
        return None
    return OperationSupervisionCapabilities(name=model.name, guarantees=frozenset(model.guarantees))


def operational_capabilities_from_model(model: BackendCapabilitiesV2Model) -> dict[str, Any]:
    """Reconstruct the internal operational capability blocks from a v2 model."""

    return {
        "cleanup": _cleanup_from_model(model.cleanup),
        "time": _time_from_model(model.time),
        "recovery_observation": _recovery_observation_from_model(model.recovery_observation),
        "operation_supervision": _operation_supervision_from_model(model.operation_supervision),
    }


__all__ = ["operational_capabilities_from_model", "operational_capability_payloads"]
