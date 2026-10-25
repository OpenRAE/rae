"""Review regressions for reusable control isolation, identity and lifecycle."""

from dataclasses import replace

import pytest
from participant_crossing_fixtures import admission_request, behavior, evidence, policy_capable_target
from raes_contracts.participant_action_arguments import ParticipantValidatedActionSelection
from raes_contracts.runtime_state import ApplyResult, OperationState
from raes_runtime.control_plane_execution import execute_participant_action
from raes_runtime.control_plane_security import ParticipantControlSubjectBinding
from raes_runtime.control_plane_store import LocalControlPlaneStore
from raes_runtime.participant_crossing_action import ActionIngressExecution
from raes_runtime.participant_crossing_boundary import execute_action_ingress_crossing
from reusable_control_runtime_fixtures import PARTICIPANT, configured_plane, handoff, identity
from sem233_flow_sink_fixtures import Sem233FlowSinkResolver, permit_resolver
from test_issue_1364_cancellation import admitted_attempt, cancellation, proposal


@pytest.mark.parametrize("actor", ["participant.behavior.independent-agent", PARTICIPANT])
def test_governed_action_cannot_erase_another_participants_cancellation(actor):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    caller = replace(identity(), participant_control_subjects=(ParticipantControlSubjectBinding(actor, actor),))
    request = replace(
        admission_request(),
        participant_address=actor,
        implementation_selection=admission_request().implementation_selection.model_copy(
            update={"participant_address": actor}
        ),
    )
    started, release = Event(), Event()
    with configured_plane(
        target=policy_capable_target("participant_ingress_admission", "participant_intervention"),
        crossing_policy_resolver=permit_resolver(),
    )[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        if actor != PARTICIPANT:
            plane.initialize_participant_episode(actor, episode_id="episode-1", identity=caller)
        plane.record_participant_control(
            PARTICIPANT,
            proposal(plane, owner),
            identity=identity(),
            crossing_evidence=evidence(),
            idempotency_key="propose",
        )

        def slow(request, snapshot):
            started.set()
            assert release.wait(5)
            return ApplyResult(True, snapshot)

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                execute_action_ingress_crossing,
                plane,
                replace(behavior(), address=actor),
                request,
                ActionIngressExecution(evidence(), caller, "slow", slow, actor),
            )
            try:
                if not started.wait(3):
                    early = pending.result(timeout=1)
                    pytest.fail(str(plane.get_operation(early.operation_id).diagnostics))
                cancelled = plane.record_participant_control(
                    PARTICIPANT,
                    cancellation(plane, owner, "propose"),
                    identity=identity(),
                    crossing_evidence=evidence(),
                    idempotency_key="cancel",
                )
                assert plane.get_operation(cancelled.operation_id).state is OperationState.SUCCEEDED
                status = plane.participant_cancellation_status(cancelled.operation_id, identity=identity())
                assert (status.cancellation_effect is None) == (actor == PARTICIPANT)
            finally:
                release.set()
            action = pending.result(timeout=5)

        assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 2
        assert plane.get_operation(action.operation_id).state is OperationState.INDETERMINATE
        assert plane.participant_cancellation_status(cancelled.operation_id, identity=identity()) == status


class TransformedControlResolver(Sem233FlowSinkResolver):
    def resolve_operation(self, intent, snapshot, carrier):
        from raes_contracts.contracts.participant_crossing import (
            ParticipantCrossingGateDisposition,
            ParticipantCrossingOperation,
        )
        from raes_runtime.participant_crossing_intents import control_subject
        from raes_runtime.participant_crossing_mediation import ParticipantCrossingTransformationResolution

        self.governed = carrier.model_copy(
            update={
                "client_correlation_id": f"{carrier.client_correlation_id}.redacted",
                "limitation_refs": ["limitation:redacted"],
            }
        )
        subject = control_subject(intent.participant_address, self.governed)
        self.subjects.append(subject)
        base = super().resolve(intent, snapshot)
        return replace(
            base,
            gates=replace(base.gates, transformation_validity=ParticipantCrossingGateDisposition.PERMIT),
            required_operation=ParticipantCrossingOperation.REDACTION,
            transformation=ParticipantCrossingTransformationResolution(
                result_subject=subject,
                rule_ref="rule:redact-control",
                rule_revision="1",
                result_marking_refs=("marking:participant-control",),
            ),
        )

    def transform_ingress(self, intent, governed_subject, carrier):
        return self.governed


def test_transformed_control_retries_the_original_submission_without_live_resolution():
    from raes_runtime.participant_control_request import control_application_context

    resolver = TransformedControlResolver()
    with configured_plane(
        target=policy_capable_target(
            "participant_ingress_admission",
            "participant_intervention",
            "participant_transformation",
        ),
        crossing_policy_resolver=resolver,
    )[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intent = handoff(plane, owner, "take", revision=0, head=0, order=1, key="transformed")
        owner.orders["transformed.redacted"] = 1
        receipt = plane.record_participant_control(
            PARTICIPANT, intent, identity=identity(), crossing_evidence=evidence(), idempotency_key="transformed"
        )
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["limitation_refs"] == [
            "limitation:redacted"
        ]
        assert receipt.context == control_application_context(plane, PARTICIPANT, intent, identity(), evidence())
        owner.orders.clear()

        def unavailable(*args):
            pytest.fail("an exact retry must not resolve today's crossing policy")

        resolver.resolve_operation = unavailable
        assert (
            plane.record_participant_control(
                PARTICIPANT, intent, identity=identity(), crossing_evidence=evidence(), idempotency_key="transformed"
            )
            == receipt
        )


def test_prevention_witness_survives_later_cycles_work_and_process_recovery(tmp_path):
    store = tmp_path / "store"
    with configured_plane(store=LocalControlPlaneStore(store))[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        for cycle in range(2):
            key = f"proposal-{cycle}"
            plane.record_participant_control(
                PARTICIPANT,
                proposal(plane, owner, key, revision=2 * cycle, head=2 * cycle, order=2 * cycle + 1),
                identity=identity(),
                idempotency_key=key,
            )
            receipt = plane.record_participant_control(
                PARTICIPANT,
                cancellation(
                    plane,
                    owner,
                    key,
                    revision=2 * cycle + 1,
                    head=2 * cycle + 1,
                    order=2 * cycle + 2,
                    key=f"cancel-{cycle}",
                ),
                identity=identity(),
                idempotency_key=f"cancel-{cycle}",
            )
            assert plane.participant_cancellation_status(receipt.operation_id, identity=identity()).cancellation_effect
            if cycle == 0:
                original = receipt
        admitted_attempt(plane)
        status = plane.participant_cancellation_status(original.operation_id, identity=identity())
        assert status.cancellation_effect is not None
        assert status.cancellation_effect.value == "prevented"
    with configured_plane(store=LocalControlPlaneStore(store))[0] as plane:
        recovered = plane.participant_cancellation_status(original.operation_id, identity=identity())
        assert recovered == status


class EpisodeFlowSinkResolver(Sem233FlowSinkResolver):
    def resolve_flow_sink_decision(self, **kwargs):
        resolution = super().resolve_flow_sink_decision(**kwargs)

        def rebound(model):
            return type(model).model_validate_json(
                model.model_dump_json().replace('"episode-1"', f'"{kwargs["intent"].episode_id}"')
            )

        relation = rebound(resolution.relation)
        context = replace(
            resolution.context,
            source_labels={label.label_id: label for label in relation.labels[:2]},
            runtime_fact_planes={key: rebound(value) for key, value in resolution.context.runtime_fact_planes.items()},
            control_records=tuple(rebound(value) for value in resolution.context.control_records),
            control_declarations=tuple(rebound(value) for value in resolution.context.control_declarations),
            crossing_records=tuple(rebound(value) for value in resolution.context.crossing_records),
            crossing_subjects=tuple(rebound(value) for value in resolution.context.crossing_subjects),
        )
        return replace(resolution, relation=relation, context=context)


@pytest.mark.parametrize("governed", [False, True])
@pytest.mark.parametrize("current_records", [False, True])
def test_old_cancelled_proposals_cannot_reach_action_admission_after_restart(governed, current_records):
    options = (
        {
            "target": policy_capable_target("participant_ingress_admission", "participant_intervention"),
            "crossing_policy_resolver": EpisodeFlowSinkResolver(),
        }
        if governed
        else {}
    )
    control_options = {"crossing_evidence": evidence()} if governed else {}
    with configured_plane(**options)[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        intent = proposal(plane, owner).model_copy(
            update={"action_contract_ref": admission_request().action_contract_address}
        )
        plane.record_participant_control(
            PARTICIPANT,
            intent,
            identity=identity(),
            idempotency_key="propose",
            **control_options,
        )
        plane.record_participant_control(
            PARTICIPANT,
            cancellation(plane, owner, "propose"),
            identity=identity(),
            idempotency_key="cancel",
            **control_options,
        )
        plane.terminate_participant_episode(PARTICIPANT, identity=identity())
        plane.restart_participant_episode(PARTICIPANT, episode_id="episode-2", identity=identity())
        if current_records:
            fresh = proposal(plane, owner, "fresh", revision=0, head=2).model_copy(update={"episode_id": "episode-2"})
            plane.record_participant_control(
                PARTICIPANT,
                fresh,
                identity=identity(),
                idempotency_key="fresh",
                **control_options,
            )
        request = admission_request()
        request = replace(
            request,
            validated_selection=ParticipantValidatedActionSelection(
                action_contract_address=request.action_contract_address,
                argument_shape_ref="shape:test",
                proposal_ref="propose",
                normalized_arguments=(),
            ),
        )
        called = []

        def admit(request, snapshot):
            called.append(request)
            return ApplyResult(True, snapshot)

        if governed:
            caller = replace(identity(), participant_control_subjects=identity().participant_control_subjects[:1])
            receipt = execute_action_ingress_crossing(
                plane,
                behavior(),
                request,
                ActionIngressExecution(evidence(), caller, "action", admit, PARTICIPANT),
            )
        else:
            receipt = execute_participant_action(
                plane,
                method=admit,
                request=request,
                address=PARTICIPANT,
                identity=identity(),
                idempotency_key="action",
                request_fingerprint="",
            )
        assert called == []
        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
        assert any(
            item.code
            in {"runtime.participant-control.action-not-authorized", "runtime.participant-control.admission-unverified"}
            for item in plane.get_operation(receipt.operation_id).diagnostics
        ), plane.get_operation(receipt.operation_id).diagnostics
