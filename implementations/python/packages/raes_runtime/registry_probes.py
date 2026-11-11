"""Typed probe values used to inspect runtime-target method signatures."""

from raes_contracts.contracts import (
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest


def sample_participant_action_admission_request() -> ParticipantActionAdmissionRequest:
    """Build a valid autonomous-action request for registry shape checks."""

    manifest = ParticipantImplementationManifestModel.model_validate(
        {
            "schema_version": "participant-implementation-manifest/v1",
            "identity": {"name": "registry-shape-probe", "version": "1.0.0"},
            "implementation_kind": "agent",
            "supported_contract_versions": [
                "participant-implementation-manifest-v1",
                "participant-implementation-provenance-v1",
                "participant-episode-state-envelope-v1",
                "participant-behavior-history-event-stream-v1",
            ],
            "compatibility": {"participant_runtimes": ["registry"], "processors": [], "backends": []},
            "concept_bindings": [
                {"scope": "implementation_kind", "family": "apparatus-declarations"},
                {
                    "scope": "capabilities.supported_participant_contracts",
                    "family": "apparatus-declarations",
                },
                {
                    "scope": "capabilities.supported_decision_surface_modes",
                    "family": "apparatus-declarations",
                },
                {
                    "scope": "capabilities.tool_affordance_expectations",
                    "family": "tools-and-artifacts",
                },
                {"scope": "capabilities.exposure_policy_kinds", "family": "provenance-and-evidence"},
            ],
            "capabilities": {
                "supported_participant_contracts": [
                    "participant-episode-state-envelope-v1",
                    "participant-behavior-history-event-stream-v1",
                ],
                "supported_decision_surface_modes": ["policy-directed"],
                "tool_affordance_expectations": ["shell"],
                "exposure_policy_kinds": ["task-statement"],
            },
        }
    )
    selection = ParticipantImplementationSelectionModel.model_validate(
        {
            "participant_address": "participant.behavior.registry-probe",
            "implementation_identity": {"name": "registry-shape-probe", "version": "1.0.0"},
            "manifest_ref": "registry://participant-implementation-manifest",
            "manifest_digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "selected_decision_surface_mode": "policy-directed",
            "participant_contract_versions": [
                "participant-episode-state-envelope-v1",
                "participant-behavior-history-event-stream-v1",
            ],
            "exposure_policy": {
                "policy_id": "registry-shape-probe-policy",
                "exposure_policy_kinds": ["task-statement"],
                "disclosed_refs": ["scenario.registry-probe"],
            },
        }
    )
    return ParticipantActionAdmissionRequest(
        participant_address="participant.behavior.registry-probe",
        action_contract_address="participant.action-contract.registry-probe",
        observation_boundary_address="participant.observation-boundary.registry-probe",
        action_instance_id="registry-probe-action",
        implementation_manifest=manifest,
        implementation_selection=selection,
    )
