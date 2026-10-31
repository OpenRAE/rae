"""Bounded falsification evidence for SEM-233 boundary-flow semantics."""

from __future__ import annotations

from dataclasses import replace
from itertools import permutations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from raes_contracts.behavioral_relations import load_behavioral_relation_catalog
from sem233_boundary_flow_model import (
    FlowGateState,
    FlowOperation,
    FlowProfile,
    FlowValue,
    SinkPolicy,
    UnsupportedFlow,
    carry,
    derive,
    join_labels,
    label_leq,
    may_flow_at_sink,
    rewrite_coordinate,
)

CONFIDENTIALITY_UNIVERSE = frozenset(
    {
        "conf:audience:red",
        "conf:destination:vault",
        "conf:sink:no-error-output",
        "conf:deny-unresolved",
    }
)
INTEGRITY_UNIVERSE = frozenset(
    {
        "int:influence:external-mail",
        "int:influence:participant-alice",
        "int:influence:tool-search",
        "int:deny-unresolved",
    }
)

PROFILE = FlowProfile(
    profile_id="participant-boundary-flow-policy-v1",
    profile_revision="rev1",
    authority_revision="sem-233/rev1",
    confidentiality_universe=CONFIDENTIALITY_UNIVERSE,
    integrity_universe=INTEGRITY_UNIVERSE,
)


def _value(
    ref: str,
    *,
    confidentiality: frozenset[str] = frozenset(),
    integrity: frozenset[str] = frozenset(),
    participant: str = "participant:alice",
    episode: str = "episode:one",
    cut: str = "state-cut:7",
) -> FlowValue:
    return FlowValue(
        value_ref=ref,
        label=PROFILE.label(confidentiality=confidentiality, integrity=integrity),
        provenance_refs=frozenset({f"provenance:{ref}"}),
        influence_refs=frozenset({f"influence:{ref}"}),
        participant_ref=participant,
        episode_ref=episode,
        policy_ref="policy:participant-egress",
        policy_revision="rev3",
        state_cut_ref=cut,
    )


def _sink(**overrides: object) -> SinkPolicy:
    values: dict[str, object] = {
        "sink_ref": "sink:external-tool",
        "destination_ref": "destination:vault",
        "profile_id": PROFILE.profile_id,
        "profile_revision": PROFILE.profile_revision,
        "policy_ref": "policy:participant-egress",
        "policy_revision": "rev3",
        "state_cut_ref": "state-cut:7",
        "satisfied_confidentiality": CONFIDENTIALITY_UNIVERSE,
        "satisfied_integrity": INTEGRITY_UNIVERSE,
    }
    values.update(overrides)
    return SinkPolicy(**values)


def test_profile_closes_two_independent_obligation_coordinates() -> None:
    assert PROFILE.bottom.confidentiality == frozenset()
    assert PROFILE.bottom.integrity == frozenset()
    assert PROFILE.top.confidentiality == CONFIDENTIALITY_UNIVERSE
    assert PROFILE.top.integrity == INTEGRITY_UNIVERSE
    assert PROFILE.unknown_label == PROFILE.top

    confidential = PROFILE.label(confidentiality={"conf:audience:red"})
    influenced = PROFILE.label(integrity={"int:influence:external-mail"})

    assert confidential.confidentiality
    assert not confidential.integrity
    assert influenced.integrity
    assert not influenced.confidentiality
    with pytest.raises(UnsupportedFlow, match="outside the closed confidentiality universe"):
        PROFILE.label(confidentiality={"trusted"})


@settings(max_examples=60)
@given(
    a_conf=st.sets(st.sampled_from(sorted(CONFIDENTIALITY_UNIVERSE))),
    a_int=st.sets(st.sampled_from(sorted(INTEGRITY_UNIVERSE))),
    b_conf=st.sets(st.sampled_from(sorted(CONFIDENTIALITY_UNIVERSE))),
    b_int=st.sets(st.sampled_from(sorted(INTEGRITY_UNIVERSE))),
    c_conf=st.sets(st.sampled_from(sorted(CONFIDENTIALITY_UNIVERSE))),
    c_int=st.sets(st.sampled_from(sorted(INTEGRITY_UNIVERSE))),
)
def test_join_is_closed_associative_commutative_idempotent_and_monotone(
    a_conf: set[str],
    a_int: set[str],
    b_conf: set[str],
    b_int: set[str],
    c_conf: set[str],
    c_int: set[str],
) -> None:
    a = PROFILE.label(confidentiality=a_conf, integrity=a_int)
    b = PROFILE.label(confidentiality=b_conf, integrity=b_int)
    c = PROFILE.label(confidentiality=c_conf, integrity=c_int)

    assert join_labels(PROFILE, (a, a)) == a
    assert join_labels(PROFILE, (a, b)) == join_labels(PROFILE, (b, a))
    assert join_labels(PROFILE, (join_labels(PROFILE, (a, b)), c)) == join_labels(
        PROFILE, (a, join_labels(PROFILE, (b, c)))
    )
    joined = join_labels(PROFILE, (a, b, c))
    assert joined.confidentiality <= CONFIDENTIALITY_UNIVERSE
    assert joined.integrity <= INTEGRITY_UNIVERSE

    smaller = PROFILE.label(
        confidentiality=a.confidentiality & b.confidentiality,
        integrity=a.integrity & b.integrity,
    )
    larger = PROFILE.label(
        confidentiality=a.confidentiality | b.confidentiality,
        integrity=a.integrity | b.integrity,
    )
    assert label_leq(smaller, larger)
    assert label_leq(
        join_labels(PROFILE, (smaller, c)),
        join_labels(PROFILE, (larger, c)),
    )


def test_derivation_is_traversal_independent_and_carries_every_possible_influence() -> None:
    inputs = (
        _value("mail", integrity=frozenset({"int:influence:external-mail"})),
        _value("secret", confidentiality=frozenset({"conf:destination:vault"})),
        _value("tool", integrity=frozenset({"int:influence:tool-search"})),
    )

    outcomes = {
        derive(
            PROFILE,
            result_ref="proposal:1",
            inputs=ordering,
            participant_ref="participant:alice",
            episode_ref="episode:one",
            policy_ref="policy:participant-egress",
            policy_revision="rev3",
            state_cut_ref="state-cut:7",
        ).semantic_state
        for ordering in permutations(inputs)
    }

    assert len(outcomes) == 1
    label, provenance, influences = outcomes.pop()
    assert label.confidentiality == frozenset({"conf:destination:vault"})
    assert label.integrity == frozenset({"int:influence:external-mail", "int:influence:tool-search"})
    assert {"provenance:mail", "provenance:secret", "provenance:tool"} <= provenance
    assert {"influence:mail", "influence:secret", "influence:tool"} <= influences


def test_missing_label_and_mismatched_profile_fail_closed() -> None:
    unlabeled = _value("mail")
    unlabeled = unlabeled.without_label()
    derived = derive(
        PROFILE,
        result_ref="proposal:missing-label",
        inputs=(unlabeled,),
        participant_ref="participant:alice",
        episode_ref="episode:one",
        policy_ref="policy:participant-egress",
        policy_revision="rev3",
        state_cut_ref="state-cut:7",
    )

    assert derived.label == PROFILE.unknown_label
    assert derived.supported is False
    assert may_flow_at_sink(PROFILE, derived, _sink(), FlowGateState.allowing()) is False

    other_profile = FlowProfile(
        profile_id=PROFILE.profile_id,
        profile_revision="rev2",
        authority_revision="sem-233/rev2",
        confidentiality_universe=CONFIDENTIALITY_UNIVERSE,
        integrity_universe=INTEGRITY_UNIVERSE,
    )
    with pytest.raises(UnsupportedFlow, match="profile coordinates"):
        join_labels(PROFILE, (PROFILE.bottom, other_profile.bottom))


@pytest.mark.parametrize("missing_field", ["provenance_refs", "influence_refs"])
def test_missing_provenance_or_influence_fails_closed(missing_field: str) -> None:
    value = replace(_value("incomplete-history"), **{missing_field: frozenset()})

    assert may_flow_at_sink(PROFILE, value, _sink(), FlowGateState.allowing()) is False


def test_redaction_cannot_launder_confidentiality_or_integrity() -> None:
    source = _value(
        "retrieved-secret",
        confidentiality=frozenset({"conf:destination:vault"}),
        integrity=frozenset({"int:influence:external-mail"}),
    )
    redacted = derive(
        PROFILE,
        result_ref="redaction:1",
        inputs=(source,),
        participant_ref="participant:bob",
        episode_ref="episode:one",
        policy_ref="policy:participant-egress",
        policy_revision="rev3",
        state_cut_ref="state-cut:7",
    )

    assert redacted.label == source.label
    assert source.provenance_refs <= redacted.provenance_refs
    assert source.influence_refs <= redacted.influence_refs


def test_declassification_and_endorsement_change_only_the_named_coordinate() -> None:
    source = _value(
        "candidate",
        confidentiality=frozenset({"conf:audience:red", "conf:destination:vault"}),
        integrity=frozenset({"int:influence:external-mail"}),
    )
    declassified = rewrite_coordinate(
        PROFILE,
        source,
        result_ref="candidate:declassified",
        operation=FlowOperation.DECLASSIFICATION,
        remove_confidentiality=frozenset({"conf:audience:red"}),
        remove_integrity=frozenset(),
        authority_ref="authority:release-officer",
        sink_ref="sink:external-tool",
        state_cut_ref="state-cut:7",
    )
    endorsed = rewrite_coordinate(
        PROFILE,
        source,
        result_ref="candidate:endorsed",
        operation=FlowOperation.ENDORSEMENT,
        remove_confidentiality=frozenset(),
        remove_integrity=frozenset({"int:influence:external-mail"}),
        authority_ref="authority:integrity-officer",
        sink_ref="sink:external-tool",
        state_cut_ref="state-cut:7",
    )

    assert declassified.label.confidentiality == frozenset({"conf:destination:vault"})
    assert declassified.label.integrity == source.label.integrity
    assert endorsed.label.confidentiality == source.label.confidentiality
    assert endorsed.label.integrity == frozenset()
    assert source.influence_refs == endorsed.influence_refs
    assert source.provenance_refs <= declassified.provenance_refs
    assert source.provenance_refs <= endorsed.provenance_refs
    assert source.label.confidentiality == frozenset({"conf:audience:red", "conf:destination:vault"})
    assert source.label.integrity == frozenset({"int:influence:external-mail"})
    assert declassified.rewrites[-1].profile_id == PROFILE.profile_id
    assert declassified.rewrites[-1].profile_revision == PROFILE.profile_revision
    assert declassified.rewrites[-1].policy_ref == source.policy_ref
    assert declassified.rewrites[-1].policy_revision == source.policy_revision


@pytest.mark.parametrize(
    "operation",
    [
        FlowOperation.APPROVAL,
        FlowOperation.ADMISSION,
        FlowOperation.AUTHENTICATION,
        FlowOperation.AUTHORIZATION,
        FlowOperation.REDACTION,
        FlowOperation.TRANSFORMATION,
    ],
)
def test_non_release_operations_cannot_rewrite_either_coordinate(operation: FlowOperation) -> None:
    source = _value(
        "candidate",
        confidentiality=frozenset({"conf:audience:red"}),
        integrity=frozenset({"int:influence:external-mail"}),
    )

    with pytest.raises(UnsupportedFlow, match="cannot rewrite flow coordinates"):
        rewrite_coordinate(
            PROFILE,
            source,
            result_ref=f"candidate:{operation.value}",
            operation=operation,
            remove_confidentiality=source.label.confidentiality,
            remove_integrity=source.label.integrity,
            authority_ref="authority:supervisor",
            sink_ref="sink:external-tool",
            state_cut_ref="state-cut:7",
        )


def test_handoff_and_episode_replay_preserve_labels_provenance_and_influence() -> None:
    labeled_source = _value(
        "shared-context",
        confidentiality=frozenset({"conf:audience:red"}),
        integrity=frozenset({"int:influence:participant-alice"}),
    )
    source = rewrite_coordinate(
        PROFILE,
        labeled_source,
        result_ref="shared-context:declassified",
        operation=FlowOperation.DECLASSIFICATION,
        remove_confidentiality=frozenset({"conf:audience:red"}),
        remove_integrity=frozenset(),
        authority_ref="authority:release-officer",
        sink_ref="sink:participant-handoff",
        state_cut_ref="state-cut:7",
    )
    handed_off = carry(
        PROFILE,
        source,
        result_ref="handoff:bob",
        participant_ref="participant:bob",
        episode_ref="episode:one",
        policy_ref="policy:participant-egress",
        policy_revision="rev3",
        state_cut_ref="state-cut:7",
    )
    replayed = carry(
        PROFILE,
        handed_off,
        result_ref="replay:episode-two",
        participant_ref="participant:bob",
        episode_ref="episode:two",
        policy_ref="policy:participant-egress",
        policy_revision="rev3",
        state_cut_ref="state-cut:8",
    )

    assert handed_off.value_ref != source.value_ref
    assert replayed.value_ref != handed_off.value_ref
    assert replayed.label == source.label
    assert source.provenance_refs <= replayed.provenance_refs
    assert source.influence_refs <= replayed.influence_refs
    assert replayed.rewrites == source.rewrites
    assert replayed.participant_ref == "participant:bob"
    assert replayed.episode_ref == "episode:two"


def test_final_sink_is_exact_cut_and_deny_first_across_independent_gates() -> None:
    value = _value(
        "action-argument",
        confidentiality=frozenset({"conf:destination:vault"}),
        integrity=frozenset({"int:influence:tool-search"}),
    )
    assert may_flow_at_sink(PROFILE, value, _sink(), FlowGateState.allowing()) is True
    assert (
        may_flow_at_sink(
            PROFILE,
            value,
            _sink(state_cut_ref="state-cut:8"),
            FlowGateState.allowing(),
        )
        is False
    )
    assert (
        may_flow_at_sink(
            PROFILE,
            value,
            _sink(satisfied_integrity=frozenset()),
            FlowGateState.allowing(),
        )
        is False
    )

    for gate_name in FlowGateState.gate_names():
        assert (
            may_flow_at_sink(
                PROFILE,
                value,
                _sink(),
                FlowGateState.allowing().deny(gate_name),
            )
            is False
        )


def test_coordinate_rewrite_is_scoped_to_its_exact_sink_and_cut() -> None:
    source = _value(
        "confidential-output",
        confidentiality=frozenset({"conf:destination:vault"}),
    )
    declassified = rewrite_coordinate(
        PROFILE,
        source,
        result_ref="confidential-output:released",
        operation=FlowOperation.DECLASSIFICATION,
        remove_confidentiality=frozenset({"conf:destination:vault"}),
        remove_integrity=frozenset(),
        authority_ref="authority:release-officer",
        sink_ref="sink:external-tool",
        state_cut_ref="state-cut:7",
    )

    assert may_flow_at_sink(PROFILE, declassified, _sink(), FlowGateState.allowing()) is True
    assert (
        may_flow_at_sink(
            PROFILE,
            declassified,
            _sink(sink_ref="sink:participant-output"),
            FlowGateState.allowing(),
        )
        is False
    )
    replayed = carry(
        PROFILE,
        declassified,
        result_ref="confidential-output:episode-two",
        participant_ref="participant:alice",
        episode_ref="episode:two",
        policy_ref="policy:participant-egress",
        policy_revision="rev3",
        state_cut_ref="state-cut:8",
    )
    assert (
        may_flow_at_sink(
            PROFILE,
            replayed,
            _sink(state_cut_ref="state-cut:8"),
            FlowGateState.allowing(),
        )
        is False
    )


def test_catalog_keeps_one_relation_and_bounds_sem_233_evidence() -> None:
    catalog = load_behavioral_relation_catalog()

    assert catalog.taxonomy_revision == "rev14"
    relation = catalog.relations["policy-noninterference"]
    assert "SEM-233" in relation.definition
    assert "sem-233/rev1" in relation.observation_projection.policy_revision
    assert "test_sem_233_adversarial_boundary_flow.py" in " ".join(relation.bounded_evidence)
    assert relation.assurance.proof_status == "deliberately-unproved"
    assert {
        "denning-1976",
        "myers-liskov-1998",
        "myers-sabelfeld-zdancewic-2006",
        "cecchetti-myers-arden-2017",
    } <= set(relation.source_refs)

    surfaces = [
        surface for surface in catalog.claim_surfaces if surface.surface_id == "participant-information-flow-policy"
    ]
    assert len(surfaces) == 1
    assert surfaces[0].intended_relation_ids == ["policy-noninterference"]
    assert "SEM-233" in surfaces[0].evidence_boundary
    assert any("runtime" in claim.lower() for claim in surfaces[0].explicit_non_claims)
