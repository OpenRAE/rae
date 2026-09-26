"""Executable mixed-edge and stage-evidence regressions for issue #1355."""

from __future__ import annotations

from dataclasses import replace

import pytest
import raes_runtime.control_plane_recovery as recovery_module
from participant_crossing_fixtures import ACTION, PARTICIPANT, admission_request, behavior, evidence, identity
from raes_backend_protocols.recovery_observation import RecoveryEffectClassification
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import seal_mixed_composition_profile
from raes_contracts.contracts.time_model import ClockTransitionEventModel, RuntimeClockStateModel, TimeRuntimeStateModel
from raes_contracts.operation_lifecycle import OperationAdmissionContext
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    ApplyResult,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_health import control_plane_readiness
from raes_runtime.control_plane_recovery import (
    IndeterminateResolutionDisposition,
    unresolved_indeterminate_operation_ids_from_records,
)
from raes_runtime.control_plane_store import ControlPlaneOperationRecord, InMemoryControlPlaneStore, NewClaimRejected
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.mixed_runtime_dispatch import mixed_recovery_target
from raes_runtime.mixed_runtime_edge import MixedEdgeExecutionBinding, MixedTimeCoordinationEvidence
from raes_runtime.mixed_runtime_edge_execution import _require_time_grant
from raes_runtime.mixed_runtime_phase import _require_handoff_time_grant
from raes_runtime.participant_crossing_mediation import validate_persisted_crossing_history
from raes_runtime.time_coordinator import ReferenceTimeRuntime
from sem233_flow_sink_fixtures import permit_resolver
from test_issue_1016_mixed_runtime_coordination import (
    _admitted_binding,
    _runtime_mixed_profile,
    _runtime_profile,
    _runtime_staged_profile,
    _staged_time_snapshot,
)


@pytest.mark.parametrize("store_kind", ["memory", "local"])
def test_phase_and_action_claims_exclude_each_other_at_the_store(tmp_path, store_kind) -> None:
    store = InMemoryControlPlaneStore() if store_kind == "memory" else LocalControlPlaneStore(tmp_path / "claims")
    lease = store.admit_runtime(target_scope="target:1355", run_scope="run:run-1355") if store_kind == "local" else None
    history_key = "mixed_composition_history:run-1355"

    def record(operation_id, kind):
        context = OperationAdmissionContext(
            actor_id="actor-1355",
            authorization_scope=("participant-control",),
            target_scope="target:1355",
            run_scope="run:run-1355",
            operation_kind=kind,
            request_commitment="sha256:" + "a" * 64,
        )
        receipt = OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at="2026-09-24T00:00:00Z",
            accepted=True,
            context=context,
        )
        return ControlPlaneOperationRecord(
            receipt=receipt,
            status=OperationStatus(
                operation_id=operation_id,
                domain=receipt.domain,
                state=OperationState.RUNNING,
                submitted_at=receipt.submitted_at,
                updated_at=receipt.submitted_at,
                context=context,
            ),
            decision_history_heads={history_key: None},
            result_history_heads={history_key: None},
        )

    phase = record("phase-1355", OperationKind.COMPOSITION_PHASE)
    action = record("action-1355", OperationKind.PARTICIPANT_ACTION)
    assert store.claim_record(phase) == phase
    with pytest.raises(NewClaimRejected):
        store.claim_record(action)
    store.save_record(replace(phase, status=replace(phase.status, state=OperationState.SUCCEEDED)))
    assert store.claim_record(action) == action
    with pytest.raises(NewClaimRejected):
        store.claim_record(record("action-1355-b", OperationKind.PARTICIPANT_ACTION))
    with pytest.raises(NewClaimRejected):
        store.claim_record(record("phase-1355-b", OperationKind.COMPOSITION_PHASE))
    store.save_record(replace(action, status=replace(action.status, state=OperationState.SUCCEEDED)))
    assert store.claim_record(record("action-1355-c", OperationKind.PARTICIPANT_ACTION)).receipt.operation_id == (
        "action-1355-c"
    )
    if lease is not None:
        lease.close()


def test_backend_success_does_not_invent_delivery_or_observation() -> None:
    binding, run_id, runtimes = _admitted_binding(_runtime_profile)
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

    receipt = plane.admit_participant_action(
        behavior(),
        admission_request(),
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="unproven-delivery",
    )

    assert receipt.accepted
    assert runtimes["sim"].admission_count == 1
    kinds = [event["event_kind"] for event in plane.snapshot.mixed_composition_history[run_id]]
    assert kinds[-3:] == ["decision", "attempt", "result"]
    assert "delivery" not in kinds
    assert "observation" not in kinds


def test_unbound_mixed_edge_refuses_before_bridge_or_provider_call() -> None:
    binding, run_id, runtimes = _admitted_binding(_runtime_mixed_profile)
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

    with pytest.raises(ValueError, match="executable edge binding"):
        plane.admit_participant_action(
            behavior(),
            admission_request(),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="unbound-edge",
        )

    assert all(runtime.admission_count == 0 for runtime in runtimes.values())


def test_metadata_only_edge_binding_cannot_admit_mixed_execution() -> None:
    original, _, _ = _admitted_binding(_runtime_mixed_profile)

    with pytest.raises(TypeError, match="executable edge binding"):
        replace(original, edge_bindings={"edge.sim-to-emu": object()})


def _executable_edge_plane(
    *,
    deliver: bool = True,
    observe: bool = True,
    execution_status: str = "succeeded",
    fail_after_provider: bool = False,
    change_terminal_requirement: bool = False,
    stage_readback: bool = True,
    stale_time_readback: bool = False,
    stale_post_time_readback: bool = False,
    destination_action_address: str = ACTION,
    fail_stage: str | None = None,
    profile_factory=_runtime_mixed_profile,
):
    binding, run_id, runtimes = _admitted_binding(profile_factory)
    edge = binding.profile.edges["edge.sim-to-emu"]
    declaration = binding.context.time_models[edge.time_binding.time_model_ref]
    time_runtime = ReferenceTimeRuntime()
    initial_time = time_runtime.initialize(declaration, RuntimeSnapshot()).snapshot
    if stale_time_readback or stale_post_time_readback:
        original_readback = time_runtime.state

        def stale_readback(snapshot):
            state = original_readback(snapshot)
            if stale_time_readback or runtimes["emu"].admission_count > 0:
                return state.model_copy(update={"declaration_digest": "sha256:" + "0" * 64})
            return state

        time_runtime.state = stale_readback
    calls: list[str] = []

    def map_action(request):
        calls.append("map")
        return replace(
            request,
            action_contract_address=destination_action_address,
            requires_terminal_outcome=(
                not request.requires_terminal_outcome
                if change_terminal_requirement
                else request.requires_terminal_outcome
            ),
        )

    def coordinate(operation_id, admitted_edge, time_state):
        calls.append("coordinate")
        assert admitted_edge.edge_id == edge.edge_id
        source = time_state.clocks[edge.time_binding.source_clock_address].coordinate
        destination = time_state.clocks[edge.time_binding.target_clock_address].coordinate
        return {
            "operation_id": operation_id,
            "mapping_ref": edge.time_binding.mapping_address,
            "ordering_basis": edge.time_binding.ordering_basis,
            "order_ref": f"order:bridge:{operation_id}",
            "comparison": "ordered",
            "source_coordinate": source.model_dump(mode="json"),
            "destination_coordinate": destination.model_dump(mode="json"),
            "mapping_evidence_refs": ["evidence:mapping-call"],
            "timing_evidence_refs": ["evidence:time-grant", "evidence:edge-realization"],
        }

    def bridge(operation_id, request, snapshot, provider_call):
        calls.append("bridge")
        result = provider_call(request, snapshot)
        if fail_after_provider:
            raise RuntimeError("private bridge outcome")
        return result, {
            "operation_id": operation_id,
            "bridge_ref": edge.routing_ref,
            "bridge_version": "1",
            "bridge_digest": "sha256:" + "1" * 64,
            "source_action_address": ACTION,
            "destination_action_address": destination_action_address,
            "execution_status": execution_status,
            "execution_evidence_refs": ["evidence:backend-readback"],
            "delivery_evidence_refs": ["evidence:destination-receipt"] if deliver else [],
            "observation_evidence_refs": ["evidence:participant-readback"] if observe else [],
            "mapping_loss_refs": [edge.mapping_loss.limitation_ref],
            "cessation_evidence_refs": ["evidence:provider-cessation"] if execution_status == "failed" else [],
        }

    def delivery_readback(operation_id, _snapshot):
        calls.append("delivery-readback")
        if fail_stage == "delivery":
            raise RuntimeError("private destination readback failure")
        return {
            "operation_id": operation_id,
            "destination_component_id": edge.target_component_id,
            "receipt_ref": f"receipt:{operation_id}",
            "evidence_refs": ["evidence:destination-receipt"],
        }

    def observation_readback(operation_id, _snapshot):
        calls.append("observation-readback")
        if fail_stage == "observation":
            raise RuntimeError("private participant readback failure")
        return {
            "operation_id": operation_id,
            "participant_address": PARTICIPANT,
            "audience_ref": edge.audience_scope_ref,
            "observation_ref": f"observation:{operation_id}",
            "evidence_refs": ["evidence:participant-readback"],
        }

    executable = MixedEdgeExecutionBinding(
        edge_id=edge.edge_id,
        bridge_ref=edge.routing_ref,
        bridge_version="1",
        bridge_digest="sha256:" + "1" * 64,
        source_action_address=ACTION,
        destination_action_address=destination_action_address,
        mapping_ref=edge.time_binding.mapping_address,
        mapping_loss_ref=edge.mapping_loss.limitation_ref,
        time_runtime=time_runtime,
        map_action=map_action,
        coordinate=coordinate,
        bridge=bridge,
        delivery_readback=delivery_readback if stage_readback else None,
        observation_readback=observation_readback if stage_readback else None,
    )
    binding = replace(binding, edge_bindings={edge.edge_id: executable})
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        store=InMemoryControlPlaneStore(snapshot=initial_time),
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
    return plane, run_id, runtimes, calls, time_runtime


def test_mapped_edge_invokes_bridge_and_records_distinct_evidenced_stages() -> None:
    plane, run_id, runtimes, calls, _ = _executable_edge_plane()

    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="mapped"
    )

    assert receipt.accepted
    assert calls == ["map", "coordinate", "bridge", "delivery-readback", "observation-readback"]
    assert runtimes["sim"].admission_count == 0
    assert runtimes["emu"].admission_count == 1
    kinds = [event["event_kind"] for event in plane.snapshot.mixed_composition_history[run_id]]
    assert kinds[-6:] == ["decision", "attempt", "result", "delivery", "observation", "weakening"]
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "succeeded"
    assert mixed_recovery_target(plane, receipt.operation_id) is plane._mixed_runtime.components["emu"].target


def _reversed_microstep_state(state, source_address, destination_address):
    clocks = dict(state.clocks)
    for address, microstep in ((source_address, 2), (destination_address, 1)):
        clock = clocks[address]
        coordinate = clock.coordinate.model_copy(update={"microstep": microstep})
        event = ClockTransitionEventModel(
            sequence=clock.sequence + 1,
            kind="advance",
            previous=clock.coordinate,
            resulting=coordinate,
            resulting_state=clock.state,
        )
        clocks[address] = RuntimeClockStateModel.model_validate(
            clock.model_copy(
                update={
                    "coordinate": coordinate,
                    "sequence": event.sequence,
                    "history": [*clock.history, event],
                }
            ).model_dump(mode="python")
        )
    return TimeRuntimeStateModel.model_validate(state.model_copy(update={"clocks": clocks}).model_dump(mode="python"))


def test_edge_order_grant_rejects_reversed_microsteps() -> None:
    binding, _, _ = _admitted_binding(_runtime_mixed_profile)
    edge = binding.profile.edges["edge.sim-to-emu"]
    declaration = binding.context.time_models[edge.time_binding.time_model_ref]
    state = ReferenceTimeRuntime().initialize(declaration, RuntimeSnapshot()).snapshot.time_model_state
    assert state is not None
    state = _reversed_microstep_state(
        state, edge.time_binding.source_clock_address, edge.time_binding.target_clock_address
    )
    installed = _executable_edge_plane()[0]._mixed_runtime.edge_bindings[edge.edge_id]
    grant = MixedTimeCoordinationEvidence.model_validate(installed.coordinate("operation:microsteps", edge, state))

    with pytest.raises(ValueError, match="governed order is unsupported"):
        _require_time_grant(
            grant,
            "operation:microsteps",
            edge,
            declaration.mappings[edge.time_binding.mapping_address],
            state,
        )


def test_handoff_order_grant_rejects_reversed_microsteps() -> None:
    binding, _, _ = _admitted_binding(_runtime_staged_profile)
    transition = binding.profile.transitions["transition.sim-to-emu"]
    installed = binding.handoff_bindings[transition.transition_id]
    declaration = binding.context.time_models[installed.time_model_ref]
    state = _staged_time_snapshot(binding).time_model_state
    assert state is not None
    state = _reversed_microstep_state(state, installed.source_clock_address, installed.destination_clock_address)
    grant = MixedTimeCoordinationEvidence.model_validate(
        installed.coordinate("operation:microsteps", transition, state)
    )

    with pytest.raises(ValueError, match="handoff time coordination is unsupported"):
        _require_handoff_time_grant(installed, grant, "operation:microsteps", declaration, state, transition)


@pytest.mark.parametrize("stale_post_time_readback", [False, True])
def test_rejected_backend_result_cannot_publish_successful_mixed_stages(stale_post_time_readback) -> None:
    plane, run_id, runtimes, calls, _ = _executable_edge_plane(stale_post_time_readback=stale_post_time_readback)
    runtime = runtimes["emu"]
    original = runtime.admit_action

    def invalid_changed_address(request, snapshot):
        result = original(request, snapshot)
        return replace(result, changed_addresses=["participant.unadmitted-address"])

    runtime.admit_action = invalid_changed_address
    receipt = plane.admit_participant_action(
        behavior(),
        admission_request(),
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="invalid-result",
    )

    assert runtime.admission_count == 1
    assert calls == ["map", "coordinate", "bridge"]
    assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.INDETERMINATE
    events = plane.snapshot.mixed_composition_history[run_id]
    result = next(event for event in events if event["event_kind"] == "result")
    assert result["disposition"] == "indeterminate"
    assert "evidence:backend-readback" not in result["evidence_refs"]
    assert not any(event["event_kind"] in {"delivery", "observation", "weakening"} for event in events)


def test_failed_bridge_retains_correlation_and_cessation_evidence() -> None:
    plane, run_id, runtimes, _, _ = _executable_edge_plane(deliver=False, observe=False, execution_status="failed")
    runtime = runtimes["emu"]
    original = runtime.admit_action

    def provider_failure(request, snapshot):
        original(request, snapshot)
        return ApplyResult(success=False, snapshot=snapshot)

    runtime.admit_action = provider_failure
    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="failed"
    )

    assert runtime.admission_count == 1
    assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.FAILED
    events = plane.snapshot.mixed_composition_history[run_id]
    assert [event["event_kind"] for event in events[-2:]] == ["result", "failure"]
    assert all("evidence:provider-cessation" in event["evidence_refs"] for event in events[-2:])


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("audience_scope_ref", "audience:unrelated"),
        ("crossing_subject.subject_ref", "participant-action-admission:unrelated"),
        ("policy.policy_decision_ref", "decision:unrelated"),
        ("disclosure_authority_ref", "authority:unrelated"),
    ],
)
def test_edge_authority_must_match_the_authorized_crossing_before_effect(field, replacement) -> None:
    def changed_edge_profile():
        profile = _runtime_mixed_profile()
        fields = profile.model_dump(mode="python", exclude={"profile_digest"})
        edge = fields["edges"]["edge.sim-to-emu"]
        if "." in field:
            parent, child = field.split(".", 1)
            edge[parent][child] = replacement
        else:
            edge[field] = replacement
        return seal_mixed_composition_profile(**fields)

    plane, _, runtimes, calls, _ = _executable_edge_plane(profile_factory=changed_edge_profile)
    with pytest.raises(ValueError, match="mixed edge differs from the authorized crossing"):
        plane.admit_participant_action(
            behavior(),
            admission_request(),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="wrong-audience",
        )

    assert all(runtime.admission_count == 0 for runtime in runtimes.values())
    assert calls == []


def test_partial_bridge_report_preserves_execution_evidence_without_delivery_claim() -> None:
    plane, run_id, runtimes, _, _ = _executable_edge_plane(deliver=False, observe=False, execution_status="partial")

    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="partial"
    )

    assert runtimes["emu"].admission_count == 1
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "indeterminate"
    events = plane.snapshot.mixed_composition_history[run_id]
    execution = next(event for event in events if event["event_kind"] == "result")
    assert execution["disposition"] == "indeterminate"
    assert "evidence:backend-readback" in execution["evidence_refs"]
    assert not any(event["event_kind"] in {"delivery", "observation"} for event in events)


def test_bridge_report_without_destination_readback_cannot_claim_delivery() -> None:
    plane, run_id, runtimes, calls, _ = _executable_edge_plane(stage_readback=False)

    receipt = plane.admit_participant_action(
        behavior(),
        admission_request(),
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="no-readback",
    )

    assert runtimes["emu"].admission_count == 1
    assert calls == ["map", "coordinate", "bridge"]
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "indeterminate"
    assert not any(
        event["event_kind"] in {"delivery", "observation"} for event in plane.snapshot.mixed_composition_history[run_id]
    )


@pytest.mark.parametrize("fail_stage", ["delivery", "observation"])
def test_later_readback_failure_retains_known_execution_and_only_confirmed_stages(fail_stage) -> None:
    plane, run_id, runtimes, _, _ = _executable_edge_plane(fail_stage=fail_stage)

    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key=fail_stage
    )

    assert runtimes["emu"].admission_count == 1
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "indeterminate"
    events = plane.snapshot.mixed_composition_history[run_id]
    result = next(event for event in events if event["event_id"] == f"composition:{receipt.operation_id}:result")
    assert result["disposition"] == "indeterminate"
    assert "evidence:backend-readback" in result["evidence_refs"]
    kinds = [event["event_kind"] for event in events]
    assert ("delivery" in kinds) is (fail_stage == "observation")
    assert "observation" not in kinds
    assert "weakening" in kinds
    assert (
        plane._mixed_runtime.profile.edges["edge.sim-to-emu"].mapping_loss.limitation_ref in result["mapping_loss_refs"]
    )


def test_stale_time_readback_refuses_before_bridge_or_provider() -> None:
    plane, run_id, runtimes, calls, _ = _executable_edge_plane(stale_time_readback=True)

    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="stale-time"
    )

    assert calls == ["map"]
    assert all(runtime.admission_count == 0 for runtime in runtimes.values())
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "failed"
    assert "delivery" not in [event["event_kind"] for event in plane.snapshot.mixed_composition_history[run_id]]
    events = plane.snapshot.mixed_composition_history[run_id]
    assert events[-1]["event_kind"] == "failure"
    assert events[-2]["event_kind"] == "result"
    assert events[-2]["mapping_loss_refs"] == []
    assert events[-3]["mapping_loss_refs"] == [
        plane._mixed_runtime.profile.edges["edge.sim-to-emu"].mapping_loss.limitation_ref
    ]


def test_post_execution_stale_time_keeps_backend_evidence_without_governed_order() -> None:
    plane, run_id, runtimes, _, _ = _executable_edge_plane(stale_post_time_readback=True)

    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="post-stale"
    )

    assert runtimes["emu"].admission_count == 1
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "indeterminate"
    result = next(
        event
        for event in plane.snapshot.mixed_composition_history[run_id]
        if event["event_id"] == f"composition:{receipt.operation_id}:result"
    )
    assert result["disposition"] == "indeterminate"
    assert "evidence:backend-readback" in result["evidence_refs"]
    assert not result["order_ref"].startswith("order:bridge:")
    assert not any(
        event["event_kind"] in {"delivery", "observation", "weakening"}
        for event in plane.snapshot.mixed_composition_history[run_id]
    )


def test_timestamp_only_edge_cannot_claim_governed_order() -> None:
    def timestamp_profile():
        source = _runtime_mixed_profile()
        fields = source.model_dump(mode="python", exclude={"profile_digest"})
        fields["edges"]["edge.sim-to-emu"]["time_binding"]["ordering_basis"] = "wall_clock_only"
        return seal_mixed_composition_profile(**fields)

    plane, run_id, runtimes, calls, _ = _executable_edge_plane(profile_factory=timestamp_profile)

    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="weak-clock"
    )

    assert calls == ["map", "coordinate"]
    assert all(runtime.admission_count == 0 for runtime in runtimes.values())
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "failed"
    assert "delivery" not in [event["event_kind"] for event in plane.snapshot.mixed_composition_history[run_id]]


def test_unknown_bridge_outcome_is_indeterminate_and_replay_never_reinvokes() -> None:
    plane, run_id, runtimes, calls, _ = _executable_edge_plane(fail_after_provider=True)
    action_behavior = behavior()
    request = admission_request()
    caller = identity()
    crossing = evidence()

    receipt = plane.admit_participant_action(
        action_behavior,
        request,
        identity=caller,
        crossing_evidence=crossing,
        idempotency_key="unknown-bridge",
    )
    replay = plane.admit_participant_action(
        action_behavior,
        request,
        identity=caller,
        crossing_evidence=crossing,
        idempotency_key="unknown-bridge",
    )

    assert replay.operation_id == receipt.operation_id
    assert runtimes["emu"].admission_count == 1
    assert calls == ["map", "coordinate", "bridge"]
    assert plane.get_operation(receipt.operation_id, identity=caller).state.value == "indeterminate"
    assert plane.snapshot.mixed_composition_history[run_id][-1]["disposition"] == "indeterminate"
    assert "private bridge outcome" not in repr(plane.get_operation(receipt.operation_id, identity=caller).diagnostics)


def test_mapping_cannot_expand_the_authorized_action_carrier() -> None:
    plane, _, runtimes, calls, _ = _executable_edge_plane(change_terminal_requirement=True)

    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="bad-map"
    )

    assert receipt.accepted
    assert calls == ["map"]
    assert all(runtime.admission_count == 0 for runtime in runtimes.values())
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "failed"


@pytest.mark.parametrize("mutator", ["mapper", "bridge"])
def test_mutable_action_carrier_cannot_escape_authorized_mapping(mutator) -> None:
    plane, _, runtimes, _, _ = _executable_edge_plane()
    binding = plane._mixed_runtime
    assert binding is not None
    edge = binding.edge_bindings["edge.sim-to-emu"]
    original_map, original_bridge = edge.map_action, edge.bridge

    def mutating_map(request):
        request.implementation_manifest.constraints["unauthorized"] = "injected"
        return original_map(request)

    def mutating_bridge(operation_id, request, snapshot, provider_call):
        request.implementation_manifest.constraints["unauthorized"] = "injected"
        return original_bridge(operation_id, request, snapshot, provider_call)

    changed = replace(
        edge,
        map_action=mutating_map if mutator == "mapper" else original_map,
        bridge=mutating_bridge if mutator == "bridge" else original_bridge,
    )
    plane._mixed_runtime = replace(binding, edge_bindings={edge.edge_id: changed})
    request = admission_request()
    receipt = plane.admit_participant_action(
        behavior(), request, identity=identity(), crossing_evidence=evidence(), idempotency_key=f"mutating-{mutator}"
    )

    assert all(runtime.admission_count == 0 for runtime in runtimes.values())
    assert "unauthorized" not in request.implementation_manifest.constraints
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "failed"


def test_bridge_cannot_change_snapshot_before_the_provider_call() -> None:
    plane, _, runtimes, _, _ = _executable_edge_plane()
    binding = plane._mixed_runtime
    assert binding is not None
    installed = binding.edge_bindings["edge.sim-to-emu"]

    def mutating_bridge(operation_id, request, snapshot, provider_call):
        snapshot.metadata["forged-by-bridge"] = True
        return installed.bridge(operation_id, request, snapshot, provider_call)

    changed = replace(installed, bridge=mutating_bridge)
    plane._mixed_runtime = replace(binding, edge_bindings={changed.edge_id: changed})
    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="bad-cut"
    )

    assert runtimes["emu"].admission_count == 0
    assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.FAILED
    assert "forged-by-bridge" not in plane.snapshot.metadata


@pytest.mark.parametrize("mutator", ["time-readback", "coordinate"])
def test_time_callbacks_cannot_mutate_the_provider_snapshot(mutator) -> None:
    plane, _, runtimes, _, time_runtime = _executable_edge_plane()
    binding = plane._mixed_runtime
    assert binding is not None
    installed = binding.edge_bindings["edge.sim-to-emu"]
    original_state = time_runtime.state

    def mutating_state(snapshot):
        snapshot.metadata["forged-by-time"] = True
        return original_state(snapshot)

    def mutating_coordinate(operation_id, edge, state):
        grant = installed.coordinate(operation_id, edge, state)
        state.clocks["clock.forged"] = next(iter(state.clocks.values()))
        return grant

    changed = replace(installed, coordinate=mutating_coordinate if mutator == "coordinate" else installed.coordinate)
    if mutator == "time-readback":
        time_runtime.state = mutating_state
    plane._mixed_runtime = replace(binding, edge_bindings={changed.edge_id: changed})
    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key=mutator
    )

    assert runtimes["emu"].admission_count == 1
    assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.SUCCEEDED
    assert "forged-by-time" not in plane.snapshot.metadata
    assert "clock.forged" not in plane.snapshot.time_model_state.clocks


def test_interrupted_mixed_edge_cannot_recover_from_provider_observation_alone(monkeypatch) -> None:
    class Interrupted(BaseException):
        pass

    plane, run_id, runtimes, _, _ = _executable_edge_plane()
    binding = plane._mixed_runtime
    assert binding is not None
    edge = binding.edge_bindings["edge.sim-to-emu"]

    def interrupted_bridge(operation_id, request, snapshot, provider_call):
        provider_call(request, snapshot)
        raise Interrupted

    plane._mixed_runtime = replace(binding, edge_bindings={edge.edge_id: replace(edge, bridge=interrupted_bridge)})
    with pytest.raises(Interrupted):
        plane.admit_participant_action(
            behavior(),
            admission_request(),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="crashed-edge",
        )
    pending = next(
        record for record in plane._store.load_records().values() if record.idempotency_key == "crashed-edge"
    )
    assert pending.status.state is OperationState.RUNNING
    assert runtimes["emu"].admission_count == 1

    def provider_only_observation(control_plane, _record, _target):
        return RecoveryEffectClassification.EFFECT_APPLIED, ApplyResult(success=True, snapshot=control_plane._snapshot)

    monkeypatch.setattr(recovery_module, "_observe_recovery_target", provider_only_observation)

    restarted = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=plane._mixed_runtime,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        store=plane._store,
    )
    assert (
        restarted.get_operation(pending.receipt.operation_id, identity=identity()).state is OperationState.INDETERMINATE
    )
    assert restarted.snapshot.mixed_composition_history[run_id][-1]["event_kind"] == "attempt"
    assert control_plane_readiness(restarted).to_payload()["status"] == "unready"
    with pytest.raises(ValueError, match="mixed stage reconciliation is required"):
        restarted.resolve_indeterminate_operation(
            pending.receipt.operation_id,
            disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
            idempotency_key="accept-partial-cut",
            identity=identity(),
        )
    plane._store.load_snapshot().participant_crossing_history["participant.behavior.unrelated"] = [{}]
    with pytest.raises(ValueError):
        RuntimeControlPlane(
            create_stub_target(with_participant_runtime=False),
            mixed_runtime=plane._mixed_runtime,
            crossing_policy_resolver=permit_resolver(),
            run_scope=f"run:{run_id}",
            store=plane._store,
        )


def test_valid_mixed_crossing_cannot_clear_missing_stages_by_generic_resolution() -> None:
    plane, run_id, _, _, _ = _executable_edge_plane(deliver=False, observe=False, execution_status="partial")
    receipt = plane.admit_participant_action(
        behavior(), admission_request(), identity=identity(), crossing_evidence=evidence(), idempotency_key="partial"
    )
    assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.INDETERMINATE
    assert plane.snapshot.participant_crossing_history[PARTICIPANT]
    assert plane.snapshot.mixed_composition_history[run_id][-1]["event_kind"] == "weakening"
    validate_persisted_crossing_history(plane.snapshot, plane._crossing_policy_resolver)

    with pytest.raises(ValueError, match="mixed stage reconciliation is required"):
        plane.resolve_indeterminate_operation(
            receipt.operation_id,
            disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
            idempotency_key="accept-partial",
            identity=identity(),
        )
    assert control_plane_readiness(plane).to_payload()["status"] == "unready"
    parent = plane._store.load_records()[receipt.operation_id]
    child_context = parent.status.context.model_copy(
        update={
            "operation_kind": OperationKind.INDETERMINATE_RESOLUTION,
            "parent_operation_id": receipt.operation_id,
            "authorization_scope": tuple(dict.fromkeys([*parent.status.context.authorization_scope, "role:operator"])),
        }
    )
    child = replace(
        parent,
        receipt=replace(parent.receipt, operation_id="historical-resolution", context=child_context),
        status=replace(
            parent.status,
            operation_id="historical-resolution",
            state=OperationState.SUCCEEDED,
            context=child_context,
            diagnostics=[],
        ),
        idempotency_key="historical-resolution",
        result_payload={"resolution_disposition": IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT.value},
    )
    assert receipt.operation_id in unresolved_indeterminate_operation_ids_from_records(
        {receipt.operation_id: parent, "historical-resolution": child}
    )
    history = plane._store.load_snapshot().participant_crossing_history[PARTICIPANT]
    history.append({**history[-1], "event_id": "crossing-occurrence.decided.unrelated"})
    with pytest.raises(ValueError, match="crossing result head differs"):
        RuntimeControlPlane(
            create_stub_target(with_participant_runtime=False),
            mixed_runtime=plane._mixed_runtime,
            crossing_policy_resolver=permit_resolver(),
            run_scope=f"run:{run_id}",
            store=plane._store,
        )


def test_handoff_refuses_time_readback_outside_the_stored_cut() -> None:
    binding, run_id, _ = _admitted_binding(_runtime_staged_profile)
    invoked: list[str] = []
    installed = binding.handoff_bindings["transition.sim-to-emu"]

    def coordinate(*_args):
        invoked.append("coordinate")
        return {}

    changed = replace(installed, coordinate=coordinate)
    binding = replace(binding, handoff_bindings={changed.transition_id: changed})
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")

    receipt = plane.advance_mixed_composition(
        "transition.sim-to-emu", identity=identity(), idempotency_key="mismatched-time-cut"
    )

    assert invoked == []
    assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.FAILED
    assert plane.snapshot.mixed_composition_states[run_id]["phase_id"] == "phase.sim"


@pytest.mark.parametrize("mutator", ["evaluator", "pre-time", "invoke", "readback", "post-time"])
def test_native_handoff_callbacks_cannot_mutate_authoritative_snapshot(mutator) -> None:
    binding, run_id, _ = _admitted_binding(_runtime_staged_profile)
    initial_snapshot = _staged_time_snapshot(binding)
    transition = binding.profile.transitions["transition.sim-to-emu"]
    installed = binding.handoff_bindings[transition.transition_id]
    evaluator = binding.transition_evaluators[transition.evaluator_ref]

    def changed_evaluator(admitted, state, snapshot):
        snapshot.metadata["forged-by-handoff"] = mutator
        return evaluator(admitted, state, snapshot)

    def changed_invoke(operation_id, admitted, state, snapshot):
        snapshot.metadata["forged-by-handoff"] = mutator
        return installed.invoke(operation_id, admitted, state, snapshot)

    def changed_readback(operation_id, snapshot):
        snapshot.metadata["forged-by-handoff"] = mutator
        return installed.readback(operation_id, snapshot)

    class ChangedTimeRuntime:
        def __init__(self):
            self.calls = 0

        def state(self, snapshot):
            self.calls += 1
            if (mutator == "pre-time" and self.calls == 1) or (mutator == "post-time" and self.calls == 2):
                snapshot.metadata["forged-by-handoff"] = mutator
            return installed.time_runtime.state(snapshot)

    if mutator == "evaluator":
        binding = replace(binding, transition_evaluators={transition.evaluator_ref: changed_evaluator})
    else:
        changed = replace(
            installed,
            invoke=changed_invoke if mutator == "invoke" else installed.invoke,
            readback=changed_readback if mutator == "readback" else installed.readback,
            time_runtime=ChangedTimeRuntime() if mutator in {"pre-time", "post-time"} else installed.time_runtime,
        )
        binding = replace(binding, handoff_bindings={transition.transition_id: changed})
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        initial_snapshot=initial_snapshot,
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")

    receipt = plane.advance_mixed_composition(
        transition.transition_id, identity=identity(), idempotency_key=f"mutating-{mutator}"
    )

    assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.SUCCEEDED
    assert "forged-by-handoff" not in plane.snapshot.metadata
    assert "forged-by-handoff" not in plane._store.load_snapshot().metadata


def test_interrupted_native_handoff_retains_uncertain_owner_on_restart() -> None:
    class Interrupted(BaseException):
        pass

    binding, run_id, runtimes = _admitted_binding(_runtime_staged_profile)
    installed = binding.handoff_bindings["transition.sim-to-emu"]
    old_invoke = installed.invoke

    def interrupted_invoke(operation_id, transition, state, snapshot):
        old_invoke(operation_id, transition, state, snapshot)
        raise Interrupted

    changed = replace(installed, invoke=interrupted_invoke)
    binding = replace(binding, handoff_bindings={changed.transition_id: changed})
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        initial_snapshot=_staged_time_snapshot(binding),
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

    with pytest.raises(Interrupted):
        plane.advance_mixed_composition("transition.sim-to-emu", identity=identity(), idempotency_key="crashed-handoff")
    pending = next(
        record for record in plane._store.load_records().values() if record.idempotency_key == "crashed-handoff"
    )
    assert pending.status.state is OperationState.RUNNING

    restarted = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        store=plane._store,
    )
    assert (
        restarted.get_operation(pending.receipt.operation_id, identity=identity()).state is OperationState.INDETERMINATE
    )
    assert restarted.snapshot.mixed_composition_states[run_id]["phase_id"] == "phase.sim"
    assert control_plane_readiness(restarted).to_payload()["status"] == "unready"
    with pytest.raises(ValueError, match="mixed stage reconciliation is required"):
        restarted.resolve_indeterminate_operation(
            pending.receipt.operation_id,
            disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
            idempotency_key="accept-handoff",
            identity=identity(),
        )
    with pytest.raises(RuntimeError, match="indeterminate operation requires resolution"):
        restarted.admit_participant_action(
            behavior(),
            admission_request(),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="old-owner",
        )
    assert all(runtime.admission_count == 0 for runtime in runtimes.values())


def test_native_handoff_retains_confirmed_transfer_evidence_when_readback_fails() -> None:
    binding, run_id, _ = _admitted_binding(_runtime_staged_profile)
    installed = binding.handoff_bindings["transition.sim-to-emu"]

    def invoke(operation_id, transition, state, snapshot):
        report = installed.invoke(operation_id, transition, state, snapshot)
        return {**report, "evidence_refs": [*report["evidence_refs"], "evidence:native-transfer"]}

    def failed_readback(_operation_id, _snapshot):
        raise RuntimeError("owner readback unavailable")

    changed = replace(installed, invoke=invoke, readback=failed_readback)
    binding = replace(binding, handoff_bindings={changed.transition_id: changed})
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        initial_snapshot=_staged_time_snapshot(binding),
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")

    receipt = plane.advance_mixed_composition(
        "transition.sim-to-emu", identity=identity(), idempotency_key="lost-owner-readback"
    )

    assert plane.get_operation(receipt.operation_id, identity=identity()).state is OperationState.INDETERMINATE
    failure = plane.snapshot.mixed_composition_history[run_id][-1]
    assert failure["event_kind"] == "failure"
    assert {"evidence:handoff-mapping", "evidence:native-transfer"}.issubset(failure["evidence_refs"])


def test_translated_action_outside_the_admitted_policy_cut_refuses_before_provider() -> None:
    plane, _, runtimes, calls, _ = _executable_edge_plane(
        destination_action_address="participant.action-contract.unadmitted"
    )

    with pytest.raises(ValueError, match="destination action differs from admitted policy"):
        plane.admit_participant_action(
            behavior(),
            admission_request(),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="unadmitted-translation",
        )

    assert calls == []
    assert all(runtime.admission_count == 0 for runtime in runtimes.values())


def test_staged_membership_change_needs_an_executable_handoff() -> None:
    prepared, run_id, _ = _admitted_binding(_runtime_staged_profile)
    binding = replace(prepared, handoff_bindings={})
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        initial_snapshot=_staged_time_snapshot(prepared),
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")

    receipt = plane.advance_mixed_composition(
        "transition.sim-to-emu", identity=identity(), idempotency_key="unbound-handoff"
    )

    assert plane.snapshot.mixed_composition_states[run_id]["phase_id"] == "phase.sim"
    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "failed"
    assert "handoff" not in [event["event_kind"] for event in plane.snapshot.mixed_composition_history[run_id]]


@pytest.mark.parametrize("readback_operation_matches", [True, False])
def test_evidenced_staged_handoff_commits_after_native_readback(readback_operation_matches) -> None:
    original, run_id, _ = _admitted_binding(_runtime_staged_profile)
    calls: list[str] = []
    installed = original.handoff_bindings["transition.sim-to-emu"]
    owner = {"component": "sim", "revision": 0}

    def coordinate(operation_id, transition, state):
        calls.append("time-coordinate")
        report = installed.coordinate(operation_id, transition, state)
        return {**report, "order_ref": "order:native-transfer"}

    def invoke(operation_id, transition, state, _snapshot):
        calls.append("invoke")
        owner.update(component="emu", revision=1)
        return {
            "operation_id": operation_id,
            "transition_id": transition.transition_id,
            "source_component_id": "sim",
            "destination_component_id": "emu",
            "predecessor_history_head": state.history_head,
            "phase_revision": state.phase_revision,
            "status": "committed",
            "order_ref": "order:native-transfer",
            "evidence_refs": ["evidence:phase-realization", "evidence:native-transfer"],
        }

    def readback(operation_id, _snapshot):
        calls.append("readback")
        return {
            "operation_id": operation_id if readback_operation_matches else "unrelated-operation",
            "owner_component_id": owner["component"],
            "owner_ref": original.profile.components[owner["component"]].native_ownership_ref,
            "phase_revision": owner["revision"],
            "evidence_refs": ["evidence:native-owner-readback"],
        }

    binding = replace(
        original,
        handoff_bindings={
            "transition.sim-to-emu": replace(
                installed,
                coordinate=coordinate,
                invoke=invoke,
                readback=readback,
            )
        },
    )
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        initial_snapshot=_staged_time_snapshot(original),
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")

    receipt = plane.advance_mixed_composition(
        "transition.sim-to-emu", identity=identity(), idempotency_key="evidenced-handoff"
    )

    assert calls == ["time-coordinate", "invoke", "readback"]
    if readback_operation_matches:
        assert plane.snapshot.mixed_composition_states[run_id]["phase_id"] == "phase.emu"
        assert plane.snapshot.mixed_composition_history[run_id][-1]["event_kind"] == "handoff"
        assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "succeeded"
    else:
        assert plane.snapshot.mixed_composition_states[run_id]["phase_id"] == "phase.sim"
        assert plane.snapshot.mixed_composition_history[run_id][-1]["event_kind"] == "failure"
        assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == "indeterminate"


@pytest.mark.parametrize(
    ("handoff_status", "terminal_state"),
    [("pending", "indeterminate"), ("failed", "failed"), ("stale", "failed")],
)
def test_uncommitted_handoff_retains_prior_phase_and_classifies_outcome(handoff_status, terminal_state) -> None:
    original, run_id, runtimes = _admitted_binding(_runtime_staged_profile)
    installed = original.handoff_bindings["transition.sim-to-emu"]

    def uncommitted(operation_id, transition, state, _snapshot):
        return {
            "operation_id": operation_id,
            "transition_id": transition.transition_id,
            "source_component_id": "sim",
            "destination_component_id": "emu",
            "predecessor_history_head": state.history_head,
            "phase_revision": state.phase_revision,
            "status": handoff_status,
            "order_ref": f"order:native:{operation_id}",
            "evidence_refs": ["evidence:phase-realization"],
        }

    def old_owner(operation_id, _snapshot):
        return {
            "operation_id": operation_id,
            "owner_component_id": "sim",
            "owner_ref": original.profile.components["sim"].native_ownership_ref,
            "phase_revision": 0,
            "evidence_refs": ["evidence:old-owner-readback"],
        }

    binding = replace(
        original,
        handoff_bindings={
            "transition.sim-to-emu": replace(
                installed,
                invoke=uncommitted,
                readback=old_owner,
            )
        },
    )
    plane = RuntimeControlPlane(
        create_stub_target(with_participant_runtime=False),
        mixed_runtime=binding,
        crossing_policy_resolver=permit_resolver(),
        run_scope=f"run:{run_id}",
        initial_snapshot=_staged_time_snapshot(original),
    )
    plane.activate_mixed_composition(identity=identity(), idempotency_key="initial-phase")
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

    receipt = plane.advance_mixed_composition(
        "transition.sim-to-emu", identity=identity(), idempotency_key="pending-handoff"
    )

    assert plane.get_operation(receipt.operation_id, identity=identity()).state.value == terminal_state
    assert plane.snapshot.mixed_composition_states[run_id]["phase_id"] == "phase.sim"
    failure = plane.snapshot.mixed_composition_history[run_id][-1]
    assert failure["event_kind"] == "failure"
    assert {"evidence:handoff-mapping", "evidence:phase-realization", "evidence:old-owner-readback"}.issubset(
        failure["evidence_refs"]
    )
    if terminal_state == "indeterminate":
        with pytest.raises(RuntimeError, match="indeterminate operation requires resolution"):
            plane.admit_participant_action(
                behavior(),
                admission_request(),
                identity=identity(),
                crossing_evidence=evidence(),
                idempotency_key="after-pending",
            )
        assert all(runtime.admission_count == 0 for runtime in runtimes.values())
    else:
        retry = plane.admit_participant_action(
            behavior(),
            admission_request(),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="old-owner",
        )
        assert plane.get_operation(retry.operation_id, identity=identity()).state.value == "succeeded"
        assert runtimes["sim"].admission_count == 1
