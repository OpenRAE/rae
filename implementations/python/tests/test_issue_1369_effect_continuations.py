"""Committed effect graphs advance only on independently validated owner facts."""

from dataclasses import replace

import pytest
from governed_effect_runtime_fixtures import EffectResolver
from participant_control_contract_fixtures import ref
from participant_control_v2_fixtures import binding
from participant_crossing_fixtures import (
    CONTROLLER,
    PARTICIPANT,
    StaticCrossingResolver,
    admit,
    control_specification,
    identity,
)
from raes_contracts.contracts.participant_control_applicability import ParticipantControlSelectionV2Model
from raes_contracts.errors import ConflictError
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import LocalControlPlaneStore
from test_issue_1069_participant_control_effects import _target


def chain_plane(owner, store, crossing_resolver=None):
    specification = control_specification()
    first = specification.control_transitions[0]
    second = replace(
        first,
        address=first.address + "-follow",
        transition_id="handoff-follow",
        expected_state_revision=1,
        resulting_state_revision=2,
        effective_order=2,
    )
    specification = replace(
        specification,
        control_transitions=(first, second),
        controller_states=(
            specification.controller_states[0],
            replace(specification.controller_states[1], controller_address="participant.behavior.next-supervisor"),
        ),
    )
    plane = RuntimeControlPlane(
        _target(),
        crossing_policy_resolver=crossing_resolver or StaticCrossingResolver(),
        behavior_specifications={specification.address: specification},
        participant_control=binding(owner),
        enforce_final_sink_flow_control=False,
        store=store,
    )
    return plane


def chain_owner():
    owner = EffectResolver(phase="required-predecessor")
    selection = owner.selection.model_dump(mode="json")
    selection["slots"].append({**selection["slots"][-1], "slot_id": "follow"})
    owner.selection = ParticipantControlSelectionV2Model.model_validate(selection)
    target = dict(
        kind="handoff",
        transition=ref("participant.behavior-specification.controlled.control-transition.handoff", "control"),
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        prior_controller_ref=CONTROLLER,
        resulting_controller_ref="participant.behavior.next-supervisor",
        expected_state_revision=0,
        completion_obligation=ref("handoff-evidence"),
    )
    owner.target = target
    owner.effect_specs = {
        "follow": dict(
            effect_id="effect-follow",
            predecessor_effect_ids=["effect-1"],
            key=dict(slot="follow"),
            target={
                **target,
                "transition": ref(target["transition"]["ref"] + "-follow", "control"),
                "expected_state_revision": 1,
            },
        )
    }
    return owner


def test_predecessor_continuation_survives_restart_without_repeating_owners(tmp_path):
    owner = chain_owner()
    directory = tmp_path / "chain"
    plane = chain_plane(owner, LocalControlPlaneStore(directory))
    caller = identity(audience_bound=True)
    with plane:
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
        parent = admit(plane, control_identity=caller)
        original = plane.snapshot.participant_control_evaluation_history[PARTICIPANT][0]
        assert original["commit"]["dispatchable_effect_ids"] == ["effect-1"], (
            original["composition"],
            original["results"],
        )
        assert plane.get_operation(parent.operation_id).state is OperationState.FAILED
        available = owner.effect_operation
        owner.effect_operation = lambda effect, context: (
            available(effect, context) if effect.effect_id == "effect-1" else None
        )
        first = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert first[0].disposition == "applied"
        assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1
    owner.effect_operation = available
    reopened = chain_plane(owner, LocalControlPlaneStore(directory), plane._crossing_policy_resolver)
    with reopened:
        outcomes = reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert {item.effect_id: item.disposition for item in outcomes} == {
            "effect-1": "applied",
            "effect-follow": "failed",
        }
        assert reopened.snapshot.participant_control_evaluation_history[PARTICIPANT][0] == original
        assert len(reopened.snapshot.participant_control_history[PARTICIPANT]) == 1
        claims = [r for r in reopened._store.load_records().values() if r.idempotency_key.startswith("control-effect:")]
        assert len(claims) == 2
        assert {r.result_payload["effect_id"]: r.result_payload["disposition"] for r in claims} == {
            "effect-1": "applied",
            "effect-follow": "failed",
        }
        assert reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == outcomes
        assert len(reopened.snapshot.participant_control_history[PARTICIPANT]) == 1
        from raes_runtime.participant_control_causal_state import causal_state_from_history

        context = original["request"]["context"]
        state = causal_state_from_history(
            reopened.snapshot.participant_control_evaluation_history[PARTICIPANT],
            run_ref=context["run"]["ref"],
            trigger_root=context["trigger_root"],
        )
        assert state.effects_consumed == 2
        from raes_contracts.contracts.participant_control_continuation import (
            validate_participant_control_continuation_v2,
        )
        from raes_contracts.contracts.participant_control_evaluation_v2 import ParticipantControlEvaluationV2Model
        from raes_contracts.contracts.participant_control_resolution import (
            validate_participant_control_resolved_context_v2,
        )
        from raes_runtime.participant_control_effect_evidence import (
            retained_effect_intents,
            with_retained_effect_evidence,
        )

        source = ParticipantControlEvaluationV2Model.model_validate(original)
        continuation = next(
            ParticipantControlEvaluationV2Model.model_validate(item)
            for item in reopened.snapshot.participant_control_evaluation_history[PARTICIPANT]
            if item.get("continuation")
        )
        context = with_retained_effect_evidence(
            owner.validation_context(continuation), retained_effect_intents(reopened, source.effect_plan.effects)
        )
        context = replace(
            context,
            commit_receipt=continuation.commit.receipt,
            parent_admission_receipt=continuation.effect_plan.parent_admission_receipt,
            parent_application_receipt=continuation.effect_plan.parent_application_receipt,
        )
        validate_participant_control_continuation_v2(continuation, source, context)
        with pytest.raises(ValueError, match="trusted-context"):
            validate_participant_control_resolved_context_v2(continuation, lambda _: context)
        foreign_source = source.model_copy(update={"evaluation_id": "foreign-source"})
        with pytest.raises(ValueError, match="trusted continuation"):
            validate_participant_control_continuation_v2(continuation, foreign_source, context)
        assert "continuation" not in source.model_dump(mode="json")


def test_newly_ready_predecessor_effect_requires_independent_authority(tmp_path):
    owner = chain_owner()
    trusted = owner.validation_context
    from raes_contracts.contracts.participant_control_applicability import control_digest

    owner.validation_context = lambda evaluation: replace(
        trusted(evaluation),
        authorized_effects={
            control_digest(effect): evaluation.request.context
            for effect in evaluation.effect_plan.effects
            if effect.effect_id == "effect-1"
        },
    )
    plane = chain_plane(owner, LocalControlPlaneStore(tmp_path / "authority"))
    caller = identity(audience_bound=True)
    with plane:
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
        admit(plane, control_identity=caller)
        first = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert {item.effect_id: item.disposition for item in first} == {"effect-1": "applied"}
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == first
        assert (
            len([r for r in plane._store.load_records().values() if r.idempotency_key.startswith("control-effect:")])
            == 1
        )


def test_interrupted_continuation_keeps_recovery_barrier_and_resumes(tmp_path, monkeypatch):
    from raes_runtime.control_plane_recovery import IndeterminateResolutionDisposition

    owner = chain_owner()
    directory = tmp_path / "interrupted-continuation"
    plane = chain_plane(owner, LocalControlPlaneStore(directory))
    caller = identity(audience_bound=True)
    commit = plane._commit_participant_transition

    def interrupted(**kwargs):
        if kwargs["record"].idempotency_key.startswith("control-effect-continuation:"):
            raise OSError("synthetic interruption before continuation commit")
        return commit(**kwargs)

    with plane:
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
        admit(plane, control_identity=caller)
        monkeypatch.setattr(plane, "_commit_participant_transition", interrupted)
        with pytest.raises(OSError):
            plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        claim = next(
            r
            for r in plane._store.load_records().values()
            if r.idempotency_key.startswith("control-effect-continuation:")
        )
    reopened = chain_plane(owner, LocalControlPlaneStore(directory), plane._crossing_policy_resolver)
    with reopened:
        with pytest.raises(ConflictError, match="indeterminate operation requires resolution"):
            reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        reopened.resolve_indeterminate_operation(
            claim.receipt.operation_id,
            disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
            idempotency_key="resolve-continuation",
            identity=caller,
        )
        outcomes = reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert {item.effect_id: item.disposition for item in outcomes} == {
            "effect-1": "applied",
            "effect-follow": "failed",
        }
        assert len(reopened.snapshot.participant_control_history[PARTICIPANT]) == 1
        assert reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == outcomes
