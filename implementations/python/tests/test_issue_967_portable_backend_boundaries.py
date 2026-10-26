"""Portable backend-boundary checks kept after concrete backend removal (issue #967).

The removed libvirt backend tests also exercised RAES-owned behavior: planner
envelope binding, the shared participant episode machinery, and the run-archive
label rule. These checks keep that behavior covered against the stub target,
which owns no concrete realization.
"""

from __future__ import annotations

from dataclasses import replace
from textwrap import dedent

import pytest
from raes.parser import parse_sdl
from raes_backend_stubs.stubs import create_stub_manifest, create_stub_target
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel, realization_envelope_digest
from raes_operations.run_artifacts import is_valid_run_id_label
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import OperationState
from raes_processor.reference import run_reference_processor
from raes_runtime.control_plane import RuntimeControlPlane
from test_runtime_control_plane import (
    _participant_binding_scenario_yaml,
    _participant_implementation_manifest,
    _participant_implementation_selection,
    _scenario,
    _succeeded_scan_result,
)

_ENVELOPE_SCENARIO = dedent(
    """
    name: envelope-test
    nodes:
      vm:
        type: compute
        resources: {ram: 1 gib, cpu: 1}
    """
)


def test_planner_carries_selected_envelope_identity_to_provisioning_plan():
    manifest = create_stub_manifest(with_realization_envelope=True)

    result = run_reference_processor(parse_sdl(_ENVELOPE_SCENARIO), manifest)

    assert not result.diagnostics
    assert result.execution_plan.provisioning.realization_envelope == manifest.realization_envelope.identity


def test_planner_rejects_a_scenario_outside_the_selected_envelope_membership():
    manifest = create_stub_manifest(with_realization_envelope=True)
    payload = manifest.realization_envelope.model_dump(mode="json")
    payload["expression"]["domains"] = {"name": {"kind": "exact", "value": "different-scenario"}}
    payload["expression"]["bindings"] = [{"path": "name", "scope": "scenario", "posture": "exact", "domain": "name"}]
    payload["digest"] = realization_envelope_digest(payload)
    restricted = BackendRealizationEnvelopeModel.model_validate(payload)

    result = run_reference_processor(parse_sdl(_ENVELOPE_SCENARIO), replace(manifest, realization_envelope=restricted))

    assert "realization-envelope.membership.domain-mismatch" in {diag.code for diag in result.diagnostics}


def test_participant_action_without_a_live_episode_fails_without_history():
    runtime_model = compile_runtime_model(_scenario(_participant_binding_scenario_yaml()))
    behavior = runtime_model.participant_behaviors["participant.behavior.red-agent"]
    action_address = behavior.action_contract_addresses[0]
    control_plane = RuntimeControlPlane(create_stub_target())

    # No initialize_participant_episode(): the binding has no live episode.
    request = ParticipantActionAdmissionRequest(
        participant_address=behavior.address,
        implementation_manifest=_participant_implementation_manifest(),
        implementation_selection=_participant_implementation_selection(behavior.address),
        action_contract_address=action_address,
        observation_boundary_address=behavior.observation_boundary_addresses[0],
        action_instance_id="scan-0001",
        observation_boundary_evidence_refs=("evidence.scan-output",),
        evidence_refs=("evidence.scan-output",),
        action_result=_succeeded_scan_result(
            participant_address=behavior.address,
            episode_id="episode-missing",
            action_instance_id="scan-0001",
            action_contract_address=action_address,
        ),
    )
    receipt = control_plane.admit_participant_action(behavior, request)
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None
    assert status.state == OperationState.FAILED
    assert any("no live episode" in diag.message for diag in status.diagnostics)
    assert control_plane.get_snapshot().snapshot.participant_behavior_history.get(behavior.address, []) == []


@pytest.mark.parametrize("label", ["evidence-run_2026.06.29", "A", "r" * 128])
def test_run_id_label_accepts_safe_filesystem_labels(label):
    assert is_valid_run_id_label(label)


@pytest.mark.parametrize("label", ["../escape", ".hidden", "with/slash", "", "r" * 129, "-leading", "trailing\n"])
def test_run_id_label_rejects_unsafe_filesystem_labels(label):
    assert not is_valid_run_id_label(label)
