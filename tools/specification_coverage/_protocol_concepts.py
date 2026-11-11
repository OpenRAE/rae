"""Concept-catalog validation for the specification-coverage protocol."""

from __future__ import annotations

from tools.policy.common import PolicyFailure
from tools.specification_coverage._keys import (
    _CONCEPT_KEYS,
    EXPECTED_CLASSIFICATIONS,
)
from tools.specification_coverage._primitives import (
    _bounded_list,
    _exact_keys,
    _failure,
    _hashable,
    _member,
    _record_ids,
)

_ALLOWED_CLASSIFICATIONS_BY_KIND = {
    "sdl": {"directly-expressible"},
    "contract": {"directly-expressible", "profile-or-manifest-constraint"},
    "profile": {
        "profile-or-manifest-constraint",
        "deliberately-backend-specific",
    },
    "missing": {"missing"},
}


def _concept_reference_failures(
    concept: dict[str, object],
    request_ids: set[str],
    carrier_ids: set[str],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    if concept.get("atomic") is not True:
        failures.append(
            _failure(
                "specification-coverage-concept-atomicity",
                f"concept {concept.get('concept_id')!r} must be explicitly atomic",
                path,
            )
        )
    if not _member(concept.get("request_id"), request_ids):
        failures.append(
            _failure(
                "specification-coverage-concepts",
                "concept has unknown request",
                path,
            )
        )
    if not _member(concept.get("expected_carrier_id"), carrier_ids):
        failures.append(
            _failure(
                "specification-coverage-concepts",
                "concept has unknown carrier",
                path,
            )
        )


def _concept_classification_failures(
    concept: dict[str, object],
    carriers_by_id: dict[str, dict[str, object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    expected_classification = concept.get("expected_classification")
    carrier_id = concept.get("expected_carrier_id")
    carrier = carriers_by_id.get(carrier_id) if _hashable(carrier_id) else None
    kind = carrier.get("kind") if isinstance(carrier, dict) else None
    allowed = _ALLOWED_CLASSIFICATIONS_BY_KIND.get(kind, set()) if _hashable(kind) else set()
    if not _member(expected_classification, EXPECTED_CLASSIFICATIONS):
        failures.append(
            _failure(
                "specification-coverage-classification-boundary",
                f"concept {concept.get('concept_id')!r} has an invalid expected classification",
                path,
            )
        )
    elif not isinstance(carrier, dict) or expected_classification not in allowed:
        failures.append(
            _failure(
                "specification-coverage-classification-boundary",
                f"concept {concept.get('concept_id')!r} classification is incompatible with its carrier",
                path,
            )
        )
    elif expected_classification == "deliberately-backend-specific" and carrier.get("portable") is not False:
        failures.append(
            _failure(
                "specification-coverage-classification-boundary",
                f"concept {concept.get('concept_id')!r} marks a portable carrier as backend-specific",
                path,
            )
        )
    if concept.get("load_bearing") is True and not _member(
        expected_classification, {"directly-expressible", "profile-or-manifest-constraint"}
    ):
        failures.append(
            _failure(
                "specification-coverage-classification-boundary",
                f"load-bearing concept {concept.get('concept_id')!r} must preregister typed coverage",
                path,
            )
        )


def _concept_stage_declaration_failures(
    concept: dict[str, object],
    stage_ids: set[str],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    concept_stages = concept.get("artifact_stage_ids")
    if (
        not isinstance(concept_stages, list)
        or not concept_stages
        or not all(_hashable(stage) for stage in concept_stages)
        or len(concept_stages) != len(set(concept_stages))
        or any(stage not in stage_ids for stage in concept_stages)
    ):
        failures.append(
            _failure(
                "specification-coverage-concepts",
                "concept stages are invalid",
                path,
            )
        )
    if not isinstance(concept.get("load_bearing"), bool):
        failures.append(
            _failure(
                "specification-coverage-concepts",
                "load_bearing must be boolean",
                path,
            )
        )


def _validated_concepts(
    protocol: dict[str, object],
    request_ids: set[str],
    carrier_ids: set[str],
    carriers_by_id: dict[str, dict[str, object]],
    stage_ids: set[str],
    failures: list[PolicyFailure],
    path: str,
) -> tuple[list[object], set[str]]:
    concepts = _bounded_list(
        protocol.get("concepts"),
        failures,
        rule_id="specification-coverage-concepts",
        label="concepts",
        path=path,
    )
    for index, concept in enumerate(concepts):
        if not _exact_keys(
            concept,
            _CONCEPT_KEYS,
            failures,
            rule_id="specification-coverage-concepts",
            label=f"concepts[{index}]",
            path=path,
        ):
            continue
        _concept_reference_failures(concept, request_ids, carrier_ids, failures, path)
        _concept_classification_failures(concept, carriers_by_id, failures, path)
        _concept_stage_declaration_failures(concept, stage_ids, failures, path)
    concept_ids = _record_ids(
        concepts,
        "concept_id",
        failures,
        rule_id="specification-coverage-concepts",
        label="concepts",
        path=path,
    )
    return concepts, concept_ids


def _request_join_failures(
    request: dict[str, object],
    concepts: list[object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    for concept_id in request["concept_ids"]:
        concept = next(
            (item for item in concepts if isinstance(item, dict) and item.get("concept_id") == concept_id),
            None,
        )
        if concept is None or concept.get("request_id") != request.get("request_id"):
            failures.append(
                _failure(
                    "specification-coverage-concepts",
                    "request/concept join is invalid",
                    path,
                )
            )


def _request_concept_join_failures(
    requests: list[object],
    concepts: list[object],
    concept_ids: set[str],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    declared: list[str] = []
    for request in requests:
        if not isinstance(request, dict) or not isinstance(request.get("concept_ids"), list):
            continue
        declared.extend(request["concept_ids"])
        _request_join_failures(request, concepts, failures, path)
    if (
        not all(_hashable(item) for item in declared)
        or len(declared) != len(set(declared))
        or set(declared) != concept_ids
    ):
        failures.append(
            _failure(
                "specification-coverage-concepts",
                "request concept coverage is not exact",
                path,
            )
        )
