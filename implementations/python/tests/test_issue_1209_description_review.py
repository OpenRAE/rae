"""Regression evidence for the first partial-description review."""

from copy import deepcopy

import pytest
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.realization_descriptions import TypedRealizationDescriptionModel
from raes_contracts.description_projection import assess_realization_description, description_conflict
from raes_contracts.observation_demand import (
    AchievedObservationValue,
    ObservationBasis,
    ObservationDemandMode,
    ObservationDemandResolution,
    ObservationSelector,
    realization_description_report,
)
from raes_contracts.realization_structure import RealizationClosure
from test_issue_1209_description_relations import authored_and_capture
from test_issue_1209_descriptions import description_payload
from test_issue_1212_runtime_boundaries import _demands


def test_literal_conflicts_preserve_integer_versus_float_type():
    payload = description_payload()
    payload["coverage"] = []
    payload["facts"] = [
        {
            "fact_id": str(i),
            "subject": "/value",
            "state": "known",
            "value": {"kind": "literal", "origin": "backend", "value": value},
        }
        for i, value in enumerate((1, 1.0))
    ]
    assert description_conflict(TypedRealizationDescriptionModel.model_validate(payload)).status.value == "invalid"


def test_mixed_windows_do_not_hide_a_known_author_violation():
    original, capture = authored_and_capture(value="wrong", complete=True)
    payload = capture.model_dump(mode="json")
    payload["facts"][1]["provenance"] = {**payload["provenance"], "window_ref": "another-window"}
    assert (
        assess_realization_description(TypedRealizationDescriptionModel.model_validate(payload), original).status.value
        == "nonconformant"
    )


def test_conformance_rejects_coverage_of_wrong_kind():
    original, capture = authored_and_capture(complete=True)
    payload = capture.model_dump(mode="json")
    payload["coverage"][0]["kind"] = "collection"
    assert not assess_realization_description(
        TypedRealizationDescriptionModel.model_validate(payload), original
    ).conformant


def test_conformance_requires_root_effective_coverage_universe():
    original, capture = authored_and_capture(complete=True)
    payload = capture.model_dump(mode="json")
    original = original.model_copy(
        update={
            "root": original.root.model_copy(
                update={
                    "closure": RealizationClosure(posture="open", universe="root-fields/v1", profile="example-state/v1")
                }
            )
        }
    )
    payload["authored_ref"]["ref_digest"] = canonical_json_digest(original.model_dump(mode="json"))
    assert not assess_realization_description(
        TypedRealizationDescriptionModel.model_validate(payload), original
    ).conformant
    payload["coverage"][0]["universe"] = "root-fields/v1"
    assert assess_realization_description(TypedRealizationDescriptionModel.model_validate(payload), original).conformant


def _report(payload, *, exhaustive=False, protector=None):
    selector = ObservationSelector(
        semantic_scope="/nodes/a",
        data_kind="field",
        names=("family",),
        coverage_profile="example-state/v1",
        max_items=8,
    )
    demands = _demands(selector, purpose="realization-description", required=True)
    if exhaustive:
        demands = tuple(d.model_copy(update={"mode": ObservationDemandMode.EXHAUSTIVE}) for d in demands)
    value = AchievedObservationValue(
        TypedRealizationDescriptionModel.model_validate(payload), ObservationBasis.BACKEND_SELECTED
    )
    return realization_description_report(
        ObservationDemandResolution(demands), {selector.key: value}, protector=protector
    )


@pytest.mark.parametrize("change", ["missing", "partial", "profile", "kind", "broader", "excluded", "unknown"])
def test_required_exhaustive_description_rejects_unmatched_coverage(change):
    payload = description_payload()
    payload["facts"] = payload["facts"][:1]
    payload["coverage"][0].update(status="complete", recursive=True, fact_ids=["family"])
    if change == "missing":
        payload["coverage"] = []
    elif change == "partial":
        payload["coverage"][0]["status"] = "partial"
    elif change == "profile":
        payload["coverage"][0]["profile"] = "other/v1"
    elif change == "kind":
        payload["coverage"][0]["kind"] = "collection"
    elif change == "broader":
        payload["coverage"][0]["subject"] = "/nodes"
    elif change == "unknown":
        payload["facts"][0].update(state="not-observed", value=None)
    else:
        payload["coverage"][0]["limitations"] = ["A requested field was excluded."]
    with pytest.raises(ValueError, match="coverage|unsatisfied"):
        _report(payload, exhaustive=True)


def test_exhaustive_description_accepts_matching_complete_coverage():
    payload = description_payload()
    payload["facts"] = payload["facts"][:1]
    payload["coverage"][0].update(status="complete", recursive=True, fact_ids=["family"])
    assert _report(payload, exhaustive=True)[0].value.coverage[0].status == "complete"


def test_narrow_report_does_not_retain_a_broader_complete_claim():
    payload = description_payload()
    payload["facts"] = payload["facts"][:1]
    payload["coverage"][0].update(subject="/nodes", status="complete", recursive=True, fact_ids=["family"])
    assert _report(payload)[0].value.coverage == ()


@pytest.mark.parametrize("carrier", ["mapping", "text"])
def test_protector_cannot_escape_typed_projection_by_changing_carrier(carrier):
    payload = description_payload()
    restored = deepcopy(payload)
    restored["facts"][1].update(
        state="known", value={"kind": "literal", "origin": "backend", "value": "excluded-sentinel"}
    )
    raw = restored if carrier == "mapping" else repr(restored)
    with pytest.raises(ValueError, match="typed description"):
        _report(payload, protector=lambda *_: AchievedObservationValue(raw, ObservationBasis.BACKEND_SELECTED))


def test_selector_exclusions_remove_complete_coverage_claims():
    payload = description_payload()
    payload["facts"] = payload["facts"][:1]
    payload["coverage"][0].update(status="complete", recursive=True, fact_ids=["family"])
    selector = ObservationSelector(
        semantic_scope="/nodes/a",
        excluded_scopes=("/nodes/a/private",),
        data_kind="field",
        names=("family",),
        coverage_profile="example-state/v1",
        max_items=8,
    )
    demands = tuple(
        d.model_copy(update={"mode": ObservationDemandMode.EXHAUSTIVE})
        for d in _demands(selector, purpose="realization-description", required=True)
    )
    value = AchievedObservationValue(
        TypedRealizationDescriptionModel.model_validate(payload), ObservationBasis.BACKEND_SELECTED
    )
    resolution = ObservationDemandResolution(demands)
    with pytest.raises(ValueError, match="coverage|unsatisfied"):
        realization_description_report(resolution, {selector.key: value})


def test_coverage_cannot_claim_stronger_basis_than_the_report():
    payload = description_payload()
    payload["facts"] = payload["facts"][:1]
    payload["coverage"][0].update(
        status="complete",
        recursive=True,
        fact_ids=["family"],
        provenance={
            **payload["provenance"],
            "basis": "observed",
            "evidence_refs": [{"ref_kind": "other", "ref_id": "forged"}],
        },
    )
    with pytest.raises(ValueError, match="basis|coverage|unsatisfied"):
        _report(payload, exhaustive=True)


def test_optional_exhaustive_description_omits_an_unsatisfied_result():
    selector = ObservationSelector(
        semantic_scope="/nodes/a",
        data_kind="field",
        names=("family",),
        coverage_profile="example-state/v1",
        max_items=8,
    )
    demands = tuple(
        d.model_copy(update={"mode": ObservationDemandMode.EXHAUSTIVE})
        for d in _demands(selector, purpose="realization-description", required=False)
    )
    value = AchievedObservationValue(
        TypedRealizationDescriptionModel.model_validate(description_payload()), ObservationBasis.BACKEND_SELECTED
    )
    assert realization_description_report(ObservationDemandResolution(demands), {selector.key: value}) == ()
