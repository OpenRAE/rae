"""Backend conformance tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from raes_backend_protocols.capabilities import (
    BackendCapabilitySet,
    BackendManifest,
    ParticipantFeatureSupport,
    ProvisionerCapabilities,
)
from raes_backend_stubs.stubs import create_stub_components, create_stub_manifest, create_stub_target
from raes_conformance.conformance import (
    BackendCapabilityProfile,
    _semantic_diagnostics,
    profile_for_manifest,
    required_contracts,
    run_fixture_suite,
    run_target_conformance,
)
from raes_contracts.apparatus import ConceptBinding, RealizationSupportDeclaration
from raes_contracts.planning import ChangeAction, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel, RealizationSupportMode
from raes_runtime.registry import RuntimeTarget

API_406_CARRIER_CONTRACTS = {
    "participant-lifecycle-event-v1",
    "participant-observation-envelope-v1",
    "participant-shared-state-record-v1",
}


def test_fixture_suite_passes_for_orchestration_evaluation_profile():
    report = run_fixture_suite(profile=BackendCapabilityProfile.ORCHESTRATION_EVALUATION)

    assert report.passed is True
    assert report.claim.relation_id == "bounded-probe-success"
    assert report.claim.right_carrier_ref == "backend-profile:orchestration-evaluation"
    assert report.claim.quantifier_scope == "finite-cases"
    assert set(report.claim.evidence_refs) == {
        f"conformance-case:{case.contract_name}:{case.name}" for case in report.cases
    }
    assert report.cases
    assert not report.diagnostics
    assert required_contracts(report.profile)


def test_stub_target_realization_claim_fails_closed_until_its_envelope_is_constructive():
    report = run_target_conformance(create_stub_target())

    assert report.profile == BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE
    assert report.passed is False
    constructive = next(case for case in report.cases if case.name == "realization-envelope-constructive")
    assert constructive.outcome == "unsupported"
    assert report.claim.left_carrier_ref.startswith("backend-target:stub@")
    assert ";envelope=sha256:" in report.claim.left_carrier_ref
    assert report.claim.observation_projection_revision == "rev1"
    assert "Does not establish trace equivalence or bisimulation." in report.claim.explicit_non_claims
    assert not report.unsupported_contract_gaps
    assert not report.unsupported_capability_gaps
    feature_cases = [case for case in report.cases if case.capability_feature is not None]
    assert len(feature_cases) == 6
    assert all(case.declared_support_level == "unsupported" for case in feature_cases)
    assert all(case.effective_support_level == "unsupported" for case in feature_cases)
    assert all(
        case.finite_scope and "no unexecuted participant behavior" in case.finite_scope for case in feature_cases
    )
    assert all(case.limitations for case in feature_cases)
    assert all(case.explicit_non_claims for case in feature_cases)
    # RUN-311 finding 4: the live probe must actually drive every
    # participant episode control action and end with a non-empty,
    # consistent snapshot for the conformance participant.
    case_names = {case.name for case in report.cases}
    assert {
        "participant-initialize",
        "participant-reset",
        "participant-terminate",
        "participant-restart",
        "participant-snapshot-consistent",
    }.issubset(case_names)
    for case in report.cases:
        if case.name in {
            "participant-initialize",
            "participant-reset",
            "participant-terminate",
            "participant-restart",
            "participant-snapshot-consistent",
        }:
            assert case.passed, (
                f"Live participant probe case {case.name!r} must succeed for the stub backend; "
                f"diagnostics: {[diag.message for diag in case.diagnostics]}"
            )


def test_target_conformance_records_evidence_backed_exact_policy_support():
    target = create_stub_target()
    manifest = target.manifest
    assert manifest.participant_runtime is not None
    feature = "participant_ingress_admission"
    declaration = ParticipantFeatureSupport(
        feature=feature,
        support_level=ParticipantFeatureSupportLevel.EXACT,
        evidence_refs=("conformance:participant-ingress-admission:case-1",),
    )
    manifest = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            participant_runtime=replace(
                manifest.participant_runtime,
                supported_behavior_features=manifest.participant_runtime.supported_behavior_features | {feature},
                feature_support=(declaration,),
            ),
        ),
    )

    report = run_target_conformance(replace(target, manifest=manifest))

    case = next(case for case in report.cases if case.policy_binding is None and case.capability_feature == feature)
    assert case.passed is True
    assert case.declared_support_level == "exact"
    assert case.effective_support_level == "exact"
    assert case.evidence_refs == ("conformance:participant-ingress-admission:case-1",)
    assert case.finite_scope and "no unexecuted participant behavior" in case.finite_scope
    assert case.explicit_non_claims
    # ASR-535: the manifest declaration is recorded, but declaring exact support
    # no longer conforms on its own. With no participant-policy probe harness
    # driving the declared feature, the report is explicitly unsupported.
    unprobed = next(case for case in report.cases if case.policy_binding is not None)
    assert unprobed.capability_feature == feature
    assert unprobed.outcome == "unsupported"
    assert report.passed is False


def test_full_remote_control_plane_profile_requires_api_406_carriers():
    contracts = required_contracts(BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE)

    assert contracts >= API_406_CARRIER_CONTRACTS
    assert {
        "runtime-snapshot-v1",
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
        "participant-control-occurrence-v1",
        "participant-crossing-occurrence-v1",
    } <= contracts


def test_fixture_suite_validates_api_406_carrier_fixtures(tmp_path: Path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "provisioning-only.json").write_text(
        json.dumps(
            {
                "schema_version": "backend-profile/v1",
                "profile": "provisioning-only",
                "required_contracts": sorted(API_406_CARRIER_CONTRACTS),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_fixture_suite(
        profile=BackendCapabilityProfile.PROVISIONING_ONLY,
        profiles_root=backend_dir,
    )

    assert report.passed is True
    assert {case.contract_name for case in report.cases} == API_406_CARRIER_CONTRACTS
    assert any(case.valid is False for case in report.cases)
    assert all(
        diagnostic.code != "conformance.contract-unknown" for case in report.cases for diagnostic in case.diagnostics
    )


def test_profile_is_inferred_as_full_when_manifest_declares_participant_runtime():
    """RUN-311 — finding 3: a manifest that declares orchestrator,
    evaluator, and participant_runtime must infer the
    ``FULL_REMOTE_CONTROL_PLANE`` profile so the default
    ``run_target_conformance`` path validates the participant-episode
    contract family without requiring callers to override the profile.
    """

    target = create_stub_target()

    assert profile_for_manifest(target.manifest) == BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE


def test_profile_falls_back_to_orchestration_evaluation_without_participant_runtime():
    """A manifest without participant_runtime continues to infer
    ``ORCHESTRATION_EVALUATION`` so existing two-tier backends remain
    compatible.
    """
    from raes_backend_stubs.stubs import create_stub_manifest

    manifest = create_stub_manifest(with_participant_runtime=False)
    assert profile_for_manifest(manifest) == BackendCapabilityProfile.ORCHESTRATION_EVALUATION


def test_live_probe_catches_participant_runtime_that_does_not_populate_snapshot():
    """RUN-311 finding 4: a backend that exposes the participant runtime
    surface but never publishes state/history through the snapshot must
    fail conformance, not silently certify clean.
    """
    from raes_backend_stubs.stubs import (
        StubEvaluator,
        StubOrchestrator,
        StubProvisioner,
        create_stub_manifest,
    )
    from raes_processor.models import ApplyResult

    class _SilentParticipantRuntime:
        """Accepts every action without mutating the snapshot."""

        def initialize(self, request, snapshot):
            return ApplyResult(success=True, snapshot=snapshot)

        def reset(self, request, snapshot):
            return ApplyResult(success=True, snapshot=snapshot)

        def restart(self, request, snapshot):
            return ApplyResult(success=True, snapshot=snapshot)

        def terminate(self, request, snapshot):
            return ApplyResult(success=True, snapshot=snapshot)

        def admit_action(self, request, snapshot):
            return ApplyResult(success=True, snapshot=snapshot)

        def status(self):
            return {}

        def results(self):
            return {}

        def history(self):
            return {}

    manifest = create_stub_manifest()
    target = RuntimeTarget(
        name="silent-participant",
        manifest=manifest,
        provisioner=StubProvisioner(),
        orchestrator=StubOrchestrator(),
        evaluator=StubEvaluator(),
        participant_runtime=_SilentParticipantRuntime(),
    )

    report = run_target_conformance(target)

    assert report.profile == BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE
    assert report.passed is False
    snapshot_case = next(case for case in report.cases if case.name == "participant-snapshot-consistent")
    assert snapshot_case.passed is False
    messages = [diag.message for diag in snapshot_case.diagnostics]
    assert any("exposes no participant_episode_results" in msg for msg in messages)
    assert any("exposes no participant_episode_history" in msg for msg in messages)


def test_target_conformance_rejects_participant_capability_claims_without_contract_evidence():
    manifest = create_stub_manifest()
    weak_manifest = BackendManifest(
        identity=manifest.identity,
        supported_contract_versions=manifest.supported_contract_versions
        - frozenset({"participant-behavior-history-event-stream-v1"}),
        compatibility=manifest.compatibility,
        realization_support=manifest.realization_support,
        concept_bindings=manifest.concept_bindings,
        constraints=manifest.constraints,
        capabilities=manifest.capabilities,
    )
    components = create_stub_components(manifest=weak_manifest)
    target = RuntimeTarget(
        name="weak-participant-claims",
        manifest=weak_manifest,
        provisioner=components.provisioner,
        orchestrator=components.orchestrator,
        evaluator=components.evaluator,
        participant_runtime=components.participant_runtime,
    )

    report = run_target_conformance(target, profile=BackendCapabilityProfile.PROVISIONING_ONLY)

    assert report.passed is False
    assert any(diagnostic.code == "conformance.unsupported-capability-claim" for diagnostic in report.diagnostics)
    assert any("supported_behavior_features.action_contracts" in gap for gap in report.unsupported_capability_gaps)


def test_fixture_suite_passes_for_full_remote_control_plane_profile():
    """RUN-311 — the FULL_REMOTE_CONTROL_PLANE profile now requires the
    participant episode envelope + history event stream fixtures, so running
    the fixture suite at that profile must succeed cleanly and must touch
    every newly-registered contract.
    """

    report = run_fixture_suite(profile=BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE)

    assert report.passed is True
    assert not report.diagnostics
    contract_names = {case.contract_name for case in report.cases}
    assert "participant-episode-state-envelope-v1" in contract_names
    assert "participant-episode-history-event-stream-v1" in contract_names
    assert "participant-behavior-history-event-stream-v1" in contract_names
    assert "participant-control-occurrence-v1" in contract_names
    assert "participant-crossing-occurrence-v1" in contract_names


def test_runtime_snapshot_semantic_diagnostics_reject_invalid_participant_episode_state():
    """RUN-311 — a ``/snapshot`` payload that embeds participant episode state
    that violates the state-machine invariants (e.g. ``status=running`` with a
    terminal reason) must raise a ``conformance.semantic-invalid`` diagnostic.
    Without this guard, invalid RUN-311 data could pass both schema validation
    and conformance.
    """

    snapshot_payload = {
        "schema_version": "runtime-snapshot/v1",
        "entries": {},
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {
            "participant.alice": {
                "state_schema_version": "participant-episode-state/v1",
                "participant_address": "participant.alice",
                "episode_id": "ep-0001",
                "sequence_number": 0,
                "status": "running",
                "terminal_reason": "completed",
                "initialized_at": "2026-04-12T10:00:00Z",
                "updated_at": "2026-04-12T10:00:05Z",
                "terminated_at": None,
                "last_control_action": "initialize",
                "previous_episode_id": None,
            }
        },
        "participant_episode_history": {},
        "metadata": {},
    }

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", snapshot_payload)

    codes = {diag.code for diag in diagnostics}
    assert "conformance.semantic-invalid" in codes
    assert any("participant episode result is invalid" in diag.message for diag in diagnostics)


def test_runtime_snapshot_semantic_diagnostics_reject_invalid_participant_episode_history():
    """RUN-311 — a history stream emitting ``episode_reset`` at
    ``sequence_number=0`` cannot correspond to any valid episode chain.
    Conformance must reject it with a semantic diagnostic.
    """

    snapshot_payload = {
        "schema_version": "runtime-snapshot/v1",
        "entries": {},
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {},
        "participant_episode_history": {
            "participant.alice": [
                {
                    "event_type": "episode_reset",
                    "timestamp": "2026-04-12T10:00:00Z",
                    "participant_address": "participant.alice",
                    "episode_id": "ep-0001",
                    "sequence_number": 0,
                    "terminal_reason": None,
                    "control_action": "reset",
                    "details": {},
                }
            ]
        },
        "metadata": {},
    }

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", snapshot_payload)

    codes = {diag.code for diag in diagnostics}
    assert "conformance.semantic-invalid" in codes
    assert any("must report sequence_number>0" in diag.message for diag in diagnostics)


def test_runtime_snapshot_behavior_history_refs_must_match_snapshot_entries():
    action_address = "participant.action-contract.scan"
    missing_boundary_address = "participant.observation-boundary.missing"
    snapshot_payload = {
        "schema_version": "runtime-snapshot/v1",
        "entries": {
            action_address: {
                "address": action_address,
                "domain": "participant",
                "resource_type": "participant-action-contract",
                "payload": {},
                "ordering_dependencies": [],
                "refresh_dependencies": [],
                "status": "ready",
            }
        },
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {},
        "participant_episode_history": {},
        "participant_behavior_history": {
            "participant.red": [
                {
                    "event_type": "action_attempted",
                    "timestamp": "2026-05-18T18:30:00Z",
                    "participant_address": "participant.red",
                    "episode_id": "episode-1",
                    "action_instance_id": "scan-1",
                    "action_contract_address": action_address,
                    "actor_provenance": "participant:red",
                    "details": {},
                },
                {
                    "event_type": "state_transition_recorded",
                    "timestamp": "2026-05-18T18:30:01Z",
                    "participant_address": "participant.red",
                    "episode_id": "episode-1",
                    "action_instance_id": "scan-1",
                    "action_contract_address": action_address,
                    "state_transition_kind": "knowledge-expanded",
                    "post_state_digest": "sha256:known",
                    "details": {},
                },
                {
                    "event_type": "observation_emitted",
                    "timestamp": "2026-05-18T18:30:02Z",
                    "participant_address": "participant.red",
                    "episode_id": "episode-1",
                    "action_instance_id": "scan-1",
                    "action_contract_address": action_address,
                    "observation_boundary_address": missing_boundary_address,
                    "observation_status": "terminal",
                    "post_state_digest": "sha256:known",
                    "details": {},
                },
            ]
        },
        "metadata": {},
    }

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", snapshot_payload)

    messages = [diagnostic.message for diagnostic in diagnostics]
    assert any("unknown observation_boundary_address" in message for message in messages)
    assert not any("unknown action_contract_address" in message for message in messages)


def test_runtime_snapshot_behavior_history_requires_participant_behavior_binding():
    action_address = "participant.action-contract.scan"
    boundary_address = "participant.observation-boundary.red-view"
    participant_address = "participant.behavior.red-agent"

    def _snapshot_entry(address: str, resource_type: str) -> dict[str, object]:
        return {
            "address": address,
            "domain": "participant",
            "resource_type": resource_type,
            "payload": {},
            "ordering_dependencies": [],
            "refresh_dependencies": [],
            "status": "ready",
        }

    snapshot_payload = {
        "schema_version": "runtime-snapshot/v1",
        "entries": {
            action_address: _snapshot_entry(action_address, "participant-action-contract"),
            boundary_address: _snapshot_entry(boundary_address, "participant-observation-boundary"),
        },
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {},
        "participant_episode_history": {},
        "participant_behavior_history": {
            participant_address: [
                {
                    "event_type": "action_attempted",
                    "timestamp": "2026-05-18T18:30:00Z",
                    "participant_address": participant_address,
                    "episode_id": "episode-1",
                    "action_instance_id": "scan-1",
                    "action_contract_address": action_address,
                    "actor_provenance": participant_address,
                    "details": {},
                },
                {
                    "event_type": "state_transition_recorded",
                    "timestamp": "2026-05-18T18:30:01Z",
                    "participant_address": participant_address,
                    "episode_id": "episode-1",
                    "action_instance_id": "scan-1",
                    "action_contract_address": action_address,
                    "state_transition_kind": "knowledge-expanded",
                    "post_state_digest": "sha256:scan-1",
                    "details": {},
                },
                {
                    "event_type": "observation_emitted",
                    "timestamp": "2026-05-18T18:30:02Z",
                    "participant_address": participant_address,
                    "episode_id": "episode-1",
                    "action_instance_id": "scan-1",
                    "action_contract_address": action_address,
                    "observation_boundary_address": boundary_address,
                    "observation_status": "terminal",
                    "post_state_digest": "sha256:scan-1",
                    "details": {},
                },
            ]
        },
        "metadata": {},
    }

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", snapshot_payload)

    assert any(
        diagnostic.code == "conformance.semantic-invalid"
        and diagnostic.address == f"runtime.snapshot.participant-behavior-history.{participant_address}"
        and "requires a participant.behavior snapshot entry" in diagnostic.message
        for diagnostic in diagnostics
    )


def test_runtime_snapshot_behavior_history_validates_joint_action_order_across_participants():
    action_address = "participant.action-contract.scan"
    boundary_address = "participant.observation-boundary.red-view"

    def _snapshot_entry(address: str, resource_type: str) -> dict[str, object]:
        return {
            "address": address,
            "domain": "participant",
            "resource_type": resource_type,
            "payload": {},
            "ordering_dependencies": [],
            "refresh_dependencies": [],
            "status": "ready",
        }

    def _behavior_history(participant_address: str, action_instance_id: str) -> list[dict[str, object]]:
        return [
            {
                "event_type": "action_attempted",
                "timestamp": "2026-05-18T18:30:00Z",
                "participant_address": participant_address,
                "episode_id": "episode-1",
                "action_instance_id": action_instance_id,
                "action_contract_address": action_address,
                "actor_provenance": f"participant:{participant_address.rsplit('.', 1)[-1]}",
                "joint_action_set_id": "joint-0001",
                "realized_order": 0,
                "interaction_class": "shared_state_change",
                "shared_state_refs": ["nodes.web.services.http"],
                "details": {},
            },
            {
                "event_type": "state_transition_recorded",
                "timestamp": "2026-05-18T18:30:01Z",
                "participant_address": participant_address,
                "episode_id": "episode-1",
                "action_instance_id": action_instance_id,
                "action_contract_address": action_address,
                "state_transition_kind": "knowledge-expanded",
                "post_state_digest": f"sha256:{action_instance_id}",
                "details": {},
            },
            {
                "event_type": "observation_emitted",
                "timestamp": "2026-05-18T18:30:02Z",
                "participant_address": participant_address,
                "episode_id": "episode-1",
                "action_instance_id": action_instance_id,
                "action_contract_address": action_address,
                "observation_boundary_address": boundary_address,
                "observation_status": "terminal",
                "post_state_digest": f"sha256:{action_instance_id}",
                "details": {},
            },
        ]

    snapshot_payload = {
        "schema_version": "runtime-snapshot/v1",
        "entries": {
            action_address: _snapshot_entry(action_address, "participant-action-contract"),
            boundary_address: _snapshot_entry(boundary_address, "participant-observation-boundary"),
        },
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {},
        "participant_episode_history": {},
        "participant_behavior_history": {
            "participant.red": _behavior_history("participant.red", "scan-red-1"),
            "participant.blue": _behavior_history("participant.blue", "scan-blue-1"),
        },
        "metadata": {},
    }

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", snapshot_payload)

    assert any(
        diagnostic.code == "conformance.semantic-invalid"
        and diagnostic.address == "runtime.snapshot.participant-behavior-history.joint-action-set.joint-0001"
        and "realized_order 0 is assigned to multiple action_attempted events" in diagnostic.message
        for diagnostic in diagnostics
    )


def test_runtime_snapshot_behavior_visibility_validation_is_participant_local():
    action_address = "participant.action-contract.scan"
    red_boundary = "participant.observation-boundary.red-view"
    blue_boundary = "participant.observation-boundary.blue-view"
    red_participant = "participant.behavior.red-agent"
    blue_participant = "participant.behavior.blue-agent"

    def _snapshot_entry(address: str, resource_type: str, payload: dict[str, object]) -> dict[str, object]:
        return {
            "address": address,
            "domain": "participant",
            "resource_type": resource_type,
            "payload": payload,
            "ordering_dependencies": [],
            "refresh_dependencies": [],
            "status": "ready",
        }

    def _boundary_payload(transition_id: str, action_instance_id: str) -> dict[str, object]:
        return {
            "name": transition_id,
            "boundary_name": transition_id,
            "projection_basis": "participant-local projection",
            "hidden_refs": ["nodes.web"],
            "observable_refs": [],
            "evidence_refs": ["evidence.scan-output"],
            "disclosed_refs": [],
            "evidence_only_refs": [],
            "discovered_refs": [],
            "inferred_refs": [],
            "concealed_refs": [],
            "deceptive_refs": [],
            "view_transitions": [
                {
                    "transition_id": transition_id,
                    "history_event_type": "observation_emitted",
                    "action_instance_id": action_instance_id,
                    "effective_order": 10,
                }
            ],
            "view_relation_timeline": [
                {
                    "transition_id": "initial",
                    "effective_order": -1,
                    "view_relation": {"nodes.web": "hidden"},
                },
                {
                    "transition_id": transition_id,
                    "effective_order": 10,
                    "view_relation": {"nodes.web": "discovered"},
                },
            ],
            "realized_view_disclosure": "terminal scan result only",
            "spec": {},
        }

    def _participant_payload(boundary_address: str) -> dict[str, object]:
        return {
            "participant_name": "agent",
            "entity_name": "team",
            "action_contract_addresses": [action_address],
            "observation_boundary_addresses": [boundary_address],
            "interpretation_mode": "role-neutral-projection",
            "spec": {},
        }

    def _behavior_history(
        participant_address: str,
        action_instance_id: str,
        boundary_address: str,
    ) -> list[dict[str, object]]:
        return [
            {
                "event_type": "action_attempted",
                "timestamp": "2026-05-18T18:30:00Z",
                "participant_address": participant_address,
                "episode_id": "episode-1",
                "action_instance_id": action_instance_id,
                "action_contract_address": action_address,
                "actor_provenance": participant_address,
                "details": {},
            },
            {
                "event_type": "state_transition_recorded",
                "timestamp": "2026-05-18T18:30:01Z",
                "participant_address": participant_address,
                "episode_id": "episode-1",
                "action_instance_id": action_instance_id,
                "action_contract_address": action_address,
                "state_transition_kind": "knowledge-expanded",
                "post_state_digest": f"sha256:{action_instance_id}",
                "details": {},
            },
            {
                "event_type": "observation_emitted",
                "timestamp": "2026-05-18T18:30:02Z",
                "participant_address": participant_address,
                "episode_id": "episode-1",
                "action_instance_id": action_instance_id,
                "action_contract_address": action_address,
                "observation_boundary_address": boundary_address,
                "observation_status": "terminal",
                "post_state_digest": f"sha256:{action_instance_id}",
                "details": {"visible_refs": ["nodes.web"]},
            },
        ]

    snapshot_payload = {
        "schema_version": "runtime-snapshot/v1",
        "entries": {
            action_address: _snapshot_entry(action_address, "participant-action-contract", {}),
            red_boundary: _snapshot_entry(
                red_boundary, "participant-observation-boundary", _boundary_payload("red-discover", "red-scan")
            ),
            blue_boundary: _snapshot_entry(
                blue_boundary, "participant-observation-boundary", _boundary_payload("blue-discover", "blue-scan")
            ),
            red_participant: _snapshot_entry(
                red_participant, "participant-behavior", _participant_payload(red_boundary)
            ),
            blue_participant: _snapshot_entry(
                blue_participant, "participant-behavior", _participant_payload(blue_boundary)
            ),
        },
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {},
        "participant_episode_history": {},
        "participant_behavior_history": {
            red_participant: _behavior_history(red_participant, "red-scan", red_boundary),
            blue_participant: _behavior_history(blue_participant, "blue-scan", blue_boundary),
        },
        "metadata": {},
    }

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", snapshot_payload)

    assert diagnostics == []


def test_runtime_snapshot_behavior_history_rejects_outer_key_participant_mismatch():
    action_address = "participant.action-contract.scan"
    boundary_address = "participant.observation-boundary.red-view"
    red_participant = "participant.behavior.red-agent"
    blue_participant = "participant.behavior.blue-agent"

    def _snapshot_entry(address: str, resource_type: str, payload: dict[str, object]) -> dict[str, object]:
        return {
            "address": address,
            "domain": "participant",
            "resource_type": resource_type,
            "payload": payload,
            "ordering_dependencies": [],
            "refresh_dependencies": [],
            "status": "ready",
        }

    def _participant_payload() -> dict[str, object]:
        return {
            "participant_name": "red-agent",
            "entity_name": "red-team",
            "action_contract_addresses": [action_address],
            "observation_boundary_addresses": [boundary_address],
            "interpretation_mode": "role-neutral-projection",
            "spec": {},
        }

    def _behavior_history(participant_address: str) -> list[dict[str, object]]:
        return [
            {
                "event_type": "action_attempted",
                "timestamp": "2026-05-18T18:30:00Z",
                "participant_address": participant_address,
                "episode_id": "episode-1",
                "action_instance_id": "scan-1",
                "action_contract_address": action_address,
                "actor_provenance": participant_address,
                "details": {},
            },
            {
                "event_type": "state_transition_recorded",
                "timestamp": "2026-05-18T18:30:01Z",
                "participant_address": participant_address,
                "episode_id": "episode-1",
                "action_instance_id": "scan-1",
                "action_contract_address": action_address,
                "state_transition_kind": "knowledge-expanded",
                "post_state_digest": "sha256:scan-1",
                "details": {},
            },
            {
                "event_type": "observation_emitted",
                "timestamp": "2026-05-18T18:30:02Z",
                "participant_address": participant_address,
                "episode_id": "episode-1",
                "action_instance_id": "scan-1",
                "action_contract_address": action_address,
                "observation_boundary_address": boundary_address,
                "observation_status": "terminal",
                "post_state_digest": "sha256:scan-1",
                "details": {},
            },
        ]

    snapshot_payload = {
        "schema_version": "runtime-snapshot/v1",
        "entries": {
            action_address: _snapshot_entry(action_address, "participant-action-contract", {}),
            boundary_address: _snapshot_entry(boundary_address, "participant-observation-boundary", {}),
            red_participant: _snapshot_entry(red_participant, "participant-behavior", _participant_payload()),
        },
        "orchestration_results": {},
        "orchestration_history": {},
        "evaluation_results": {},
        "evaluation_history": {},
        "participant_episode_results": {},
        "participant_episode_history": {},
        "participant_behavior_history": {
            red_participant: _behavior_history(blue_participant),
        },
        "metadata": {},
    }

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", snapshot_payload)

    mismatch_messages = [
        diagnostic.message
        for diagnostic in diagnostics
        if "does not match inner participant_address" in diagnostic.message
    ]
    expected_message = (
        "participant behavior history event outer key 'participant.behavior.red-agent' "
        "does not match inner participant_address 'participant.behavior.blue-agent'"
    )
    assert mismatch_messages == [expected_message, expected_message, expected_message]


def test_target_conformance_fails_when_declared_contracts_do_not_cover_profile_requirements():
    reference_manifest = create_stub_manifest()
    manifest = BackendManifest(
        identity=reference_manifest.identity,
        supported_contract_versions=frozenset({"backend-manifest-v2"}),
        compatibility=reference_manifest.compatibility,
        realization_support=reference_manifest.realization_support,
        concept_bindings=reference_manifest.concept_bindings,
        constraints=reference_manifest.constraints,
        capabilities=replace(reference_manifest.capabilities, cleanup=None),
    )
    components = create_stub_components(manifest=manifest)
    target = RuntimeTarget(
        name=manifest.name,
        manifest=manifest,
        provisioner=components.provisioner,
        orchestrator=components.orchestrator,
        evaluator=components.evaluator,
        participant_runtime=components.participant_runtime,
    )

    report = run_target_conformance(target)

    # The reference stub manifest now declares participant_runtime, so
    # profile_for_manifest infers the FULL_REMOTE_CONTROL_PLANE profile
    # (RUN-311 finding 3). The contract gap set therefore also covers
    # the participant-episode contracts and the plan contracts that
    # the FULL profile requires.
    assert report.profile == BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE
    assert report.passed is False
    assert set(report.unsupported_contract_gaps) == {
        "evaluation-history-event-stream-v1",
        "evaluation-plan-v1",
        "evaluation-result-envelope-v1",
        "operation-receipt-v1",
        "operation-status-v1",
        "orchestration-plan-v1",
        "participant-behavior-history-event-stream-v1",
        "participant-control-occurrence-v1",
        "participant-crossing-occurrence-v1",
        "participant-episode-history-event-stream-v1",
        "participant-episode-state-envelope-v1",
        "participant-lifecycle-event-v1",
        "participant-observation-envelope-v1",
        "participant-shared-state-record-v1",
        "provisioning-plan-v1",
        "runtime-snapshot-v1",
        "workflow-history-event-stream-v1",
        "workflow-result-envelope-v1",
    }
    assert any(diagnostic.code == "conformance.unsupported-contract-declaration" for diagnostic in report.diagnostics)


def test_required_contracts_authority_is_the_published_backend_profile(tmp_path: Path):
    """ASR-502: the runner reads ``required_contracts(...)`` from the
    published ``contracts/profiles/backend/<profile>.json`` artifact, not
    from a code-side table. Pointing a temporary ``profiles_root`` at a
    synthetic profile must change the result the runner sees — proving
    the published JSON is the single source of truth."""

    synthetic = {
        "profile": "provisioning-only",
        "required_contracts": ["backend-manifest-v2"],
    }
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "provisioning-only.json").write_text(json.dumps(synthetic) + "\n", encoding="utf-8")

    contracts = required_contracts(
        BackendCapabilityProfile.PROVISIONING_ONLY,
        profiles_root=backend_dir,
    )

    assert contracts == frozenset({"backend-manifest-v2"})


def test_run_fixture_suite_uses_profiles_root_override(tmp_path: Path):
    """The fixture suite must accept a ``profiles_root`` override so the
    JSON authority is visible end-to-end, not just at ``required_contracts``."""

    synthetic = {
        "profile": "provisioning-only",
        "required_contracts": ["backend-manifest-v2"],
    }
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "provisioning-only.json").write_text(json.dumps(synthetic) + "\n", encoding="utf-8")

    report = run_fixture_suite(
        profile=BackendCapabilityProfile.PROVISIONING_ONLY,
        profiles_root=backend_dir,
    )

    contract_names = {case.contract_name for case in report.cases}
    assert contract_names == {"backend-manifest-v2"}
    assert report.passed is True


def test_in_code_profile_requirements_table_is_removed():
    """ASR-502 demands a single authority for backend profile contract sets.
    The pre-refactor ``_PROFILE_REQUIREMENTS`` dict was that authority; once
    the runner loads from ``contracts/profiles/backend/*.json`` the dict must
    be gone. This is a structural gate: if a future change re-introduces the
    in-code table, this test fails and the drift is caught before merge."""

    from raes_conformance import conformance as conformance_module

    assert not hasattr(conformance_module, "_PROFILE_REQUIREMENTS")


def test_required_contracts_rejects_unknown_profile_id(tmp_path: Path):
    """A profile id that has no published JSON should produce a clear error,
    not a silent empty contract set.

    ``required_contracts`` is the raising surface; the runner wraps it in
    :func:`_resolve_required_contracts` so the conformance report can stay
    structured. See ``test_run_fixture_suite_reports_profile_load_failure_*``.
    """

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        required_contracts(
            BackendCapabilityProfile.PROVISIONING_ONLY,
            profiles_root=backend_dir,
        )


def test_run_fixture_suite_reports_profile_load_failure_as_diagnostic(tmp_path: Path):
    """ASR-502 + codex review (issue #66, finding 1): if the published
    profile cannot be loaded, the runner must still emit a structured
    :class:`BackendConformanceReport` with a ``conformance.profile-load-failed``
    diagnostic and ``passed=False``, not raise out of the conformance boundary.
    """

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()

    report = run_fixture_suite(
        profile=BackendCapabilityProfile.PROVISIONING_ONLY,
        profiles_root=backend_dir,
    )

    assert report.passed is False
    assert report.cases == ()
    codes = {diag.code for diag in report.diagnostics}
    assert "conformance.profile-load-failed" in codes


def test_run_fixture_suite_reports_malformed_profile_json_as_diagnostic(tmp_path: Path):
    """Malformed profile JSON must surface as a structured diagnostic, not a
    raw JSONDecodeError escape."""

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "provisioning-only.json").write_text("{not valid json", encoding="utf-8")

    report = run_fixture_suite(
        profile=BackendCapabilityProfile.PROVISIONING_ONLY,
        profiles_root=backend_dir,
    )

    assert report.passed is False
    codes = {diag.code for diag in report.diagnostics}
    assert "conformance.profile-load-failed" in codes


def test_run_fixture_suite_reports_schema_invalid_profile_as_diagnostic(tmp_path: Path):
    """A profile whose payload fails closed-world Pydantic validation must
    surface as a structured diagnostic, not a raw ValidationError escape."""

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "provisioning-only.json").write_text(
        json.dumps(
            {"profile": "provisioning-only", "required_contracts": ["definitely-not-a-published-contract-v999"]}
        ),
        encoding="utf-8",
    )

    report = run_fixture_suite(
        profile=BackendCapabilityProfile.PROVISIONING_ONLY,
        profiles_root=backend_dir,
    )

    assert report.passed is False
    codes = {diag.code for diag in report.diagnostics}
    assert "conformance.profile-load-failed" in codes


def test_run_fixture_suite_rejects_swapped_profile_identity(tmp_path: Path):
    """ASR-502 + codex review (issue #66, finding 2): a profile artifact
    whose ``profile`` field does not match the requested profile id must
    fail the load, not silently drive the wrong contract set."""

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "provisioning-only.json").write_text(
        json.dumps(
            {
                "profile": "full-remote-control-plane",
                "required_contracts": ["backend-manifest-v2"],
            }
        ),
        encoding="utf-8",
    )

    report = run_fixture_suite(
        profile=BackendCapabilityProfile.PROVISIONING_ONLY,
        profiles_root=backend_dir,
    )

    assert report.passed is False
    codes = {diag.code for diag in report.diagnostics}
    assert "conformance.profile-load-failed" in codes
    assert any("full-remote-control-plane" in diag.message for diag in report.diagnostics)


def test_run_target_conformance_surfaces_profile_load_failure(tmp_path: Path):
    """The target-conformance entry point must also convert profile-load
    failures into structured diagnostics rather than raise — the boundary
    applies to every public conformance surface.

    Codex review (issue #66, finding 1 of cycle 2): a failed profile load is
    a hard prerequisite, so the runner must NOT proceed to ``_live_target_cases``
    (which would submit provisioning/orchestration/evaluation actions against
    the target). The report must therefore contain no live probe cases.
    """

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()

    report = run_target_conformance(create_stub_target(), profiles_root=backend_dir)

    assert report.passed is False
    codes = {diag.code for diag in report.diagnostics}
    assert "conformance.profile-load-failed" in codes
    case_names = {case.name for case in report.cases}
    assert "target-manifest" not in case_names
    assert "target-snapshot" not in case_names
    assert "participant-initialize" not in case_names


def test_run_target_conformance_refuses_unknown_profile_id(tmp_path: Path):
    """ASR-502 + codex review (issue #66, finding 2 of cycle 4): target
    conformance enforces runtime-surface gates (orchestrator/evaluator/
    participant_runtime). Those gates depend on knowing the profile's
    runtime-surface contract; an unknown profile id has no such authority.
    The runner must refuse with a structured
    ``conformance.profile-runtime-surface-unknown`` diagnostic instead of
    silently certifying a target that's missing every required role."""

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    (backend_dir / "future-control-plane.json").write_text(
        json.dumps(
            {
                "schema_version": "backend-profile/v1",
                "profile": "future-control-plane",
                "required_contracts": ["backend-manifest-v2"],
            }
        ),
        encoding="utf-8",
    )

    report = run_target_conformance(
        create_stub_target(),
        profile="future-control-plane",
        profiles_root=backend_dir,
    )

    assert report.passed is False
    codes = {diag.code for diag in report.diagnostics}
    assert "conformance.profile-runtime-surface-unknown" in codes
    case_names = {case.name for case in report.cases}
    assert "target-manifest" not in case_names
    assert "target-snapshot" not in case_names


def test_run_fixture_suite_path_traversal_id_surfaces_as_load_diagnostic(tmp_path: Path):
    """ASR-502 + codex review (issue #66, cycle 4 security finding): a profile
    id that contains path separators must be rejected at the loader and
    surface as a structured ``conformance.profile-load-failed`` diagnostic,
    not escape the profile root."""

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()

    report = run_fixture_suite(profile="../etc/passwd", profiles_root=backend_dir)

    assert report.passed is False
    codes = {diag.code for diag in report.diagnostics}
    assert "conformance.profile-load-failed" in codes


def test_run_fixture_suite_load_failure_diagnostic_does_not_echo_input(tmp_path: Path):
    """Codex review (issue #66, cycle 4 security finding, sanitization arm):
    the profile-load diagnostic must not echo the rejected JSON payload
    verbatim. A Pydantic ``ValidationError`` carries the rejected input;
    rendering it through ``str(exc)`` would turn a malformed-profile failure
    into a file-content disclosure when the loader is wrapped behind a
    less-trusted boundary."""

    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    sentinel = "PRIVATE-DATA-SENTINEL-9D8A"
    (backend_dir / "provisioning-only.json").write_text(
        json.dumps(
            {
                "schema_version": "backend-profile/v1",
                "profile": "provisioning-only",
                "required_contracts": [sentinel],
            }
        ),
        encoding="utf-8",
    )

    report = run_fixture_suite(
        profile=BackendCapabilityProfile.PROVISIONING_ONLY,
        profiles_root=backend_dir,
    )

    assert report.passed is False
    for diag in report.diagnostics:
        assert sentinel not in diag.message, "profile-load diagnostic must not echo the rejected input value verbatim"


# --- Issue #663: caller-supplied reference scenario for target conformance ---
#
# A fixed-topology emulation backend (e.g. APTL) declares generic provisioning
# capability but only realizes nodes that map to its pre-built environment. The
# probe must not fail it for refusing an arbitrary hard-coded scenario; it must
# let the backend supply a scenario it can realize, held to full realization.
# Temporary runner-parameter bridge, superseded by #667/#668.

_FIXED_TOPOLOGY_PREBUILT_NODE = "prebuilt"


def _fixed_topology_manifest() -> BackendManifest:
    """Provisioning-only manifest declaring generic vm/linux support.

    Both the default conformance scenario (node ``vm``) and a supplied scenario
    (node ``prebuilt``) plan cleanly against it; the difference is purely at
    realization, exercised by ``_FixedTopologyProvisioner``.
    """

    return BackendManifest(
        name="fixed-topology",
        version="1.0.0",
        realization_envelope=create_stub_manifest(with_realization_envelope=True).realization_envelope,
        supported_contract_versions=frozenset(
            {
                "backend-manifest-v2",
                "operation-receipt-v1",
                "operation-status-v1",
                "runtime-snapshot-v1",
                "realization-envelope-v1",
            }
        ),
        compatible_processors=frozenset({"raes-reference-processor"}),
        concept_bindings=(
            ConceptBinding(scope="capabilities.provisioner.supported_node_types", family="assets"),
            ConceptBinding(scope="capabilities.provisioner.supported_os_families", family="assets"),
        ),
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.CONSTRAINED,
                supported_constraint_kinds=frozenset({"node-type", "os-family", "compute-substrate"}),
                supported_exact_requirement_kinds=frozenset({"declared-capability-match"}),
                disclosure_kinds=frozenset({"backend-manifest-v2", "runtime-snapshot-v1", "operation-status-v1"}),
            ),
        ),
        capabilities=BackendCapabilitySet(
            provisioner=ProvisionerCapabilities(
                name="fixed-topology-provisioner",
                supported_node_types=frozenset({"compute"}),
                supported_os_families=frozenset({"linux"}),
            ),
        ),
    )


class _FixedTopologyProvisioner:
    """Realizes only the one pre-built node; fails fast on anything else.

    Mirrors a fixed-topology emulation backend that maps RAES nodes onto a
    pre-built environment and refuses nodes it has no realization for.
    """

    def validate(self, plan) -> list:
        return []

    def apply(self, plan, snapshot: RuntimeSnapshot) -> ApplyResult:
        node_ops = [op for op in plan.operations if op.resource_type == "node" and op.action != ChangeAction.DELETE]
        unmapped = [op for op in node_ops if op.payload.get("node_name") != _FIXED_TOPOLOGY_PREBUILT_NODE]
        if not node_ops or unmapped:
            return ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=("fixed-topology backend has no realization for the requested node(s)",),
            )
        entries = dict(snapshot.entries)
        changed: list[str] = []
        for op in plan.operations:
            entries[op.address] = SnapshotEntry(
                address=op.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=op.resource_type,
                payload=op.payload,
                ordering_dependencies=op.ordering_dependencies,
                refresh_dependencies=op.refresh_dependencies,
                status="applied",
            )
            changed.append(op.address)
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries, realization_envelope=_fixed_topology_manifest().realization_envelope.identity
            ),
            changed_addresses=changed,
        )


class _NoopProvisioner(_FixedTopologyProvisioner):
    """Accepts everything but realizes nothing (success-returning no-op)."""

    def apply(self, plan, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(success=True, snapshot=snapshot, changed_addresses=[])


def _reference_scenario(node_name: str) -> str:
    return f"""
name: conformance
nodes:
  {node_name}:
    type: compute
    resources: {{ram: 1 gib, cpu: 1}}
    conditions: {{health: ops}}
    roles: {{ops: operator}}
conditions:
  health: {{command: /bin/true, interval: 15}}
propositions:
  health:
    description: The governed node has declared runtime state.
    subjects: [nodes.{node_name}]
    basis: declared_state
    predicate: {{kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}}
assertions:
  health: {{proposition: health, role: postcondition, polarity: positive}}
entities:
  blue: {{role: blue}}
objectives:
  validate: {{entity: blue, success: {{assertions: [health]}}}}
workflows:
  response:
    start: run
    steps:
      run: {{type: objective, objective: validate, on_success: finish}}
      finish: {{type: end}}
"""


def _fixed_topology_target(provisioner=None) -> RuntimeTarget:
    return RuntimeTarget(
        name="fixed-topology",
        manifest=_fixed_topology_manifest(),
        provisioner=provisioner or _FixedTopologyProvisioner(),
    )


def test_target_conformance_default_scenario_fails_fixed_topology_backend():
    """Issue #663: the hard-coded default scenario is not universally realizable.

    A fixed-topology backend that cannot realize the generic ``vm`` node fails
    the default probe — the reported false negative the reference-scenario seam
    exists to correct.
    """

    report = run_target_conformance(_fixed_topology_target())

    assert report.profile == BackendCapabilityProfile.PROVISIONING_ONLY
    assert report.passed is False
    provisioning = next(case for case in report.cases if case.name == "target-provisioning")
    assert provisioning.passed is False
    assert any(diag.code == "conformance.provisioning-failed" for diag in provisioning.diagnostics)


def test_target_conformance_accepts_supplied_reference_scenario():
    """Issue #663: a backend-supplied scenario it can realize passes, and full
    provisioning (issue #606 mutation guard) is still required and met.

    This fixture supplies no independent realization-honesty harness; successful
    provisioning must not upgrade the inherited non-constructive envelope claim.
    """

    report = run_target_conformance(
        _fixed_topology_target(),
        reference_scenario=_reference_scenario(_FIXED_TOPOLOGY_PREBUILT_NODE),
    )

    provisioning = next(case for case in report.cases if case.name == "target-provisioning")
    assert provisioning.passed is True
    snapshot_case = next(case for case in report.cases if case.name == "target-snapshot")
    assert snapshot_case.passed is True
    assert report.passed is False
    failures = [case for case in report.cases if not case.passed]
    assert [case.name for case in failures] == ["realization-envelope-constructive"]
    assert failures[0].outcome == "unsupported"


def test_supplied_reference_scenario_still_enforces_mutation_guard():
    """The reference-scenario seam does not weaken the realization bar: a
    success-returning no-op provisioner still fails on a supplied scenario."""

    report = run_target_conformance(
        _fixed_topology_target(provisioner=_NoopProvisioner()),
        reference_scenario=_reference_scenario(_FIXED_TOPOLOGY_PREBUILT_NODE),
    )

    assert report.passed is False
    provisioning = next(case for case in report.cases if case.name == "target-provisioning")
    snapshot_case = next(case for case in report.cases if case.name == "target-snapshot")
    assert provisioning.passed is False
    assert snapshot_case.passed is False
    codes = {diag.code for case in report.cases for diag in case.diagnostics}
    assert "conformance.snapshot-not-mutated" in codes
