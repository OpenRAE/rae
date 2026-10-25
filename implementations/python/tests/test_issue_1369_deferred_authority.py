"""Deferred work retains its intent but requires current governed authority."""

from copy import deepcopy
from dataclasses import replace

import pytest
from participant_crossing_fixtures import PARTICIPANT, admit, identity
from raes_contracts.contracts.participant_control_applicability import control_digest
from raes_runtime.control_plane_store import LocalControlPlaneStore
from test_issue_1369_effect_continuations import chain_owner, chain_plane


@pytest.mark.parametrize("fallback", [False, True])
def test_queued_source_rechecks_current_authority(tmp_path, fallback):
    from governed_effect_runtime_fixtures import EffectResolver, effect_plane

    owner = chain_owner() if fallback else EffectResolver()
    if fallback:
        owner.phase = "independent"
        owner.effect_specs["follow"].update(
            phase="success-dependent", parent_outcome="applied", allowed_parent_dispositions=[]
        )
        plane = chain_plane(owner, LocalControlPlaneStore(tmp_path / "fallback"))
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
    else:
        plane, _ = effect_plane(owner)
    caller = identity(audience_bound=True)
    trusted = owner.validation_context
    with plane:
        admit(plane, control_identity=caller)
        original = deepcopy(plane.snapshot.participant_control_evaluation_history[PARTICIPANT])
        owner.validation_context = lambda evaluation: replace(trusted(evaluation), authorized_effects={})
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert [item.disposition for item in outcomes] == ["withheld"]
        assert not plane.snapshot.participant_control_history.get(PARTICIPANT)
        assert plane.snapshot.participant_control_evaluation_history[PARTICIPANT] == original


def test_retained_continuation_rechecks_current_authority(tmp_path):
    owner = chain_owner()
    plane = chain_plane(owner, LocalControlPlaneStore(tmp_path / "retained"))
    caller = identity(audience_bound=True)
    trusted, available = owner.validation_context, owner.effect_operation
    with plane:
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
        admit(plane, control_identity=caller)
        owner.effect_operation = lambda effect, context: (
            available(effect, context) if effect.effect_id == "effect-1" else None
        )
        plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert any(
            item.get("continuation") for item in plane.snapshot.participant_control_evaluation_history[PARTICIPANT]
        )
        owner.effect_operation = available
        owner.validation_context = lambda evaluation: replace(
            trusted(evaluation),
            authorized_effects={
                control_digest(effect): evaluation.request.context
                for effect in evaluation.effect_plan.effects
                if effect.effect_id == "effect-1"
            },
        )
        outcomes = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert {item.effect_id: item.disposition for item in outcomes} == {
            "effect-1": "applied",
            "effect-follow": "withheld",
        }
        claims = [r for r in plane._store.load_records().values() if r.idempotency_key.startswith("control-effect:")]
        assert len(claims) == 1
