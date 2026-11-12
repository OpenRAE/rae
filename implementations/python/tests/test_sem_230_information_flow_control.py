"""Bounded executable evidence for SEM-230 information-flow semantics."""

from __future__ import annotations

from copy import deepcopy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from raes_contracts.behavioral_relations import load_behavioral_relation_catalog
from sem230_information_flow_model import (
    Crossing,
    CrossingKind,
    Decision,
    Label,
    ParticipantMemoryScope,
    ProjectionPolicyDecision,
    decide_crossing,
    participant_information_state,
    policy_noninterference_holds,
    project_history,
    reactive_policy_noninterference_holds,
)
from tools.check_behavioral_relation_claims import _validate_claim_text

BASE_POLICY = ProjectionPolicyDecision(
    policy_id="participant-egress",
    revision="rev1",
    decision_ref="policy-decisions.participant-egress.cut-1",
    decision_cut_ref="state-cuts.1",
    visible_low_refs=frozenset({"status"}),
    permitted_declassifications=frozenset(),
)


def _crossing(**overrides: object) -> Crossing:
    values: dict[str, object] = {
        "participant": "alice",
        "audience": "participant:alice",
        "order": 1,
        "kind": CrossingKind.DISCLOSURE,
        "label": Label.DISCLOSURE,
        "source_ref": "status",
        "value": "ready",
        "policy_revision": "rev1",
        "policy_decision_ref": "policy-decisions.participant-egress.cut-1",
        "decision_cut_ref": "state-cuts.1",
        "authorized": True,
        "admitted": True,
        "visible": True,
        "marking_authorized": True,
        "declassification_authorized": False,
        "backend_supported": True,
        "transformation_valid": True,
    }
    values.update(overrides)
    return Crossing(**values)


def test_catalog_publishes_revisioned_policy_noninterference_claim_surface():
    catalog = load_behavioral_relation_catalog()

    assert catalog.taxonomy_revision == "rev14"
    relation = catalog.relations["policy-noninterference"]
    assert relation.projection_required is True
    assert relation.quantification.states
    assert relation.quantification.traces
    assert relation.quantification.schedulers
    assert "adaptive low participant strategies" in relation.quantification.strategies
    assert relation.quantification.environments
    assert relation.dimensions.nondeterminism.status == "supported"
    assert relation.dimensions.probability.status == "outside-scope"
    assert relation.dimensions.time.status == "abstracted"
    assert relation.assurance.definition_status == "defined"
    assert relation.assurance.test_status == "bounded"
    assert relation.assurance.proof_status == "deliberately-unproved"
    assert {
        "fagin-halpern-moses-vardi-1995",
        "bohannon-pierce-sjoberg-weirich-zdancewic-2009",
        "clarkson-schneider-2010",
        "goguen-meseguer-1982",
        "milner-1980",
        "sabelfeld-sands-2009",
        "van-glabbeek-1990",
    } <= set(relation.source_refs)

    surface = next(
        candidate
        for candidate in catalog.claim_surfaces
        if candidate.surface_id == "participant-information-flow-policy"
    )
    assert surface.intended_relation_ids == ["policy-noninterference"]
    assert {
        "participant-projected-history-equivalence",
        "trace-equivalence",
        "strong-bisimulation",
        "weak-bisimulation",
    } <= set(surface.prohibited_relation_ids)


def test_unauthorized_high_variation_is_purged_from_projected_histories():
    low = _crossing()
    high_left = _crossing(
        order=2,
        source_ref="hidden-answer",
        value="left-secret",
        visible=False,
    )
    high_right = _crossing(
        order=2,
        source_ref="hidden-answer",
        value="right-secret",
        visible=False,
    )

    assert policy_noninterference_holds(
        left_runs=((low, high_left),),
        right_runs=((low, high_right),),
        policy_decisions=(BASE_POLICY,),
        participant="alice",
        audience="participant:alice",
    )


def test_governed_declassification_changes_low_history_only_at_its_exact_state_cut():
    before_policy = ProjectionPolicyDecision(
        policy_id="participant-egress",
        revision="rev1",
        decision_ref="policy-decisions.participant-egress.cut-3",
        decision_cut_ref="state-cuts.3",
        visible_low_refs=frozenset({"status"}),
        permitted_declassifications=frozenset(),
    )
    future_policy = ProjectionPolicyDecision(
        policy_id="participant-egress",
        revision="rev2",
        decision_ref="policy-decisions.participant-egress.cut-4",
        decision_cut_ref="state-cuts.4",
        visible_low_refs=frozenset({"status"}),
        permitted_declassifications=frozenset({"hidden-answer"}),
    )
    before = _crossing(
        order=3,
        source_ref="hidden-answer",
        value="secret",
        policy_revision="rev1",
        policy_decision_ref=before_policy.decision_ref,
        decision_cut_ref=before_policy.decision_cut_ref,
        visible=False,
        declassification_authorized=True,
    )
    after = _crossing(
        order=4,
        source_ref="hidden-answer",
        value="released",
        policy_revision="rev2",
        policy_decision_ref=future_policy.decision_ref,
        decision_cut_ref=future_policy.decision_cut_ref,
        declassification_authorized=True,
    )

    assert project_history(
        (before, after),
        (before_policy, future_policy),
        participant="alice",
        audience="participant:alice",
    ) == ((4, "hidden-answer", "released"),)


def test_future_policy_revision_cannot_retroactively_authorize_a_crossing():
    future_policy = ProjectionPolicyDecision(
        policy_id="participant-egress",
        revision="rev2",
        decision_ref="policy-decisions.participant-egress.cut-10",
        decision_cut_ref="state-cuts.10",
        visible_low_refs=frozenset({"status", "hidden-answer"}),
        permitted_declassifications=frozenset({"hidden-answer"}),
    )
    earlier = _crossing(
        order=9,
        source_ref="hidden-answer",
        policy_revision="rev2",
        policy_decision_ref=future_policy.decision_ref,
        decision_cut_ref="state-cuts.9",
        declassification_authorized=True,
    )

    assert decide_crossing(earlier, (BASE_POLICY, future_policy)) is Decision.WITHHELD


def test_an_equal_scalar_order_cannot_substitute_for_an_incomparable_state_cut():
    incomparable = _crossing(
        decision_cut_ref="state-cuts.concurrent-right",
        policy_decision_ref=BASE_POLICY.decision_ref,
    )

    assert decide_crossing(incomparable, (BASE_POLICY,)) is Decision.WITHHELD


def test_observability_is_participant_audience_policy_and_exact_cut_relative():
    crossing = _crossing(participant="alice", audience="team:red")

    assert (
        project_history(
            (crossing,),
            (BASE_POLICY,),
            participant="alice",
            audience="participant:alice",
        )
        == ()
    )
    assert project_history(
        (crossing,),
        (BASE_POLICY,),
        participant="alice",
        audience="team:red",
    ) == ((1, "status", "ready"),)


@settings(max_examples=40)
@given(
    authorized=st.booleans(),
    admitted=st.booleans(),
    visible=st.booleans(),
    marking_authorized=st.booleans(),
    backend_supported=st.booleans(),
)
def test_crossing_decision_is_deny_first_across_independent_gates(
    authorized: bool,
    admitted: bool,
    visible: bool,
    marking_authorized: bool,
    backend_supported: bool,
):
    crossing = _crossing(
        authorized=authorized,
        admitted=admitted,
        visible=visible,
        marking_authorized=marking_authorized,
        backend_supported=backend_supported,
    )
    all_gates = authorized and admitted and visible and marking_authorized and backend_supported

    assert (decide_crossing(crossing, (BASE_POLICY,)) is Decision.DISCLOSED) is all_gates


def test_redaction_does_not_grant_authority_and_transformation_requires_fresh_admission():
    redacted_but_unauthorized = _crossing(value="[REDACTED]", authorized=False)
    transformed_without_fresh_admission = _crossing(
        kind=CrossingKind.TRANSFORMATION,
        label=Label.TRANSFORMATION,
        source_ref="derived-status",
        admitted=False,
    )

    assert decide_crossing(redacted_but_unauthorized, (BASE_POLICY,)) is Decision.WITHHELD
    assert decide_crossing(transformed_without_fresh_admission, (BASE_POLICY,)) is Decision.WITHHELD


def test_concealment_and_revocation_do_not_erase_prior_participant_knowledge():
    disclosed = _crossing(order=1)
    concealed = _crossing(
        order=2,
        kind=CrossingKind.CONCEALMENT,
        label=Label.CONCEALMENT,
        value="concealed",
        visible=False,
    )
    revoked = _crossing(
        order=3,
        kind=CrossingKind.REVOCATION,
        label=Label.REVOCATION,
        value="revoked",
        visible=False,
    )

    history = project_history(
        (disclosed, concealed, revoked),
        (BASE_POLICY,),
        participant="alice",
        audience="participant:alice",
    )

    assert history == ((1, "status", "ready"),)


def test_set_based_nondeterminism_compares_all_bounded_projected_histories():
    low = _crossing()
    extra_low = _crossing(order=2, source_ref="status", value="done")
    high = _crossing(order=2, source_ref="hidden-answer", visible=False)

    assert policy_noninterference_holds(
        left_runs=((low,), (low, high)),
        right_runs=((low,),),
        policy_decisions=(BASE_POLICY,),
        participant="alice",
        audience="participant:alice",
    )
    assert not policy_noninterference_holds(
        left_runs=((low,), (low, extra_low)),
        right_runs=((low,),),
        policy_decisions=(BASE_POLICY,),
        participant="alice",
        audience="participant:alice",
    )


def test_adaptive_low_strategy_is_unchanged_by_undelivered_high_variation():
    low = _crossing()
    high_left = _crossing(order=2, source_ref="hidden-answer", value="left-secret", visible=False)
    high_right = _crossing(order=2, source_ref="hidden-answer", value="right-secret", visible=False)

    def choose(history):
        return "inspect" if any(value == "left-secret" for _, _, value in history) else "continue"

    assert reactive_policy_noninterference_holds(
        left_runs=((low, high_left),),
        right_runs=((low, high_right),),
        policy_decisions=(BASE_POLICY,),
        participant="alice",
        audience="participant:alice",
        strategies=(choose,),
        memory_scope=ParticipantMemoryScope.PERSISTENT_ACROSS_EPISODES,
        memory_reset_authority_ref=None,
    )


def test_delivered_high_variation_can_change_an_adaptive_strategy_choice_and_refutes_the_bounded_relation():
    leaky_policy = ProjectionPolicyDecision(
        policy_id="participant-egress",
        revision="rev-leaky",
        decision_ref="policy-decisions.participant-egress.leaky",
        decision_cut_ref="state-cuts.leaky",
        visible_low_refs=frozenset({"status", "hidden-answer"}),
        permitted_declassifications=frozenset(),
    )
    low = _crossing(
        policy_revision=leaky_policy.revision,
        policy_decision_ref=leaky_policy.decision_ref,
        decision_cut_ref=leaky_policy.decision_cut_ref,
    )
    high_left = _crossing(
        order=2,
        source_ref="hidden-answer",
        value="left-secret",
        policy_revision=leaky_policy.revision,
        policy_decision_ref=leaky_policy.decision_ref,
        decision_cut_ref=leaky_policy.decision_cut_ref,
    )
    high_right = _crossing(
        order=2,
        source_ref="hidden-answer",
        value="right-secret",
        policy_revision=leaky_policy.revision,
        policy_decision_ref=leaky_policy.decision_ref,
        decision_cut_ref=leaky_policy.decision_cut_ref,
    )

    def choose(history):
        return "inspect" if any(value == "left-secret" for _, _, value in history) else "continue"

    left_history = project_history(
        (low, high_left),
        (leaky_policy,),
        participant="alice",
        audience="participant:alice",
    )
    right_history = project_history(
        (low, high_right),
        (leaky_policy,),
        participant="alice",
        audience="participant:alice",
    )
    assert choose(left_history) == "inspect"
    assert choose(right_history) == "continue"
    assert not reactive_policy_noninterference_holds(
        left_runs=((low, high_left),),
        right_runs=((low, high_right),),
        policy_decisions=(leaky_policy,),
        participant="alice",
        audience="participant:alice",
        strategies=(choose,),
        memory_scope=ParticipantMemoryScope.PERSISTENT_ACROSS_EPISODES,
        memory_reset_authority_ref=None,
    )


def test_reset_does_not_erase_persistent_information_state_without_memory_reset_authority():
    prior = ((1, "status", "remembered"),)
    current = ((1, "status", "new-episode"),)

    assert participant_information_state(
        current,
        prior_delivered_history=prior,
        memory_scope=ParticipantMemoryScope.PERSISTENT_ACROSS_EPISODES,
        memory_reset_authority_ref=None,
    ) == (*prior, *current)
    with pytest.raises(ValueError, match="authoritative reset"):
        participant_information_state(
            current,
            prior_delivered_history=prior,
            memory_scope=ParticipantMemoryScope.EPISODE_LOCAL_RESET,
            memory_reset_authority_ref=None,
        )
    assert (
        participant_information_state(
            current,
            prior_delivered_history=prior,
            memory_scope=ParticipantMemoryScope.EPISODE_LOCAL_RESET,
            memory_reset_authority_ref="memory-reset-authorities.alice",
        )
        == current
    )


def test_positive_noninterference_claim_requires_relation_and_evidence_boundary():
    failures = _validate_claim_text(
        "The participant channel guarantees noninterference.",
        "docs/example.md",
    )
    assert {failure.rule_id for failure in failures} == {"behavioral-relation-unbound-positive-claim"}

    assert not _validate_claim_text(
        "Relation: `policy-noninterference`. The bounded model satisfies noninterference only for the "
        "enumerated traces; the evidence boundary is the finite SEM-230 abstract domain.",
        "docs/example.md",
    )
    assert not _validate_claim_text(
        "The finite leakage cases do not establish universal noninterference.",
        "docs/example.md",
    )


def test_mutating_any_required_gate_changes_a_successful_decision():
    baseline = _crossing()
    assert decide_crossing(baseline, (BASE_POLICY,)) is Decision.DISCLOSED

    for gate in (
        "authorized",
        "admitted",
        "visible",
        "marking_authorized",
        "backend_supported",
        "transformation_valid",
    ):
        changed = deepcopy(baseline)
        object.__setattr__(changed, gate, False)
        assert decide_crossing(changed, (BASE_POLICY,)) is Decision.WITHHELD, gate
