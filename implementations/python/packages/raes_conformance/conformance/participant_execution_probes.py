"""Conditional autonomous participant execution conformance probes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from raes_contracts.contracts import (
    ParticipantTemporalRuntimeContextModel,
)
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.registry import RuntimeTarget

from raes_conformance.conformance.diagnostics import _diagnostic
from raes_conformance.conformance.report import ConformanceCaseResult


def _probe_digest(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _participant_execution_probe_snapshot(
    target: RuntimeTarget,
) -> RuntimeSnapshot:
    capability = target.manifest.participant_runtime
    if capability is None or not capability.supports_autonomous_execution:
        return RuntimeSnapshot()
    scope = "participant.autonomous-execution.conformance"
    needs_start = "start" in capability.supported_execution_control_actions
    state = ParticipantExecutionServiceStateModel(
        execution_scope_ref=scope,
        policy_address=scope,
        desired_lifecycle="stopped" if needs_start else "running",
        observed_lifecycle="stopped" if needs_start else "running",
        generation=0,
        observed_generation=0,
        health="healthy",
        readiness="not_ready" if needs_start else "ready",
        accepting_new_work=not needs_start,
        draining=False,
        quiescent=True,
        resources_released=False,
        policy_digest=_probe_digest({"scope": scope}),
        binding_digest=_probe_digest(
            [
                {
                    "action": binding.action_contract_address,
                    "targets": binding.target_addresses,
                }
                for binding in capability.execution_bindings
            ]
        ),
        time_declaration_digest=_probe_digest({"clock": "time.clock.conformance"}),
        scheduler_state_refs=(
            f"{scope}.state.participant.conformance",
            f"{scope}.state.participant.conformance-2",
        ),
        capacity=capability.max_concurrent_actions or 2,
        reserved=0,
        in_flight=0,
        last_transition_ref="operation:participant-execution:configure:0",
        evidence_refs=("conformance:participant-execution:configured",),
    )
    return RuntimeSnapshot(participant_execution_services={scope: state.model_dump(mode="json")})


def _participant_execution_operation_case(
    control_plane: RuntimeControlPlane,
    *,
    scope: str,
    action: str,
    generation: int,
    timeout_seconds: int | None = None,
) -> ConformanceCaseResult:
    request = ParticipantExecutionControlRequestModel(
        execution_scope_ref=scope,
        action=action,
        expected_generation=generation,
        timeout_seconds=timeout_seconds,
    )
    receipt = control_plane.control_participant_execution(request)
    status = control_plane.get_operation(receipt.operation_id)
    diagnostics: list[Diagnostic] = []
    if status is None or status.state.value != "succeeded":
        diagnostics.append(
            _diagnostic(
                "conformance.participant-execution-lifecycle-failed",
                f"runtime.control-plane.participant-execution.{scope}",
                f"Participant execution {action!r} did not complete successfully.",
            )
        )
    else:
        try:
            state = control_plane.participant_execution_state(scope)
        except (TypeError, ValueError) as exc:
            diagnostics.append(
                _diagnostic(
                    "conformance.participant-execution-readback-missing",
                    f"runtime.snapshot.participant-execution-services.{scope}",
                    f"Participant execution readback failed: {exc}",
                )
            )
        else:
            if not state.evidence_refs or not state.last_transition_ref:
                diagnostics.append(
                    _diagnostic(
                        "conformance.participant-execution-evidence-missing",
                        f"runtime.snapshot.participant-execution-services.{scope}",
                        "Participant execution lifecycle readback lacks transition evidence.",
                    )
                )
    return ConformanceCaseResult(
        name=f"participant-execution-{action}",
        contract_name="participant-execution-service-state-v1",
        valid=True,
        passed=not diagnostics,
        diagnostics=tuple(diagnostics),
        expected_operations=(action,),
        accounted_operations=(action,) if not diagnostics else (),
    )


def _participant_execution_action_case(
    target: RuntimeTarget,
    control_plane: RuntimeControlPlane,
    *,
    scope: str,
) -> ConformanceCaseResult:
    runtime = target.participant_runtime
    capability = target.manifest.participant_runtime
    diagnostics: list[Diagnostic] = []
    evidence_refs: tuple[str, ...] = ()
    action_count = 1
    if runtime is None or capability is None or not capability.execution_bindings:
        diagnostics.append(
            _diagnostic(
                "conformance.participant-execution-binding-missing",
                "capabilities.participant_runtime.execution_bindings",
                "Autonomous execution requires at least one executable binding.",
            )
        )
    else:
        binding = capability.execution_bindings[0]
        evidence_refs = binding.evidence_refs
        action_count = min(
            2 if capability.supports_bounded_concurrency else 1,
            capability.max_concurrent_actions or 1,
            capability.max_autonomous_participants or 1,
            binding.max_in_flight,
        )
        participants = (
            "participant.conformance",
            "participant.conformance-2",
        )[:action_count]
        temporal_contexts = (
            ParticipantTemporalRuntimeContextModel(
                temporal_contract_id="time.constraint.conformance",
                time_domain="scenario_time",
                clock_authority="time.clock.conformance",
                event_points=["submit", "start", "end", "observed"],
                observation_point="time.clock.conformance@segment=0,tick=0",
                reset_boundary="time.clock.conformance:segment=0",
            ),
        )
        try:
            if action_count > 1:
                control_plane.initialize_participant_episode(participants[1])
            requests = []
            for ordinal, participant_address in enumerate(participants):
                request = runtime.bind_autonomous_action(
                    participant_address,
                    binding.action_contract_address,
                    next(iter(capability.supported_autonomous_observation_boundaries)),
                    binding.participant_implementation_ref,
                    f"participant-execution-conformance-{ordinal}",
                    temporal_contexts,
                    control_plane.snapshot,
                )
                requests.append(
                    replace(
                        request,
                        participant_address=participant_address,
                        action_contract_address=binding.action_contract_address,
                        action_instance_id=(f"participant-execution-conformance-{ordinal}"),
                        requires_terminal_outcome=True,
                        target_addresses=binding.target_addresses,
                        execution_scope_ref=scope,
                        execution_generation=0,
                    )
                )
            results = (
                runtime.admit_actions_concurrently(tuple(requests), control_plane.snapshot, action_count)
                if action_count > 1
                else (runtime.admit_action(requests[0], control_plane.snapshot),)
            )
        except Exception as exc:
            diagnostics.append(
                _diagnostic(
                    "conformance.participant-execution-action-failed",
                    f"runtime.participant-execution.{scope}",
                    (f"Bounded native action execution raised {type(exc).__name__}: {exc}"),
                )
            )
        else:
            if len(results) != action_count or any(
                not result.success
                or result.action_result is None
                or not result.snapshot.participant_behavior_history.get(request.participant_address)
                for request, result in zip(requests, results, strict=True)
            ):
                diagnostics.append(
                    _diagnostic(
                        "conformance.participant-execution-action-inert",
                        f"runtime.participant-execution.{scope}",
                        (
                            "Declared bounded execution did not produce the required "
                            "typed native outcomes with behavior evidence."
                        ),
                    )
                )
    return ConformanceCaseResult(
        name="participant-execution-bounded-native-actions",
        contract_name="participant-execution-binding-v1",
        valid=True,
        passed=not diagnostics,
        diagnostics=tuple(diagnostics),
        expected_operations=("admit-action",) * action_count,
        accounted_operations=(("admit-action",) * action_count if not diagnostics else ()),
        evidence_refs=evidence_refs,
    )


def _drive_participant_execution_probe(
    target: RuntimeTarget,
    control_plane: RuntimeControlPlane,
) -> list[ConformanceCaseResult]:
    """Conditionally prove autonomous action execution and lifecycle behavior."""

    scope = "participant.autonomous-execution.conformance"
    capability = target.manifest.participant_runtime
    if capability is None or not capability.supports_autonomous_execution:
        return []
    controls = capability.supported_execution_control_actions
    cases = []
    if "start" in controls:
        cases.append(_participant_execution_operation_case(control_plane, scope=scope, action="start", generation=0))
    cases.append(_participant_execution_action_case(target, control_plane, scope=scope))
    if controls != {"start", "pause", "resume", "drain", "reset", "teardown"}:
        cases.extend(_isolated_control_cases(target, control_plane.snapshot, scope, controls - {"start"}))
        return cases
    actions = ["pause", "resume", "drain", "reset"]
    if "reset" in controls:
        actions.append("drain")
    actions.append("teardown")
    for action in actions:
        if action not in controls:
            continue
        state = ParticipantExecutionServiceStateModel.model_validate(
            control_plane.snapshot.participant_execution_services[scope]
        )
        cases.append(
            _participant_execution_operation_case(
                control_plane,
                scope=scope,
                action=action,
                generation=state.generation,
                timeout_seconds=1 if action == "drain" else None,
            )
        )
    return cases


def _isolated_control_cases(target, snapshot, scope, controls):
    """Supply each protocol probe's precondition without calling unclaimed controls.

    These are controlled protocol fixtures, not evidence of native lifecycle
    fidelity or a required backend control-plane architecture.
    """

    initial_states = {
        "pause": "running",
        "resume": "paused",
        "drain": "running",
        "reset": "quiescent",
        "teardown": "quiescent",
    }
    for action, lifecycle in initial_states.items():
        if action not in controls:
            continue
        state = ParticipantExecutionServiceStateModel.model_validate(snapshot.participant_execution_services[scope])
        state = state.model_copy(
            update={
                "desired_lifecycle": lifecycle,
                "observed_lifecycle": lifecycle,
                "readiness": "ready" if lifecycle == "running" else "not_ready",
                "accepting_new_work": lifecycle == "running",
                "quiescent": True,
                "draining": False,
            }
        )
        fixture = snapshot.with_entries(
            dict(snapshot.entries), participant_execution_services={scope: state.model_dump(mode="json")}
        )
        isolated = RuntimeControlPlane(target, initial_snapshot=fixture)
        try:
            yield _participant_execution_operation_case(
                isolated,
                scope=scope,
                action=action,
                generation=state.generation,
                timeout_seconds=1 if action == "drain" else None,
            )
        finally:
            isolated.close()
