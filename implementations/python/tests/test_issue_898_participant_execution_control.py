"""Issue #898 portable participant execution and lifecycle control."""

from __future__ import annotations

import threading
from dataclasses import replace

import pytest
import yaml
from implementations.python.tests.test_dsl_437_benign_participant_execution import (
    _autonomous_manifest,
    _compiled,
    _NativeParticipantRuntime,
    _scenario_yaml,
)
from implementations.python.tests.test_runtime_control_plane_api import _test_security
from raes import parse_sdl
from raes.participant_behavior import ParticipantFailureClass
from raes_backend_protocols.capability_admission import (
    participant_autonomous_execution_capability_gaps,
)
from raes_backend_protocols.manifest import (
    backend_manifest_from_v2_model,
    backend_manifest_v2_model,
)
from raes_backend_protocols.participant_runtime_base import BaseParticipantRuntime
from raes_backend_stubs.stubs import create_stub_target
from raes_conformance.conformance.profiles import BackendCapabilityProfile
from raes_conformance.conformance.target_probes import _target_adapter_cases
from raes_contracts.contracts import (
    ParticipantAutonomousExecutionStateModel,
    ParticipantTemporalRuntimeContextModel,
)
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionBindingModel,
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.participant_binding import (
    ParticipantActionAdmissionRequest,
    ParticipantNativeActionExecution,
)
from raes_contracts.participant_episode import ParticipantEpisodeInitializeRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_scheduler_concurrent_commit import (
    participant_generation_commit_diagnostic,
)
from starlette.testclient import TestClient


def _binding() -> ParticipantExecutionBindingModel:
    return ParticipantExecutionBindingModel(
        binding_id="green-login-service",
        action_contract_address="participant.action-contract.portal-login",
        target_addresses=("service.customer-portal.https",),
        participant_implementation_ref="participant-implementation-manifests.green-worker.v1",
        constraint_refs=("constraint.green-login.capacity",),
        evidence_refs=("evidence.green-login.native-action",),
        max_action_attempts=24,
        max_in_flight=2,
        timeout_seconds=30,
        max_retries=2,
    )


def _service_state(
    **updates: object,
) -> ParticipantExecutionServiceStateModel:
    payload: dict[str, object] = {
        "execution_scope_ref": "participant.autonomous-execution.green-activity",
        "policy_address": "participant.autonomous-execution.green-activity",
        "desired_lifecycle": "stopped",
        "observed_lifecycle": "stopped",
        "generation": 0,
        "observed_generation": 0,
        "health": "healthy",
        "readiness": "not_ready",
        "accepting_new_work": False,
        "draining": False,
        "quiescent": True,
        "resources_released": False,
        "policy_digest": "sha256:" + "1" * 64,
        "binding_digest": "sha256:" + "2" * 64,
        "time_declaration_digest": "sha256:" + "3" * 64,
        "scheduler_state_refs": ("participant.autonomous-execution.green-activity.state.participant.behavior.green",),
        "capacity": 2,
        "reserved": 0,
        "in_flight": 0,
        "last_transition_ref": "operation.participant-execution.configure.0",
        "evidence_refs": ("evidence.participant-execution.health.0",),
    }
    payload.update(updates)
    return ParticipantExecutionServiceStateModel.model_validate(payload)


def test_execution_binding_is_relational_and_finite() -> None:
    binding = _binding()

    assert binding.action_contract_address == "participant.action-contract.portal-login"
    assert binding.target_addresses == ("service.customer-portal.https",)
    assert binding.max_in_flight == 2

    invalid_target_binding = _binding().model_copy(update={"target_addresses": ()}).model_dump()
    invalid_max_in_flight_binding = {**_binding().model_dump(), "max_in_flight": 0}
    with pytest.raises(ValueError, match="target_addresses"):
        ParticipantExecutionBindingModel.model_validate(invalid_target_binding)
    with pytest.raises(ValueError, match="max_in_flight"):
        ParticipantExecutionBindingModel.model_validate(invalid_max_in_flight_binding)


def test_execution_control_request_requires_generation_and_bounded_drain() -> None:
    request = ParticipantExecutionControlRequestModel(
        execution_scope_ref="participant.autonomous-execution.green-activity",
        action="drain",
        expected_generation=3,
        timeout_seconds=10,
    )

    assert request.expected_generation == 3
    assert request.timeout_seconds == 10

    with pytest.raises(ValueError, match="timeout_seconds"):
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=request.execution_scope_ref,
            action="drain",
            expected_generation=3,
        )
    with pytest.raises(ValueError, match="only valid for drain"):
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=request.execution_scope_ref,
            action="pause",
            expected_generation=3,
            timeout_seconds=10,
        )


def test_execution_readback_separates_health_readiness_and_lifecycle() -> None:
    state = _service_state(
        desired_lifecycle="running",
        observed_lifecycle="running",
        generation=3,
        observed_generation=3,
        readiness="ready",
        accepting_new_work=True,
        last_transition_ref="operation.participant-execution.start.3",
        evidence_refs=("evidence.participant-execution.health.3",),
    )

    assert state.health == "healthy"
    assert state.readiness == "ready"
    assert state.accepting_new_work is True

    invalid_admission_readback = {
        **state.model_dump(),
        "observed_lifecycle": "paused",
        "accepting_new_work": True,
    }
    invalid_generation_readback = {**state.model_dump(), "observed_generation": 4}
    with pytest.raises(ValueError, match="accepting_new_work"):
        ParticipantExecutionServiceStateModel.model_validate(invalid_admission_readback)
    with pytest.raises(ValueError, match="observed_generation"):
        ParticipantExecutionServiceStateModel.model_validate(invalid_generation_readback)


def test_compiler_preserves_exact_action_to_target_execution_binding() -> None:
    runtime_model = compile_runtime_model(parse_sdl(_scenario_yaml()))
    policy = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution

    assert policy is not None
    assert len(policy.execution_bindings) == 1
    binding = policy.execution_bindings[0]
    assert binding.action_contract_address == "participant.action-contract.probe-customer-portal-login"
    assert "provision.node.customer-portal.service.http" in binding.target_addresses
    assert binding.participant_implementation_ref == policy.participant_implementation_ref
    assert binding.max_in_flight == policy.max_in_flight
    assert binding.commutative_shared_state_refs == ("nodes.customer-portal.services.http",)
    assert binding.merge_rule_refs == ()


def test_compiler_preserves_action_interaction_footprint_for_concurrency_admission() -> None:
    scenario_payload = yaml.safe_load(_scenario_yaml())
    action = scenario_payload["action_contracts"]["probe-customer-portal-login"]
    action["interactions"] = [
        {
            "interaction_class": "shared_state_change",
            "target": "nodes.customer-portal.services.http",
            "rationale": "Concurrent login probes update one governed service state.",
            "shared_state_refs": ["nodes.customer-portal.services.http"],
        }
    ]

    runtime_model = compile_runtime_model(parse_sdl(yaml.safe_dump(scenario_payload, sort_keys=False)))
    policy = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution

    assert policy is not None
    binding = policy.execution_bindings[0]
    assert binding.interaction_classes == ("shared_state_change",)
    assert binding.shared_state_refs == ("nodes.customer-portal.services.http",)
    assert binding.related_action_contract_addresses == ()
    assert binding.commutative_shared_state_refs == ()
    assert binding.merge_rule_refs == ()


def test_autonomous_manifest_requires_execution_control_and_relational_bindings() -> None:
    runtime_model, policy = _compiled()
    manifest = _autonomous_manifest(runtime_model, with_realization_envelope=False)
    capability = manifest.participant_runtime

    assert capability is not None
    assert capability.supports_execution_control is True
    assert capability.supports_bounded_concurrency is True
    assert capability.supported_execution_control_actions == frozenset(
        {"start", "pause", "resume", "drain", "reset", "teardown"}
    )
    assert capability.execution_bindings[0].action_contract_address == (policy.action_contract_addresses[0])
    assert capability.execution_bindings[0].target_addresses == (policy.execution_bindings[0].target_addresses)

    wire = backend_manifest_v2_model(manifest)
    restored = backend_manifest_from_v2_model(wire)
    assert restored.participant_runtime == capability


def test_admission_rejects_cartesian_action_and_target_declarations() -> None:
    runtime_model, policy = _compiled()
    manifest = _autonomous_manifest(runtime_model)
    capability = manifest.participant_runtime
    assert capability is not None
    binding = capability.execution_bindings[0]
    portal_target = "provision.node.customer-portal.service.http"
    assert portal_target in binding.target_addresses
    weakened_binding = replace(
        binding,
        target_addresses=tuple(target for target in binding.target_addresses if target != portal_target),
    )
    weakened_manifest = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            participant_runtime=replace(
                capability,
                execution_bindings=(weakened_binding,),
            ),
        ),
    )

    gaps = participant_autonomous_execution_capability_gaps(
        weakened_manifest,
        (policy,),
        runtime_model.time_model,
    )

    assert any("execution binding" in gap and portal_target in gap for gap in gaps)


def test_execution_lifecycle_rejects_stale_generation_and_preserves_evidence() -> None:
    runtime = _NativeParticipantRuntime()
    scope = "participant.autonomous-execution.green-activity"
    snapshot = RuntimeSnapshot(participant_execution_services={scope: _service_state().model_dump(mode="json")})

    started = runtime.control_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=scope,
            action="start",
            expected_generation=0,
        ),
        snapshot,
    )
    assert started.success is True
    state = ParticipantExecutionServiceStateModel.model_validate(started.snapshot.participant_execution_services[scope])
    assert state.observed_lifecycle == "running"
    assert state.readiness == "ready"
    assert state.accepting_new_work is True

    stale = runtime.control_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=scope,
            action="pause",
            expected_generation=1,
        ),
        started.snapshot,
    )
    assert stale.success is False
    assert stale.snapshot is started.snapshot
    assert stale.diagnostics[0].code == "runtime.participant-execution-stale-generation"

    paused = runtime.control_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=scope,
            action="pause",
            expected_generation=0,
        ),
        started.snapshot,
    )
    resumed = runtime.control_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=scope,
            action="resume",
            expected_generation=0,
        ),
        paused.snapshot,
    )
    drained = runtime.control_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=scope,
            action="drain",
            expected_generation=0,
            timeout_seconds=1,
        ),
        resumed.snapshot,
    )
    reset = runtime.control_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=scope,
            action="reset",
            expected_generation=0,
        ),
        drained.snapshot,
    )
    reset_state = ParticipantExecutionServiceStateModel.model_validate(
        reset.snapshot.participant_execution_services[scope]
    )
    assert reset_state.generation == 1
    assert reset_state.observed_generation == 1
    assert reset_state.observed_lifecycle == "running"
    assert reset_state.evidence_refs

    drained_again = runtime.control_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=scope,
            action="drain",
            expected_generation=1,
            timeout_seconds=1,
        ),
        reset.snapshot,
    )
    torn_down = runtime.control_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=scope,
            action="teardown",
            expected_generation=1,
        ),
        drained_again.snapshot,
    )
    final_state = ParticipantExecutionServiceStateModel.model_validate(
        torn_down.snapshot.participant_execution_services[scope]
    )
    assert final_state.observed_lifecycle == "terminated"
    assert final_state.resources_released is True
    assert final_state.accepting_new_work is False


def test_base_runtime_does_not_synthesize_backend_lifecycle_success() -> None:
    assert not callable(getattr(BaseParticipantRuntime(), "control_execution", None))


def test_native_drain_waits_for_in_flight_work_within_bound() -> None:
    runtime = _NativeParticipantRuntime()
    scope = "participant.autonomous-execution.green-activity"
    snapshot = RuntimeSnapshot(
        participant_execution_services={
            scope: _service_state(
                desired_lifecycle="running",
                observed_lifecycle="running",
                readiness="ready",
                accepting_new_work=True,
            ).model_dump(mode="json")
        }
    )
    runtime._execution_controller.begin_action()
    outcome: list[object] = []

    def drain() -> None:
        outcome.append(
            runtime.control_execution(
                ParticipantExecutionControlRequestModel(
                    execution_scope_ref=scope,
                    action="drain",
                    expected_generation=0,
                    timeout_seconds=1,
                ),
                snapshot,
            )
        )

    thread = threading.Thread(target=drain)
    thread.start()
    thread.join(timeout=0.05)
    assert thread.is_alive()
    runtime._execution_controller.finish_action()
    thread.join(timeout=1)

    assert len(outcome) == 1
    assert outcome[0].success is True


def _generation_bound_request(
    runtime: _NativeParticipantRuntime,
    snapshot: RuntimeSnapshot,
    *,
    generation: int,
):
    scope = "participant.autonomous-execution.green-activity"
    request = runtime.bind_autonomous_action(
        "participant.behavior.green",
        "participant.action-contract.portal-login",
        "participant.observation-boundary.portal",
        "participant-implementation-manifests.green-worker.v1",
        f"green-login-generation-{generation}",
        (
            ParticipantTemporalRuntimeContextModel(
                temporal_contract_id="time.constraint.green-login",
                time_domain="scenario_time",
                clock_authority="time.clock.scenario",
                event_points=["submit", "start", "end", "observed"],
                observation_point="time.clock.scenario@segment=0,tick=0",
                reset_boundary="time.clock.scenario:segment=0",
            ),
        ),
        snapshot,
    )
    return replace(
        request,
        target_addresses=("service.customer-portal.https",),
        execution_scope_ref=scope,
        execution_generation=generation,
        requires_terminal_outcome=True,
    )


def test_generation_fence_rejects_stale_work_before_native_execution() -> None:
    runtime = _NativeParticipantRuntime()
    scope = "participant.autonomous-execution.green-activity"
    snapshot = RuntimeSnapshot(
        participant_execution_services={
            scope: _service_state(
                desired_lifecycle="running",
                observed_lifecycle="running",
                generation=1,
                observed_generation=1,
                readiness="ready",
                accepting_new_work=True,
            ).model_dump(mode="json")
        }
    )
    snapshot = runtime.initialize(
        ParticipantEpisodeInitializeRequest(participant_address="participant.behavior.green"),
        snapshot,
    ).snapshot

    result = runtime.admit_action(
        _generation_bound_request(runtime, snapshot, generation=0),
        snapshot,
    )

    assert result.success is False
    assert result.diagnostics[0].code == ("runtime.participant-execution-stale-work")
    assert runtime.native_actions == []


def test_generation_fence_uses_authoritative_serialized_commit_state() -> None:
    scope = "participant.autonomous-execution.green-activity"
    runtime = _NativeParticipantRuntime()
    snapshot = RuntimeSnapshot(
        participant_execution_services={
            scope: _service_state(
                desired_lifecycle="running",
                observed_lifecycle="running",
                generation=1,
                observed_generation=1,
                readiness="ready",
                accepting_new_work=True,
            ).model_dump(mode="json")
        }
    )
    snapshot = runtime.initialize(
        ParticipantEpisodeInitializeRequest(participant_address="participant.behavior.green"),
        snapshot,
    ).snapshot
    request = _generation_bound_request(runtime, snapshot, generation=1)
    worker_result = runtime.admit_action(request, snapshot)
    service = ParticipantExecutionServiceStateModel.model_validate(snapshot.participant_execution_services[scope])
    services = dict(snapshot.participant_execution_services)
    services[scope] = service.model_copy(update={"generation": 2, "observed_generation": 2}).model_dump(mode="json")
    authoritative = snapshot.with_entries(
        dict(snapshot.entries),
        participant_execution_services=services,
    )

    diagnostic = participant_generation_commit_diagnostic(request, authoritative)

    assert worker_result.success is True
    worker_service = ParticipantExecutionServiceStateModel.model_validate(
        worker_result.snapshot.participant_execution_services[scope]
    )
    assert worker_service.generation == 1
    assert diagnostic is not None
    assert diagnostic.code == "runtime.participant-execution-stale-completion"


class _OverlappingParticipantRuntime(_NativeParticipantRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._barrier = threading.Barrier(2)
        self._active_lock = threading.Lock()
        self._active = 0
        self.peak_active = 0

    def _model_action(self, request, snapshot, *, episode_id):
        with self._active_lock:
            self._active += 1
            self.peak_active = max(self.peak_active, self._active)
        try:
            self._barrier.wait(timeout=2)
            execution = super()._model_action(
                request,
                snapshot,
                episode_id=episode_id,
            )
            metadata = dict(execution.apply_result.snapshot.metadata)
            action_instance_id = metadata.pop("last_native_action")
            metadata[f"last_native_action:{request.participant_address}"] = action_instance_id
            return replace(
                execution,
                apply_result=replace(
                    execution.apply_result,
                    snapshot=execution.apply_result.snapshot.with_entries(
                        dict(execution.apply_result.snapshot.entries),
                        metadata=metadata,
                    ),
                ),
            )
        finally:
            with self._active_lock:
                self._active -= 1


class _OneFailedOverlappingParticipantRuntime(_OverlappingParticipantRuntime):
    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        execution = super()._model_action(request, snapshot, episode_id=episode_id)
        if request.participant_address.endswith("participant-agent"):
            assert execution.action_result is not None
            return replace(
                execution,
                action_result=execution.action_result.model_copy(
                    update={
                        "status": "failed",
                        "failure_class": ParticipantFailureClass.TARGET_UNAVAILABLE,
                    }
                ),
            )
        return execution


class _SnapshotProjectionParticipantRuntime(_NativeParticipantRuntime):
    """Backend that writes a portable field outside the historical merge allowlist."""

    def __init__(self) -> None:
        super().__init__()
        self._retained_results: list[object] = []

    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        execution = super()._model_action(request, snapshot, episode_id=episode_id)
        result_address = f"evaluation.result.native-{request.participant_address.rsplit('.', 1)[-1]}"
        metadata = dict(execution.apply_result.snapshot.metadata)
        action_instance_id = metadata.pop("last_native_action")
        metadata[f"last_native_action:{request.participant_address}"] = action_instance_id
        evaluation_results = {
            **execution.apply_result.snapshot.evaluation_results,
            result_address: {
                "participant_address": request.participant_address,
                "nested": {"state": "committed"},
            },
        }
        modeled = replace(
            execution.apply_result,
            snapshot=execution.apply_result.snapshot.with_entries(
                dict(execution.apply_result.snapshot.entries),
                evaluation_results=evaluation_results,
                metadata=metadata,
            ),
            changed_addresses=[*execution.apply_result.changed_addresses, result_address],
        )
        return replace(execution, apply_result=modeled)

    def admit_action(self, request, snapshot):
        result = super().admit_action(request, snapshot)
        self._retained_results.append(result)
        return result


class _ProtectedStateMutationParticipantRuntime(_NativeParticipantRuntime):
    """Backend that attempts to write serialized scheduler-owned state."""

    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        execution = super()._model_action(request, snapshot, episode_id=episode_id)
        services = {
            **execution.apply_result.snapshot.participant_execution_services,
            "participant.autonomous-execution.injected": {},
        }
        return replace(
            execution,
            apply_result=replace(
                execution.apply_result,
                snapshot=execution.apply_result.snapshot.with_entries(
                    dict(execution.apply_result.snapshot.entries),
                    participant_execution_services=services,
                ),
            ),
        )


def _two_green_participant_scenario(*, max_in_flight: int = 2):
    payload = yaml.safe_load(_scenario_yaml())
    payload["entities"]["enterprise-participant-2"] = {
        **payload["entities"]["enterprise-participant"],
        "mission": "Perform a second bounded green participant action.",
    }
    payload["agents"]["participant-agent-2"] = {
        **payload["agents"]["participant-agent"],
        "entity": "enterprise-participant-2",
        "description": "Second ordinary green participant.",
    }
    specification = payload["behavior_specifications"]["participant-behavior"]
    specification["participant_refs"].append("participant-agent-2")
    specification["autonomous_execution"]["max_in_flight"] = max_in_flight
    return parse_sdl(yaml.safe_dump(payload, sort_keys=False))


def test_scheduler_executes_two_due_green_participants_with_bounded_overlap() -> None:
    scenario = _two_green_participant_scenario()
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _OverlappingParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success is True
    assert participant_runtime.peak_active == 2
    assert len(participant_runtime.native_actions) == 2
    states = [
        ParticipantExecutionServiceStateModel.model_validate(payload)
        for payload in applied.snapshot.participant_execution_services.values()
    ]
    assert len(states) == 1
    assert states[0].capacity == 2
    assert states[0].reserved == 0
    assert states[0].in_flight == 0


def test_serial_and_concurrent_actions_commit_the_same_backend_owned_projection() -> None:
    def _apply(max_in_flight: int):
        scenario = _two_green_participant_scenario(max_in_flight=max_in_flight)
        runtime_model = compile_runtime_model(scenario)
        participant_runtime = _SnapshotProjectionParticipantRuntime()
        target = replace(
            create_stub_target(),
            manifest=_autonomous_manifest(runtime_model),
            participant_runtime=participant_runtime,
        )
        manager = RuntimeManager(target)
        return manager.apply(manager.plan(scenario)), participant_runtime

    serial, _serial_runtime = _apply(1)
    concurrent, concurrent_runtime = _apply(2)
    prefix = "evaluation.result.native-"
    serial_projection = {
        key: value for key, value in serial.snapshot.evaluation_results.items() if key.startswith(prefix)
    }
    concurrent_projection = {
        key: value for key, value in concurrent.snapshot.evaluation_results.items() if key.startswith(prefix)
    }

    assert serial.success is True
    assert concurrent.success is True
    assert concurrent_projection == serial_projection
    assert len(concurrent_projection) == 2
    assert set(concurrent_projection) <= set(concurrent.changed_addresses)

    retained = next(
        result
        for result in concurrent_runtime._retained_results
        if any(key.startswith(prefix) for key in result.snapshot.evaluation_results)
    )
    retained_key = next(key for key in retained.snapshot.evaluation_results if key.startswith(prefix))
    retained.snapshot.evaluation_results[retained_key]["nested"]["state"] = "mutated-after-return"
    assert concurrent.snapshot.evaluation_results[retained_key]["nested"]["state"] == "committed"


def test_serial_action_rejects_backend_mutation_of_scheduler_owned_state() -> None:
    scenario = _two_green_participant_scenario(max_in_flight=1)
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _ProtectedStateMutationParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success is False
    assert any(
        diagnostic.code == "runtime.participant-autonomous-action-protocol-invalid"
        for diagnostic in applied.diagnostics
    )
    assert "participant.autonomous-execution.injected" not in applied.snapshot.participant_execution_services


def test_stop_policy_settles_every_already_dispatched_peer() -> None:
    scenario = _two_green_participant_scenario()
    runtime_model = compile_runtime_model(scenario)
    participant_runtime = _OneFailedOverlappingParticipantRuntime()
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=participant_runtime,
    )
    manager = RuntimeManager(target)

    applied = manager.apply(manager.plan(scenario))

    assert applied.success is False
    assert len(participant_runtime.native_actions) == 2
    scheduler_states = {
        state.participant_address: state
        for state in (
            ParticipantAutonomousExecutionStateModel.model_validate(payload)
            for payload in applied.snapshot.participant_autonomous_execution_states.values()
        )
    }
    failed = scheduler_states["participant.behavior.participant-agent"]
    succeeded = scheduler_states["participant.behavior.participant-agent-2"]
    assert (failed.lifecycle_state, failed.failed_actions, failed.in_flight) == ("failed", 1, 0)
    assert (succeeded.succeeded_actions, succeeded.in_flight) == (1, 0)
    assert set(applied.snapshot.participant_behavior_history) == set(scheduler_states)
    service = ParticipantExecutionServiceStateModel.model_validate(
        applied.snapshot.participant_execution_services["participant.autonomous-execution.participant-behavior"]
    )
    assert (service.reserved, service.in_flight, service.quiescent) == (0, 0, True)


def test_control_plane_exposes_authenticated_generation_bound_execution_control() -> None:
    scope = "participant.autonomous-execution.green-activity"
    initial_snapshot = RuntimeSnapshot(participant_execution_services={scope: _service_state().model_dump(mode="json")})
    target = replace(
        create_stub_target(),
        participant_runtime=_NativeParticipantRuntime(),
    )
    control_plane = RuntimeControlPlane(target, initial_snapshot=initial_snapshot)
    app = create_control_plane_app(
        control_plane,
        security=_test_security(target.name),
    )
    backend_headers = {
        "x-raes-client-verified": "true",
        "x-raes-client-identity": "backend-service",
        "idempotency-key": "start-generation-0",
    }
    auditor_headers = {"authorization": "Bearer test-auditor-token"}

    with TestClient(app) as client:
        unauthenticated = client.post(
            f"/participant-executions/{scope}/control",
            json={"action": "start", "expected_generation": 0},
        )
        started = client.post(
            f"/participant-executions/{scope}/control",
            json={"action": "start", "expected_generation": 0},
            headers=backend_headers,
        )
        repeated = client.post(
            f"/participant-executions/{scope}/control",
            json={"action": "start", "expected_generation": 0},
            headers=backend_headers,
        )
        readback = client.get(
            f"/participant-executions/{scope}",
            headers=auditor_headers,
        )
        status = client.get(
            f"/operations/{started.json()['operation_id']}",
            headers=auditor_headers,
        )

    assert unauthenticated.status_code == 401
    assert started.status_code == 200
    assert repeated.json()["operation_id"] == started.json()["operation_id"]
    assert status.json()["state"] == "succeeded"
    assert readback.status_code == 200
    assert readback.headers["x-raes-snapshot-revision"].isdigit()
    assert readback.json()["observed_lifecycle"] == "running"
    assert readback.json()["observed_generation"] == 0
    assert readback.json()["health"] == "healthy"
    assert readback.json()["readiness"] == "ready"


def test_control_plane_rejects_synthetic_lifecycle_readback() -> None:
    class _SyntheticControlRuntime(_NativeParticipantRuntime):
        def control_execution(self, request, snapshot):
            return ApplyResult(
                success=True,
                snapshot=snapshot,
                changed_addresses=[request.execution_scope_ref],
            )

    scope = "participant.autonomous-execution.green-activity"
    snapshot = RuntimeSnapshot(participant_execution_services={scope: _service_state().model_dump(mode="json")})
    target = replace(
        create_stub_target(),
        participant_runtime=_SyntheticControlRuntime(),
    )
    control_plane = RuntimeControlPlane(target, initial_snapshot=snapshot)

    receipt = control_plane.control_participant_execution(
        ParticipantExecutionControlRequestModel(
            execution_scope_ref=scope,
            action="start",
            expected_generation=0,
        )
    )
    status = control_plane.get_operation(receipt.operation_id)

    assert status is not None
    assert status.state.value == "failed"
    assert status.diagnostics[0].code == ("runtime.participant-execution-readback-invalid")


def test_live_conformance_conditionally_proves_autonomous_action_and_lifecycle() -> None:
    runtime_model = compile_runtime_model(_two_green_participant_scenario())
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=_NativeParticipantRuntime(),
    )

    cases = _target_adapter_cases(
        target,
        BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE,
    )
    participant_execution_cases = tuple(case for case in cases if case.name.startswith("participant-execution-"))

    assert participant_execution_cases
    assert all(case.passed for case in participant_execution_cases)
    assert any(
        case.name == "participant-execution-bounded-native-actions" and case.evidence_refs
        for case in participant_execution_cases
    )


def test_live_conformance_rejects_autonomous_claim_without_executable_behavior() -> None:
    class _InertParticipantRuntime(_NativeParticipantRuntime):
        def _model_action(self, request, snapshot, *, episode_id):
            execution = super()._model_action(
                request,
                snapshot,
                episode_id=episode_id,
            )
            return replace(execution, action_result=None)

    runtime_model = compile_runtime_model(_two_green_participant_scenario())
    target = replace(
        create_stub_target(),
        manifest=_autonomous_manifest(runtime_model),
        participant_runtime=_InertParticipantRuntime(),
    )

    cases = _target_adapter_cases(
        target,
        BackendCapabilityProfile.FULL_REMOTE_CONTROL_PLANE,
    )
    action_case = next(case for case in cases if case.name == "participant-execution-bounded-native-actions")

    assert action_case.passed is False
    assert action_case.diagnostics[0].code == ("conformance.participant-execution-action-inert")
