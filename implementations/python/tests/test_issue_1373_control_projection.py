"""Incremental causal/provider indexes agree with complete retained-history folds."""

from copy import deepcopy

import pytest
from participant_control_contract_fixtures import evaluation_payload
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.participant_control_causal_state import causal_state_from_history


def test_causal_projection_matches_full_fold_after_every_append_and_replacement():
    from raes_contracts.immutable_history import append_history
    from raes_runtime.participant_control_projection import ControlStateProjection

    snapshot = RuntimeSnapshot()
    projection = ControlStateProjection()
    payload = evaluation_payload()
    context = payload["request"]["context"]
    participant = context["participant_address"]
    run, root = context["run"]["ref"], context["trigger_root"]
    for number in range(4):
        record = deepcopy(payload)
        record["evaluation_id"] = f"evaluation-{number}"
        snapshot = snapshot.with_entries(
            {},
            participant_control_evaluation_history=append_history(
                snapshot, "participant_control_evaluation_history", participant, [record]
            ),
        )
        projection.refresh(snapshot)
        assert projection.causal_state(run, root, participant=participant) == causal_state_from_history(
            snapshot.participant_control_evaluation_history[participant], run_ref=run, trigger_root=root
        )
    replacement = RuntimeSnapshot(participant_control_evaluation_history={participant: [payload]})
    projection.refresh(replacement)
    assert projection.causal_state(run, root, participant=participant) == causal_state_from_history(
        [payload], run_ref=run, trigger_root=root
    )


def test_unchanged_cut_does_not_reparse_unrelated_evaluations(monkeypatch):
    from raes_runtime import participant_control_projection as projections

    payload = evaluation_payload()
    participant = payload["request"]["context"]["participant_address"]
    snapshot = RuntimeSnapshot(participant_control_evaluation_history={participant: [payload]})
    projection = projections.ControlStateProjection()
    projection.refresh(snapshot)

    def no_replay(_):
        pytest.fail("unchanged history was parsed again")

    monkeypatch.setattr(projections, "participant_control_evaluation_from_payload", no_replay)
    projection.refresh(snapshot.with_entries({}))
    context = payload["request"]["context"]
    assert projection.causal_state(context["run"]["ref"], context["trigger_root"], participant=participant).attempts


@pytest.mark.parametrize("commit_status", ["prepared", "rejected"])
def test_retained_incomplete_evaluation_never_becomes_dispatchable(commit_status):
    from governed_effect_runtime_fixtures import effect_plane
    from participant_crossing_fixtures import PARTICIPANT, admit, identity
    from raes_contracts.immutable_history import mutable_history_value
    from raes_runtime.participant_control_projection import ControlStateProjection

    plane, _ = effect_plane()
    with plane:
        admit(plane, control_identity=identity(audience_bound=True))
        payload = mutable_history_value(plane._snapshot.participant_control_evaluation_history[PARTICIPANT][0])
    payload["commit"].update(status=commit_status, receipt=None, dispatchable_effect_ids=[])
    snapshot = RuntimeSnapshot(participant_control_evaluation_history={PARTICIPANT: [payload]})
    projection = ControlStateProjection()
    projection.refresh(snapshot)
    assert projection.pending == {}
    assert projection.by_origin == {}
    context = payload["request"]["context"]
    assert projection.causal_state(context["run"]["ref"], context["trigger_root"]) == causal_state_from_history(
        [payload], run_ref=context["run"]["ref"], trigger_root=context["trigger_root"]
    )


def test_commit_finalization_preserves_every_participants_new_suffix():
    from governed_effect_runtime_fixtures import effect_plane
    from participant_crossing_fixtures import PARTICIPANT, admit, identity
    from raes_contracts.immutable_history import mutable_history_value
    from raes_runtime.participant_control_effect_evidence import finalize_evaluation_commits

    plane, _ = effect_plane()
    with plane:
        admit(plane, control_identity=identity(audience_bound=True))
        first = mutable_history_value(plane._snapshot.participant_control_evaluation_history[PARTICIPANT][0])
        owner = plane._operations[first["commit"]["receipt"]["ref"]]
    second = evaluation_payload()
    second["evaluation_id"] = "second-evaluation"
    second_participant = second["request"]["context"]["participant_address"]
    first["commit"].update(status="prepared", receipt=None, dispatchable_effect_ids=[])
    proposed = RuntimeSnapshot(
        participant_control_evaluation_history={PARTICIPANT: [first], second_participant: [second]}
    )
    finalized = finalize_evaluation_commits(RuntimeSnapshot(), proposed, owner)
    histories = finalized.participant_control_evaluation_history
    assert tuple(histories) == (PARTICIPANT, second_participant)
    assert histories[PARTICIPANT][0]["commit"]["status"] == "committed"
    assert histories[second_participant][0]["evaluation_id"] == "second-evaluation"


def test_provider_projection_matches_full_fold_across_refusal_retry_and_rebuild():
    from governed_effect_runtime_fixtures import EffectResolver, effect_plane
    from participant_crossing_fixtures import admit, identity
    from raes_runtime.participant_control_projection import control_projection
    from raes_runtime.participant_control_provider_state import _state_chains

    owner = EffectResolver()
    owner.writes = {"fact"}
    plane, _ = effect_plane(owner)
    with plane:
        caller = identity(audience_bound=True)
        admit(plane, control_identity=caller, idempotency_key="state-first")
        projected = control_projection(plane)
        assert projected.provider_chains == _state_chains(plane._snapshot)
        assert len(projected.provider_chains) == 1
        retained = projected.history
        admit(plane, control_identity=caller, idempotency_key="state-first")
        assert control_projection(plane).history is retained
        # The resolver still supplies the predecessor state, so admission refuses it.
        admit(plane, control_identity=caller, idempotency_key="stale-state")
        assert projected.provider_chains == _state_chains(plane._snapshot)
        assert len(projected.evaluations) == 1
        projected.version = -1
        projected.refresh(plane._snapshot)
        assert projected.provider_chains == _state_chains(plane._snapshot)


def test_inserting_a_stream_before_an_existing_stream_rebuilds_claim_priority():
    import json

    from raes_contracts.canonical import canonical_json_digest
    from raes_runtime.participant_control_projection import ControlStateProjection

    later = evaluation_payload()
    participant = later["request"]["context"]["participant_address"]
    earlier = json.loads(json.dumps(later).replace(participant, "participants.earlier"))
    earlier["evaluation_id"] = "earlier-stream-evaluation"
    context_digest = canonical_json_digest(earlier["request"]["context"])
    bindings = {
        item["instance_id"]: canonical_json_digest(item) for item in earlier["request"]["selection"]["bindings"]
    }
    for result in earlier["results"]:
        result["context_digest"] = context_digest
        result["binding_digest"] = bindings[result["instance_id"]]
    earlier = json.loads(json.dumps(earlier).replace(later["results"][0]["context_digest"], context_digest))
    for old_binding in later["request"]["selection"]["bindings"]:
        earlier = json.loads(
            json.dumps(earlier).replace(canonical_json_digest(old_binding), bindings[old_binding["instance_id"]])
        )
    projection = ControlStateProjection()
    projection.refresh(RuntimeSnapshot(participant_control_evaluation_history={participant: [later]}))
    replacement = RuntimeSnapshot(
        participant_control_evaluation_history={"participants.earlier": [earlier], participant: [later]}
    )
    projection.refresh(replacement)
    context = later["request"]["context"]
    complete = [
        *replacement.participant_control_evaluation_history["participants.earlier"],
        *replacement.participant_control_evaluation_history[participant],
    ]
    assert projection.causal_state(context["run"]["ref"], context["trigger_root"]) == causal_state_from_history(
        complete, run_ref=context["run"]["ref"], trigger_root=context["trigger_root"]
    )
