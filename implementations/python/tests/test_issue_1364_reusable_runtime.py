"""Actual runtime applications reuse policy edges without reusing coordinates."""

import pytest
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane_store import LocalControlPlaneStore
from reusable_control_runtime_fixtures import PARTICIPANT, configured_plane, handoff, identity


def test_installed_policy_children_must_match_the_retained_compiler_source():
    from dataclasses import replace

    from mixed_control_rev1_scenarios import parse, rev1_scenario
    from raes_processor.compiler import compile_runtime_model
    from raes_runtime.participant_control_runtime import MixedControlRuntimeBinding
    from reusable_control_runtime_fixtures import SPEC, CutOwner

    model = compile_runtime_model(parse(rev1_scenario()))
    specification = model.behavior_specifications[SPEC]
    model.behavior_specifications[SPEC] = replace(
        specification, mixed_control_policy=replace(specification.mixed_control_policy, policy_revision="forged")
    )
    owner = CutOwner()
    with pytest.raises(ValueError, match="compiler context"):
        MixedControlRuntimeBinding(model=model, resolver=owner)


def test_configured_control_does_not_admit_an_unsupported_directed_delivery_path():
    from mixed_control_rev1_scenarios import parse, rev1_delivery_scenario
    from raes_processor.compiler import compile_runtime_model
    from raes_runtime.control_plane_configuration import ControlPlaneConfiguration
    from raes_runtime.participant_control_runtime import MixedControlRuntimeBinding
    from reusable_control_runtime_fixtures import CutOwner

    model = compile_runtime_model(parse(rev1_delivery_scenario()))
    binding = MixedControlRuntimeBinding(model=model, resolver=CutOwner())
    with pytest.raises(ValueError, match="delivery"):
        ControlPlaneConfiguration(
            behavior_specifications=model.behavior_specifications,
            mixed_control=binding,
        )


def test_governed_application_keeps_final_sink_authority_and_historical_retry_identity():
    from participant_crossing_fixtures import evidence, policy_capable_target
    from sem233_flow_sink_fixtures import permit_resolver

    resolver = permit_resolver()
    with configured_plane(
        target=policy_capable_target("participant_ingress_admission", "participant_intervention"),
        crossing_policy_resolver=resolver,
    )[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="governed")
        receipt = plane.record_participant_control(
            PARTICIPANT, intent, identity=identity(), crossing_evidence=evidence(), idempotency_key="governed"
        )
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert plane.snapshot.participant_control_history[PARTICIPANT][0]["schema_version"] == "2.0.0"
        assert resolver.flow_sink_calls
        assert (
            plane.snapshot.participant_crossing_history[PARTICIPANT][0]["occurrence"]["subject"]["contract_id"]
            == "participant-control-intent-v2"
        )
        owner.orders.clear()
        assert (
            plane.record_participant_control(
                PARTICIPANT, intent, identity=identity(), crossing_evidence=evidence(), idempotency_key="governed"
            )
            == receipt
        )


def test_four_handoffs_reuse_two_edges_in_one_running_episode():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        initialized = plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        assert plane.get_operation(initialized.operation_id).state is OperationState.SUCCEEDED
        for revision, edge in enumerate(("take", "return", "take", "return")):
            key = f"handoff-{revision}"
            intent = handoff(plane, owner, edge, revision=revision, head=revision, order=revision + 1, key=key)
            receipt = plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key=key)
            assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        events = plane.snapshot.participant_control_history[PARTICIPANT]
        assert [event["occurrence"]["resulting_state_revision"] for event in events] == [1, 2, 3, 4]
        assert all(event["schema_version"] == "2.0.0" for event in events)


def test_ordered_contenders_are_evaluated_by_admitted_order_without_rebasing():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        first = handoff(plane, owner, "take", revision=0, head=0, order=1, key="first")
        second = handoff(plane, owner, "take", revision=0, head=0, order=2, key="second")

        plane.record_participant_controls(PARTICIPANT, [(second, "second"), (first, "first")], identity=identity())

        events = plane.snapshot.participant_control_history[PARTICIPANT]
        assert events[0]["occurrence"]["effective_order"] == 1
        assert events[1]["occurrence"]["disposition"] == "rejected"
        assert events[1]["occurrence"]["attempted"]["expected_state_revision"] == 0
        assert events[1]["occurrence"]["observed"]["state_revision"] == 1


def test_ambiguous_group_has_no_winner():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intents = [handoff(plane, owner, "take", revision=0, head=0, order=1, key=key) for key in ("one", "two")]
        applications = [(intent, intent.client_correlation_id) for intent in intents]
        caller = identity()
        with pytest.raises(ValueError, match="ambiguous"):
            plane.record_participant_controls(PARTICIPANT, applications, identity=caller)

        assert plane.snapshot.participant_control_history.get(PARTICIPANT, []) == []


def test_process_recovery_replays_the_same_episode_and_exact_retry(tmp_path):
    path = tmp_path / "store"
    with configured_plane(store=LocalControlPlaneStore(path))[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="first")
        receipt = plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="first")
    with configured_plane(store=LocalControlPlaneStore(path))[0] as plane:
        assert (
            plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="first")
            == receipt
        )
        owner = plane._mixed_control.resolver
        next_intent = handoff(plane, owner, "return", revision=1, head=1, order=2, key="second")
        plane.record_participant_control(PARTICIPANT, next_intent, identity=identity(), idempotency_key="second")
        assert (
            plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["resulting_state_revision"] == 2
        )


def test_lost_commit_acknowledgement_returns_the_original_receipt_without_a_new_live_cut(tmp_path):
    class LostAckStore(LocalControlPlaneStore):
        lost = False

        def commit_control_transition(self, **kwargs):
            committed = super().commit_control_transition(**kwargs)
            if not self.lost:
                self.lost = True
                raise ConnectionError("synthetic lost acknowledgement")
            return committed

    store = LostAckStore(tmp_path / "store")
    with configured_plane(store=store)[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="handoff")
        caller = identity()
        with pytest.raises(ConnectionError):
            plane.record_participant_control(PARTICIPANT, intent, identity=caller, idempotency_key="handoff")
        owner.orders.clear()
        receipt = plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="handoff")
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1


def test_revoked_destination_authority_refuses_a_handoff():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        owner.revoked.add("entities.blue-team")
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="revoked")

        plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="revoked")

        assert (
            plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["reason_code"]
            == "revoked-authority"
        )


def test_invalid_initial_authority_is_rejected_without_an_orphaned_running_claim():
    with configured_plane()[0] as plane:
        plane._mixed_control.resolver.revoked.add("entities.red-team")

        receipt = plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())

        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
        assert plane.snapshot.participant_episode_results == {}
        assert not any(record.status.state is OperationState.RUNNING for record in plane._store.load_records().values())


def test_read_only_principal_is_refused_before_live_owner_evaluation_without_a_retry_key():
    from dataclasses import replace

    from raes_runtime.control_plane_security import ControlPlaneRole

    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="handoff")
        called = []
        original = owner.resolve_cut

        def spy(*args):
            called.append(True)
            return original(*args)

        owner.resolve_cut = spy
        reader = replace(identity(), roles=frozenset({ControlPlaneRole.AUDITOR}))
        with pytest.raises(PermissionError):
            plane.record_participant_control(PARTICIPANT, intent, identity=reader)
        assert called == []


def test_missing_transfer_evidence_is_a_rejection_not_a_completed_handoff():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="handoff")
        intent = intent.model_copy(update={"completion_evidence_ref": "evidence:unresolved"})

        plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="handoff")

        assert (
            plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["reason_code"]
            == "missing-evidence"
        )


def test_finite_script_exhaustion_and_episode_restart_keep_distinct_meanings():
    from reusable_control_runtime_fixtures import SPEC

    with configured_plane(form="finite-script")[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        policy = plane._behavior_specifications[SPEC].mixed_control_policy
        for revision, edge in enumerate(("take", "return")):
            intent = handoff(
                plane,
                owner,
                edge,
                revision=revision,
                head=revision,
                order=revision + 1,
                key=f"h{revision}",
                step=policy.script_steps[revision].address,
            )
            plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key=f"h{revision}")
        exhausted = handoff(
            plane, owner, "take", revision=2, head=2, order=3, key="exhausted", step=policy.script_steps[0].address
        )
        plane.record_participant_control(PARTICIPANT, exhausted, identity=identity(), idempotency_key="exhausted")
        assert (
            plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["reason_code"]
            == "script-exhausted"
        )
        plane.terminate_participant_episode(PARTICIPANT, identity=identity())
        plane.restart_participant_episode(PARTICIPANT, episode_id="episode-2", identity=identity())
        fresh = handoff(
            plane,
            owner,
            "take",
            revision=0,
            head=3,
            order=1,
            key="fresh",
            episode="episode-2",
            step=policy.script_steps[0].address,
        )
        plane.record_participant_control(PARTICIPANT, fresh, identity=identity(), idempotency_key="fresh")
        assert (
            plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["resulting_state_revision"] == 1
        )


def test_out_of_window_attempt_does_not_consume_state_or_accepted_order():
    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        invalid = handoff(plane, owner, "take", revision=0, head=0, order=1001, key="late")
        plane.record_participant_control(PARTICIPANT, invalid, identity=identity(), idempotency_key="late")
        rejected = plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]
        assert rejected["reason_code"] == "late-authority"
        assert rejected["attempted"]["effective_order"] == 1001
        assert rejected["observed"]["last_accepted_order"] is None
        valid = handoff(plane, owner, "take", revision=0, head=1, order=1, key="valid")
        plane.record_participant_control(PARTICIPANT, valid, identity=identity(), idempotency_key="valid")
        assert (
            plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["resulting_state_revision"] == 1
        )


def test_repeated_proposals_get_fresh_decisions_without_reopening_old_proposals():
    from raes_runtime.participant_control_intents import ParticipantApprovalControlIntent
    from test_issue_1364_cancellation import proposal

    with configured_plane()[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        revision = head = 0
        for cycle in range(2):
            for edge in ("propose", "take", "approve", "return"):
                key = f"{edge}-{cycle}"
                if edge == "propose":
                    intent = proposal(plane, owner, key, revision=revision, head=head, order=head + 1)
                elif edge == "approve":
                    fields = handoff(
                        plane, owner, edge, revision=revision, head=head, order=head + 1, key=key
                    ).model_dump(mode="json")
                    fields.pop("completion_evidence_ref")
                    intent = ParticipantApprovalControlIntent.model_validate(
                        {
                            **fields,
                            "kind": "approval",
                            "proposal_ref": f"propose-{cycle}",
                            "proposal_revision": 1,
                            "decision_ref": f"decision-{cycle}",
                            "decision_revision": 1,
                        }
                    )
                else:
                    intent = handoff(plane, owner, edge, revision=revision, head=head, order=head + 1, key=key)
                plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key=key)
                assert (
                    plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["disposition"]
                    == "accepted"
                )
                revision += 1
                head += 1
                if edge == "approve":
                    duplicate = intent.model_copy(
                        update={
                            "client_correlation_id": f"duplicate-{cycle}",
                            "decision_ref": f"other-decision-{cycle}",
                            "expected_state_revision": revision,
                            "application": intent.application.model_copy(
                                update={"expected_history_head": head, "effective_order": head + 1}
                            ),
                        }
                    )
                    owner.orders[duplicate.client_correlation_id] = head + 1
                    plane.record_participant_control(
                        PARTICIPANT, duplicate, identity=identity(), idempotency_key=duplicate.client_correlation_id
                    )
                    assert (
                        plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["reason_code"]
                        == "proposal-already-decided"
                    )
                    head += 1
        accepted = [
            event["occurrence"]
            for event in plane.snapshot.participant_control_history[PARTICIPANT]
            if event["occurrence"]["disposition"] == "accepted"
        ]
        assert [event["resulting_state_revision"] for event in accepted] == list(range(1, 9))
