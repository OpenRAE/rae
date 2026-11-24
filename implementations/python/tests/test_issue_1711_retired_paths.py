"""Issue #1711 / ADR-121: a moved name has one public path, so each retired named import fails."""

from __future__ import annotations

import importlib

import pytest

# The former owner, the moved name and its one owner.
RETIRED = [
    ("raes._source", "ArtifactIdentity", "raes_contracts.artifact_identity"),
    ("raes._source", "ArtifactMechanismProfile", "raes_contracts.artifact_identity"),
    ("raes.explicitness", "ExplicitnessClass", "raes_contracts.explicitness"),
    ("raes.explicitness", "ExplicitnessProvenance", "raes_contracts.explicitness"),
    ("raes.nodes", "parse_ram", "raes_contracts.runtime_values"),
    ("raes.observability_plane_semantics", "ObservabilityEvidencePlane", "raes_contracts.observability_planes"),
    (
        "raes.participant_behavior._action_contracts",
        "ParticipantInteractionClass",
        "raes_contracts.participant_action_semantics",
    ),
    (
        "raes.participant_temporal_semantics",
        "ParticipantTemporalEventPoint",
        "raes_contracts.participant_temporal_vocabulary",
    ),
    ("raes.participant_temporal_semantics", "ParticipantTimeDomain", "raes_contracts.participant_temporal_vocabulary"),
    ("raes.runtime_configuration", "parse_ram", "raes_contracts.runtime_values"),
    ("raes.runtime_filesystem", "RuntimeSensitivityClassification", "raes_contracts.runtime_values"),
    ("raes.semantic_migration", "SDLSemanticMigrationContext", "raes.semantic_migration_context"),
    ("raes_contracts.contracts.experiment_allocation", "AllocationOrdinal", "raes_contracts.contracts.random_stream"),
    (
        "raes_contracts.contracts.experiment_allocation",
        "AllocationStreamAddressModel",
        "raes_contracts.contracts.random_stream",
    ),
    (
        "raes_contracts.contracts.participant_control",
        "ParticipantControlTargetKind",
        "raes_contracts.participant_mixed_control_vocabulary",
    ),
    (
        "raes_contracts.contracts.participant_information_state",
        "ParticipantInformationReconstructionProfileModel",
        "raes_contracts.contracts.participant_information_reconstruction_profiles",
    ),
    (
        "raes_contracts.contracts.participant_information_state",
        "ParticipantInformationSourceContract",
        "raes_contracts.contracts.participant_information_reconstruction_profiles",
    ),
    (
        "raes_contracts.contracts.participant_owner_flow",
        "ParticipantFlowObligationAuthorityCoordinate",
        "raes_contracts.contracts.participant_flow_control_context",
    ),
    (
        "raes_contracts.contracts.participant_owner_flow",
        "ParticipantOwnerFlowSinkResolution",
        "raes_contracts.contracts.participant_flow_control_context",
    ),
    (
        "raes_contracts.participant_binding",
        "ParticipantActionAdmissionRequest",
        "raes_contracts.contracts.participant_action_admission",
    ),
    (
        "raes_contracts.participant_binding",
        "participant_action_admission_request_violations",
        "raes_contracts.contracts.participant_action_admission",
    ),
    (
        "raes_contracts.participant_episode",
        "iter_participant_episode_snapshot_violations",
        "raes_contracts.participant_episode_snapshot",
    ),
    ("raes_contracts.runtime_state", "ExplicitnessClass", "raes_contracts.explicitness"),
    ("raes_contracts.runtime_state", "ExplicitnessProvenance", "raes_contracts.explicitness"),
]


@pytest.mark.parametrize(("former_owner", "name", "owner"), RETIRED)
def test_a_moved_name_is_importable_only_from_its_owner(former_owner: str, name: str, owner: str) -> None:
    assert not hasattr(importlib.import_module(former_owner), name)
    assert hasattr(importlib.import_module(owner), name)
