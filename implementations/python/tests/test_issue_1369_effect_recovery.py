"""Durable effect replay and failures retain the incumbent owner authority."""

import pytest
from governed_effect_runtime_fixtures import effect_plane
from participant_crossing_fixtures import PARTICIPANT, admit, identity
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane_store import LocalControlPlaneStore


def test_effect_reopens_without_another_owner_submission(tmp_path):
    directory = tmp_path / "ledger"
    plane, owner = effect_plane(store=LocalControlPlaneStore(directory))
    caller = identity(audience_bound=True)
    with plane:
        admit(plane, control_identity=caller)
        first = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        claims = [r for r in plane._store.load_records().values() if r.idempotency_key.startswith("control-effect:")]
        assert len(claims) == 1
        owner_record = plane._store.load_records()[first[0].receipt_ref]
        assert owner_record.receipt.context.parent_operation_id == claims[0].receipt.operation_id
    reopened, _ = effect_plane(
        store=LocalControlPlaneStore(directory), crossing_resolver=plane._crossing_policy_resolver
    )
    with reopened:
        assert reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == first
        assert len(reopened.snapshot.participant_control_history[PARTICIPANT]) == 1


def test_owner_applied_before_outcome_commit_is_observed_without_redispatch(monkeypatch):
    from raes_runtime import participant_control_effect_evidence as evidence

    plane, _ = effect_plane()
    caller = identity(audience_bound=True)
    original = evidence.commit_effect_outcome
    with plane:
        admit(plane, control_identity=caller)

        def interrupted(*args):
            raise OSError("synthetic interruption before outcome commit")

        monkeypatch.setattr(evidence, "commit_effect_outcome", interrupted)
        with pytest.raises(OSError):
            plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1
        monkeypatch.setattr(evidence, "commit_effect_outcome", original)
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert [item.disposition for item in outcomes] == ["applied"]
        assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1


def test_current_owner_refusal_is_failed_and_never_retried():
    from dataclasses import replace

    plane, owner = effect_plane()
    caller = identity(audience_bound=True)
    with plane:
        admit(plane, control_identity=caller)
        original = owner.effect_operation

        def refused(request, context):
            operation = original(request, context)
            # Same admitted coordinates; current policy no longer permits the actor.
            return replace(operation, intent=operation.intent.model_copy(update={"policy_revision": "revoked"}))

        owner.effect_operation = refused
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert [item.disposition for item in outcomes] == ["failed"]
        assert plane.snapshot.participant_control_history[PARTICIPANT][-1]["occurrence"]["disposition"] == "rejected"
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == outcomes


def test_changed_effect_content_cannot_reuse_a_committed_logical_key():
    plane, owner = effect_plane()
    caller = identity(audience_bound=True)
    with plane:
        admit(plane, control_identity=caller)
        first = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        owner.target = owner.providers["influence"].results[-1].payload.target.model_dump(mode="json")
        owner.target["expected_state_revision"] = 1
        receipt = admit(plane, control_identity=caller, idempotency_key="changed-content")
        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
        assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == first


def test_unattributed_drain_cannot_read_or_dispatch_effects():
    plane, _ = effect_plane()
    with plane:
        admit(plane, control_identity=identity(audience_bound=True))
        unbound = identity(bound=False)
        with pytest.raises(PermissionError):
            plane.dispatch_participant_control_effects(PARTICIPANT, identity=unbound)
        assert not plane.snapshot.participant_control_history.get(PARTICIPANT)


def test_effect_owner_cannot_reset_its_causal_depth_or_root():
    plane, owner = effect_plane()
    caller = identity(audience_bound=True)
    with plane:
        admit(plane, control_identity=caller)
        owner.context_override = lambda context, coordinates: context.update(depth=0)
        outcome = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert [item.disposition for item in outcome] == ["failed"]
        assert not plane.snapshot.participant_control_history.get(PARTICIPANT)


def test_a_stale_owner_callback_cannot_dispatch_at_a_refreshed_cut():
    plane, owner = effect_plane()
    caller = identity(audience_bound=True)
    with plane:
        admit(plane, control_identity=caller)
        original = owner.effect_operation

        def stale(request, context):
            operation = original(request, context)
            state = plane._store.load_snapshot_state()
            plane._store.save_snapshot(
                state.snapshot.with_entries(dict(state.snapshot.entries), metadata={"cut": "advanced"}),
                expected_revision=state.revision,
            )
            return operation

        owner.effect_operation = stale
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert [item.disposition for item in outcomes] == ["unsupported"]
        assert not plane.snapshot.participant_control_history.get(PARTICIPANT)
        assert not any(
            record.idempotency_key.startswith("control-effect:") for record in plane._store.load_records().values()
        )


@pytest.mark.parametrize("phase", ["independent", "required-predecessor"])
def test_reopened_unsettled_claim_keeps_the_recovery_barrier_and_does_not_repeat_owner(tmp_path, monkeypatch, phase):
    from governed_effect_runtime_fixtures import EffectResolver
    from raes_runtime import participant_control_effect_evidence as evidence
    from raes_runtime.control_plane_recovery import IndeterminateResolutionDisposition

    directory = tmp_path / "interrupted-ledger"
    plane, _ = effect_plane(EffectResolver(phase=phase), store=LocalControlPlaneStore(directory))
    caller = identity(audience_bound=True)
    original = evidence.commit_effect_outcome
    with plane:
        admit(plane, control_identity=caller)

        def interrupted(*args):
            raise OSError("synthetic lost outcome commit")

        monkeypatch.setattr(evidence, "commit_effect_outcome", interrupted)
        with pytest.raises(OSError):
            plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        claim = next(
            record
            for record in plane._store.load_records().values()
            if record.idempotency_key.startswith("control-effect:")
        )
    monkeypatch.setattr(evidence, "commit_effect_outcome", original)
    reopened, _ = effect_plane(
        EffectResolver(phase=phase),
        store=LocalControlPlaneStore(directory),
        crossing_resolver=plane._crossing_policy_resolver,
    )
    with reopened:
        with pytest.raises(RuntimeError, match="indeterminate operation requires resolution"):
            reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert len(reopened.snapshot.participant_control_history[PARTICIPANT]) == 1
        reopened.resolve_indeterminate_operation(
            claim.receipt.operation_id,
            disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
            idempotency_key="resolve-effect",
            identity=caller,
        )
        outcomes = reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert [item.disposition for item in outcomes] == ["applied"]
        assert reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == outcomes
        assert len(reopened.snapshot.participant_control_history[PARTICIPANT]) == 1
        if phase == "required-predecessor":
            resumed = admit(reopened, control_identity=caller, idempotency_key="resume-after-recovery")
            assert reopened.get_operation(resumed.operation_id).state is OperationState.SUCCEEDED


def test_a_foreign_participant_specification_cannot_supply_the_handoff_owner():
    from dataclasses import replace

    from governed_effect_runtime_fixtures import EffectResolver
    from participant_control_v2_fixtures import binding
    from participant_crossing_fixtures import StaticCrossingResolver, control_specification
    from raes_runtime.control_plane import RuntimeControlPlane
    from test_issue_1069_participant_control_effects import _target

    real = replace(control_specification(), control_transitions=())
    foreign = replace(
        control_specification(),
        address="participant.behavior-specification.foreign",
        mixed_control_participant_address="participant.behavior.foreign",
        participant_addresses=("participant.behavior.foreign",),
    )
    foreign = replace(
        foreign,
        controller_states=(
            foreign.controller_states[0],
            replace(foreign.controller_states[1], controller_address="participant.behavior.next-supervisor"),
        ),
    )
    plane = RuntimeControlPlane(
        _target(),
        participant_control=binding(EffectResolver()),
        behavior_specifications={foreign.address: foreign, real.address: real},
        crossing_policy_resolver=StaticCrossingResolver(),
        enforce_final_sink_flow_control=False,
    )
    with plane:
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
        receipt = admit(plane, control_identity=identity(audience_bound=True))
        assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
        assert (
            plane.snapshot.participant_control_evaluation_history[PARTICIPANT][-1]["composition"]["disposition"]
            == "unsupported"
        )
