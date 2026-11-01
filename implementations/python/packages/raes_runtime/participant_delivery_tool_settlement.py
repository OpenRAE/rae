"""Atomic child outcome, behavior history and audit publication."""

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

from .control_plane_store import terminal_operation_audit
from .participant_crossing_state_cut import expected_participant_history_heads
from .participant_result_contracts import participant_runtime_state_contract_diagnostics


def settle_delivery_tool(port, entry, settlement, outcome):
    plane = port._plane
    plane._require_state_writer()
    plane._reload_derived_state()
    if settlement is ParticipantToolActionSettlement.INDETERMINATE:
        port.has_unresolved_effects = True
        port._registry.mark_unresolved()
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
                plane._snapshot.time_model_state.clocks[shared.binding.clock_address],
                native_execution="not_dispatched"
                if settlement is ParticipantToolActionSettlement.WITHHELD
                else "reported",
            )
        )
    events = (*events[:-1], events[-1].model_copy(update={"temporal_assessments": assessments}))
    histories = dict(plane._snapshot.participant_behavior_history)
    histories[port.participant_address] = [
        *histories.get(port.participant_address, ()),
        *(participant_behavior_event_payload(event) for event in events),
    ]
    snapshot = plane._snapshot.with_entries(dict(plane._snapshot.entries), participant_behavior_history=histories)
    require_participant_temporal_history(snapshot)
    if participant_runtime_state_contract_diagnostics(snapshot):
        raise ValueError("delivery tool settlement violates participant state contracts")
    terminal = port._ledger.settlement_record(entry.record, settlement, outcome)
    terminal = replace(
        terminal,
        decision_history_heads=expected_participant_history_heads(plane._snapshot, port.participant_address),
        result_history_heads=expected_participant_history_heads(snapshot, port.participant_address),
    )
    try:
        plane._commit_participant_transition(
            expected_history_heads=terminal.decision_history_heads,
            snapshot=snapshot,
            record=terminal,
            audit_event=terminal_operation_audit(terminal),
        )
    except Exception:
        # The durability owner already read back the record, snapshot and actor audit.
        # Accept only the exact confirmed terminal cut; never repeat the write or effect.
        if (
            getattr(plane, "_durability_poisoned", False)
            or plane._operations.get(entry.action_instance_id) != terminal
            or expected_participant_history_heads(plane._snapshot, port.participant_address)
            != terminal.result_history_heads
        ):
            raise
    entry.record, entry.state, entry.settlement = terminal, "settled", settlement
    entry.action_result, entry.settled_at = outcome, settled_at
    if settlement is not ParticipantToolActionSettlement.INDETERMINATE:
        port._registry.release(entry.action_instance_id)
