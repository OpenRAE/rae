"""Cancellation acceptance and evidenced work outcomes are separate facts."""

from raes_contracts.planning import ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import OperationKind, OperationState
from raes_runtime.control_plane_execution import OperationExecutionRequest
from raes_runtime.control_plane_operation_context import operation_admission_context
from raes_runtime.control_plane_supervised_execution import claim_accepted
from raes_runtime.participant_control_intents import (
    ParticipantCancellationControlIntent,
    ParticipantProposalControlIntent,
)
from reusable_control_runtime_fixtures import PARTICIPANT, configured_plane, handoff, identity
from test_run_310_supervisory_lifecycle import _behavior_target_snapshot


def proposal(plane, owner, key="propose", *, revision=0, head=0, order=1):
    template = handoff(plane, owner, "propose", revision=revision, head=head, order=order, key=key).model_dump(
        mode="json"
    )
    template.pop("completion_evidence_ref")
    template["kind"] = "proposal"
    return ParticipantProposalControlIntent.model_validate(
        {
            **template,
            "proposal_id": key,
            "proposal_revision": 1,
            "action_contract_ref": "participant.action-contract.contain",
            "payload_ref": "payload:test",
        }
    )


def cancellation(plane, owner, target_ref, *, target_kind="proposal", revision=1, head=1, key="cancel", order=2):
    template = handoff(plane, owner, "cancel", revision=revision, head=head, order=order, key=key).model_dump(
        mode="json"
    )
    template.pop("completion_evidence_ref")
    template["kind"] = "cancellation"
    return ParticipantCancellationControlIntent.model_validate(
        {**template, "target_kind": target_kind, "target_ref": target_ref, "target_revision": 1}
    )


def test_cancelling_a_pending_proposal_records_a_durable_prevention_witness():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intent = proposal(plane, owner)
        plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="propose")
        cancel = cancellation(plane, owner, "propose")

        receipt = plane.record_participant_control(PARTICIPANT, cancel, identity=identity(), idempotency_key="cancel")
        status = plane.participant_cancellation_status(receipt.operation_id, identity=identity())

        assert status.control_disposition == "accepted"
        assert status.cancellation_effect.value == "prevented"
        assert status.evidence_refs
        assert "cancellation_effect" not in plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]


def admitted_attempt(plane, *, native=True):
    from uuid import uuid4

    from raes_runtime.control_plane_execution import _utc_now
    from raes_runtime.control_plane_supervised_execution import invocation_request

    operation_id = str(uuid4())
    history = _behavior_target_snapshot().participant_behavior_history
    history[PARTICIPANT][-1]["operation_ref"] = operation_id
    snapshot = plane.snapshot.with_entries(dict(plane.snapshot.entries), participant_behavior_history=history)
    plane._store.save_snapshot(snapshot, expected_revision=plane._store.load_snapshot_state().revision)
    plane._reload_derived_state()
    context = operation_admission_context(
        plane, kind=OperationKind.PARTICIPANT_ACTION, request={"action_instance_id": "action-1"}, identity=identity()
    )
    request = OperationExecutionRequest(
        domain=RuntimeDomain.PARTICIPANT,
        method=lambda: None,
        plan=ProvisioningPlan(),
        address=PARTICIPANT,
        context=context,
        diagnostics=[],
        base_snapshot=None,
        idempotency_key="action-1",
        request_fingerprint=context.request_commitment,
    )
    backend = invocation_request(plane, request, operation_id, _utc_now())
    record, _ = claim_accepted(plane, request, backend_request=backend, native=native)
    return record


def test_cancellation_wins_the_unconsumed_dispatch_grant_without_a_backend_call():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        target = admitted_attempt(plane)
        cancel = cancellation(
            plane, owner, target.receipt.operation_id, target_kind="attempt", revision=0, head=0, order=1
        )

        receipt = plane.record_participant_control(PARTICIPANT, cancel, identity=identity(), idempotency_key="cancel")
        plane.dispatch_participant_cancellation(receipt.operation_id, identity=identity())

        status = plane.participant_cancellation_status(receipt.operation_id, identity=identity())
        assert plane.get_operation(target.receipt.operation_id).state is OperationState.CANCELLED
        assert status.cancellation_effect.value == "prevented"
        assert status.target_operation_id == target.receipt.operation_id
        assert status.evidence_refs


def test_target_visibility_attestations_are_retained_once_per_actual_target():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        target = admitted_attempt(plane)
        receipts = []
        for revision in range(2):
            key = f"cancel-{revision}"
            intent = cancellation(
                plane,
                owner,
                target.receipt.operation_id,
                target_kind="attempt",
                revision=revision,
                head=revision,
                order=revision + 1,
                key=key,
            )
            receipts.append(
                plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key=key)
            )
        records = plane._store.load_records()
        assert records[receipts[0].operation_id].result_payload["participant_control_available_targets"]
        assert records[receipts[1].operation_id].result_payload["participant_control_available_targets"] == []


def test_stored_target_attestations_reject_boolean_coordinates():
    from copy import deepcopy
    from dataclasses import replace

    import pytest
    from raes_runtime.participant_control_targets import archived_control_targets

    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        target = admitted_attempt(plane)
        intent = cancellation(
            plane, owner, target.receipt.operation_id, target_kind="attempt", revision=0, head=0, order=1
        )
        receipt = plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="cancel")
        record = plane._operations[receipt.operation_id]
        payload = deepcopy(record.result_payload)
        payload["participant_control_available_targets"][0]["available_at"] = False
        plane._operations[receipt.operation_id] = replace(record, result_payload=payload)
        with pytest.raises(ValueError):
            archived_control_targets(plane, PARTICIPANT)


def test_cancelled_proposal_cannot_reach_native_action_admission():
    from dataclasses import replace

    from raes_contracts.participant_action_arguments import ParticipantValidatedActionSelection
    from raes_contracts.runtime_state import ApplyResult
    from raes_runtime.control_plane_execution import execute_participant_action
    from test_sem_220_participant_decision_surface import _admission_request

    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        request = _admission_request()
        request = replace(
            request,
            participant_address=PARTICIPANT,
            implementation_selection=request.implementation_selection.model_copy(
                update={"participant_address": PARTICIPANT}
            ),
            validated_selection=ParticipantValidatedActionSelection(
                action_contract_address=request.action_contract_address,
                argument_shape_ref="shape:test",
                proposal_ref="propose",
                normalized_arguments=(),
            ),
        )
        intent = proposal(plane, owner).model_copy(update={"action_contract_ref": request.action_contract_address})
        plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="propose")
        plane.record_participant_control(
            PARTICIPANT, cancellation(plane, owner, "propose"), identity=identity(), idempotency_key="cancel"
        )
        called = []

        def admit(request, snapshot):
            called.append(request)
            return ApplyResult(True, snapshot)

        receipt = execute_participant_action(
            plane,
            method=admit,
            request=request,
            address=PARTICIPANT,
            idempotency_key="action",
            request_fingerprint="",
            identity=identity(),
        )

        assert called == []
        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED


def test_control_remains_responsive_and_a_late_native_result_cannot_erase_it():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from raes_contracts.participant_episode import ParticipantEpisodeTerminateRequest
    from raes_contracts.runtime_state import ApplyResult
    from raes_runtime.control_plane_execution import execute_participant_action

    started, release = Event(), Event()
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        plane.record_participant_control(
            PARTICIPANT, proposal(plane, owner), identity=identity(), idempotency_key="propose"
        )

        def slow(request, snapshot):
            started.set()
            assert release.wait(5)
            return ApplyResult(True, snapshot)

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                execute_participant_action,
                plane,
                method=slow,
                request=ParticipantEpisodeTerminateRequest(PARTICIPANT),
                address=PARTICIPANT,
                idempotency_key="slow",
                request_fingerprint="",
                identity=identity(),
            )
            try:
                assert started.wait(3)
                receipt = plane.record_participant_control(
                    PARTICIPANT, cancellation(plane, owner, "propose"), identity=identity(), idempotency_key="cancel"
                )
                assert (
                    plane.participant_cancellation_status(receipt.operation_id, identity=identity()).cancellation_effect
                    is None
                )
            finally:
                release.set()
            pending.result(timeout=5)
        assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 2
