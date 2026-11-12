"""Governed cancellation reaches the real control and execution owners."""

import pytest
from governed_effect_runtime_fixtures import EffectResolver
from participant_control_contract_fixtures import ref
from participant_control_v2_fixtures import binding
from participant_crossing_fixtures import StaticCrossingResolver, evidence
from raes_contracts.runtime_state import OperationState
from raes_runtime.participant_control_effects import ParticipantControlEffectOperation
from reusable_control_runtime_fixtures import PARTICIPANT, configured_plane, identity
from test_issue_1069_participant_control_effects import _target
from test_issue_1364_cancellation import admitted_attempt, cancellation


def test_governed_cancellation_prevents_the_exact_unconsumed_attempt():
    owner = EffectResolver()
    owner.principal = "operator"
    owner.trigger_key = "trigger-cancel"
    plane, cuts = configured_plane(
        target=_target(),
        participant_control=binding(owner),
        crossing_policy_resolver=StaticCrossingResolver(),
        enforce_final_sink_flow_control=False,
    )
    with plane:
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        target = admitted_attempt(plane)
        source = cancellation(
            plane, cuts, target.receipt.operation_id, target_kind="attempt", revision=0, head=0, order=1, key="source"
        )
        effect = cancellation(
            plane, cuts, target.receipt.operation_id, target_kind="attempt", revision=1, head=1, order=2, key="effect"
        )
        owner.target = dict(
            kind="interrupt",
            target_kind="execution",
            target_ref=target.receipt.operation_id,
            operation="cancel",
            lifecycle_authority=ref(effect.application.policy_ref, "authority"),
            expected_revision="1",
        )
        owner.operation = lambda request, context: ParticipantControlEffectOperation(
            kind="interrupt",
            intent=effect,
            participant_address=PARTICIPANT,
            crossing_evidence=evidence(),
        )
        source_receipt = plane.record_participant_control(
            PARTICIPANT, source, identity=identity(), idempotency_key="trigger-cancel", crossing_evidence=evidence()
        )
        assert plane.get_operation(source_receipt.operation_id).state is OperationState.SUCCEEDED
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        assert [item.disposition for item in outcomes] == ["applied"]
        assert plane.get_operation(target.receipt.operation_id).state is OperationState.CANCELLED
        owner_record = plane._store.load_records()[outcomes[0].receipt_ref]
        status = plane.participant_cancellation_status(owner_record.receipt.operation_id, identity=identity())
        assert status.cancellation_effect.value == "prevented"
        assert status.evidence_refs
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity()) == outcomes


def cancellation_race_plane(
    *,
    complete=False,
    partial=False,
    backlog=False,
    prerequisite=None,
    reject_source=False,
    store=None,
    pending_native=False,
):
    from dataclasses import replace

    from test_issue_1362_provider_execution import Provider
    from test_issue_1362_provider_execution import target as provider_target
    from test_issue_1364_cancellation_evidence import ScopedEvidence, consume

    owner = EffectResolver()
    if prerequisite is not None:
        owner.phase, owner.parent_outcome = "success-dependent", prerequisite
    if backlog:
        owner.selection = owner.selection.model_copy(
            update={"bounds": owner.selection.bounds.model_copy(update={"max_attempts": 8})}
        )
    owner.principal, owner.trigger_key = "operator", "trigger-cancel"
    provider = Provider()
    selected = provider_target(provider)
    selected = replace(selected, manifest=replace(selected.manifest, capabilities=_target().manifest.capabilities))
    plane, cuts = configured_plane(
        target=selected,
        operation_evidence=ScopedEvidence(),
        participant_control=binding(owner),
        crossing_policy_resolver=StaticCrossingResolver(),
        enforce_final_sink_flow_control=False,
        store=store,
    )
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
    offset = 0
    if backlog:
        from reusable_control_runtime_fixtures import handoff
        from test_issue_1364_cancellation import proposal

        specification = next(iter(plane._behavior_specifications.values()))
        policy = specification.mixed_control_policy
        transition = next(
            item
            for item in policy.permitted_transitions
            if item.transition_kind == "handoff"
            and item.from_state_address == specification.mixed_control_initial_state_address
        )
        states = {state.address: state for state in specification.controller_states}
        pending_revision = 3 if partial else 2
        pending = handoff(
            plane,
            cuts,
            transition.transition_id,
            revision=pending_revision,
            head=pending_revision,
            order=pending_revision + 1,
            key="pending-owner",
        )
        owner.trigger_key, owner.effect_id = "pending-source", "pending-handoff"
        owner.target = dict(
            kind="handoff",
            transition=ref(transition.address, "control"),
            participant_address=PARTICIPANT,
            episode_id="episode-1",
            prior_controller_ref=states[transition.from_state_address].controller_address,
            resulting_controller_ref=states[transition.to_state_address].controller_address,
            expected_state_revision=pending_revision,
            completion_obligation=ref(pending.completion_evidence_ref),
        )
        owner.operation = lambda request, context: ParticipantControlEffectOperation(
            kind="handoff", intent=pending, crossing_evidence=evidence()
        )
        plane.record_participant_control(
            PARTICIPANT,
            proposal(plane, cuts, key="pending-source"),
            identity=identity(),
            idempotency_key="pending-source",
            crossing_evidence=evidence(),
        )
        owner.trigger_key, owner.effect_id = "trigger-cancel", "effect-cancel"
        offset = 1
    target = (
        admitted_attempt(plane) if pending_native else consume(plane, admitted_attempt(plane, native=False), provider)
    )
    if complete or partial:
        from test_issue_1364_cancellation_evidence import settle_evidence

        settle_evidence(
            plane,
            target,
            provider,
            effect="partial" if partial else "complete",
            state=OperationState.CANCELLED if partial else OperationState.SUCCEEDED,
        )
    source = cancellation(
        plane,
        cuts,
        target.receipt.operation_id,
        target_kind="attempt",
        revision=offset,
        head=offset,
        order=1 + offset,
        key="source",
    )
    if reject_source:
        source = source.model_copy(update={"policy_revision": "revoked"})
    effect = cancellation(
        plane,
        cuts,
        target.receipt.operation_id,
        target_kind="attempt",
        revision=1 + offset,
        head=1 + offset,
        order=2 + offset,
        key="effect",
    )
    owner.target = dict(
        kind="interrupt",
        target_kind="execution",
        target_ref=target.receipt.operation_id,
        operation="cancel",
        lifecycle_authority=ref(effect.application.policy_ref, "authority"),
        expected_revision="1",
    )
    owner.operation = lambda request, context: (
        ParticipantControlEffectOperation(kind="handoff", intent=pending, crossing_evidence=evidence())
        if request.target.kind == "handoff" and backlog
        else ParticipantControlEffectOperation(
            kind="interrupt", intent=effect, participant_address=PARTICIPANT, crossing_evidence=evidence()
        )
    )
    plane.record_participant_control(
        PARTICIPANT, source, identity=identity(), idempotency_key="trigger-cancel", crossing_evidence=evidence()
    )
    return plane, provider, target


def test_completion_before_cancellation_never_becomes_applied():
    plane, provider, target = cancellation_race_plane(complete=True)
    with plane:
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        assert [item.disposition for item in outcomes] == ["failed"]
        source = next(
            record for record in plane._store.load_records().values() if record.idempotency_key == "trigger-cancel"
        )
        status = plane.participant_cancellation_status(source.receipt.operation_id, identity=identity())
        assert status.cancellation_effect.value == "too-late"
        assert plane.get_operation(target.receipt.operation_id).state is OperationState.SUCCEEDED


def test_an_accepted_control_without_cessation_evidence_remains_indeterminate():
    plane, provider, target = cancellation_race_plane()
    with plane:
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        assert [item.disposition for item in outcomes] == ["indeterminate"]
        assert plane.get_operation(target.receipt.operation_id).state is OperationState.RUNNING
        assert provider.cancels == 1
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity()) == outcomes
        assert provider.cancels == 1


@pytest.mark.parametrize("complete", [False, True])
@pytest.mark.parametrize("prerequisite", ["admitted", "applied"])
def test_parent_cancellation_acceptance_does_not_prove_application(complete, prerequisite):
    plane, provider, _ = cancellation_race_plane(complete=complete, prerequisite=prerequisite)
    with plane:
        source = next(r for r in plane._store.load_records().values() if r.idempotency_key == "trigger-cancel")
        assert source.status.state is OperationState.SUCCEEDED
        status = plane.participant_cancellation_status(source.receipt.operation_id, identity=identity())
        assert status.cancellation_effect is None or status.cancellation_effect.value == "too-late"
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        if prerequisite == "applied":
            assert outcomes == ()
            assert provider.cancels == 0
        else:
            assert [item.disposition for item in outcomes] == ["failed" if complete else "indeterminate"]


def test_rejected_parent_cannot_release_an_admitted_consequence():
    plane, provider, _ = cancellation_race_plane(prerequisite="admitted", reject_source=True)
    with plane:
        source = next(r for r in plane._store.load_records().values() if r.idempotency_key == "trigger-cancel")
        assert source.status.state is OperationState.FAILED
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity()) == ()
        assert provider.cancels == 0


def test_unsupported_cancellation_does_not_starve_ordinary_backlog():
    plane, _, _ = cancellation_race_plane(complete=True, backlog=True)
    owner = plane._participant_control.resolver
    original = owner.operation
    owner.operation = lambda request, context: original(request, context) if request.target.kind == "handoff" else None
    with plane:
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        assert {item.effect_id: item.disposition for item in outcomes} == {
            "effect-cancel": "unsupported",
            "pending-handoff": "applied",
        }


def test_indeterminate_cancellation_does_not_starve_ordinary_backlog():
    plane, _, _ = cancellation_race_plane(partial=True, backlog=True)
    with plane:
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        assert {item.effect_id: item.disposition for item in outcomes} == {
            "effect-cancel": "indeterminate",
            "pending-handoff": "applied",
        }
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity()) == outcomes


@pytest.mark.parametrize("backlog", [False, True])
def test_cancellation_effect_can_enter_while_an_effect_reservation_is_held(backlog):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from raes_contracts.runtime_state import OperationKind

    plane, provider, _ = cancellation_race_plane(backlog=backlog)
    entered, release = Event(), Event()

    def blocked_effect():
        with (
            plane._mutation_authority.mutation(OperationKind.PARTICIPANT_ACTION),
            plane._mutation_authority.external_call(),
        ):
            entered.set()
            assert release.wait(5)

    with plane, ThreadPoolExecutor(max_workers=1) as pool:
        blocked = pool.submit(blocked_effect)
        assert entered.wait(3)
        try:
            outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
            assert [item.disposition for item in outcomes] == ["indeterminate"]
            assert provider.cancels == 1
        finally:
            release.set()
        blocked.result()
