"""Reference runtime control-plane tests."""

from __future__ import annotations

import textwrap
from dataclasses import replace
from typing import Any

import pytest
from raes import parse_sdl
from raes_backend_protocols.capabilities import BackendManifest
from raes_backend_stubs.stubs import create_stub_components, create_stub_manifest, create_stub_target
from raes_contracts.contracts import (
    ParticipantActionResultModel,
    ParticipantContextViewModel,
    ParticipantHistoryViewModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantStatusViewModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.planning import (
    ChangeAction,
    ProvisioningPlan,
    ProvisionOp,
    RealizationAuthorityMode,
    RealizationResolutionSource,
    ResolvedRealizationAuthority,
)
from raes_contracts.runtime_state import OperationAdmissionContext, OperationKind, RuntimeSnapshot, SnapshotEntry
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import (
    OperationReceipt,
    OperationState,
    OperationStatus,
    ParticipantEpisodeTerminalReason,
    RuntimeDomain,
    iter_participant_behavior_history_violations,
    iter_participant_episode_snapshot_violations,
)
from raes_processor.planner import plan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import ControlPlaneOperationRecord
from raes_runtime.registry import RuntimeTarget


def _scenario(yaml_str: str):
    return parse_sdl(textwrap.dedent(yaml_str))


def _participant_binding_scenario_yaml() -> str:
    return """
name: participant-binding
nodes:
  web:
    type: compute
    resources: {ram: 1 GiB, cpu: 1}
    services: [{port: 80, name: http}]
entities:
  red-team:
    role: red
action_contracts:
  scan:
    semantic_version: 1.0.0
    lifecycle_state: active
    behavioral_granularity: atomic
    procedure_basis: governed service discovery
    realization_profile: backend-declared
    fidelity_claim: records participant discovery intent and terminal observation
    preconditions:
      - precondition_id: authority-in-scope
        precondition_class: authority
        description: red participant is authorized to scan the web service
    effects:
      - effect_id: terminal-scan-observation
        effect_class: observation_effect
        description: terminal scan observation
        evidence_refs: [evidence.scan-output]
    failure_classes: [backend_error, unknown]
observation_boundaries:
  red-view:
    projection_basis: participant-local projection over observed services
    evidence_refs: [evidence.scan-output]
    redaction_policy: hidden refs never project without explicit disclosure
    latency_profile: terminal observation emitted after state transition commit
agents:
  red-agent:
    entity: red-team
    actions: [scan]
    observation_boundaries: [red-view]
"""


def _participant_implementation_manifest() -> ParticipantImplementationManifestModel:
    return ParticipantImplementationManifestModel.model_validate(
        {
            "schema_version": "participant-implementation-manifest/v1",
            "identity": {"name": "reference-red-agent", "version": "1.0.0"},
            "implementation_kind": "agent",
            "supported_contract_versions": [
                "participant-implementation-manifest-v1",
                "participant-implementation-provenance-v1",
                "participant-episode-state-envelope-v1",
                "participant-episode-history-event-stream-v1",
                "participant-behavior-history-event-stream-v1",
            ],
            "compatibility": {
                "participant_runtimes": ["stub-participant-runtime"],
                "processors": ["raes-reference-processor"],
                "backends": ["stub"],
            },
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
            "constraints": {"max_parallel_episodes": "1"},
            "capabilities": {
                "supported_participant_contracts": [
                    "participant-episode-state-envelope-v1",
                    "participant-episode-history-event-stream-v1",
                    "participant-behavior-history-event-stream-v1",
                ],
                "supported_decision_surface_modes": ["autonomous", "policy-directed"],
                "tool_affordance_expectations": ["shell", "http-api"],
                "exposure_policy_kinds": ["task-statement", "observation-stream"],
            },
        }
    )


def _participant_implementation_selection(participant_address: str) -> ParticipantImplementationSelectionModel:
    return ParticipantImplementationSelectionModel.model_validate(
        {
            "participant_address": participant_address,
            "implementation_identity": {"name": "reference-red-agent", "version": "1.0.0"},
            "manifest_ref": "contracts/fixtures/participant-implementation-manifest/reference.json",
            "manifest_digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
            "selected_decision_surface_mode": "policy-directed",
            "participant_contract_versions": [
                "participant-episode-state-envelope-v1",
                "participant-behavior-history-event-stream-v1",
            ],
            "exposure_policy": {
                "policy_id": "red-agent-policy",
                "policy_version": "1.0.0",
                "policy_digest": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
                "exposure_policy_kinds": ["task-statement", "observation-stream"],
                "disclosed_refs": ["scenario.tasks.red"],
                "withheld_refs": ["scenario.hidden.answer-key"],
                "tool_affordance_refs": ["tool.shell"],
                "visibility_scope_refs": ["participants.red.visible"],
            },
        }
    )


def _succeeded_scan_result(
    *,
    participant_address: str,
    episode_id: str,
    action_instance_id: str,
    action_contract_address: str,
) -> ParticipantActionResultModel:
    return ParticipantActionResultModel.model_validate(
        {
            "status": "succeeded",
            "participant_address": participant_address,
            "episode_id": episode_id,
            "action_instance_id": action_instance_id,
            "action_contract_address": action_contract_address,
            "observation_point": f"{action_instance_id}:terminal-observation",
            "preconditions": [
                {
                    "precondition_id": "authority-in-scope",
                    "precondition_class": "authority",
                    "status": "satisfied",
                    "participant_address": participant_address,
                    "episode_id": episode_id,
                    "action_contract_address": action_contract_address,
                    "observation_point": f"{action_instance_id}:precondition-authority",
                }
            ],
            "effects": [
                {
                    "effect_id": "terminal-scan-observation",
                    "effect_class": "observation_effect",
                    "description": "terminal scan observation",
                    "evidence_refs": ["evidence.scan-output"],
                }
            ],
            "observations": [f"{action_instance_id}:terminal-observation"],
            "evidence_refs": ["evidence.scan-output"],
        }
    )


def _episode_state(participant_address: str, episode_id: str) -> dict[str, object]:
    return {
        "state_schema_version": "participant-episode-state/v1",
        "participant_address": participant_address,
        "episode_id": episode_id,
        "sequence_number": 0,
        "status": "running",
        "terminal_reason": None,
        "initialized_at": "2026-06-05T10:00:00Z",
        "updated_at": "2026-06-05T10:00:00Z",
        "terminated_at": None,
        "last_control_action": "initialize",
        "previous_episode_id": None,
    }


def _episode_history_event(participant_address: str, episode_id: str) -> dict[str, object]:
    return {
        "event_type": "episode_running",
        "timestamp": "2026-06-05T10:00:00Z",
        "participant_address": participant_address,
        "episode_id": episode_id,
        "sequence_number": 0,
        "terminal_reason": None,
        "control_action": None,
        "details": {},
    }


def _behavior_history_event(participant_address: str, episode_id: str) -> dict[str, object]:
    return {
        "event_type": "action_attempted",
        "timestamp": "2026-06-05T10:00:01Z",
        "participant_address": participant_address,
        "episode_id": episode_id,
        "action_instance_id": f"{participant_address}.action-1",
        "details": {},
    }


def _participant_operation_record(operation_id: str, participant_address: str) -> ControlPlaneOperationRecord:
    submitted_at = "2026-06-05T10:00:00Z"
    context = OperationAdmissionContext(
        actor_id="embedded-process",
        authorization_scope=("process:trusted-embedder",),
        target_scope="target:stub",
        run_scope="run:test",
        operation_kind=OperationKind.PARTICIPANT_ACTION,
        request_commitment=f"sha256:{'a' * 64}",
    )
    return ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at=submitted_at,
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            state=OperationState.RUNNING,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=context,
            changed_addresses=[participant_address],
        ),
    )


def _submit_registered(control_plane: RuntimeControlPlane, domain: str, submitted_plan):
    """Forge component authorization where planner validity is explicitly out of scope."""

    authorization_plan = plan(
        compile_runtime_model(_scenario("name: phase-authorization")),
        control_plane._target.manifest,
        target_name=control_plane.target_name,
    )
    authorization_plan = replace(authorization_plan, **{domain: submitted_plan})
    control_plane.register_planner_produced_plan(authorization_plan)
    return getattr(control_plane, f"submit_{domain}")(submitted_plan)


def test_control_plane_submits_provisioning_and_updates_snapshot():
    scenario = _scenario("""
name: provision
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
""")
    execution_plan = plan(compile_runtime_model(scenario), create_stub_target().manifest)
    control_plane = RuntimeControlPlane(create_stub_target())

    receipt = _submit_registered(control_plane, "provisioning", execution_plan.provisioning)
    status = control_plane.get_operation(receipt.operation_id)
    snapshot = control_plane.get_snapshot()

    assert receipt.accepted is True
    assert receipt.domain == RuntimeDomain.PROVISIONING
    assert status is not None
    assert status.state == OperationState.SUCCEEDED
    assert snapshot.snapshot.entries


def test_control_plane_rejects_dependency_outside_plan_and_snapshot() -> None:
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.node.vm",
                resource_type="node",
                payload={},
                ordering_dependencies=("provision.network.missing",),
            )
        ]
    )
    control_plane = RuntimeControlPlane(create_stub_target())

    receipt = _submit_registered(control_plane, "provisioning", plan)

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == ["runtime.plan-dependency-unresolved"]


def test_control_plane_rejects_snapshot_resource_identity_disagreement() -> None:
    address = "provision.node.vm"
    snapshot = RuntimeSnapshot(
        entries={
            address: SnapshotEntry(
                address=address,
                domain=RuntimeDomain.EVALUATION,
                resource_type="objective",
                payload={},
            )
        }
    )
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.UPDATE,
                address=address,
                resource_type="node",
                payload={},
            )
        ]
    )
    control_plane = RuntimeControlPlane(create_stub_target(), initial_snapshot=snapshot)

    receipt = _submit_registered(control_plane, "provisioning", plan)

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == ["runtime.plan-resource-incoherent"]


class _CountingProvisioner:
    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.validate_calls = 0
        self.apply_calls = 0

    def validate(self, provisioning_plan: ProvisioningPlan):
        self.validate_calls += 1
        return self._delegate.validate(provisioning_plan)

    def apply(self, provisioning_plan: ProvisioningPlan, snapshot: RuntimeSnapshot):
        self.apply_calls += 1
        return self._delegate.apply(provisioning_plan, snapshot)


def _generated_artifact_spec(generator: str = "rendered_config") -> dict[str, Any]:
    consumer: dict[str, Any] = {
        "node": "vm",
        "mount_destination": "/etc/config.yml",
        "access_mode": "read_only",
    }
    if generator == "ssh_key_bundle":
        consumer["selected_outputs"] = ["config"]
    return {
        "generator": generator,
        "lifecycle": "regenerate_on_change",
        "provenance": "config.yml",
        "outputs": [
            {
                "name": "config",
                "path": "config.yml",
                "sensitivity": "restricted",
                "disposition": "consumer_selected",
            }
        ],
        "consumers": [consumer],
    }


def _stateful_plan(
    resource_type: str = "generated-artifact",
    *,
    spec: dict[str, Any] | None = None,
) -> ProvisioningPlan:
    address = f"provision.{resource_type}.config"
    requirement_kind = "generated-artifact" if resource_type == "generated-artifact" else "persistent-volume"
    field_section = "generated_artifacts" if resource_type == "generated-artifact" else "persistent_volumes"
    manifest = create_stub_manifest()
    return ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address=address,
                resource_type=resource_type,
                payload={"spec": spec if spec is not None else _generated_artifact_spec()},
            )
        ],
        realization_authority=(
            ResolvedRealizationAuthority(
                address=address,
                field_path=f"{field_section}.config",
                domain="runtime-realization",
                requirement_kind=requirement_kind,
                payload_pointer="/spec",
                mode=RealizationAuthorityMode.EXACT,
                source=RealizationResolutionSource.PROCESSOR_DERIVED,
            ),
        ),
        realization_envelope=manifest.realization_envelope.identity if manifest.realization_envelope else None,
    )


def _target_with_manifest(manifest: BackendManifest) -> tuple[RuntimeTarget, _CountingProvisioner]:
    base = create_stub_target()
    provisioner = _CountingProvisioner(base.provisioner)
    return (
        RuntimeTarget(
            name=base.name,
            manifest=manifest,
            provisioner=provisioner,
            orchestrator=base.orchestrator,
            evaluator=base.evaluator,
            participant_runtime=base.participant_runtime,
        ),
        provisioner,
    )


@pytest.mark.parametrize(
    ("resource_type", "capability_attribute", "expected_code"),
    [
        (
            "generated-artifact",
            "supports_generated_artifacts",
            "provisioner.generated-artifacts-unsupported",
        ),
        (
            "persistent-volume",
            "supports_persistent_volumes",
            "provisioner.persistent-volumes-unsupported",
        ),
    ],
)
def test_control_plane_rejects_stateful_kind_before_backend_calls(
    resource_type: str,
    capability_attribute: str,
    expected_code: str,
) -> None:
    manifest = create_stub_manifest()
    capability_changes: dict[str, Any] = {capability_attribute: False}
    if capability_attribute == "supports_generated_artifacts":
        capability_changes["supported_generated_artifact_kinds"] = frozenset()
        capability_changes["supported_generated_artifact_delivery_modes"] = frozenset()
    unsupported = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            provisioner=replace(manifest.provisioner, **capability_changes),
        ),
    )
    target, provisioner = _target_with_manifest(unsupported)

    control_plane = RuntimeControlPlane(target)
    receipt = _submit_registered(control_plane, "provisioning", _stateful_plan(resource_type))

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == [expected_code]
    assert provisioner.validate_calls == 0
    assert provisioner.apply_calls == 0


def test_control_plane_rejects_stateful_plan_without_exact_realization_support() -> None:
    manifest = create_stub_manifest()
    support = replace(
        manifest.realization_support[0],
        supported_exact_requirement_kinds=frozenset(),
    )
    target, provisioner = _target_with_manifest(replace(manifest, realization_support=(support,)))

    control_plane = RuntimeControlPlane(target)
    receipt = _submit_registered(control_plane, "provisioning", _stateful_plan())

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == ["realization.unsupported-exact-requirement"]
    assert provisioner.validate_calls == 0
    assert provisioner.apply_calls == 0


def test_control_plane_rejects_malformed_generated_artifact_before_backend_calls() -> None:
    target, provisioner = _target_with_manifest(create_stub_manifest())

    control_plane = RuntimeControlPlane(target)
    receipt = _submit_registered(
        control_plane,
        "provisioning",
        _stateful_plan(spec={"provenance": "config.yml"}),
    )

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == ["provisioner.generated-artifact-invalid"]
    assert provisioner.validate_calls == 0
    assert provisioner.apply_calls == 0


def test_control_plane_rejects_explicitly_empty_generated_artifact_selection() -> None:
    target, provisioner = _target_with_manifest(create_stub_manifest())
    spec = _generated_artifact_spec()
    spec["consumers"][0]["selected_outputs"] = []

    control_plane = RuntimeControlPlane(target)
    receipt = _submit_registered(control_plane, "provisioning", _stateful_plan(spec=spec))

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == ["provisioner.generated-artifact-invalid"]
    assert provisioner.validate_calls == 0
    assert provisioner.apply_calls == 0


def test_control_plane_rejects_mismatched_generated_artifact_consumer_target() -> None:
    target, provisioner = _target_with_manifest(create_stub_manifest())
    spec = _generated_artifact_spec()
    spec["consumers"][0]["target_address"] = "provision.node.somewhere-else"

    control_plane = RuntimeControlPlane(target)
    receipt = _submit_registered(control_plane, "provisioning", _stateful_plan(spec=spec))

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == ["provisioner.generated-artifact-invalid"]
    assert provisioner.validate_calls == 0
    assert provisioner.apply_calls == 0


def test_control_plane_rejects_unclaimed_generated_artifact_kind_before_backend_calls() -> None:
    manifest = create_stub_manifest()
    unsupported = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            provisioner=replace(
                manifest.provisioner,
                supported_generated_artifact_kinds=frozenset({"certificate_bundle", "rendered_config"}),
            ),
        ),
    )
    target, provisioner = _target_with_manifest(unsupported)

    control_plane = RuntimeControlPlane(target)
    receipt = _submit_registered(
        control_plane,
        "provisioning",
        _stateful_plan(spec=_generated_artifact_spec("ssh_key_bundle")),
    )

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == [
        "provisioner.unsupported-generated-artifact-kind"
    ]
    assert provisioner.validate_calls == 0
    assert provisioner.apply_calls == 0


def test_control_plane_rejects_exact_support_from_another_domain() -> None:
    manifest = create_stub_manifest()
    support = replace(manifest.realization_support[0], domain="orchestration")
    target, provisioner = _target_with_manifest(replace(manifest, realization_support=(support,)))

    control_plane = RuntimeControlPlane(target)
    receipt = _submit_registered(control_plane, "provisioning", _stateful_plan())

    assert receipt.accepted is False
    assert [diagnostic.code for diagnostic in receipt.diagnostics] == ["realization.unsupported-exact-requirement"]
    assert provisioner.validate_calls == 0
    assert provisioner.apply_calls == 0


def test_control_plane_dispatches_stateful_plan_after_both_admission_gates() -> None:
    target, provisioner = _target_with_manifest(create_stub_manifest())

    control_plane = RuntimeControlPlane(target)
    receipt = _submit_registered(control_plane, "provisioning", _stateful_plan())

    assert receipt.accepted is True
    assert provisioner.validate_calls == 1
    assert provisioner.apply_calls == 1


def test_control_plane_submits_orchestration_with_portable_workflow_state():
    scenario = _scenario("""
name: workflow
nodes:
  vm:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    conditions: {health: ops}
    roles: {ops: operator}
conditions:
  health: {command: /bin/true, interval: 15}
propositions:
  health:
    description: The governed VM has declared runtime state.
    subjects: [nodes.vm]
    basis: declared_state
    predicate: {kind: presence, property: runtime, semantic_ref: urn:raes:declared-property:runtime, operator: exists}
assertions:
  health: {proposition: health, role: postcondition, polarity: positive}
entities:
  blue: {role: blue}
objectives:
  validate:
    entity: blue
    success: {assertions: [health]}
workflows:
  response:
    start: run
    steps:
      run:
        type: objective
        objective: validate
        on_success: finish
      finish: {type: end}
""")
    target = create_stub_target()
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane = RuntimeControlPlane(target)

    provisioning_receipt = _submit_registered(control_plane, "provisioning", execution_plan.provisioning)
    assert provisioning_receipt.accepted is True
    evaluation_receipt = _submit_registered(control_plane, "evaluation", execution_plan.evaluation)
    assert evaluation_receipt.accepted is True
    receipt = _submit_registered(control_plane, "orchestration", execution_plan.orchestration)
    status = control_plane.get_operation(receipt.operation_id)
    snapshot = control_plane.get_snapshot()

    assert receipt.accepted is True
    assert status is not None
    assert status.state == OperationState.SUCCEEDED
    workflow_result = next(iter(snapshot.snapshot.orchestration_results.values()))
    assert workflow_result["workflow_status"] == "running"
    assert "run_id" in workflow_result
    assert snapshot.snapshot.orchestration_history


class TestParticipantEpisodeControlPlane:
    """RUN-311 — runtime-level participant episode control methods.

    These exercise the full ``initialize → reset → terminate → restart``
    lifecycle through the control plane, asserting that each backend
    ``ApplyResult`` is persisted into the snapshot, each operation gets
    a succeeded ``OperationStatus``, and the resulting
    ``participant_episode_results`` / ``participant_episode_history``
    satisfy the RUN-311 invariants.
    """

    def test_initialize_creates_first_episode_with_running_state(self):
        control_plane = RuntimeControlPlane(create_stub_target())

        receipt = control_plane.initialize_participant_episode("participant.alice")
        status = control_plane.get_operation(receipt.operation_id)
        snapshot = control_plane.get_snapshot()

        assert receipt.accepted is True
        assert receipt.domain == RuntimeDomain.PARTICIPANT
        assert status is not None
        assert status.state == OperationState.SUCCEEDED
        state = snapshot.snapshot.participant_episode_results["participant.alice"]
        assert state["status"] == "running"
        assert state["sequence_number"] == 0
        assert state["previous_episode_id"] is None
        assert state["last_control_action"] == "initialize"
        history = snapshot.snapshot.participant_episode_history["participant.alice"]
        assert [event["event_type"] for event in history] == [
            "episode_initialized",
            "episode_running",
        ]

    def test_admit_participant_action_records_implementation_bound_behavior_history(self):
        runtime_model = compile_runtime_model(_scenario(_participant_binding_scenario_yaml()))
        behavior = runtime_model.participant_behaviors["participant.behavior.red-agent"]
        action_address = behavior.action_contract_addresses[0]
        observation_address = behavior.observation_boundary_addresses[0]
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode(behavior.address, episode_id="episode-1")

        admission_request = ParticipantActionAdmissionRequest(
            participant_address=behavior.address,
            implementation_manifest=_participant_implementation_manifest(),
            implementation_selection=_participant_implementation_selection(behavior.address),
            action_contract_address=action_address,
            observation_boundary_address=observation_address,
            action_instance_id="scan-0001",
            observation_boundary_evidence_refs=("evidence.scan-output",),
            evidence_refs=("evidence.scan-output",),
            action_result=_succeeded_scan_result(
                participant_address=behavior.address,
                episode_id="episode-1",
                action_instance_id="scan-0001",
                action_contract_address=action_address,
            ),
        )
        receipt = control_plane.admit_participant_action(behavior, admission_request)
        status = control_plane.get_operation(receipt.operation_id)
        snapshot = control_plane.get_snapshot().snapshot

        assert receipt.accepted is True
        assert status is not None
        assert status.state == OperationState.SUCCEEDED
        behavior_history = snapshot.participant_behavior_history[behavior.address]
        assert [event["event_type"] for event in behavior_history] == [
            "action_attempted",
            "state_transition_recorded",
            "observation_emitted",
        ]
        assert behavior_history[0]["participant_address"] == behavior.address
        assert behavior_history[0]["action_contract_address"] == action_address
        assert behavior_history[0]["actor_provenance"] == "participant-implementation:reference-red-agent@1.0.0"
        assert "stub" not in behavior_history[0]["actor_provenance"]
        assert behavior_history[-1]["observation_boundary_address"] == observation_address
        assert behavior_history[-1]["details"]["evidence_refs"] == ["evidence.scan-output"]
        assert (
            list(
                iter_participant_episode_snapshot_violations(
                    snapshot.participant_episode_results,
                    snapshot.participant_episode_history,
                )
            )
            == []
        )
        assert (
            list(
                iter_participant_behavior_history_violations(
                    behavior_history,
                    action_contracts=runtime_model.action_contracts,
                    observation_boundaries=runtime_model.observation_boundaries,
                    participant_episode_history=snapshot.participant_episode_history[behavior.address],
                    expected_participant_address=behavior.address,
                )
            )
            == []
        )

    def test_admit_participant_action_rejects_action_outside_compiled_behavior(self):
        runtime_model = compile_runtime_model(_scenario(_participant_binding_scenario_yaml()))
        behavior = runtime_model.participant_behaviors["participant.behavior.red-agent"]
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode(behavior.address, episode_id="episode-1")

        receipt = control_plane.admit_participant_action(
            behavior,
            implementation_manifest=_participant_implementation_manifest(),
            implementation_selection=_participant_implementation_selection(behavior.address),
            action_contract_address="participant.action-contract.not-declared",
            observation_boundary_address=behavior.observation_boundary_addresses[0],
            action_instance_id="scan-0001",
            evidence_refs=("evidence.scan-output",),
        )
        status = control_plane.get_operation(receipt.operation_id)

        assert receipt.accepted is False
        assert status is None
        assert any("is not declared by compiled participant behavior" in diag.message for diag in receipt.diagnostics)

    def test_admit_participant_action_rejects_withheld_observation_refs(self):
        runtime_model = compile_runtime_model(_scenario(_participant_binding_scenario_yaml()))
        behavior = runtime_model.participant_behaviors["participant.behavior.red-agent"]
        action_address = behavior.action_contract_addresses[0]
        observation_address = behavior.observation_boundary_addresses[0]
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode(behavior.address, episode_id="episode-1")

        receipt = control_plane.admit_participant_action(
            behavior,
            implementation_manifest=_participant_implementation_manifest(),
            implementation_selection=_participant_implementation_selection(behavior.address),
            action_contract_address=action_address,
            observation_boundary_address=observation_address,
            action_instance_id="scan-0001",
            observation_boundary_evidence_refs=("scenario.hidden.answer-key",),
            evidence_refs=("scenario.hidden.answer-key",),
        )
        status = control_plane.get_operation(receipt.operation_id)

        assert receipt.accepted is False
        assert status is None
        assert any("withheld_refs" in diag.message for diag in receipt.diagnostics)

    def test_initialize_twice_rejects_duplicate(self):
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode("participant.alice")

        receipt = control_plane.initialize_participant_episode("participant.alice")
        status = control_plane.get_operation(receipt.operation_id)

        assert status is not None
        assert status.state == OperationState.FAILED
        assert any("already has a live episode" in diag.message for diag in status.diagnostics)

    def test_reset_allocates_new_episode_preserving_identity(self):
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode("participant.alice")

        receipt = control_plane.reset_participant_episode("participant.alice", reason="operator reset")
        status = control_plane.get_operation(receipt.operation_id)
        snapshot = control_plane.get_snapshot()

        assert status is not None
        assert status.state == OperationState.SUCCEEDED
        state = snapshot.snapshot.participant_episode_results["participant.alice"]
        assert state["sequence_number"] == 1
        assert state["last_control_action"] == "reset"
        assert state["previous_episode_id"] == "participant.alice-episode-1"
        assert state["episode_id"] == "participant.alice-episode-2"
        assert state["status"] == "running"

    def test_reset_rejects_terminated_participant(self):
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode("participant.alice")
        control_plane.terminate_participant_episode(
            "participant.alice",
            terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED,
        )

        receipt = control_plane.reset_participant_episode("participant.alice")
        status = control_plane.get_operation(receipt.operation_id)

        assert status is not None
        assert status.state == OperationState.FAILED
        assert any("use restart" in diag.message for diag in status.diagnostics)

    def test_terminate_drives_state_to_terminated_with_reason(self):
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode("participant.alice")

        receipt = control_plane.terminate_participant_episode(
            "participant.alice",
            terminal_reason=ParticipantEpisodeTerminalReason.TIMED_OUT,
        )
        status = control_plane.get_operation(receipt.operation_id)
        snapshot = control_plane.get_snapshot()

        assert status is not None
        assert status.state == OperationState.SUCCEEDED
        state = snapshot.snapshot.participant_episode_results["participant.alice"]
        assert state["status"] == "terminated"
        assert state["terminal_reason"] == "timed_out"
        assert state["terminated_at"] is not None
        history = snapshot.snapshot.participant_episode_history["participant.alice"]
        assert history[-1]["event_type"] == "episode_timed_out"
        assert history[-1]["terminal_reason"] == "timed_out"

    def test_terminate_rejects_already_terminated(self):
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode("participant.alice")
        control_plane.terminate_participant_episode("participant.alice")

        receipt = control_plane.terminate_participant_episode("participant.alice")
        status = control_plane.get_operation(receipt.operation_id)

        assert status is not None
        assert status.state == OperationState.FAILED
        assert any("already terminated" in diag.message for diag in status.diagnostics)

    def test_restart_resumes_from_terminated_predecessor(self):
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode("participant.alice")
        control_plane.terminate_participant_episode(
            "participant.alice",
            terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED,
        )

        receipt = control_plane.restart_participant_episode("participant.alice")
        status = control_plane.get_operation(receipt.operation_id)
        snapshot = control_plane.get_snapshot()

        assert status is not None
        assert status.state == OperationState.SUCCEEDED
        state = snapshot.snapshot.participant_episode_results["participant.alice"]
        assert state["sequence_number"] == 1
        assert state["last_control_action"] == "restart"
        assert state["previous_episode_id"] == "participant.alice-episode-1"
        assert state["status"] == "running"

    def test_restart_rejects_non_terminated_participant(self):
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode("participant.alice")

        receipt = control_plane.restart_participant_episode("participant.alice")
        status = control_plane.get_operation(receipt.operation_id)

        assert status is not None
        assert status.state == OperationState.FAILED
        assert any("non-terminated" in diag.message for diag in status.diagnostics)

    def test_initialize_rejects_target_without_participant_runtime(self):
        manifest = create_stub_manifest(with_participant_runtime=False)
        components = create_stub_components(manifest=manifest)
        target = RuntimeTarget(
            name="no-participant",
            manifest=manifest,
            provisioner=components.provisioner,
            orchestrator=components.orchestrator,
            evaluator=components.evaluator,
        )
        control_plane = RuntimeControlPlane(target)

        receipt = control_plane.initialize_participant_episode("participant.alice")
        status = control_plane.get_operation(receipt.operation_id)

        assert receipt.accepted is False
        assert status is None
        assert any("does not provide a participant runtime" in diag.message for diag in receipt.diagnostics)

    def test_full_lifecycle_snapshot_chain_is_consistent(self):
        """End-to-end: initialize → reset → terminate → restart and verify
        history chain matches the final result (RUN-311 cross-check invariant).
        """
        control_plane = RuntimeControlPlane(create_stub_target())

        control_plane.initialize_participant_episode("participant.alice")
        control_plane.reset_participant_episode("participant.alice")
        control_plane.terminate_participant_episode(
            "participant.alice",
            terminal_reason=ParticipantEpisodeTerminalReason.COMPLETED,
        )
        control_plane.restart_participant_episode("participant.alice")

        snapshot = control_plane.get_snapshot().snapshot
        assert set(snapshot.participant_episode_results) == {"participant.alice"}
        state = snapshot.participant_episode_results["participant.alice"]
        assert state["sequence_number"] == 2
        assert state["status"] == "running"
        assert state["last_control_action"] == "restart"
        assert state["previous_episode_id"] == "participant.alice-episode-2"
        assert [event["event_type"] for event in snapshot.participant_episode_history["participant.alice"]] == [
            "episode_initialized",
            "episode_running",
            "episode_reset",
            "episode_running",
            "episode_completed",
            "episode_restarted",
            "episode_running",
        ]
        violations = list(
            iter_participant_episode_snapshot_violations(
                snapshot.participant_episode_results,
                snapshot.participant_episode_history,
            )
        )
        assert violations == [], (
            f"Full participant lifecycle must satisfy every RUN-311 snapshot invariant; got violations: {violations}"
        )

    def test_initialize_is_idempotent_via_idempotency_key(self):
        """Idempotency — a second submission with the same idempotency key
        must return the original receipt without running the backend twice.
        """
        control_plane = RuntimeControlPlane(create_stub_target())

        first = control_plane.initialize_participant_episode(
            "participant.alice",
            idempotency_key="init-alice-1",
        )
        second = control_plane.initialize_participant_episode(
            "participant.alice",
            idempotency_key="init-alice-1",
        )

        assert first.operation_id == second.operation_id
        snapshot = control_plane.get_snapshot().snapshot
        history = snapshot.participant_episode_history["participant.alice"]
        assert [event["event_type"] for event in history] == [
            "episode_initialized",
            "episode_running",
        ]

    def test_status_view_projects_current_participant_episode_state(self):
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode("participant.alice")

        view = control_plane.get_participant_status_view("participant.alice")

        assert isinstance(view, ParticipantStatusViewModel)
        assert view.participant_address == "participant.alice"
        assert view.episode_id == "participant.alice-episode-1"
        assert view.source_snapshot_ref == "runtime.snapshot.current"
        assert view.episode_state is not None
        assert view.episode_state.status == "running"
        episode_state = view.episode_state.model_dump(mode="json")
        assert "participant_address" not in episode_state
        assert "episode_id" not in episode_state

    def test_status_view_scopes_open_operations_to_participant(self):
        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": _episode_state("participant.alice", "episode-1"),
                "participant.bob": _episode_state("participant.bob", "episode-1"),
            }
        )
        control_plane = RuntimeControlPlane(create_stub_target(), initial_snapshot=snapshot)
        control_plane._operations = {
            "op-alice": _participant_operation_record("op-alice", "participant.alice"),
            "op-bob": _participant_operation_record("op-bob", "participant.bob"),
        }

        view = control_plane.get_participant_status_view("participant.alice")

        assert view is not None
        assert view.open_operation_refs == ["op-alice"]

    def test_history_view_filters_to_one_participant_episode_and_projects_scope(self):
        snapshot = RuntimeSnapshot(
            participant_episode_results={
                "participant.alice": _episode_state("participant.alice", "episode-1"),
                "participant.bob": _episode_state("participant.bob", "episode-1"),
            },
            participant_episode_history={
                "participant.alice": [
                    _episode_history_event("participant.alice", "episode-1"),
                    _episode_history_event("participant.alice", "episode-2"),
                ],
                "participant.bob": [_episode_history_event("participant.bob", "episode-1")],
            },
            participant_behavior_history={
                "participant.alice": [
                    _behavior_history_event("participant.alice", "episode-1"),
                    _behavior_history_event("participant.alice", "episode-2"),
                ],
                "participant.bob": [_behavior_history_event("participant.bob", "episode-1")],
            },
        )
        control_plane = RuntimeControlPlane(create_stub_target(), initial_snapshot=snapshot)

        view = control_plane.get_participant_history_view("participant.alice", "episode-1")

        assert isinstance(view, ParticipantHistoryViewModel)
        assert view.participant_address == "participant.alice"
        assert view.episode_id == "episode-1"
        assert view.completeness == "complete"
        assert len(view.episode_history) == 1
        assert len(view.behavior_history) == 1
        for event in [*view.episode_history, *view.behavior_history]:
            payload = event.model_dump(mode="json")
            assert "participant_address" not in payload
            assert "episode_id" not in payload

    def test_context_view_declares_sem214_reference_semantics(self):
        control_plane = RuntimeControlPlane(create_stub_target())
        control_plane.initialize_participant_episode("participant.alice")

        view = control_plane.get_participant_context_view(
            "participant.alice",
            view_ref="views.context.network-posture.v1",
            episode_id="participant.alice-episode-1",
            derivation_basis_ref="rules.context.network-posture.v1",
            payload_ref="evidence.context.alice.network-posture",
        )

        assert isinstance(view, ParticipantContextViewModel)
        assert view.participant_address == "participant.alice"
        assert view.episode_id == "participant.alice-episode-1"
        assert view.view_ref == "views.context.network-posture.v1"
        assert view.derived_from_refs == ["runtime.snapshot.current"]
        assert view.meaning_ref == "views.context.network-posture.v1"
        assert view.participant_scope == "participant_local"
        assert view.audience_scope == "participant_visible"
        assert view.observation_point == "participant.alice-episode-1"
        assert view.source_layers[0].source_layer == "source_snapshot"
        assert view.source_layers[0].temporal_relation == "same_observation_point"
        assert view.transformation.transformation_rule_ref == "rules.context.network-posture.v1"
        assert view.transformation.input_source_ids == ["source-snapshot"]
        assert view.comparability.comparability_class == "portable_equivalent"
        assert view.comparability.comparison_basis_ref == "comparability.views.context.network-posture.v1"
        assert view.payload_ref == "evidence.context.alice.network-posture"

    def test_participant_retrieval_views_return_none_for_unknown_participant(self):
        control_plane = RuntimeControlPlane(create_stub_target())

        assert control_plane.get_participant_status_view("participant.unknown") is None
        assert control_plane.get_participant_history_view("participant.unknown", "episode-1") is None
        assert (
            control_plane.get_participant_context_view(
                "participant.unknown",
                view_ref="views.context.network-posture.v1",
            )
            is None
        )
