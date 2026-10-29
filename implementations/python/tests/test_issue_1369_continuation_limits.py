"""Interleaved evaluations share limits with delayed effect continuations."""

from dataclasses import replace

import pytest
from participant_crossing_fixtures import PARTICIPANT, admit, identity
from raes_contracts.contracts.participant_control_applicability import ParticipantControlRequestV2Model, control_digest
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane_store import LocalControlPlaneStore
from raes_runtime.participant_control_causal_state import causal_state_from_history
from test_issue_1369_effect_continuations import chain_owner, chain_plane


def suppress_follow_slot(owner):
    resolve = owner.resolve

    def resolution(**coordinates):
        returned = resolve(**coordinates)
        if not owner.suppress_follow or owner.empty:
            return returned
        payload = returned.request.model_dump(mode="json")
        for field in ("applicable_slot_ids", "required_slot_ids"):
            payload["applicability"][field].remove("follow")
        request = ParticipantControlRequestV2Model.model_validate(payload)
        support = tuple(item for item in returned.support if item.obligation_id != "input:follow")
        returned = replace(returned, request=request, support=support)
        owner.request, owner.support = request, support
        owner.cuts[control_digest(request)] = (returned, owner.records)
        return returned

    owner.suppress_follow = False
    owner.resolve = resolution


@pytest.mark.parametrize("limit", ["effects", "firings", "watermark"])
def test_continuation_cannot_spend_limits_consumed_by_interleaved_work(tmp_path, limit):
    owner = chain_owner()
    owner.selection = owner.selection.model_copy(
        update={
            "bounds": owner.selection.bounds.model_copy(
                update={
                    "max_attempts": 8,
                    "max_effects": {"effects": 2, "firings": 3, "watermark": 4}[limit],
                    "max_firings_per_rule": 2,
                }
            )
        }
    )
    if limit == "firings":
        owner.effect_specs["follow"]["key"]["firing_epoch"] = "epoch-follow"
    if limit == "watermark":
        declare = owner.context_override

        def reserved_consumption(context, coordinates):
            declare(context, coordinates)
            context["effects_consumed"] = max(1, context["effects_consumed"])

        owner.context_override = reserved_consumption
    suppress_follow_slot(owner)
    plane = chain_plane(owner, LocalControlPlaneStore(tmp_path / limit))
    caller = identity(audience_bound=True)
    with plane:
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
        source = admit(plane, control_identity=caller, idempotency_key="source")
        assert plane.get_operation(source.operation_id).state is OperationState.FAILED
        original = plane.snapshot.participant_control_evaluation_history[PARTICIPANT][0]
        assert original["commit"]["dispatchable_effect_ids"] == ["effect-1"]
        owner.suppress_follow = True
        owner.phase, owner.effect_id = "independent", "effect-interleaved"
        if limit == "firings":
            owner.effect_specs["effect"] = {"key": {"firing_epoch": "epoch-interleaved"}}
        interleaved = admit(plane, control_identity=caller, idempotency_key="interleaved")
        assert plane.get_operation(interleaved.operation_id).state is OperationState.SUCCEEDED
        context = original["request"]["context"]
        before = causal_state_from_history(
            plane.snapshot.participant_control_evaluation_history[PARTICIPANT],
            run_ref=context["run"]["ref"],
            trigger_root=context["trigger_root"],
        )
        assert before.effects_consumed == (3 if limit == "watermark" else 2)
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert ("effect-follow" in {item.effect_id for item in outcomes}) == (limit == "watermark")
        assert plane.snapshot.participant_control_evaluation_history[PARTICIPANT][0] == original
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == outcomes
        after = causal_state_from_history(
            plane.snapshot.participant_control_evaluation_history[PARTICIPANT],
            run_ref=context["run"]["ref"],
            trigger_root=context["trigger_root"],
        )
        assert after.effects_consumed == (4 if limit == "watermark" else 2)
        expected = {"effect-1", "effect-interleaved"} | ({"effect-follow"} if limit == "watermark" else set())
        assert {claim.effect_id for claim in after.claims.values()} == expected
        # Shared roots combine independently ordered participant histories.
        # Counting the same immutable evidence cannot depend on group order.
        reordered = causal_state_from_history(
            tuple(reversed(plane.snapshot.participant_control_evaluation_history[PARTICIPANT])),
            run_ref=context["run"]["ref"],
            trigger_root=context["trigger_root"],
        )
        assert reordered.effects_consumed == after.effects_consumed
