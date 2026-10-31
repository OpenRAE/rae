"""#1363: API-409 v2 contextual joins through the single owner entry point (MC-03 to MC-08)."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass, replace
from itertools import product
from pathlib import Path

import pytest
import test_issue_1351_mixed_control_design as model
from mixed_control_v2_support import (
    EPISODE,
    PARTICIPANT,
    SCOPE,
    STATES,
    SUPERVISOR,
    History,
    edge_ref,
    policy,
    script_step,
    state_payload,
    transition_payload,
    v1_declaration,
    v1_record,
)
from raes.participant_behavior_specification import MixedControlTransitionKind as Kind
from raes_contracts.contracts import (
    PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE,
    PARTICIPANT_CONTROL_VALIDITY_BOUNDS_MISMATCH,
    ParticipantControlOccurrenceTarget,
    ParticipantControlOccurrenceV2Model,
    ParticipantControlOccurrenceV2RejectionCode,
    fold_participant_control_episode_v2,
    participant_control_history_verifiability,
    participant_control_target_authorization,
    validate_participant_control_occurrence_context,
)
from raes_contracts.participant_mixed_control_vocabulary import ParticipantControlTargetKind as TargetKind
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]


def _validate(history: History, *extra: ParticipantControlOccurrenceV2Model, targets=()) -> None:
    validate_participant_control_occurrence_context(
        [*history.records, *extra],
        declarations=(),
        policies=[history.projection],
        available_targets=targets,
    )


def _refused(history: History, candidate: ParticipantControlOccurrenceV2Model, code: str, targets=()) -> None:
    with pytest.raises(ValueError, match=f"fails {code}$"):
        _validate(history, candidate, targets=targets)


def _proposal_then_take() -> tuple[History, ParticipantControlOccurrenceV2Model]:
    history = History()
    proposal = history.accept("propose")
    history.accept("take")
    return history, proposal


def test_two_cycles_through_the_same_edges_validate_and_the_fold_matches_the_owner() -> None:
    history = History()
    for edge in ("take", "return", "take", "return"):
        history.accept(edge)

    _validate(history)
    result = fold_participant_control_episode_v2(history.records, policy=history.projection)
    assert result.violation is None
    assert (result.state.state_ref, result.state.state_revision, result.state.last_order) == (STATES["A"], 4, 40)
    assert [record.occurrence.permitted_transition_ref for record in history.records] == [
        edge_ref("take"),
        edge_ref("return"),
    ] * 2


@pytest.mark.parametrize("cycle", [("take",), ("take", "return")])
def test_stale_replay_and_an_old_revision_contender_are_refused(cycle: tuple[str, ...]) -> None:
    history = History()
    for edge in cycle:
        history.accept(edge)
    contender = history.candidate(
        "take", prior_state_ref=STATES["A"], expected_state_revision=0, resulting_state_revision=1
    )
    _refused(history, contender, "stale-state")


def test_a_second_decision_and_an_edge_identity_as_proposal_are_refused() -> None:
    history, proposal = _proposal_then_take()
    history.accept("approve", proposal_ref=proposal.occurrence.proposal_id)
    _refused(
        history, history.candidate("approve", proposal_ref=proposal.occurrence.proposal_id), "proposal-already-decided"
    )
    fresh = History()
    _refused(fresh, fresh.candidate("propose", proposal_id=edge_ref("take")), "proposal-identity-reused")


def test_handoff_completion_evidence_is_never_reused() -> None:
    history = History()
    first = history.accept("take")
    history.accept("return")
    reused = history.candidate("take", completion_evidence_ref=first.occurrence.completion_evidence_ref)
    _refused(history, reused, "completion-evidence-reused")


def test_finite_script_admits_no_application_after_exhaustion() -> None:
    projection = policy(form="finite-script", steps=[script_step("h1", "take"), script_step("h2", "return")])
    history = History(projection)
    history.accept("take", step="h1")
    history.accept("return", step="h2")
    _validate(history)
    state = fold_participant_control_episode_v2(history.records, policy=projection).state
    assert (state.state_ref, state.state_revision, state.script_cursor) == (STATES["A"], 2, 2)
    _refused(history, history.candidate("take", step="h1"), "script-exhausted")


@pytest.mark.parametrize(
    ("target", "code"),
    [
        (
            ParticipantControlOccurrenceTarget(TargetKind.ACTION, "action-1", 1, PARTICIPANT, EPISODE, 2),
            "invalid-target",
        ),
        (
            ParticipantControlOccurrenceTarget(TargetKind.ACTION, "action-1", 1, PARTICIPANT, EPISODE, 3),
            "invalid-target",
        ),
        (ParticipantControlOccurrenceTarget(TargetKind.ACTION, "action-1", 1, PARTICIPANT, "e2", 0), "invalid-target"),
        (ParticipantControlOccurrenceTarget(TargetKind.ACTION, "action-1", 2, PARTICIPANT, EPISODE, 0), None),
        (ParticipantControlOccurrenceTarget(TargetKind.ACTION, "action-1", 1, PARTICIPANT, EPISODE, 1), None),
    ],
)
def test_owner_targets_are_eligible_only_before_the_position_in_the_exact_episode(
    target: ParticipantControlOccurrenceTarget, code: str | None
) -> None:
    history = History()
    history.accept("take")
    candidate = history.candidate("direct", target_kind="action", target_ref="action-1", target_revision=1)
    if code is not None:
        _refused(history, candidate, code, targets=[target])
    elif target.target_revision == 2:
        _refused(history, candidate, "stale-target-revision", targets=[target])
    else:
        _validate(history, candidate, targets=[target])


def _windowed_projection(*, step_window: tuple[int, int] | None = None):
    states = [state_payload("A", window=(2, 8)), state_payload("B", window=(4, 12))]
    transitions = [transition_payload("take", window=(0, 10)), transition_payload("return")]
    if step_window is None:
        return policy(states=states, transitions=transitions)
    step = script_step("h1", "take", valid_from_order=step_window[0], valid_until_order=step_window[1])
    return policy(form="finite-script", steps=[step], states=states, transitions=transitions)


@pytest.mark.parametrize(
    ("bounds", "valid"),
    [((4, 8), True), ((0, 10), False), ((4, 9), False)],
)
def test_validity_bounds_are_the_evaluated_window_not_a_copy_of_the_edge(bounds: tuple[int, int], valid: bool) -> None:
    history = History(_windowed_projection())
    candidate = history.candidate("take", effective_order=5, valid_from_order=bounds[0], valid_until_order=bounds[1])
    if valid:
        _validate(history, candidate)
        return
    with pytest.raises(ValueError, match=PARTICIPANT_CONTROL_VALIDITY_BOUNDS_MISMATCH):
        _validate(history, candidate)
    folded = fold_participant_control_episode_v2([candidate], policy=history.projection)
    assert folded.violation == PARTICIPANT_CONTROL_VALIDITY_BOUNDS_MISMATCH


def test_a_finite_script_step_narrows_the_evaluated_bounds() -> None:
    history = History(_windowed_projection(step_window=(5, 6)))
    assert history.candidate("take", step="h1", effective_order=5).occurrence.valid_from_order == 5
    _validate(history, history.candidate("take", step="h1", effective_order=5))
    wide = history.candidate("take", step="h1", effective_order=5, valid_from_order=4, valid_until_order=8)
    with pytest.raises(ValueError, match=PARTICIPANT_CONTROL_VALIDITY_BOUNDS_MISMATCH):
        _validate(history, wide)


def test_resulting_authority_must_be_valid_at_the_cut() -> None:
    late = History(policy(states=[state_payload("A"), state_payload("B", window=(500, 1000))]))
    _refused(late, late.candidate("take", valid_from_order=0, valid_until_order=1000), "late-authority")
    revoked = History(policy(states=[state_payload("A"), state_payload("B", status="revoked")]))
    _refused(revoked, revoked.candidate("take"), "revoked-authority")


@pytest.mark.parametrize(
    "changes",
    [{"controller_ref": SUPERVISOR}, {"authority_basis_refs": ["entities.blue-team"]}],
)
def test_the_record_carries_only_the_acting_source_triple(changes: dict) -> None:
    history = History()
    _refused(history, history.candidate("take", **changes), "controller-not-source")
    _validate(history, history.candidate("take"))


@pytest.mark.parametrize(
    ("scope", "grant", "code"),
    [
        ([SCOPE], [SCOPE, "provision.node.other"], None),
        (["provision.node.other"], [SCOPE, "provision.node.other"], "scope-widened"),
        (["provision.node.other"], [SCOPE], "scope-widened"),
    ],
)
def test_scope_may_narrow_but_never_widen_the_grant_or_behavior_scope(scope, grant, code) -> None:
    states = [{**state_payload("A"), "scope_refs": grant}, state_payload("B")]
    history = History(policy(states=states))
    candidate = history.candidate("take", controlled_scope_refs=scope)
    if code is None:
        _validate(history, candidate)
    else:
        _refused(history, candidate, code)


def _cancel_proposal(history: History, proposal) -> None:
    history.accept("cancel", target_kind="proposal", target_ref=proposal.occurrence.proposal_id, target_revision=1)


def _override_control(history: History, record) -> None:
    history.accept(
        "override",
        superseded_target_kind="control",
        superseded_occurrence_ref=record.event_id,
        superseded_revision=record.occurrence.occurrence_revision,
    )


@pytest.mark.parametrize("ending", ["cancel", "override"])
@pytest.mark.parametrize(
    ("edge", "fields"),
    [
        ("approve", {}),
        ("deny", {}),
        ("direct", {"target_kind": "proposal", "target_revision": 1}),
    ],
)
def test_a_superseded_proposal_cannot_be_decided_or_directed(ending: str, edge: str, fields: dict) -> None:
    history, proposal = _proposal_then_take()
    if ending == "cancel":
        _cancel_proposal(history, proposal)
    else:
        _override_control(history, proposal)
    proposal_id = proposal.occurrence.proposal_id
    key = "target_ref" if edge == "direct" else "proposal_ref"
    _refused(history, history.candidate(edge, **{key: proposal_id}, **fields), "target-superseded")


def test_the_source_of_an_accepted_transformed_proposal_is_replaced() -> None:
    history = History()
    source = history.accept("propose")
    history.accept(
        "propose",
        proposal_id="proposal-transformed",
        source_proposal_ref=source.occurrence.proposal_id,
        source_proposal_revision=1,
        transformation_ref="transformation.redaction",
        envelope={"provenance_refs": [source.event_id, "transformation.redaction"]},
    )
    history.accept("take")
    _refused(history, history.candidate("approve", proposal_ref=source.occurrence.proposal_id), "target-superseded")
    _validate(history, history.candidate("approve", proposal_ref="proposal-transformed"))


@pytest.mark.parametrize(
    ("mutation", "outcome"),
    [
        ("other-episode", "invalid-target"),
        ("later", "invalid-target"),
        ("revision", "stale-target-revision"),
        ("provenance", "provenance must bind its source"),
    ],
)
def test_a_transformed_proposal_needs_an_earlier_same_episode_source_at_its_exact_revision(mutation, outcome) -> None:
    history = History()
    source = history.accept("propose") if mutation != "later" else None
    source_id = source.occurrence.proposal_id if source else "proposal-2"
    fields = {
        "proposal_id": "proposal-transformed",
        "source_proposal_ref": "proposal-elsewhere" if mutation == "other-episode" else source_id,
        "source_proposal_revision": 2 if mutation == "revision" else 1,
        "transformation_ref": "transformation.redaction",
        "envelope": {
            "provenance_refs": ["provenance:test"]
            if mutation == "provenance"
            else [
                source.event_id if source else "participant-control.episode-1.2",
                "transformation.redaction",
            ]
        },
    }
    candidate = history.candidate("propose", **fields)
    with pytest.raises(ValueError, match=outcome):
        _validate(history, candidate)


def test_rejected_records_never_become_targets() -> None:
    history = History()
    rejected = history.reject("propose", "stale-policy")
    history.accept("take")
    for kind, ref in (("control", rejected.event_id), ("proposal", "proposal-1")):
        candidate = history.candidate("direct", target_kind=kind, target_ref=ref, target_revision=1)
        _refused(history, candidate, "invalid-target")


@pytest.mark.parametrize("first", ["override", "cancel"])
def test_one_lifecycle_per_record_shared_by_both_handles_of_an_approval(first: str) -> None:
    history, proposal = _proposal_then_take()
    approval = history.accept("approve", proposal_ref=proposal.occurrence.proposal_id)
    decision = approval.occurrence.decision_ref
    by_control = {
        "superseded_target_kind": "control",
        "superseded_occurrence_ref": approval.event_id,
        "superseded_revision": approval.occurrence.occurrence_revision,
    }
    by_decision = {"target_kind": "decision", "target_ref": decision, "target_revision": 1}
    if first == "override":
        history.accept("override", **by_control)
        second = history.candidate("cancel", **by_decision)
    else:
        history.accept("cancel", **by_decision)
        second = history.candidate("override", **by_control)
    _refused(history, second, "target-superseded")
    again = history.candidate(
        "override", superseded_target_kind="decision", superseded_occurrence_ref=decision, superseded_revision=1
    )
    _refused(history, again, "target-superseded")
    state = fold_participant_control_episode_v2(history.records, policy=history.projection).state
    assert state.lifecycle(approval.event_id).superseded
    for kind, ref in ((TargetKind.CONTROL, approval.event_id), (TargetKind.DECISION, decision)):
        assert participant_control_target_authorization(
            state, citing_kind=Kind.OVERRIDE, target_kind=kind, target_ref=ref
        )
    assert history.records[2] == approval


def test_a_cancellation_of_a_live_proposal_is_accepted_and_ends_its_decidability() -> None:
    history, proposal = _proposal_then_take()
    _cancel_proposal(history, proposal)
    _validate(history)
    _refused(history, history.candidate("approve", proposal_ref=proposal.occurrence.proposal_id), "target-superseded")


def _model_after(ending: str) -> tuple[model.State, model.Target]:
    state = model.accepted(model.State(), "p", "propose", proposal="p")
    proposal = state.targets[0]
    state = model.accepted(state, "h", "take")
    if ending == "approve":
        state = model.accepted(state, "a", "approve", target=proposal)
    return state, proposal


@pytest.mark.parametrize("ending", ["cancel", "approve"])
def test_direction_answers_differently_through_the_two_handles_of_a_proposal(ending: str) -> None:
    history, proposal = _proposal_then_take()
    if ending == "cancel":
        _cancel_proposal(history, proposal)
    else:
        history.accept("approve", proposal_ref=proposal.occurrence.proposal_id)
    code = "target-superseded" if ending == "cancel" else "proposal-already-decided"
    by_proposal = {"target_kind": "proposal", "target_ref": proposal.occurrence.proposal_id, "target_revision": 1}
    by_control = {"target_kind": "control", "target_ref": proposal.event_id, "target_revision": 1}
    _refused(history, history.candidate("direct", **by_proposal), code)
    _validate(history, history.candidate("direct", **by_control))
    intervention = {
        "affected_target_kind": "control",
        "affected_occurrence_ref": proposal.event_id,
        "affected_revision": 1,
    }
    _validate(history, history.candidate("intervene", **intervention))
    if ending == "approve":
        state, target = _model_after(ending)
        control = model.Target("control", "event:1", 1, available_at=1)
        assert model.apply(state, model.request(state, "d1", "direct", target=target))[1] == "decided-proposal"
        assert model.apply(state, model.request(state, "d2", "direct", target=control))[1] == "accepted"


def test_decisions_join_the_exact_proposal_revision_and_identities_are_fresh_per_episode() -> None:
    history, proposal = _proposal_then_take()
    proposal_id = proposal.occurrence.proposal_id
    _refused(
        history, history.candidate("approve", proposal_ref=proposal_id, proposal_revision=2), "stale-target-revision"
    )
    approval = history.accept("approve", proposal_ref=proposal_id)
    history.accept("return")
    _refused(history, history.candidate("propose", proposal_id=proposal_id), "proposal-identity-reused")
    second = history.accept("propose", proposal_id="proposal-other")
    history.accept("take")
    reused = history.candidate(
        "deny", proposal_ref=second.occurrence.proposal_id, decision_ref=approval.occurrence.decision_ref
    )
    _refused(history, reused, "decision-identity-reused")


def test_the_same_proposal_identity_may_recur_in_a_new_episode() -> None:
    first = History()
    proposal = first.accept("propose")
    second = History(policy(episode="episode-2"), episode="episode-2", start=1)
    second.accept("propose", proposal_id=proposal.occurrence.proposal_id)
    validate_participant_control_occurrence_context(
        [*first.records, *second.records], declarations=(), policies=[first.projection, second.projection]
    )


def test_an_approval_edge_resolves_any_one_live_proposal_of_its_episode() -> None:
    history = History()
    first = history.accept("propose")
    second = history.accept("propose")
    history.accept("take")
    history.accept("approve", proposal_ref=second.occurrence.proposal_id)
    history.accept("approve", proposal_ref=first.occurrence.proposal_id)
    _validate(history)
    other = History(policy(episode="episode-2"), episode="episode-2", start=len(history.records))
    other.accept("take")
    cross = other.candidate("approve", proposal_ref=first.occurrence.proposal_id)
    with pytest.raises(ValueError, match="fails invalid-target$"):
        validate_participant_control_occurrence_context(
            [*history.records, *other.records, cross], declarations=(), policies=[history.projection, other.projection]
        )


def test_same_state_proposals_restarts_and_rejected_script_steps_are_accepted() -> None:
    projection = policy(form="finite-script", steps=[script_step("h1", "propose"), script_step("h2", "take")])
    history = History(projection)
    history.reject("take", "script-step-mismatch")
    history.accept("propose", step="h1")
    history.accept("take", step="h2")
    _validate(history)
    restart = History(policy(episode="episode-2"), episode="episode-2", start=len(history.records))
    restart.accept("take")
    validate_participant_control_occurrence_context(
        [*history.records, *restart.records], declarations=(), policies=[projection, restart.projection]
    )


def test_rejected_records_keep_the_attempt_apart_from_the_observed_cut() -> None:
    history = History()
    history.accept("take")
    rejected = history.reject("take", "stale-state", state_ref=STATES["A"], expected_state_revision=0)
    _validate(history)
    assert rejected.occurrence.attempted.permitted_transition_ref == edge_ref("take")
    assert rejected.occurrence.observed.state_revision == 1
    lying = History()
    lying.accept("take")
    lie = ParticipantControlOccurrenceV2Model.model_validate(
        lying.rejected_payload("take", "stale-state", observed={"state_revision": 0, "state_ref": STATES["A"]})
    )
    with pytest.raises(ValueError, match="true observed state"):
        _validate(lying, lie)


def test_an_unknown_but_representable_ref_is_recorded_as_unknown_transition() -> None:
    history = History()
    history.reject("teleport", "unknown-transition")
    _validate(history)
    other = History()
    other.reject("teleport", "stale-state")
    with pytest.raises(ValueError, match="unknown-transition"):
        _validate(other)


def _returned_codes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.count("-") >= 1
        and node.value.replace("-", "").isalpha()
        and node.value.islower()
    }


def test_incumbent_runtime_rejection_codes_are_a_subset_of_the_closed_v2_codes() -> None:
    runtime = REPO_ROOT / "implementations/python/packages/raes_runtime"
    incumbent = _returned_codes(runtime / "participant_control_rejections.py") - {"total-effective-order"}
    incumbent |= {"invalid-target"} & _returned_codes(runtime / "participant_control_targets.py")
    assert incumbent == {
        "unsupported-order-strategy",
        "stale-policy",
        "stale-state",
        "revoked-authority",
        "late-authority",
        "invalid-target",
    }
    assert incumbent <= {code.value for code in ParticipantControlOccurrenceV2RejectionCode}


def test_unverifiable_is_a_typed_result_distinct_from_invalid() -> None:
    history = History()
    history.accept("take")
    report = participant_control_history_verifiability(history.records, policies=())
    assert [(entry.status, entry.missing) for entry in report.entries] == [("unverifiable", ("missing-policy",))]
    with pytest.raises(ValueError, match=PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE):
        validate_participant_control_occurrence_context(history.records, declarations=())

    @dataclass(frozen=True)
    class Unknown:
        participant_address: str = PARTICIPANT
        episode_id: str = EPISODE
        schema_name: str = "participant-control-occurrence"
        schema_version: str = "9.0.0"

    unknown = [Unknown()]
    report = participant_control_history_verifiability(unknown, policies=[history.projection])
    assert report.entries[0].missing == ("unsupported-lineage",)
    with pytest.raises(ValueError, match=PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE):
        validate_participant_control_occurrence_context(unknown, declarations=())

    fresh = History()
    invalid = fresh.candidate("take", controller_ref=SUPERVISOR)
    assert participant_control_history_verifiability([invalid], policies=[fresh.projection]).verifiable
    with pytest.raises(ValueError, match="controller-not-source") as raised:
        _validate(fresh, invalid)
    assert PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE not in str(raised.value)


def test_mixed_archives_select_each_episode_reader_and_report_missing_v1_context() -> None:
    legacy = v1_record(1)
    history = History(start=1)
    history.accept("take")
    archive = [legacy, *history.records]
    validate_participant_control_occurrence_context(
        archive, declarations=[v1_declaration()], policies=[history.projection]
    )
    report = participant_control_history_verifiability(archive, policies=[history.projection])
    assert [(entry.episode_id, entry.missing) for entry in report.entries] == [
        ("episode-0", ("missing-policy",)),
        (EPISODE, ()),
    ]
    with pytest.raises(ValueError, match=PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE):
        validate_participant_control_occurrence_context(archive, declarations=(), policies=[history.projection])
    with pytest.raises(ValueError, match="declaration reference must resolve"):
        validate_participant_control_occurrence_context([legacy], declarations=())


def test_a_same_episode_declaration_cannot_substitute_for_missing_v1_context() -> None:
    legacy = v1_record(1)
    history = History(start=1)
    history.accept("take")
    other = v1_declaration().model_copy(update={"declaration_ref": "participant.behavior-specification.other"})
    archive = [legacy, *history.records]
    report = participant_control_history_verifiability(archive, declarations=[other], policies=[history.projection])
    assert not report.verifiable
    assert report.entries[0].missing == ("missing-policy",)
    with pytest.raises(ValueError, match=PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE):
        validate_participant_control_occurrence_context(archive, declarations=[other], policies=[history.projection])


def test_mixed_archives_refuse_gaps_and_episodes_that_mix_lineages() -> None:
    legacy = v1_record(1)
    declarations = [v1_declaration()]
    gap = History(start=2)
    gap.accept("take")
    gapped = [legacy, *gap.records]
    with pytest.raises(ValueError, match="contiguous"):
        validate_participant_control_occurrence_context(gapped, declarations=declarations, policies=[gap.projection])
    mixed = History(policy(episode="episode-0"), episode="episode-0", start=1)
    mixed.accept("take")
    mixed_episode = [legacy, *mixed.records]
    with pytest.raises(ValueError, match="must not mix occurrence lineages"):
        validate_participant_control_occurrence_context(
            mixed_episode, declarations=declarations, policies=[mixed.projection]
        )


def test_v1_only_batches_never_reach_the_v2_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("v1-only batch reached the v2 reader")

    monkeypatch.setattr(
        "raes_contracts.contracts.participant_control_validation.validate_participant_control_history_v2", refuse
    )
    validate_participant_control_occurrence_context([v1_record(1)], declarations=[v1_declaration()])
    v1 = schema_bundle()["participant-control-occurrence-v1"]["x-raes-invariants"]
    v2 = schema_bundle()["participant-control-occurrence-v2"]["x-raes-invariants"]
    owner = "raes_contracts.contracts.validate_participant_control_occurrence_context"
    assert {item["validator"] for item in v1} & {item["validator"] for item in v2} >= {owner}


def test_trusted_targets_are_frozen_non_wire_values() -> None:
    target = ParticipantControlOccurrenceTarget(TargetKind.ACTION, "action-1", 1, PARTICIPANT, EPISODE, 0)
    with pytest.raises(FrozenInstanceError):
        target.available_at = 5  # type: ignore[misc]
    assert not any("OccurrenceTarget" in str(schema) for schema in schema_bundle().values())


def test_bounded_cycles_agree_with_the_1351_model() -> None:
    # The #1351 model's 64 six-attempt patterns: stale attempts become rejected facts.
    for choices in product((False, True), repeat=6):
        reference = model.State()
        history = History()
        for index, valid in enumerate(choices):
            edge = "take" if reference.current == "A" else "return"
            candidate = model.request(reference, str(index), edge)
            if not valid:
                candidate = replace(candidate, expected_revision=reference.revision + 1)
            reference, disposition = model.apply(reference, candidate)
            if valid:
                history.accept(edge)
            else:
                history.reject(edge, disposition, expected_state_revision=history.revision + 1)
        _validate(history)
        folded = fold_participant_control_episode_v2(history.records, policy=history.projection).state
        assert (folded.state_ref, folded.state_revision) == (STATES[reference.current], reference.revision)


def test_an_accepted_claim_of_a_stale_model_attempt_is_invalid() -> None:
    reference = model.accepted(model.State(), "h1", "take")
    stale = replace(model.request(reference, "h2", "return"), expected_revision=0)
    assert model.apply(reference, stale)[1] == "stale-state"
    history = History()
    history.accept("take")
    _refused(history, history.candidate("return", expected_state_revision=0, resulting_state_revision=1), "stale-state")


def test_participant_wide_positions_are_not_state_revisions() -> None:
    history = History()
    history.reject("take", "stale-policy")
    record = history.accept("take")
    assert (record.occurrence.occurrence_revision, record.occurrence.resulting_state_revision) == (2, 1)
    _validate(history)
