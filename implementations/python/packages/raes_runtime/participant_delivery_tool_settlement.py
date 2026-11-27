"""Atomic child outcome, behavior history and audit publication."""

from __future__ import annotations

from dataclasses import replace

from raes_contracts.contracts.participant_runtime import ParticipantDeliveryToolContextModel
from raes_contracts.contracts.participant_temporal_history import (
    assess_temporal_guarantee,
    require_participant_temporal_history,
)
from raes_contracts.participant_binding_events import (
    participant_behavior_event_payload,
    participant_implementation_actor_provenance,
)
from raes_contracts.participant_tool_actions import (
    ParticipantToolActionRecord,
    ParticipantToolActionSettlement,
    participant_tool_history_events,
)
from raes_contracts.timestamps import isoformat_z


def settle_delivery_tool(
    port: object, entry: object, settlement: ParticipantToolActionSettlement, outcome: object
) -> None:
    plane = port.delivery_tools_context().plane
    plane.delivery_require_state_writer()
    plane.delivery_reload_derived_state()
    if settlement is ParticipantToolActionSettlement.INDETERMINATE:
        port.has_unresolved_effects = True
        port.delivery_tools_context().registry.mark_unresolved()
    admission = entry.admission
    actual = replace(
        entry.request,
        action_contract_address=admission.action_contract_address,
        observation_boundary_address=admission.observation_boundary_address,
        target_addresses=admission.target_addresses,
    )
    settled_at = isoformat_z(plane.wall_clock())
    record = ParticipantToolActionRecord(
        request=actual,
        action_instance_id=entry.action_instance_id,
        admission_ordinal=entry.ordinal,
        settlement=settlement,
        action_result=outcome,
        admitted_at=entry.admitted_at,
        settled_at=settled_at,
    )
    context = ParticipantDeliveryToolContextModel(
        semantics="participant-invocation-tool-actions/v2",
        invocation_id=port.invocation_action_instance_id,
        delivery_operation_ref=port.invocation.delivery_operation_ref,
        tool_affordance_address=actual.tool_affordance_address,
        tool_call_id=actual.tool_call_id,
        admission_ordinal=entry.ordinal,
        settlement=settlement.value,
        execution_scope_ref=port.execution_scope_ref,
        execution_generation=port.execution_generation,
    )
    events = participant_tool_history_events(
        record,
        context,
        list(admission.temporal_contexts),
        actor_provenance=participant_implementation_actor_provenance(port.invocation.implementation_selection),
    )
    assessments = _temporal_assessments(plane, admission, settlement, outcome)
    events = (*events[:-1], events[-1].model_copy(update={"temporal_assessments": assessments}))
    histories = dict(plane.delivery_snapshot.participant_behavior_history)
    histories[port.participant_address] = [
        *histories.get(port.participant_address, ()),
        *(participant_behavior_event_payload(event) for event in events),
    ]
    snapshot = plane.delivery_snapshot.with_entries(
        dict(plane.delivery_snapshot.entries), participant_behavior_history=histories
    )
    require_participant_temporal_history(snapshot)
    if plane.delivery_participant_runtime_state_contract_diagnostics(snapshot):
        raise ValueError("delivery tool settlement violates participant state contracts")
    terminal = port.delivery_tools_context().ledger.settlement_record(entry.record, settlement, outcome)
    terminal = replace(
        terminal,
        decision_history_heads=plane.delivery_expected_participant_history_heads(
            plane.delivery_snapshot, port.participant_address
        ),
        result_history_heads=plane.delivery_expected_participant_history_heads(snapshot, port.participant_address),
    )
    try:
        plane.delivery_commit_participant_transition(
            expected_history_heads=terminal.decision_history_heads,
            snapshot=snapshot,
            record=terminal,
            audit_event=plane.delivery_terminal_operation_audit(terminal),
        )
    except Exception:
        # The durability owner already read back the record, snapshot and actor audit.
        # Accept only the exact confirmed terminal cut; never repeat the write or effect.
        if not _terminal_confirmed(plane, entry, terminal):
            raise
    entry.record, entry.state, entry.settlement = terminal, "settled", settlement
    entry.action_result, entry.settled_at = outcome, settled_at
    if settlement is not ParticipantToolActionSettlement.INDETERMINATE:
        port.delivery_tools_context().registry.release(entry.action_instance_id)


def _temporal_assessments(
    plane: object, admission: object, settlement: ParticipantToolActionSettlement, outcome: object
) -> list[object]:
    assessments = []
    for temporal in admission.temporal_contexts:
        shared = temporal.shared_time
        if shared is None:
            continue
        evidence = (
            admission.temporal_evidence if shared.binding.temporal_kind == "dwell" else tuple(outcome.temporal_evidence)
        )
        assessments.append(
            assess_temporal_guarantee(
                shared,
                evidence,
                admission.observation_boundary_address,
                plane.delivery_snapshot.time_model_state.clocks[shared.binding.clock_address],
                native_execution="not_dispatched"
                if settlement is ParticipantToolActionSettlement.WITHHELD
                else "reported",
            )
        )
    return assessments


def _terminal_confirmed(plane: object, entry: object, terminal: object) -> bool:
    if getattr(plane, "_durability_poisoned", False):
        return False
    if plane.delivery_operations.get(entry.action_instance_id) != terminal:
        return False
    heads = plane.delivery_expected_participant_history_heads(
        plane.delivery_snapshot, entry.request.participant_address
    )
    return heads == terminal.result_history_heads
