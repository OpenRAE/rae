"""Public directed-inject joins preserve independent world/control outcomes."""

import pytest
from raes_contracts.contracts.participant_inject_application import ParticipantInjectApplicationModel


def application(**changes):
    return ParticipantInjectApplicationModel.model_validate(
        {
            "request_key": "delivery-request-1",
            "world_operation_id": "world-operation-1",
            "delivery_address": "participant.behavior-specification.red-briefing.inject-delivery.briefing",
            "delivery_digest": "sha256:" + "1" * 64,
            "participant_address": "participant.behavior.red-agent",
            "episode_id": "episode-1",
            "expected_snapshot_revision": 1,
            **changes,
        }
    )


@pytest.mark.parametrize("revision", [True, "1", 1.0, -1])
def test_application_coordinates_are_strict(revision):
    with pytest.raises(ValueError):
        application(expected_snapshot_revision=revision)


def test_disclosure_application_needs_no_control_coordinates():
    assert application().control is None


def test_control_application_requires_exact_event_revision_and_digest():
    with pytest.raises(ValueError):
        application(control={"event_id": "control-event-1"})


def test_public_delivery_requires_an_installed_owner_and_does_not_refire_world(tmp_path):
    from test_issue_1367_inject_execution import configured_plane

    delivery_request = application()
    configured_runtime = configured_plane(tmp_path)[0]
    with configured_runtime as plane, pytest.raises(ValueError, match="delivery.*unavailable"):
        plane.deliver_participant_inject(delivery_request)


def test_disclosure_delivers_actual_governed_result_without_control_or_observation(tmp_path):
    from participant_inject_runtime_fixtures import PARTICIPANT, caller, configured_plane

    plane, backend, owner, request = configured_plane(tmp_path, world_identity=caller(controller=False))
    with plane:
        delivered = plane.deliver_participant_inject(request, identity=caller(controller=False))
        assert delivered.delivery.content == "Approved briefing result"
        assert delivered.delivery.correlation == plane.get_inject_correlation(
            request.world_operation_id, identity=caller(controller=False)
        )
        assert backend.starts == 1
        assert not plane.snapshot.participant_control_history.get(PARTICIPANT)
        stages = [item["occurrence"]["stage"] for item in plane.snapshot.participant_crossing_history[PARTICIPANT]]
        assert "delivered" in stages
        assert "observed" not in stages


def test_exact_retry_and_new_key_cannot_repeat_logical_delivery(tmp_path):
    from participant_inject_runtime_fixtures import caller, configured_plane

    plane, backend, owner, request = configured_plane(tmp_path)
    with plane:
        first = plane.deliver_participant_inject(request, identity=caller())
        owner.fail = True
        assert plane.deliver_participant_inject(request, identity=caller()) == first
        owner.fail = False
        conflicting_request = request.model_copy(
            update={"request_key": "different-key", "expected_snapshot_revision": plane._snapshot_state.revision}
        )
        delivery_identity = caller()
        with pytest.raises(ValueError, match="already claimed"):
            plane.deliver_participant_inject(
                conflicting_request,
                identity=delivery_identity,
            )
        assert backend.starts == 1


@pytest.mark.parametrize("change", ["audience", "episode", "digest", "snapshot", "world", "control"])
def test_invalid_or_unauthorized_join_discloses_nothing(tmp_path, change):
    from participant_inject_runtime_fixtures import caller, configured_plane

    plane, backend, owner, request = configured_plane(tmp_path)
    changes = {
        "episode": {"episode_id": "other-episode"},
        "digest": {"delivery_digest": "sha256:" + "0" * 64},
        "snapshot": {"expected_snapshot_revision": 999},
        "world": {"world_operation_id": "unknown"},
        "control": {"control": {"event_id": "not-control", "occurrence_revision": 1, "digest": "sha256:" + "0" * 64}},
    }
    request = type(request).model_validate({**request.model_dump(mode="json"), **changes.get(change, {})})
    with plane:
        delivery_identity = caller(audience=change != "audience")
        with pytest.raises((ValueError, PermissionError)):
            plane.deliver_participant_inject(request, identity=delivery_identity)
        assert not any(record.inject_delivery for record in plane._store.load_records().values())
        assert backend.starts == 1


def test_delivery_failure_preserves_world_and_capture_outcomes(tmp_path):
    from participant_inject_runtime_fixtures import caller, configured_plane
    from raes_contracts.runtime_state import OperationState

    plane, backend, owner, request = configured_plane(tmp_path)
    with plane:
        owner.fail = True
        delivery_identity = caller()
        with pytest.raises(ValueError, match="projection"):
            plane.deliver_participant_inject(request, identity=delivery_identity)
        assert plane.get_operation(request.world_operation_id).state is OperationState.SUCCEEDED
        assert plane.get_inject_correlation(request.world_operation_id, identity=caller())
        assert backend.starts == 1


def test_retained_delivery_survives_restart_without_projection_or_world_redispatch(tmp_path):
    from participant_inject_runtime_fixtures import caller, configured_plane
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    directory = tmp_path / "ledger"
    plane, backend, owner, request = configured_plane(tmp_path, store=LocalControlPlaneStore(directory))
    with plane:
        first = plane.deliver_participant_inject(request, identity=caller())
        resolver = plane._crossing_policy_resolver
    plane, backend, owner, _ = configured_plane(tmp_path, store=LocalControlPlaneStore(directory), resolver=resolver)
    with plane:
        owner.fail = True
        assert plane.deliver_participant_inject(request, identity=caller()) == first
        assert backend.starts == 0


def test_schedule_is_revalidated_before_world_dispatch(tmp_path):
    from participant_inject_runtime_fixtures import configured_plane

    plane, backend, _, _ = configured_plane(tmp_path, tick=0)
    with plane:
        assert backend.starts == 0
        assert not backend.path.exists()


def test_a_scheduled_world_inject_executes_at_its_cut_without_participants(tmp_path):
    from participant_inject_runtime_fixtures import caller, configured_plane
    from raes_contracts.runtime_state import OperationState

    plane, backend, _, application = configured_plane(tmp_path, participants=False)
    with plane:
        world = application.world_operation_id
        assert plane.get_operation(world).state is OperationState.SUCCEEDED
        assert plane.get_inject_outcome(world).effect == "effect-applied"
        assert not plane.snapshot.participant_episode_results
        assert backend.starts == 1
        assert plane.submit_inject(backend.world_request, identity=caller()).operation_id == world
        assert backend.starts == 1


def test_a_changed_cut_during_revalidation_withdraws_before_world_dispatch(tmp_path):
    from participant_inject_runtime_fixtures import configured_plane

    plane, backend, _, _ = configured_plane(tmp_path, revalidate_mutation=True)
    with plane:
        assert plane._store.load_snapshot_state().snapshot.metadata.get("cut") == "advanced"
        assert backend.starts == 0
        assert not backend.path.exists()


def test_a_clock_without_a_scenario_epoch_mapping_cannot_supply_schedule_time(tmp_path):
    from participant_inject_runtime_fixtures import configured_plane

    plane, backend, _, _ = configured_plane(tmp_path, epoch="run_start")
    with plane:
        assert backend.starts == 0


def test_capture_failure_preserves_applied_world_but_withholds_delivery(tmp_path):
    from participant_inject_runtime_fixtures import caller, configured_plane
    from raes_contracts.runtime_state import OperationState

    plane, backend, _, request = configured_plane(tmp_path, capture_fail=True)
    with plane:
        assert plane.get_operation(request.world_operation_id).state is OperationState.SUCCEEDED
        assert plane._store.load_records()[request.world_operation_id].result_payload["status"] == "failed"
        delivery_identity = caller()
        with pytest.raises(ValueError, match="capture"):
            plane.deliver_participant_inject(request, identity=delivery_identity)
        assert backend.starts == 1


def test_missing_capture_capability_refuses_before_claim_and_execution(tmp_path):
    from participant_inject_runtime_fixtures import configured_plane

    plane, backend, _, _ = configured_plane(tmp_path, capture_available=False)
    with plane:
        assert backend.starts == 0
        assert not any(record.inject_occurrence for record in plane._store.load_records().values())


@pytest.mark.parametrize("kind", ["external-direction", "intervention"])
def test_reusable_control_cycles_deliver_once_per_application_without_refiring_world(tmp_path, kind):
    from participant_inject_runtime_fixtures import apply_control, caller, configured_plane
    from raes_contracts.canonical import canonical_json_digest

    plane, backend, owner, request = configured_plane(tmp_path, controlled=kind)
    with plane:
        target = apply_control(plane, "handoff", revision=0, head=0, order=1)
        for revision in (1, 2):
            event = apply_control(plane, kind, revision=revision, head=revision, order=revision * 2, target=target)
            selected = type(request).model_validate(
                {
                    **request.model_dump(mode="json"),
                    "request_key": f"delivery-{revision}",
                    "expected_snapshot_revision": plane._snapshot_state.revision,
                    "control": {
                        "event_id": event["event_id"],
                        "occurrence_revision": event["occurrence"]["occurrence_revision"],
                        "digest": canonical_json_digest(event),
                    },
                }
            )
            result = plane.deliver_participant_inject(selected, identity=caller())
            assert result.delivery.application.control.event_id == event["event_id"]
            assert plane.deliver_participant_inject(selected, identity=caller()) == result
        assert backend.starts == 1


@pytest.mark.parametrize("invalid", ["controller", "revoked", "revision", "kind", "stale"])
def test_control_join_cannot_be_forged_or_revived(tmp_path, invalid):
    from participant_inject_runtime_fixtures import apply_control, caller, configured_plane
    from raes_contracts.canonical import canonical_json_digest

    plane, backend, _, request = configured_plane(tmp_path, controlled="external-direction")
    with plane:
        target = apply_control(plane, "handoff", revision=0, head=0, order=1)
        event = apply_control(plane, "external-direction", revision=1, head=1, order=2, target=target)
        if invalid == "kind":
            event = target
        if invalid == "revoked":
            policy = plane._mixed_control.policy("participant.behavior-specification.red-briefing", "episode-1")
            plane._mixed_control.resolver.revoked.update(
                policy.state(
                    policy.transition(event["occurrence"]["permitted_transition_ref"]).from_state_ref
                ).authority_basis_refs
            )
        if invalid == "stale":
            apply_control(plane, "external-direction", revision=2, head=2, order=3, target=target)
        selected = type(request).model_validate(
            {
                **request.model_dump(mode="json"),
                "expected_snapshot_revision": plane._snapshot_state.revision,
                "control": {
                    "event_id": event["event_id"],
                    "occurrence_revision": event["occurrence"]["occurrence_revision"]
                    + (1 if invalid == "revision" else 0),
                    "digest": canonical_json_digest(event),
                },
            }
        )
        delivery_identity = caller(controller=invalid != "controller")
        with pytest.raises((ValueError, PermissionError)):
            plane.deliver_participant_inject(selected, identity=delivery_identity)
        assert not any(record.inject_delivery for record in plane._store.load_records().values())
        assert backend.starts == 1


def test_delivery_policy_revision_is_independent_from_control_policy(tmp_path):
    from participant_inject_runtime_fixtures import apply_control, caller, configured_plane
    from raes_contracts.canonical import canonical_json_digest

    plane, backend, _, request = configured_plane(tmp_path, controlled="external-direction", delivery_revision="7.2.0")
    with plane:
        target = apply_control(plane, "handoff", revision=0, head=0, order=1)
        event = apply_control(plane, "external-direction", revision=1, head=1, order=2, target=target)
        selected = type(request).model_validate(
            {
                **request.model_dump(mode="json"),
                "expected_snapshot_revision": plane._snapshot_state.revision,
                "control": {
                    "event_id": event["event_id"],
                    "occurrence_revision": 2,
                    "digest": canonical_json_digest(event),
                },
            }
        )
        delivered = plane.deliver_participant_inject(selected, identity=caller())
        assert delivered.delivery.application == selected
        assert backend.starts == 1


@pytest.mark.parametrize("committed", [False, True])
def test_lost_delivery_commit_ack_retains_claim_across_reopen(tmp_path, committed):
    from participant_inject_runtime_fixtures import caller, configured_plane
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    class LostAckStore(LocalControlPlaneStore):
        def commit_participant_transition(self, **kwargs):
            if committed:
                super().commit_participant_transition(**kwargs)
            raise ConnectionError("synthetic lost delivery acknowledgement")

    directory = tmp_path / "ledger"
    plane, backend, _, request = configured_plane(tmp_path, store=LostAckStore(directory))
    resolver = plane._crossing_policy_resolver
    delivery_identity = caller()
    with plane, pytest.raises(ConnectionError):
        plane.deliver_participant_inject(request, identity=delivery_identity)
    plane, backend, owner, _ = configured_plane(tmp_path, store=LocalControlPlaneStore(directory), resolver=resolver)
    with plane:
        owner.fail = True
        if committed:
            assert plane.deliver_participant_inject(request, identity=caller()).delivery.application == request
        else:
            delivery_identity = caller()
            with pytest.raises(ValueError, match="withheld"):
                plane.deliver_participant_inject(request, identity=delivery_identity)
        assert backend.starts == 0


@pytest.mark.parametrize("coordinate", ["disclosed_item", "observation_boundary_ref"])
def test_transformation_cannot_replace_the_authored_delivery_coordinates(tmp_path, coordinate):
    from dataclasses import replace

    from participant_inject_runtime_fixtures import caller, configured_plane, reference
    from raes_contracts.contracts.participant_crossing import ParticipantCrossingOperation
    from raes_runtime.participant_crossing_egress import _view_subject
    from raes_runtime.participant_crossing_mediation import ParticipantCrossingTransformationResolution
    from sem233_flow_sink_fixtures import Sem233FlowSinkResolver

    class ChangedCoordinateResolver(Sem233FlowSinkResolver):
        def resolve_operation(self, intent, snapshot, carrier):
            base = super().resolve(intent, snapshot)
            replacement = (
                type(carrier.disclosed_item).model_validate(reference("content.other-result"))
                if coordinate == "disclosed_item"
                else "participant.observation-boundary.other"
            )
            self.changed = carrier.model_copy(
                update={coordinate: replacement, "view_id": carrier.view_id + ".transformed"}
            )
            subject = _view_subject(
                self.changed,
                participant_address=intent.participant_address,
                episode_id=intent.episode_id,
                subject_kind=intent.subject.subject_kind,
            )
            self.subjects.append(subject)
            return replace(
                base,
                required_operation=ParticipantCrossingOperation.REDACTION,
                transformation=ParticipantCrossingTransformationResolution(
                    result_subject=subject,
                    rule_ref="rule:redact-result",
                    rule_revision="1",
                    result_marking_refs=("marking:participant-control",),
                ),
            )

        def transform_egress(self, intent, subject, carrier):
            return self.changed

    plane, backend, _, request = configured_plane(tmp_path, resolver=ChangedCoordinateResolver())
    with plane:
        delivery_identity = caller()
        with pytest.raises(ValueError, match="projection binding differs"):
            plane.deliver_participant_inject(request, identity=delivery_identity)
        assert plane._crossing_policy_resolver.changed is not None
        assert not any(record.inject_delivery for record in plane._store.load_records().values())
        assert plane.get_inject_correlation(request.world_operation_id, identity=caller())
        assert backend.starts == 1


@pytest.mark.parametrize("available", [False, True])
def test_optional_capture_unavailability_or_failure_does_not_veto_world_or_delivery(tmp_path, available):
    from participant_inject_runtime_fixtures import caller, configured_plane
    from raes_contracts.runtime_state import OperationState

    plane, backend, _, request = configured_plane(
        tmp_path, capture_required=False, capture_available=available, capture_fail=True
    )
    with plane:
        assert not any(demand.required for demand in plane._inject_delivery.model.observation_demands)
        assert plane.get_operation(request.world_operation_id).state is OperationState.SUCCEEDED
        capture = plane.get_inject_capture(request.world_operation_id, identity=caller())
        if available:
            assert capture.status == "succeeded"
            assert not capture.observation["retained"]
        else:
            assert capture.status == "failed"
        assert (
            plane.deliver_participant_inject(request, identity=caller()).delivery.content == "Approved briefing result"
        )
        assert backend.starts == 1


def test_optional_capture_failure_cannot_discard_successful_mandatory_capture(tmp_path):
    from participant_inject_runtime_fixtures import caller, configured_plane

    plane, backend, _, request = configured_plane(tmp_path, optional_capture_fail=True)
    with plane:
        capture = plane.get_inject_capture(request.world_operation_id, identity=caller())
        assert capture.status == "succeeded"
        assert len(capture.observation["retained"]) == 1
        assert plane.deliver_participant_inject(request, identity=caller())
        assert backend.starts == 1
