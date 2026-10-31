"""Shared-clock scheduler for autonomous ordinary participants."""

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Callable, Iterable

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

from .participant_activity import (
    ParticipantActivityRandomControl,
)
from .participant_execution_scheduler_state import (
    execution_service_state,
    set_execution_clock_lifecycle,
)
from .participant_invocation_tool_settlement import (
    InvocationToolActionConfiguration,
    settle_invocation_tool_sessions,
)
from .participant_resource_budgets import initialize_participant_resource_budgets
from .participant_scheduler_initialization import (
    clock_tick as _clock_tick,
)
from .participant_scheduler_initialization import (
    initialize_participant as _initialize_participant,
)
from .participant_scheduler_lifecycle import reset_policy_at_clock
from .participant_scheduler_operations import (
    SchedulerRunState,
    participant_due_context,
    run_participant_due,
    run_policy_due_concurrently,
)
from .participant_scheduler_policy import _policy_digest
from .participant_scheduler_time import cadence as _cadence
from .participant_scheduler_time import cadence_missed_result, clock_coordinate

_RESOURCE_GOVERNED_PROFILE = "participant-autonomous-execution/v3"


def _missing_execution_service_result(
    policy: ParticipantAutonomousExecutionRuntime,
    run: SchedulerRunState,
) -> ApplyResult:
    return ApplyResult(
        success=False,
        snapshot=run.working,
        diagnostics=[
            Diagnostic(
                code="runtime.participant-execution-state-missing",
                domain="participant",
                address=policy.address,
                message="Autonomous participant execution requires typed execution-service state.",
            )
        ],
    )


def _execution_service_accepts_work(service: ParticipantExecutionServiceStateModel) -> bool:
    return service.observed_lifecycle == "running" and service.accepting_new_work and service.readiness == "ready"


def _execution_service_has_capacity(service: ParticipantExecutionServiceStateModel) -> bool:
    return service.reserved + service.in_flight < service.capacity


def _capacity_blocked_due_result(
    policy: ParticipantAutonomousExecutionRuntime,
    current_tick: int,
    run: SchedulerRunState,
) -> ApplyResult | None:
    for participant_address in policy.participant_addresses:
        key = f"{policy.address}.state.{participant_address}"
        state = ParticipantAutonomousExecutionStateModel.model_validate(
            run.working.participant_autonomous_execution_states[key]
        )
        if state.lifecycle_state == "running" and state.next_tick < current_tick:
            return cadence_missed_result(run.working, key, current_tick, state)
        due = (
            state.lifecycle_state == "running"
            and state.next_tick == current_tick
            and state.attempted_actions < policy.max_action_attempts
            and state.in_flight == 0
        )
        if due:
            return ApplyResult(
                success=False,
                snapshot=run.working,
                diagnostics=[
                    Diagnostic(
                        code="runtime.participant-execution-capacity-blocked",
                        domain="participant",
                        address=policy.address,
                        message=(
                            "Due participant work could not progress because execution-service capacity is exhausted."
                        ),
                    )
                ],
            )
    return None


def _run_serial_due(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_runtime: object,
    current_tick: int,
    cadence_ticks: int,
    activity_controls: dict[str, ParticipantActivityRandomControl],
    run: SchedulerRunState,
) -> None:
    for participant_address in policy.participant_addresses:
        run_participant_due(
            participant_due_context(
                policy,
                time_model,
                participant_runtime,
                participant_address,
                current_tick,
                cadence_ticks,
                activity_controls,
            ),
            run,
        )
        if run.failure is not None:
            break


def _run_due_policy(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_runtime: object,
    activity_controls: dict[str, ParticipantActivityRandomControl],
    run: SchedulerRunState,
) -> None:
    service_payload = run.working.participant_execution_services.get(policy.address)
    if service_payload is None:
        run.failure = _missing_execution_service_result(policy, run)
        return
    service = ParticipantExecutionServiceStateModel.model_validate(service_payload)
    if not _execution_service_accepts_work(service):
        return
    cadence_ticks = _cadence(policy, time_model)[1] if policy.profile == "participant-autonomous-execution/v1" else 0
    current_tick = _clock_tick(run.working, policy.clock_address)
    if not _execution_service_has_capacity(service):
        run.failure = _capacity_blocked_due_result(policy, current_tick, run)
        return
    if not run_policy_due_concurrently(policy, time_model, participant_runtime, current_tick, cadence_ticks, run):
        _run_serial_due(policy, time_model, participant_runtime, current_tick, cadence_ticks, activity_controls, run)


def _initialize_governed_resources(
    policies: tuple[ParticipantAutonomousExecutionRuntime, ...],
    snapshot: RuntimeSnapshot,
    resource_capabilities: object | None,
) -> ApplyResult:
    governed = tuple(policy for policy in policies if policy.profile == _RESOURCE_GOVERNED_PROFILE)
    if not governed:
        return ApplyResult(success=True, snapshot=snapshot)
    if resource_capabilities is None:
        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="runtime.participant-resource-capabilities-missing",
                    domain="participant",
                    address=governed[0].address,
                    message="Participant execution v3 requires admitted resource-budget capabilities.",
                )
            ],
        )
    return initialize_participant_resource_budgets(
        snapshot,
        governed,
        resource_capabilities,
        execution_generation=0,
    )


def _initialize_policy(
    policy: ParticipantAutonomousExecutionRuntime,
    time_model: CompiledTimeModel,
    participant_runtime: object,
    snapshot: RuntimeSnapshot,
    activity_controls: dict[str, ParticipantActivityRandomControl],
) -> ApplyResult:
    working = snapshot
    changed: list[str] = []
    failure = None
    for participant_address in policy.participant_addresses:
        participant_result = _initialize_participant(
            policy,
            time_model,
            participant_runtime,
            working,
            participant_address,
            activity_controls,
        )
        if not participant_result.success:
            failure = participant_result
            break
        working = participant_result.snapshot
        changed.extend(participant_result.changed_addresses)
    if failure is None:
        services = dict(working.participant_execution_services)
        expected_service = execution_service_state(
            policy,
            time_model,
            policy_digest=_policy_digest(policy, time_model),
        )
        existing_payload = services.get(policy.address)
        if existing_payload is not None:
            existing = ParticipantExecutionServiceStateModel.model_validate(existing_payload)
            identity = (
                existing.policy_digest,
                existing.binding_digest,
                existing.time_declaration_digest,
            )
            expected_identity = (
                expected_service.policy_digest,
                expected_service.binding_digest,
                expected_service.time_declaration_digest,
            )
            if identity != expected_identity:
                failure = ApplyResult(
                    success=False,
                    snapshot=working,
                    diagnostics=[
                        Diagnostic(
                            code="runtime.participant-execution-state-conflict",
                            domain="participant",
                            address=policy.address,
                            message=(
                                "Existing participant execution service state does not match "
                                "the admitted policy, bindings, or shared-time declaration."
                            ),
                        )
                    ],
                )
        else:
            services[policy.address] = expected_service.model_dump(mode="json")
            working = working.with_entries(
                dict(working.entries),
                participant_execution_services=services,
            )
            changed.append(policy.address)
    return failure or ApplyResult(
        success=True,
        snapshot=working,
        changed_addresses=list(dict.fromkeys(changed)),
    )


class ParticipantScheduler:
    """Deterministically selects due actions and delegates native execution."""

    @staticmethod
    def initialize(
        policies: Iterable[ParticipantAutonomousExecutionRuntime],
        time_model: CompiledTimeModel,
        participant_runtime: object,
        snapshot: RuntimeSnapshot,
        activity_controls: dict[str, ParticipantActivityRandomControl] | None = None,
        resource_capabilities: object | None = None,
    ) -> ApplyResult:
        working = snapshot
        resolved_activity_controls = activity_controls or {}
        changed: list[str] = []
        normalized_policies = tuple(policies)
        initialized = _initialize_governed_resources(normalized_policies, working, resource_capabilities)
        if not initialized.success:
            return initialized
        working = initialized.snapshot
        for policy in normalized_policies:
            policy_result = _initialize_policy(
                policy,
                time_model,
                participant_runtime,
                working,
                resolved_activity_controls,
            )
            if not policy_result.success:
                return policy_result
            working = policy_result.snapshot
            changed.extend(policy_result.changed_addresses)
        return ApplyResult(
            success=True,
            snapshot=working,
            changed_addresses=list(dict.fromkeys(changed)),
        )

    @staticmethod
    def run_due(
        policies: Iterable[ParticipantAutonomousExecutionRuntime],
        time_model: CompiledTimeModel,
        participant_runtime: object,
        snapshot: RuntimeSnapshot,
        activity_controls: dict[str, ParticipantActivityRandomControl] | None = None,
        *,
        cancellation_sink: Callable[[ApplyResult], None] | None = None,
        invocation_tools: InvocationToolActionConfiguration | None = None,
    ) -> ApplyResult:
        """Run each due action; on cancellation, give the settled state to ``cancellation_sink``.

        A cancelled concurrent batch has fenced its indeterminate native work in the
        scheduler state. The commit owner must commit that state before the
        cancellation leaves it, or the same action ids become due again. Tool
        actions hosted by any dispatched invocation commit on both paths.
        """

        run = SchedulerRunState(working=snapshot, diagnostics=[], changed=[], invocation_tools=invocation_tools)
        resolved_activity_controls = activity_controls or {}
        try:
            for policy in policies:
                _run_due_policy(policy, time_model, participant_runtime, resolved_activity_controls, run)
                if run.failure is not None or run.deferred_cancellation is not None:
                    break
            if run.deferred_cancellation is not None:
                raise run.deferred_cancellation
        except CancelledError:
            # Cleanup: hand the settled scheduler state to its commit owner, then propagate (ADR-116 H4).
            settle_invocation_tool_sessions(run)
            if cancellation_sink is not None:
                cancellation_sink(run.result())
            raise
        settle_invocation_tool_sessions(run)
        return run.result()

    @staticmethod
    def reset_clock(
        policies: Iterable[ParticipantAutonomousExecutionRuntime],
        time_model: CompiledTimeModel,
        participant_runtime: object,
        snapshot: RuntimeSnapshot,
        clock_address: str,
        *,
        reset_participants: bool = True,
        activity_controls: dict[str, ParticipantActivityRandomControl] | None = None,
    ) -> ApplyResult:
        """Reset bound episodes and scheduler counters at a shared-clock segment boundary."""

        working = snapshot
        resolved_activity_controls = activity_controls or {}
        changed: list[str] = []
        segment, _ = clock_coordinate(snapshot, clock_address)
        for policy in policies:
            if policy.clock_address != clock_address:
                continue
            policy_result = reset_policy_at_clock(
                policy,
                time_model,
                participant_runtime,
                working,
                segment,
                reset_participants,
                resolved_activity_controls,
            )
            if not policy_result.success:
                return policy_result
            working = policy_result.snapshot
            changed.extend(policy_result.changed_addresses)
        return ApplyResult(
            success=True,
            snapshot=working,
            changed_addresses=list(dict.fromkeys(changed)),
        )

    @staticmethod
    def set_clock_lifecycle(
        snapshot: RuntimeSnapshot,
        clock_address: str,
        lifecycle_state: str,
    ) -> ApplyResult:
        return set_execution_clock_lifecycle(
            snapshot,
            clock_address,
            lifecycle_state,
        )


__all__ = ["ParticipantScheduler"]
