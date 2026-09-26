"""Exact pre-effect dispatch and recovery routing for mixed runtimes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from raes_contracts.contracts.mixed_composition import AllocationTargetKind, MixedCompositionAllocationModel
from raes_contracts.contracts.mixed_runtime import (
    MixedCompositionRuntimeEventModel,
    MixedCompositionRuntimeStateModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .control_plane_security import ControlPlaneIdentity
from .mixed_runtime_edge import MixedEdgeExecutionCapture
from .mixed_runtime_edge_execution import _mapped_edge_method, _stage_readback_method
from .mixed_runtime_state import append_runtime_events, runtime_state
from .participant_crossing_mediation import PreparedParticipantCrossing
from .participant_flow_sink import ParticipantFlowSinkDecision
from .registry import RuntimeTarget


@dataclass(frozen=True)
class PreparedMixedActionDispatch:
    """Exact admitted provider and the durable pre-effect composition cut."""

    method: Callable[..., object]
    address: str
    snapshot: RuntimeSnapshot
    expected_history_heads: dict[str, str | None]
    committed_history_heads: dict[str, str | None]
    capture: MixedEdgeExecutionCapture | None = None
    stage_readback: Callable[[ApplyResult], None] | None = None


@dataclass(frozen=True)
class PreparedMixedLifecycleDispatch:
    """Exact participant provider plus its durable pre-effect lifecycle cut."""

    method: Callable[..., object]
    address: str
    snapshot: RuntimeSnapshot
    expected_history_heads: dict[str, str | None]
    committed_history_heads: dict[str, str | None]


def _runtime_event_fields(
    state: MixedCompositionRuntimeStateModel,
    **coordinates: object,
) -> dict[str, object]:
    return {
        "run_id": state.run_id,
        "plan_id": state.plan_id,
        "plan_entry_id": state.plan_entry_id,
        "profile_id": state.profile_id,
        "profile_digest": state.profile_digest,
        "phase_id": state.phase_id,
        "phase_revision": state.phase_revision,
        "active_component_ids": state.active_component_ids,
        "active_allocation_ids": state.active_allocation_ids,
        "active_edge_ids": state.active_edge_ids,
        **coordinates,
    }


def _active_allocation(
    binding: object,
    state: MixedCompositionRuntimeStateModel,
    kind: AllocationTargetKind,
    address: str,
) -> MixedCompositionAllocationModel:
    matches = [
        allocation
        for allocation in binding.profile.allocations.values()
        if allocation.allocation_id in state.active_allocation_ids
        and allocation.target_kind == kind
        and allocation.target_address == address
        and state.phase_id in allocation.phase_ids
    ]
    if len(matches) != 1:
        raise ValueError(f"mixed composition requires exactly one active {kind} allocation for {address}")
    return matches[0]


def mixed_policy_allocation(
    control_plane: object,
    intent: object,
) -> MixedCompositionAllocationModel | None:
    """Resolve the active allocation whose admitted capability governs a crossing."""

    binding = getattr(control_plane, "_mixed_runtime", None)
    if binding is None:
        return None
    state = runtime_state(binding, control_plane._snapshot)
    action_address = getattr(intent, "action_or_projection_ref", None)
    if isinstance(action_address, str):
        candidates = [
            allocation
            for allocation in binding.profile.allocations.values()
            if allocation.allocation_id in state.active_allocation_ids
            and allocation.target_kind in {"action-family", "observation-source", "crossing"}
            and allocation.target_address == action_address
            and state.phase_id in allocation.phase_ids
        ]
    else:
        candidates = []
    if not candidates:
        participant_address = getattr(intent, "participant_address", "")
        candidates = [_active_allocation(binding, state, "participant", participant_address)]
    if len(candidates) != 1:
        return None
    return candidates[0]


def prepare_mixed_lifecycle_dispatch(
    control_plane: object,
    request: object,
    method_name: str,
    operation_id: str,
    identity: object,
) -> PreparedMixedLifecycleDispatch:
    """Resolve and persist an exact participant lifecycle provider before effect."""

    binding = getattr(control_plane, "_mixed_runtime", None)
    if binding is None:
        raise ValueError("mixed runtime is not configured")
    lifecycle_identity = _require_lifecycle_identity(control_plane, identity)
    state = runtime_state(binding, control_plane._snapshot)
    participant_address = getattr(request, "participant_address", "")
    allocation = _active_allocation(binding, state, "participant", participant_address)
    method = _lifecycle_method(binding, state, allocation, lifecycle_identity, participant_address, method_name)
    common = _runtime_event_fields(
        state,
        allocation_id=allocation.allocation_id,
        component_id=allocation.provider_component_id,
        control_event_ref=allocation.controller_ref,
        order_ref=f"order:lifecycle:{operation_id}",
    )
    decision = MixedCompositionRuntimeEventModel(
        event_id=f"composition:{operation_id}:lifecycle-decision",
        event_kind="lifecycle-decision",
        disposition="permitted",
        predecessor_event_id=state.history_head,
        **common,
    )
    attempt = MixedCompositionRuntimeEventModel(
        event_id=f"composition:{operation_id}:lifecycle-attempt",
        event_kind="lifecycle-attempt",
        disposition="committed",
        predecessor_event_id=decision.event_id,
        **common,
    )
    snapshot = append_runtime_events(binding, control_plane._snapshot, state, [decision, attempt])
    history_key = f"mixed_composition_history:{state.run_id}"
    return PreparedMixedLifecycleDispatch(
        method=method,
        address=f"runtime.component.{allocation.provider_component_id}.participant.{method_name}",
        snapshot=snapshot,
        expected_history_heads={history_key: state.history_head},
        committed_history_heads={history_key: attempt.event_id},
    )


def _require_lifecycle_identity(control_plane: object, identity: object) -> ControlPlaneIdentity:
    if not isinstance(identity, ControlPlaneIdentity):
        raise PermissionError("mixed participant lifecycle requires an authenticated identity")
    if identity.target_name is not None and identity.target_name != control_plane.target_name:
        raise PermissionError("mixed participant lifecycle identity is not authorized for this target")
    return identity


def _lifecycle_method(
    binding: object,
    state: MixedCompositionRuntimeStateModel,
    allocation: MixedCompositionAllocationModel,
    identity: ControlPlaneIdentity,
    participant_address: str,
    method_name: str,
) -> Callable[..., object]:
    controller_bindings = {
        item.controller_ref
        for item in identity.participant_control_subjects
        if item.participant_address == participant_address
    }
    if allocation.controller_ref not in controller_bindings:
        raise PermissionError("mixed participant controller differs from the authenticated subject binding")
    features = {requirement.feature for requirement in allocation.feature_requirements}
    if "participant_ingress_admission" not in features:
        raise ValueError("mixed participant provider lacks the admitted lifecycle capability")
    if allocation.provider_component_id not in state.active_component_ids:
        raise ValueError("mixed participant provider is not active in the committed phase")
    runtime = binding.components[allocation.provider_component_id].target.participant_runtime
    method = getattr(runtime, method_name, None)
    if not callable(method):
        raise ValueError("mixed participant provider does not expose the admitted lifecycle method")
    return method


def record_mixed_lifecycle_result(
    control_plane: object,
    snapshot: RuntimeSnapshot,
    operation_id: str,
    *,
    success: bool,
) -> RuntimeSnapshot:
    """Append a lifecycle result/failure without rewriting its provider cut."""

    binding = control_plane._mixed_runtime
    state = runtime_state(binding, snapshot)
    attempt = MixedCompositionRuntimeEventModel.model_validate(snapshot.mixed_composition_history[state.run_id][-1])
    if attempt.event_id != f"composition:{operation_id}:lifecycle-attempt" or attempt.event_kind != "lifecycle-attempt":
        raise ValueError("mixed lifecycle result requires its exact durable attempt fact")
    common = _runtime_event_fields(
        state,
        allocation_id=attempt.allocation_id,
        component_id=attempt.component_id,
        control_event_ref=attempt.control_event_ref,
        order_ref=attempt.order_ref,
    )
    result = MixedCompositionRuntimeEventModel(
        event_id=f"composition:{operation_id}:lifecycle-result",
        event_kind="lifecycle-result",
        disposition="succeeded" if success else "failed",
        predecessor_event_id=state.history_head,
        **common,
    )
    events = [result]
    if not success:
        events.append(
            MixedCompositionRuntimeEventModel(
                event_id=f"composition:{operation_id}:failure",
                event_kind="failure",
                disposition="failed",
                predecessor_event_id=result.event_id,
                **common,
            )
        )
    return append_runtime_events(binding, snapshot, state, events)


def prepare_mixed_action_dispatch(
    control_plane: object,
    request: ParticipantActionAdmissionRequest,
    crossing: PreparedParticipantCrossing,
    sink_decision: ParticipantFlowSinkDecision | None,
) -> PreparedMixedActionDispatch | None:
    """Resolve and persist the exact provider decision before its effect call."""

    binding = getattr(control_plane, "_mixed_runtime", None)
    if binding is None:
        return None
    state = runtime_state(binding, crossing.next_snapshot)
    participant = _active_allocation(binding, state, "participant", request.participant_address)
    allocation = _active_allocation(binding, state, "action-family", request.action_contract_address)
    _require_action_authority(participant, allocation, crossing, request, state)
    edge = _action_edge(binding, state, participant, allocation)
    decision = crossing.decision
    if decision is None:
        raise ValueError("mixed action dispatch requires a committed crossing decision")
    if edge is not None:
        _require_edge_crossing_authority(edge, crossing, request, sink_decision)
    if edge is not None and edge.edge_id not in binding.edge_bindings:
        raise ValueError("mixed action dispatch requires an executable edge binding")
    if edge is not None:
        installed = binding.edge_bindings[edge.edge_id]
        if (
            installed.source_action_address != request.action_contract_address
            or installed.destination_action_address != allocation.target_address
        ):
            raise ValueError("mixed destination action differs from admitted policy and provider allocation")
    method = _action_method(binding, allocation)
    operation_id = crossing.record.receipt.operation_id
    capture = None
    stage_readback = None
    if edge is not None:
        capture = MixedEdgeExecutionCapture()
        installed = binding.edge_bindings[edge.edge_id]
        method = _mapped_edge_method(
            binding,
            edge,
            installed,
            method,
            operation_id,
            capture,
        )
        stage_readback = _stage_readback_method(binding, edge, installed, request, operation_id, capture)
    event_base = _runtime_event_fields(
        state,
        allocation_id=allocation.allocation_id,
        component_id=allocation.provider_component_id,
        edge_id=edge.edge_id if edge is not None else None,
        control_event_ref=allocation.controller_ref,
        crossing_event_ref=decision.event_id,
        policy_decision_ref=decision.occurrence.policy.policy_decision_ref,
        mapping_ref=edge.time_binding.mapping_address if edge is not None else None,
        order_ref=f"order:{decision.occurrence.policy.effective_order}",
        mapping_loss_refs=[edge.mapping_loss.limitation_ref] if edge is not None else [],
        evidence_refs=list(crossing.intent.required_evidence_refs),
    )
    decision_event = MixedCompositionRuntimeEventModel(
        event_id=f"composition:{operation_id}:decision",
        event_kind="decision",
        disposition="permitted",
        predecessor_event_id=state.history_head,
        **event_base,
    )
    attempt_event = MixedCompositionRuntimeEventModel(
        event_id=f"composition:{operation_id}:attempt",
        event_kind="attempt",
        disposition="committed",
        predecessor_event_id=decision_event.event_id,
        **event_base,
    )
    snapshot = append_runtime_events(binding, crossing.next_snapshot, state, [decision_event, attempt_event])
    history_key = f"mixed_composition_history:{state.run_id}"
    expected = {**crossing.expected_history_heads, history_key: state.history_head}
    committed = {**crossing.record.result_history_heads, history_key: attempt_event.event_id}
    return PreparedMixedActionDispatch(
        method=method,
        address=f"runtime.component.{allocation.provider_component_id}.participant.admit-action",
        snapshot=snapshot,
        expected_history_heads=expected,
        committed_history_heads=committed,
        capture=capture,
        stage_readback=stage_readback,
    )


def _require_edge_crossing_authority(
    edge: object,
    crossing: PreparedParticipantCrossing,
    request: ParticipantActionAdmissionRequest,
    sink_decision: ParticipantFlowSinkDecision | None,
) -> None:
    """Join the admitted edge to the live crossing and final-sink cut."""

    decision = crossing.decision
    assert decision is not None
    occurrence = decision.occurrence
    if (
        not isinstance(sink_decision, ParticipantFlowSinkDecision)
        or not sink_decision.permitted
        or not sink_decision.decision_id
        or edge.crossing_subject != crossing.governed_subject
        or edge.crossing_subject != occurrence.subject
        or edge.audience_scope_ref != crossing.intent.audience_scope_ref
        or edge.audience_scope_ref != occurrence.audience_scope_ref
        or edge.policy != occurrence.policy
        or edge.controller_ref != crossing.intent.controller_ref
        or edge.controller_ref != occurrence.controller_ref
        or edge.authority_ref not in occurrence.authority_basis_refs
        or edge.disclosure_authority_ref not in occurrence.authority_basis_refs
        or crossing.intent.action_or_projection_ref != request.action_contract_address
    ):
        raise ValueError("mixed edge differs from the authorized crossing or final-sink cut")


def _require_action_authority(
    participant: MixedCompositionAllocationModel,
    allocation: MixedCompositionAllocationModel,
    crossing: PreparedParticipantCrossing,
    request: ParticipantActionAdmissionRequest,
    state: MixedCompositionRuntimeStateModel,
) -> None:
    if participant.controller_ref != allocation.controller_ref:
        raise ValueError("mixed participant and action allocations disagree on controller authority")
    if participant.routing_ref != allocation.routing_ref:
        raise ValueError("mixed participant and action allocations disagree on routing authority")
    controller_bindings = {
        item.controller_ref
        for item in crossing.identity.participant_control_subjects
        if item.participant_address == request.participant_address
    }
    if allocation.controller_ref not in controller_bindings:
        raise PermissionError("mixed action controller differs from the authenticated subject binding")
    if allocation.action_authority_ref not in crossing.intent.authority_basis_refs:
        raise PermissionError("mixed action authority is absent from the committed crossing cut")
    if allocation.provider_component_id not in state.active_component_ids:
        raise ValueError("mixed action provider is not active in the committed phase")


def _action_edge(
    binding: object,
    state: MixedCompositionRuntimeStateModel,
    participant: MixedCompositionAllocationModel,
    allocation: MixedCompositionAllocationModel,
) -> object | None:
    if participant.provider_component_id == allocation.provider_component_id:
        return None
    edges = [
        candidate
        for candidate in binding.profile.edges.values()
        if candidate.edge_id in state.active_edge_ids
        and candidate.source_component_id == participant.provider_component_id
        and candidate.target_component_id == allocation.provider_component_id
        and state.phase_id in candidate.phase_ids
    ]
    if len(edges) != 1:
        raise ValueError("mixed action dispatch requires one active admitted topology edge")
    return edges[0]


def _action_method(binding: object, allocation: MixedCompositionAllocationModel) -> Callable[..., object]:
    runtime = binding.components[allocation.provider_component_id].target.participant_runtime
    method = getattr(runtime, "admit_action", None)
    if not callable(method):
        raise ValueError("mixed action provider has no admitted participant runtime")
    return method


def mixed_recovery_target(control_plane: object, operation_id: str) -> RuntimeTarget | None:
    """Recover the exact component from its durable pre-effect attempt fact."""

    binding = getattr(control_plane, "_mixed_runtime", None)
    if binding is None:
        target = getattr(control_plane, "_target", None)
    else:
        event = _recovery_attempt(control_plane, binding, operation_id)
        target = _recovery_component(binding, event) if event is not None else None
    return target


def _recovery_attempt(
    control_plane: object,
    binding: object,
    operation_id: str,
) -> MixedCompositionRuntimeEventModel | None:
    history = control_plane._snapshot.mixed_composition_history.get(binding.entry.run_id, ())
    matches = [
        MixedCompositionRuntimeEventModel.model_validate(event)
        for event in history
        if event.get("event_id")
        in {
            f"composition:{operation_id}:attempt",
            f"composition:{operation_id}:lifecycle-attempt",
        }
        and event.get("event_kind") in {"attempt", "lifecycle-attempt"}
    ]
    return matches[0] if len(matches) == 1 else None


def _recovery_component(
    binding: object,
    event: MixedCompositionRuntimeEventModel,
) -> RuntimeTarget | None:
    allocation = binding.profile.allocations.get(event.allocation_id or "")
    invalid = (
        allocation is None
        or allocation.provider_component_id != event.component_id
        or allocation.allocation_id not in event.active_allocation_ids
        or allocation.provider_component_id not in event.active_component_ids
    )
    component = None if invalid else binding.components.get(allocation.provider_component_id)
    return None if component is None else component.target


__all__ = (
    "PreparedMixedActionDispatch",
    "PreparedMixedLifecycleDispatch",
    "mixed_recovery_target",
    "mixed_policy_allocation",
    "prepare_mixed_action_dispatch",
    "prepare_mixed_lifecycle_dispatch",
    "record_mixed_lifecycle_result",
)
