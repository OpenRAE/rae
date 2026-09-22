"""Revision-safe state updates for bounded concurrent participant execution."""

from __future__ import annotations

from collections.abc import Callable
from copy import copy, deepcopy
from dataclasses import fields
from typing import TYPE_CHECKING

from raes_contracts.contracts import ParticipantAutonomousExecutionStateModel
from raes_contracts.contracts.participant_execution import ParticipantExecutionServiceStateModel
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ParticipantAutonomousExecutionRuntime

from .participant_action_validation import _PROTECTED_SCHEDULER_SNAPSHOT_FIELDS

if TYPE_CHECKING:
    from .participant_scheduler_types import SchedulerRunState, _DueActionContext


_MISSING = object()

# Native participant execution receives the complete portable snapshot, and the
# serial scheduler commits that complete validated result.  Concurrent commit
# therefore needs an explicit owner for every RuntimeSnapshot field: silently
# ignoring a newly added field would make serial and concurrent execution mean
# different things. Shared time, scheduler state and execution-service accounting
# are runtime-owned; a native result must carry their reserved predecessor
# unchanged and the serialized scheduler applies their deltas itself.
_PROTECTED_SCHEDULER_FIELDS = frozenset(_PROTECTED_SCHEDULER_SNAPSHOT_FIELDS)
_BACKEND_MAPPING_FIELDS = (
    "entries",
    "orchestration_results",
    "orchestration_history",
    "evaluation_results",
    "evaluation_history",
    "proposition_truth_results",
    "participant_episode_results",
    "participant_episode_history",
    "participant_episode_closure_records",
    "participant_behavior_history",
    "participant_control_history",
    "participant_crossing_history",
    "information_state_history",
    "participant_resource_budget_states",
    "participant_resource_pool_states",
    "participant_resource_budget_events",
    "shared_state_records",
    "shared_state_history",
    "joint_action_records",
    "time_management_contexts",
    "metadata",
)
_BACKEND_VALUE_FIELDS = (
    "realization_provenance",
    "realization_observations",
    "realization_envelope",
)
_OWNED_SNAPSHOT_FIELDS = frozenset((*_PROTECTED_SCHEDULER_FIELDS, *_BACKEND_MAPPING_FIELDS, *_BACKEND_VALUE_FIELDS))
_DECLARED_SNAPSHOT_FIELDS = frozenset(field.name for field in fields(RuntimeSnapshot))


def _assert_snapshot_field_ownership(
    declared_fields: frozenset[str],
    owned_fields: frozenset[str],
) -> None:
    """Fail when a snapshot field has no explicit concurrent owner."""

    missing = sorted(declared_fields - owned_fields)
    stale = sorted(owned_fields - declared_fields)
    if not missing and not stale:
        return
    raise RuntimeError(
        f"concurrent participant snapshot ownership is incomplete (missing={missing!r}, stale={stale!r})"
    )


_assert_snapshot_field_ownership(_DECLARED_SNAPSHOT_FIELDS, _OWNED_SNAPSHOT_FIELDS)


def _changed_mapping(
    base: dict[str, object],
    incoming: dict[str, object],
) -> dict[str, object]:
    changed: dict[str, object] = {}
    for key in base.keys() | incoming.keys():
        base_value = base.get(key, _MISSING)
        incoming_value = incoming.get(key, _MISSING)
        if base_value != incoming_value:
            changed[key] = incoming_value
    return changed


def _merge_mapping_revision_checked(
    *,
    base: dict[str, object],
    current: dict[str, object],
    incoming: dict[str, object],
    field_name: str,
) -> dict[str, object]:
    # The frozen result envelope is already detached from the backend, but the
    # committed snapshot must not retain aliases to either the result or an
    # older authoritative snapshot.  Deep-copying the selected values makes the
    # commit a true ownership transfer rather than a shallow dict replacement.
    merged = deepcopy(current)
    changed = _changed_mapping(base, incoming)
    for key in sorted(changed):
        value = changed[key]
        current_value = current.get(key, _MISSING)
        base_value = base.get(key, _MISSING)
        if current_value != base_value:
            # Mapping keys are backend-controlled. Keep diagnostics stable and
            # never copy a key (which may contain participant data) into them.
            # Any second write is a concurrent conflict, including an
            # apparently identical value. Treating identical writes as a
            # successful merge would assert commutativity without a governed
            # action-contract merge rule (ADR-054 section 8).
            raise ValueError(f"concurrent participant commit conflict in {field_name}")
        if value is _MISSING:
            merged.pop(key, None)
        else:
            merged[key] = deepcopy(value)
    return merged


def _merge_value_revision_checked(
    *,
    base: object,
    current: object,
    incoming: object,
    field_name: str,
) -> object:
    if incoming == base:
        return deepcopy(current)
    if current != base:
        raise ValueError(f"concurrent participant commit conflict in {field_name}")
    return deepcopy(incoming)


def _require_protected_fields_unchanged(
    base: RuntimeSnapshot,
    incoming: RuntimeSnapshot,
) -> None:
    for field_name in sorted(_PROTECTED_SCHEDULER_FIELDS):
        if getattr(incoming, field_name) != getattr(base, field_name):
            raise ValueError(f"concurrent participant result changed protected field {field_name}")


def _merge_concurrent_action_snapshot(
    base: RuntimeSnapshot,
    current: RuntimeSnapshot,
    incoming: RuntimeSnapshot,
) -> RuntimeSnapshot:
    """Three-way merge every backend-owned field without replacing scheduler state."""

    staged = _stage_concurrent_action_snapshot(base, current, incoming)
    return _materialize_concurrent_snapshot(staged)


def _stage_concurrent_action_snapshot(
    base: RuntimeSnapshot,
    current: RuntimeSnapshot,
    incoming: RuntimeSnapshot,
) -> RuntimeSnapshot:
    """Merge backend-owned fields while deferring the full scheduler-state scan."""

    _require_protected_fields_unchanged(base, incoming)
    staged = copy(current)
    for field_name in _BACKEND_MAPPING_FIELDS:
        base_mapping = getattr(base, field_name)
        incoming_mapping = getattr(incoming, field_name)
        merged = getattr(current, field_name)
        if incoming_mapping != base_mapping:
            merged = _merge_mapping_revision_checked(
                base=dict(base_mapping),
                current=dict(merged),
                incoming=dict(incoming_mapping),
                field_name=field_name,
            )
        setattr(staged, field_name, merged)
    for field_name in _BACKEND_VALUE_FIELDS:
        base_value = getattr(base, field_name)
        incoming_value = getattr(incoming, field_name)
        merged_value = getattr(current, field_name)
        if incoming_value != base_value:
            merged_value = _merge_value_revision_checked(
                base=base_value,
                current=merged_value,
                incoming=incoming_value,
                field_name=field_name,
            )
        setattr(staged, field_name, merged_value)
    # Validate every backend-owned RuntimeSnapshot invariant for this result,
    # but omit the protected participant maps already checked above. The full
    # participant-state oracle runs once when the completed batch materializes.
    staged.with_entries(
        dict(staged.entries),
        participant_autonomous_execution_states={},
        participant_execution_services={},
    )
    return staged


def _with_concurrent_scheduler_updates(
    snapshot: RuntimeSnapshot,
    *,
    states: dict[str, dict[str, object]] | None = None,
    services: dict[str, dict[str, object]] | None = None,
) -> RuntimeSnapshot:
    """Apply already model-validated scheduler updates without a global rescan."""

    staged = copy(snapshot)
    if states is not None:
        staged.participant_autonomous_execution_states = states
    if services is not None:
        staged.participant_execution_services = services
    return staged


def _materialize_concurrent_snapshot(snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
    """Detach and fully validate a completed concurrent batch."""

    return snapshot.with_entries(
        dict(snapshot.entries),
        participant_autonomous_execution_states=dict(snapshot.participant_autonomous_execution_states),
        participant_execution_services=dict(snapshot.participant_execution_services),
    )


def _freeze_concurrent_results(
    results: tuple[object, ...],
    copier: Callable[[object], object],
) -> tuple[list[object], list[bool]]:
    """Detach result envelopes while preserving repeated-object identity."""

    frozen_results: list[object] = []
    freeze_invalid: list[bool] = []
    frozen_by_identity: dict[int, tuple[object, object]] = {}
    for result in results:
        cached = frozen_by_identity.get(id(result))
        if cached is not None and cached[0] is result:
            frozen_results.append(cached[1])
            freeze_invalid.append(False)
            continue
        try:
            frozen = copier(result)
            frozen_results.append(frozen)
            freeze_invalid.append(False)
            frozen_by_identity[id(result)] = (result, frozen)
        except Exception:  # NOSONAR - reject only the unfreezable paired result
            frozen_results.append(None)
            freeze_invalid.append(True)
    return frozen_results, freeze_invalid


def _reserve_concurrent_actions(
    run: SchedulerRunState,
    contexts: tuple[_DueActionContext, ...],
) -> None:
    states = dict(run.working.participant_autonomous_execution_states)
    for context in contexts:
        state = ParticipantAutonomousExecutionStateModel.model_validate(states[context.key])
        states[context.key] = state.model_copy(
            update={
                "attempted_actions": state.attempted_actions + 1,
                "in_flight": state.in_flight + 1,
            }
        ).model_dump(mode="json")
    services = dict(run.working.participant_execution_services)
    for policy_address in {context.policy.address for context in contexts}:
        payload = services.get(policy_address)
        if payload is None:
            continue
        service = ParticipantExecutionServiceStateModel.model_validate(payload)
        count = sum(1 for context in contexts if context.policy.address == policy_address)
        available = service.capacity - service.reserved - service.in_flight
        if count > available:
            raise ValueError("concurrent participant batch exceeds available execution-service capacity")
        services[policy_address] = service.model_copy(
            update={
                "in_flight": service.in_flight + count,
                "quiescent": False,
            }
        ).model_dump(mode="json")
    run.working = _with_concurrent_scheduler_updates(
        run.working,
        states=states,
        services=services,
    )


def _finish_concurrent_service_state(
    run: SchedulerRunState,
    policy_address: str,
    completed_count: int,
) -> None:
    services = dict(run.working.participant_execution_services)
    payload = services.get(policy_address)
    if payload is None:
        return
    service = ParticipantExecutionServiceStateModel.model_validate(payload)
    if completed_count > service.in_flight:
        raise ValueError("concurrent participant completion exceeds execution-service in-flight work")
    remaining = service.in_flight - completed_count
    services[policy_address] = service.model_copy(
        update={
            "in_flight": remaining,
            "quiescent": service.reserved == 0 and remaining == 0,
        }
    ).model_dump(mode="json")
    run.working = _with_concurrent_scheduler_updates(
        run.working,
        services=services,
    )


def _available_concurrent_capacity(
    policy: ParticipantAutonomousExecutionRuntime,
    run: SchedulerRunState,
) -> int:
    payload = run.working.participant_execution_services.get(policy.address)
    if payload is None:
        return 0
    service = ParticipantExecutionServiceStateModel.model_validate(payload)
    return min(policy.max_in_flight, max(0, service.capacity - service.reserved - service.in_flight))
