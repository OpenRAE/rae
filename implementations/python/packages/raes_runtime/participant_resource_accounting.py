"""Commit, release, and reconciliation for participant resource reservations."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceBudgetEventModel,
    ParticipantResourceBudgetStateModel,
    ParticipantResourcePoolStateModel,
    participant_resource_pool_state_ref,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_resource_pool_ledger import (
    commit as commit_pool_allocation,
)
from .participant_resource_pool_ledger import (
    reconcile as reconcile_pool_allocation,
)
from .participant_resource_pool_ledger import (
    release as release_pool_allocation,
)

_STALE_GENERATION_CODE = "runtime.participant-resource-stale-generation"
_SETTLED_CODE = "runtime.participant-resource-reservation-settled"


@dataclass
class _CommitMutation:
    snapshot: RuntimeSnapshot
    operation_id: str
    execution_generation: int
    evidence_refs: tuple[str, ...]
    states: dict[str, dict[str, object]]
    pool_states: dict[str, dict[str, object]]
    events: dict[str, dict[str, object]]


def _diagnostic(code: str, policy_address: str, message: str) -> Diagnostic:
    return Diagnostic(
        code=code,
        domain="participant-runtime",
        address=f"/participant_resource_budgets/{policy_address}",
        message=message,
    )


def _state(payload: Mapping[str, object]) -> ParticipantResourceBudgetStateModel:
    return ParticipantResourceBudgetStateModel.model_validate(payload)


def _event(payload: Mapping[str, object]) -> ParticipantResourceBudgetEventModel:
    return ParticipantResourceBudgetEventModel.model_validate(payload)


def _pool_state(payload: Mapping[str, object]) -> ParticipantResourcePoolStateModel:
    return ParticipantResourcePoolStateModel.model_validate(payload)


def _payload(
    model: ParticipantResourceBudgetStateModel
    | ParticipantResourcePoolStateModel
    | ParticipantResourceBudgetEventModel,
) -> dict[str, object]:
    return model.model_dump(mode="json")


def _pool_ref_for_state(state: ParticipantResourceBudgetStateModel) -> str:
    return participant_resource_pool_state_ref(
        pool_ref=state.pool_ref,
        owner_kind=state.owner_kind,
        owner_ref=state.owner_ref,
        resource_kind=state.resource_kind,
        unit=state.unit,
        accounting_mode=state.accounting_mode,
        meter_profile_ref=state.meter_profile_ref,
    )


def _settlement_ids(reservation: ParticipantResourceBudgetEventModel) -> tuple[str, str]:
    prefix = f"{reservation.operation_id}:{reservation.budget_state_ref}"
    return f"{prefix}:commit", f"{prefix}:release"


def _settlement_failure(
    snapshot: RuntimeSnapshot,
    reservation: ParticipantResourceBudgetEventModel,
    current: ParticipantResourceBudgetStateModel,
    *,
    execution_generation: int,
    competing_settlement_id: str,
    events: Mapping[str, Mapping[str, object]],
    verb: str,
) -> ApplyResult | None:
    """Fence one settlement to its reservation generation and settle it exactly once."""

    if len({execution_generation, reservation.execution_generation, current.generation}) != 1:
        code = _STALE_GENERATION_CODE
        message = f"operation {reservation.operation_id} cannot {verb} across a generation boundary"
    elif competing_settlement_id in events:
        code = _SETTLED_CODE
        message = f"operation {reservation.operation_id} already settled resource budget {reservation.budget_id}"
    else:
        return None
    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[_diagnostic(code, reservation.policy_address, message)],
    )


def _operation_reservations(
    events: Mapping[str, Mapping[str, object]],
    operation_id: str,
) -> tuple[ParticipantResourceBudgetEventModel, ...]:
    return tuple(
        _event(payload)
        for payload in events.values()
        if payload.get("operation_id") == operation_id and payload.get("transition") == "reserve"
    )


def _missing_reservation_result(
    snapshot: RuntimeSnapshot,
    operation_id: str,
    events: Mapping[str, Mapping[str, object]],
) -> ApplyResult:
    committed = any(
        payload.get("operation_id") == operation_id and payload.get("transition") == "commit"
        for payload in events.values()
    )
    diagnostics = (
        []
        if committed
        else [
            _diagnostic(
                "runtime.participant-resource-reservation-missing",
                "unknown",
                f"operation {operation_id} has no resource reservation",
            )
        ]
    )
    return ApplyResult(
        success=committed,
        snapshot=snapshot,
        diagnostics=diagnostics,
    )


def _valid_measurement_vector(
    reservations: tuple[ParticipantResourceBudgetEventModel, ...],
    measured_quantities: Mapping[str, int],
    evidence_refs: tuple[str, ...],
) -> bool:
    expected_refs = {reservation.budget_state_ref for reservation in reservations}
    return (
        set(measured_quantities) == expected_refs
        and bool(evidence_refs)
        and all(
            0 <= measured_quantities[reservation.budget_state_ref] <= reservation.requested
            for reservation in reservations
        )
    )


def _invalid_measurement_result(
    snapshot: RuntimeSnapshot,
    policy_address: str,
) -> ApplyResult:
    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[
            _diagnostic(
                "runtime.participant-resource-measurement-invalid",
                policy_address,
                "resource commit requires an exact, bounded measured vector and native evidence",
            )
        ],
    )


def _commit_reservation(
    mutation: _CommitMutation,
    reservation: ParticipantResourceBudgetEventModel,
    measured: int,
) -> ApplyResult | None:
    commit_id, release_id = _settlement_ids(reservation)
    if commit_id in mutation.events:
        return None
    current = _state(mutation.states[reservation.budget_state_ref])
    failure = _settlement_failure(
        mutation.snapshot,
        reservation,
        current,
        execution_generation=mutation.execution_generation,
        competing_settlement_id=release_id,
        events=mutation.events,
        verb="commit",
    )
    if failure is not None:
        return failure
    committed = current.model_copy(
        update={
            "reserved": max(0, current.reserved - reservation.requested),
            "cumulative_use": current.cumulative_use + measured,
            "last_event_ref": commit_id,
            "evidence_refs": tuple(dict.fromkeys((*current.evidence_refs, *mutation.evidence_refs))),
        }
    )
    event = ParticipantResourceBudgetEventModel(
        event_id=commit_id,
        operation_id=mutation.operation_id,
        budget_state_ref=reservation.budget_state_ref,
        budget_id=reservation.budget_id,
        policy_address=reservation.policy_address,
        owner_ref=current.owner_ref,
        pool_ref=current.pool_ref,
        execution_generation=mutation.execution_generation,
        transition="commit",
        disposition="committed",
        requested=reservation.requested,
        measured=measured,
        resource_kind=current.resource_kind,
        unit=current.unit,
        meter_profile_ref=current.meter_profile_ref,
        predecessor_event_ref=reservation.event_id,
        evidence_refs=mutation.evidence_refs,
    )
    mutation.states[reservation.budget_state_ref] = _payload(committed)
    physical_pool_ref = _pool_ref_for_state(current)
    physical_pool = _pool_state(mutation.pool_states[physical_pool_ref])
    mutation.pool_states[physical_pool_ref] = _payload(
        commit_pool_allocation(
            physical_pool,
            current.state_ref,
            reserved=reservation.requested,
            measured=measured,
        )
    )
    mutation.events[commit_id] = _payload(event)
    return None


def _commit_success_result(mutation: _CommitMutation) -> ApplyResult:
    return ApplyResult(
        success=True,
        snapshot=mutation.snapshot.with_entries(
            dict(mutation.snapshot.entries),
            participant_resource_budget_states=mutation.states,
            participant_resource_pool_states=mutation.pool_states,
            participant_resource_budget_events=mutation.events,
        ),
    )


def commit_participant_resource_reservation(
    snapshot: RuntimeSnapshot,
    *,
    operation_id: str,
    execution_generation: int,
    measured_quantities: Mapping[str, int],
    evidence_refs: tuple[str, ...],
) -> ApplyResult:
    """Commit trusted, complete measurements for an operation exactly once."""

    events = dict(snapshot.participant_resource_budget_events)
    reservations = _operation_reservations(events, operation_id)
    if not reservations:
        result = _missing_reservation_result(snapshot, operation_id, events)
    elif not _valid_measurement_vector(reservations, measured_quantities, evidence_refs):
        result = _invalid_measurement_result(snapshot, reservations[0].policy_address)
    else:
        mutation = _CommitMutation(
            snapshot=snapshot,
            operation_id=operation_id,
            execution_generation=execution_generation,
            evidence_refs=evidence_refs,
            states=dict(snapshot.participant_resource_budget_states),
            pool_states=dict(snapshot.participant_resource_pool_states),
            events=events,
        )
        failure = None
        for reservation in reservations:
            failure = _commit_reservation(
                mutation,
                reservation,
                measured_quantities[reservation.budget_state_ref],
            )
            if failure is not None:
                break
        result = failure or _commit_success_result(mutation)
    return result


def release_participant_resource_reservation(
    snapshot: RuntimeSnapshot,
    *,
    operation_id: str,
    execution_generation: int,
    evidence_refs: tuple[str, ...],
) -> ApplyResult:
    """Release an uncommitted complete vector after failed or untrusted execution."""

    events = dict(snapshot.participant_resource_budget_events)
    reservations = _operation_reservations(events, operation_id)
    if not reservations:
        return ApplyResult(success=True, snapshot=snapshot)
    states = dict(snapshot.participant_resource_budget_states)
    pool_states = dict(snapshot.participant_resource_pool_states)
    for reservation in reservations:
        commit_id, release_id = _settlement_ids(reservation)
        if release_id in events:
            continue
        current = _state(states[reservation.budget_state_ref])
        failure = _settlement_failure(
            snapshot,
            reservation,
            current,
            execution_generation=execution_generation,
            competing_settlement_id=commit_id,
            events=events,
            verb="release",
        )
        if failure is not None:
            return failure
        released = current.model_copy(
            update={
                "reserved": max(0, current.reserved - reservation.requested),
                "last_event_ref": release_id,
                "evidence_refs": tuple(dict.fromkeys((*current.evidence_refs, *evidence_refs))),
            }
        )
        event = ParticipantResourceBudgetEventModel(
            event_id=release_id,
            operation_id=operation_id,
            budget_state_ref=reservation.budget_state_ref,
            budget_id=reservation.budget_id,
            policy_address=reservation.policy_address,
            owner_ref=current.owner_ref,
            pool_ref=current.pool_ref,
            execution_generation=execution_generation,
            transition="release",
            disposition="released",
            requested=reservation.requested,
            resource_kind=current.resource_kind,
            unit=current.unit,
            meter_profile_ref=current.meter_profile_ref,
            predecessor_event_ref=reservation.event_id,
            evidence_refs=evidence_refs,
        )
        states[current.state_ref] = _payload(released)
        physical_pool_ref = _pool_ref_for_state(current)
        physical_pool = _pool_state(pool_states[physical_pool_ref])
        pool_states[physical_pool_ref] = _payload(
            release_pool_allocation(physical_pool, current.state_ref, reservation.requested)
        )
        events[release_id] = _payload(event)
    return ApplyResult(
        success=True,
        snapshot=snapshot.with_entries(
            dict(snapshot.entries),
            participant_resource_budget_states=states,
            participant_resource_pool_states=pool_states,
            participant_resource_budget_events=events,
        ),
    )


def reconcile_participant_resource_budgets(
    snapshot: RuntimeSnapshot,
    *,
    policy_address: str,
    current_generation: int,
    next_generation: int,
    boundary: str | Collection[str],
    evidence_refs: tuple[str, ...] = (),
) -> ApplyResult:
    """Fence a reset generation and reconcile only dimensions owned by a crossed boundary.

    ``boundary`` names every reset boundary the transition crosses. A dimension
    is cleared only when its declared reset owner is one of them; every other
    owner keeps its use across the new generation (EBM-03).
    """

    if next_generation <= current_generation:
        raise ValueError("resource-budget reconciliation must advance generation")
    crossed = frozenset((boundary,) if isinstance(boundary, str) else boundary)
    if not crossed:
        raise ValueError("resource-budget reconciliation must name at least one crossed reset boundary")
    states = dict(snapshot.participant_resource_budget_states)
    pool_states = dict(snapshot.participant_resource_pool_states)
    events = dict(snapshot.participant_resource_budget_events)
    selected = [
        (state_ref, _state(payload))
        for state_ref, payload in states.items()
        if payload.get("policy_address") == policy_address
    ]
    for state_ref, current in selected:
        if current.generation != current_generation:
            return ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=[
                    _diagnostic(
                        _STALE_GENERATION_CODE,
                        policy_address,
                        f"resource budget {state_ref} cannot reconcile from generation {current_generation}",
                    )
                ],
            )
    for state_ref, current in selected:
        event_id = f"reconcile:{policy_address}:{next_generation}:{state_ref}"
        clears = current.reset in crossed
        reconciled = current.model_copy(
            update={
                "generation": next_generation,
                "reserved": 0,
                "current_use": 0 if clears else current.current_use,
                "cumulative_use": 0 if clears else current.cumulative_use,
                "reconciliation_status": "reconciled",
                "last_event_ref": event_id,
                "evidence_refs": tuple(dict.fromkeys((*current.evidence_refs, *evidence_refs))),
            }
        )
        event = ParticipantResourceBudgetEventModel(
            event_id=event_id,
            operation_id=f"reconcile:{policy_address}:{next_generation}",
            budget_state_ref=state_ref,
            budget_id=current.budget_id,
            policy_address=policy_address,
            owner_ref=current.owner_ref,
            pool_ref=current.pool_ref,
            execution_generation=next_generation,
            transition="reconcile",
            disposition="reconciled",
            requested=0,
            measured=0,
            resource_kind=current.resource_kind,
            unit=current.unit,
            meter_profile_ref=current.meter_profile_ref,
            predecessor_event_ref=current.last_event_ref,
            evidence_refs=evidence_refs,
        )
        states[state_ref] = _payload(reconciled)
        physical_pool_ref = _pool_ref_for_state(current)
        physical_pool = _pool_state(pool_states[physical_pool_ref])
        pool_states[physical_pool_ref] = _payload(
            reconcile_pool_allocation(
                physical_pool,
                current,
                generation=next_generation,
                clears=clears,
            )
        )
        events[event_id] = _payload(event)
    return ApplyResult(
        success=True,
        snapshot=snapshot.with_entries(
            dict(snapshot.entries),
            participant_resource_budget_states=states,
            participant_resource_pool_states=pool_states,
            participant_resource_budget_events=events,
        ),
    )


__all__ = (
    "commit_participant_resource_reservation",
    "reconcile_participant_resource_budgets",
    "release_participant_resource_reservation",
)
