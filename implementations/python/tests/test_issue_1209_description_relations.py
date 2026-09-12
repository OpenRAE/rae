"""Coverage-aware comparison and explicit promotion into a new author artifact."""

from copy import deepcopy

import pytest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.realization_descriptions import TypedRealizationDescriptionModel
from raes_contracts.realization_structure import (
    RealizationClosure,
    evaluate_realization_constraint,
    normalize_realization_literal,
)
from test_issue_1209_descriptions import description_payload


def authored_and_capture(*, value="linux", complete=False):
    original = normalize_realization_literal(
        {"nodes": {"a": {"family": "linux", "release": "1"}}},
        semantic_profile="example-state/v1",
        default_closure=RealizationClosure(posture="open", universe="node-fields/v1", profile="example-state/v1"),
    ).document
    payload = description_payload()
    payload["authored_ref"]["ref_digest"] = canonical_json_digest(original.model_dump(mode="json"))
    payload["facts"] = [payload["facts"][0]]
    payload["facts"][0]["value"]["value"] = value
    payload["coverage"][0]["fact_ids"] = ["family"]
    if complete:
        payload["facts"].append(
            {
                "fact_id": "release",
                "subject": "/nodes/a/release",
                "state": "known",
                "value": {"kind": "literal", "value": "1", "origin": "backend"},
            }
        )
        payload["coverage"][0].update(subject="", status="complete", recursive=True, fact_ids=["family", "release"])
    return original, TypedRealizationDescriptionModel.model_validate(payload)


def test_partial_match_is_unresolved_but_known_violation_is_detected():
    from raes_contracts.description_projection import assess_realization_description

    original, partial = authored_and_capture()
    _, wrong = authored_and_capture(value="other")
    assert assess_realization_description(partial, original).status.value == "unresolved"
    assert assess_realization_description(wrong, original).status.value == "nonconformant"


def test_complete_named_coverage_can_establish_conformance_without_changing_author():
    from raes_contracts.description_projection import assess_realization_description

    original, complete = authored_and_capture(complete=True)
    before = deepcopy(original.model_dump(mode="json"))
    assert assess_realization_description(complete, original).conformant
    assert original.model_dump(mode="json") == before


def test_conflicting_same_time_facts_survive_roundtrip_and_do_not_establish_truth():
    from raes_contracts.description_projection import assess_realization_description

    original, partial = authored_and_capture()
    payload = partial.model_dump(mode="json")
    competing = deepcopy(payload["facts"][0])
    competing.update(fact_id="other-observer")
    competing["value"]["value"] = "other"
    competing["provenance"] = deepcopy(payload["provenance"])
    competing["provenance"]["observer_ref"]["ref_id"] = "observer-2"
    payload["facts"].append(competing)
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    restored = TypedRealizationDescriptionModel.model_validate_json(capture.model_dump_json())
    result = assess_realization_description(restored, original)
    assert len(restored.facts) == 2
    assert result.status.value == "invalid"
    assert result.diagnostics[0].code == "description.contradictory"
    competing["provenance"]["recorded_at"] = "2026-09-12T11:00:00Z"
    changed_over_time = TypedRealizationDescriptionModel.model_validate(payload)
    assert assess_realization_description(changed_over_time, original).status.value == "nonconformant"


def test_promotion_selects_only_named_facts_and_records_a_new_artifact():
    from raes_contracts.description_promotion import promote_description

    original, capture = authored_and_capture(complete=True)
    before = capture.model_dump(mode="json")
    result = promote_description(
        capture,
        original,
        fact_ids=("family",),
        actor="author-1",
        decision_id="decision-1",
        decided_at="2026-09-12T12:00:00Z",
        target_id="new-request",
        target_version="2",
    )
    assert result.constraints is not original
    assert result.selected_fact_ids == ("family",)
    assert result.target_ref.ref_id == "new-request"
    assert result.decision_id == "decision-1" and result.actor == "author-1"
    assert result.transformation.source_digest == canonical_json_digest(before)
    assert result.transformation.target_digest == canonical_json_digest(result.constraints.model_dump(mode="json"))
    assert evaluate_realization_constraint(
        result.constraints, {"nodes": {"a": {"family": "linux", "release": "1"}}}
    ).conformant
    assert not evaluate_realization_constraint(
        result.constraints, {"nodes": {"a": {"family": "linux", "release": "2"}}}
    ).conformant
    assert capture.model_dump(mode="json") == before


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("other", "promotion cannot resolve conflicting assertions or weaken author constraints"),
        (None, "promotion requires selected known supported scalar facts without limitations"),
    ],
)
def test_promotion_refuses_conflicting_or_unobserved_facts(value, message):
    from raes_contracts.description_promotion import promote_description

    original, capture = authored_and_capture(value=value)
    if value is None:
        payload = capture.model_dump(mode="json")
        payload["facts"][0].update(state="not-observed", value=None)
        capture = TypedRealizationDescriptionModel.model_validate(payload)
    with pytest.raises(ValueError, match=message):
        promote_description(
            capture,
            original,
            fact_ids=("family",),
            actor="author-1",
            decision_id="decision-1",
            decided_at="2026-09-12T12:00:00Z",
            target_id="new-request",
            target_version="2",
        )


def test_known_absence_disproves_required_field_even_in_partial_capture():
    from raes_contracts.description_projection import assess_realization_description

    original, capture = authored_and_capture()
    payload = capture.model_dump(mode="json")
    payload["facts"][0].update(state="known-absent", value=None)
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    assert assess_realization_description(capture, original).status.value == "nonconformant"


def test_promotion_cannot_add_a_field_under_closed_author_scope():
    from raes_contracts.description_promotion import promote_description

    original, capture = authored_and_capture()
    original = original.model_copy(
        update={
            "default_closure": RealizationClosure(
                posture="closed", universe="node-fields/v1", profile="example-state/v1"
            )
        }
    )
    payload = capture.model_dump(mode="json")
    payload["authored_ref"]["ref_digest"] = canonical_json_digest(original.model_dump(mode="json"))
    payload["facts"][0]["subject"] = "/nodes/a/extra"
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    with pytest.raises(
        ValueError, match="promotion cannot resolve conflicting assertions or weaken author constraints"
    ):
        promote_description(
            capture,
            original,
            fact_ids=("family",),
            actor="author-1",
            decision_id="decision-1",
            decided_at="2026-09-12T12:00:00Z",
            target_id="new-request",
            target_version="2",
        )


def test_complete_coverage_cannot_combine_different_configuration_windows():
    from raes_contracts.description_projection import assess_realization_description

    original, capture = authored_and_capture(complete=True)
    payload = capture.model_dump(mode="json")
    payload["facts"][0]["provenance"] = {**payload["provenance"], "window_ref": "different-execution"}
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    assert assess_realization_description(capture, original).status.value == "unresolved"


def test_nested_partial_record_still_exposes_a_known_scalar_violation():
    from raes_contracts.description_projection import assess_realization_description

    original, capture = authored_and_capture()
    payload = capture.model_dump(mode="json")
    payload["facts"][0].update(
        subject="/nodes/a",
        value={
            "kind": "recursive-record",
            "origin": "backend",
            "fields": {"family": {"kind": "literal", "origin": "backend", "value": "other"}},
        },
    )
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    assert assess_realization_description(capture, original).status.value == "nonconformant"


def test_mutated_overbudget_input_returns_limit_exceeded():
    from raes_contracts.description_projection import assess_realization_description

    original, capture = authored_and_capture()
    capture = capture.model_copy(update={"limitations": ("x" * 5000,)})
    assert assess_realization_description(capture, original).status.value == "limit-exceeded"


def test_keyed_reordering_is_not_a_conflict_and_sequence_order_survives():
    from raes_contracts.description_projection import description_conflict

    payload = description_payload()

    def member(identity):
        return {
            "identity": [identity],
            "constraint": {
                "kind": "recursive-record",
                "origin": "backend",
                "fields": {"id": {"kind": "literal", "origin": "backend", "value": identity}},
            },
        }

    value = {
        "kind": "keyed-collection",
        "origin": "backend",
        "collection_kind": "components",
        "identity_fields": ["id"],
        "members": [member("a"), member("b")],
    }
    payload["facts"] = [{"fact_id": "one", "subject": "/components", "state": "known", "value": value}]
    second = deepcopy(payload["facts"][0])
    second["fact_id"] = "two"
    second["value"]["members"].reverse()
    payload["facts"].append(second)
    payload["coverage"] = []
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    assert description_conflict(capture) is None
    sequence = {
        "kind": "sequence",
        "origin": "backend",
        "items": [{"kind": "literal", "origin": "backend", "value": n} for n in (2, 1, 2)],
    }
    payload["facts"] = [{"fact_id": "trace", "subject": "/trace", "state": "known", "value": sequence}]
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    restored = TypedRealizationDescriptionModel.model_validate_json(capture.model_dump_json())
    assert [item.value for item in restored.facts[0].value.items] == [2, 1, 2]


def test_disjoint_partial_records_do_not_contradict_each_other():
    from raes_contracts.description_projection import description_conflict

    payload = description_payload()
    payload["facts"] = [
        {
            "fact_id": field,
            "subject": "/nodes/a",
            "state": "known",
            "value": {
                "kind": "recursive-record",
                "origin": "backend",
                "fields": {field: {"kind": "literal", "origin": "backend", "value": value}},
            },
        }
        for field, value in (("family", "linux"), ("release", "1"))
    ]
    payload["coverage"] = []
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    assert description_conflict(capture) is None


def test_incompatible_assertions_in_one_window_are_not_hidden_by_another_window():
    from raes_contracts.description_projection import description_conflict

    payload = description_payload()
    payload["coverage"] = []
    source = payload["facts"][0]
    other = deepcopy(source)
    other.update(fact_id="other")
    other["value"]["value"] = "other"
    later = deepcopy(source)
    later.update(fact_id="later", provenance={**payload["provenance"], "recorded_at": "2026-09-12T13:00:00Z"})
    payload["facts"] = [source, other, later]
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    assert description_conflict(capture).status.value == "invalid"


def test_overlapping_partial_records_require_reconciliation_before_projection():
    from raes_contracts.description_projection import description_values

    payload = description_payload()
    payload["coverage"] = []
    payload["facts"] = [
        {
            "fact_id": field,
            "subject": "/nodes/a",
            "state": "known",
            "value": {
                "kind": "recursive-record",
                "origin": "backend",
                "fields": {field: {"kind": "literal", "origin": "backend", "value": value}},
            },
        }
        for field, value in (("family", "linux"), ("release", "1"))
    ]
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    with pytest.raises(ValueError, match="reconciliation"):
        description_values(capture.facts)


def test_promotion_does_not_ignore_an_absent_ancestor():
    from raes_contracts.description_promotion import promote_description

    original, capture = authored_and_capture()
    payload = capture.model_dump(mode="json")
    payload["facts"].append({"fact_id": "absent-node", "subject": "/nodes/a", "state": "known-absent"})
    capture = TypedRealizationDescriptionModel.model_validate(payload)
    with pytest.raises(
        ValueError, match="promotion cannot resolve conflicting assertions or weaken author constraints"
    ):
        promote_description(
            capture,
            original,
            fact_ids=("family",),
            actor="author",
            decision_id="decision",
            decided_at="2026-09-12T12:00:00Z",
            target_id="new",
            target_version="1",
        )
