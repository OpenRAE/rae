"""Claim-result recomputation from frozen observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from tools.formal_semantic_validation._shape import _hashable, _is_sequence, _lookup


def recompute_claim_results(
    protocol: Mapping[str, object],
    corpus: Mapping[str, object],
    snapshot: Mapping[str, object],
) -> list[dict[str, object]]:
    claim_classes = protocol.get("claim_classes", [])
    cases = corpus.get("cases", [])
    observations = snapshot.get("observations", [])
    participant_observations = snapshot.get("participant_observations", [])
    if not all(_is_sequence(value) for value in (claim_classes, cases, observations, participant_observations)):
        return []

    observations_by_case = {
        item.get("case_id"): item
        for item in observations
        if isinstance(item, Mapping) and _hashable(item.get("case_id"))
    }
    participant_count = len(participant_observations)
    derive_from_supported_controls = protocol.get("revision") == "2.0.0"
    return [
        _claim_class_result(
            declaration,
            cases,
            observations_by_case,
            participant_count,
            derive_from_supported_controls=derive_from_supported_controls,
        )
        for declaration in claim_classes
        if isinstance(declaration, Mapping)
    ]


def _matching_case_count(cases: list[Mapping[str, object]], observations_by_case: Mapping[object, object]) -> int:
    return sum(
        1
        for case in cases
        if isinstance(_lookup(observations_by_case, case.get("case_id")), Mapping)
        and observations_by_case[case.get("case_id")].get("actual_outcome") == case.get("expected_outcome")
    )


def _claim_status(
    expected_status: object,
    class_cases: list[Mapping[str, object]],
    supported_cases: list[Mapping[str, object]],
    matching: int,
    supported_matching: int,
    *,
    derive_from_supported_controls: bool,
) -> object:
    status_rank = {"untested": 0, "partial": 1, "demonstrated": 2}
    if not derive_from_supported_controls:
        return expected_status if matching == len(class_cases) and class_cases else "refuted"
    if matching != len(class_cases) or supported_matching != len(supported_cases):
        status: object = "refuted"
    elif not supported_cases:
        status = "untested"
    else:
        status = min(
            ("demonstrated", str(expected_status)),
            key=lambda value: status_rank.get(value, -1),
        )
    return status


def _claim_class_result(
    declaration: Mapping[str, object],
    cases: Sequence[object],
    observations_by_case: Mapping[object, object],
    participant_count: int,
    *,
    derive_from_supported_controls: bool,
) -> dict[str, object]:
    claim_class_id = declaration.get("claim_class_id")
    class_cases = [item for item in cases if isinstance(item, Mapping) and item.get("claim_class_id") == claim_class_id]
    matching = _matching_case_count(class_cases, observations_by_case)
    supported_cases = [item for item in class_cases if item.get("replay_mode") != "unsupported"]
    supported_matching = _matching_case_count(supported_cases, observations_by_case)
    status = _claim_status(
        declaration.get("expected_evidence_status"),
        class_cases,
        supported_cases,
        matching,
        supported_matching,
        derive_from_supported_controls=derive_from_supported_controls,
    )
    return {
        "claim_class_id": claim_class_id,
        "evidence_status": status,
        "case_count": len(class_cases),
        "matching_case_count": matching,
        "replayable_case_count": len(supported_cases),
        "unsupported_case_count": sum(1 for item in class_cases if item.get("replay_mode") == "unsupported"),
        "participant_obligation_count": participant_count if claim_class_id == "semantic-consistency" else 0,
    }
