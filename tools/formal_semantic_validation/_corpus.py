"""Corpus validation for the formal-semantic evidence bundle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from tools.formal_semantic_validation._shape import (
    _closed_object,
    _failure,
    _hashable,
    _is_sequence,
    _member,
    _members,
    _nonempty_string,
    _stable_ids,
)
from tools.formal_semantic_validation._types import (
    _CASE_KEYS,
    _CORPUS_KEYS,
    _MAX_CASES,
    PRODUCTION_EVIDENCE_REPLAY_MODES,
    REPLAY_MODES,
    _JsonObject,
)
from tools.policy.common import PolicyFailure, safe_repo_path


def _case_reference_failures(
    item: Mapping[str, object],
    claim_ids: set[object],
    polarities: dict[object, set[object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    case_id = item.get("case_id")
    claim_id = item.get("claim_class_id")
    polarity = item.get("polarity")
    if not _member(claim_id, claim_ids):
        failures.append(
            _failure(
                "formal-validation-case-claim",
                f"case {case_id!r} references unknown claim class",
                path,
            )
        )
    else:
        # An unhashable polarity is invalid; None keeps the polarity coverage incomplete.
        polarities[claim_id].add(polarity if _hashable(polarity) else None)
    if not _member(polarity, {"positive", "negative"}):
        failures.append(
            _failure(
                "formal-validation-case-polarity",
                f"case {case_id!r} has invalid polarity",
                path,
            )
        )
    if not _member(item.get("replay_mode"), REPLAY_MODES | PRODUCTION_EVIDENCE_REPLAY_MODES):
        failures.append(
            _failure(
                "formal-validation-replay-mode",
                f"case {case_id!r} has invalid replay mode",
                path,
            )
        )


def _replayable_case_fixture_failures(
    repo_root: Path,
    item: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    case_id = item.get("case_id")
    fixture_value = item.get("fixture_path")
    comparison_value = item.get("comparison_fixture_path")
    fixture = safe_repo_path(repo_root, str(fixture_value)) if _nonempty_string(fixture_value) else None
    if fixture is None or not fixture.is_file():
        failures.append(
            _failure(
                "formal-validation-case-path",
                f"case {case_id!r} has a missing or unsafe fixture",
                path,
            )
        )
    if item.get("replay_mode") == "compile-distinguish":
        comparison = safe_repo_path(repo_root, str(comparison_value)) if _nonempty_string(comparison_value) else None
        if comparison is None or not comparison.is_file():
            failures.append(
                _failure(
                    "formal-validation-case-path",
                    f"case {case_id!r} has a missing or unsafe comparison fixture",
                    path,
                )
            )
    elif comparison_value is not None:
        failures.append(
            _failure(
                "formal-validation-case-path",
                f"case {case_id!r} has an unexpected comparison fixture",
                path,
            )
        )


def _case_fixture_failures(
    repo_root: Path,
    item: Mapping[str, object],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    case_id = item.get("case_id")
    if item.get("replay_mode") == "unsupported":
        if (
            item.get("fixture_path") is not None
            or item.get("comparison_fixture_path") is not None
            or item.get("expected_outcome") != "unsupported"
        ):
            failures.append(
                _failure(
                    "formal-validation-unsupported-case",
                    f"unsupported case {case_id!r} must have no fixture and outcome unsupported",
                    path,
                )
            )
    else:
        _replayable_case_fixture_failures(repo_root, item, failures, path)
    if not _nonempty_string(item.get("limitation")):
        failures.append(
            _failure(
                "formal-validation-case-limit",
                f"case {case_id!r} must record a limitation",
                path,
            )
        )


def _validate_corpus(
    repo_root: Path,
    protocol: _JsonObject,
    corpus: _JsonObject,
    failures: list[PolicyFailure],
    path: str,
) -> dict[str, Mapping[str, object]]:
    if not _closed_object(
        corpus,
        _CORPUS_KEYS,
        rule_id="formal-validation-corpus-shape",
        label="corpus",
        failures=failures,
        path=path,
    ):
        return {}
    cases = corpus.get("cases")
    if not _is_sequence(cases) or not cases or len(cases) > _MAX_CASES:
        failures.append(
            _failure(
                "formal-validation-case-count",
                f"corpus cases must contain 1..{_MAX_CASES} entries",
                path,
            )
        )
        return {}
    _, unique_case_ids = _stable_ids(cases, "case_id")
    if not unique_case_ids:
        failures.append(_failure("formal-validation-case-ids", "case ids must be unique stable ids", path))
    claim_ids = {
        item.get("claim_class_id")
        for item in _members(protocol.get("claim_classes", []))
        if isinstance(item, Mapping) and _hashable(item.get("claim_class_id"))
    }
    return _cases_by_id(repo_root, cases, claim_ids, failures, path)


def _cases_by_id(
    repo_root: Path,
    cases: Sequence[object],
    claim_ids: set[object],
    failures: list[PolicyFailure],
    path: str,
) -> dict[str, Mapping[str, object]]:
    cases_by_id: dict[str, Mapping[str, object]] = {}
    polarities: dict[object, set[object]] = {claim_id: set() for claim_id in claim_ids}
    for item in cases:
        if not _closed_object(
            item,
            _CASE_KEYS,
            rule_id="formal-validation-case-shape",
            label="case",
            failures=failures,
            path=path,
        ):
            continue
        case_id = item.get("case_id")
        if isinstance(case_id, str):
            cases_by_id[case_id] = item
        _case_reference_failures(item, claim_ids, polarities, failures, path)
        _case_fixture_failures(repo_root, item, failures, path)
    _polarity_coverage_failures(polarities, failures, path)
    return cases_by_id


def _polarity_coverage_failures(
    polarities: dict[object, set[object]],
    failures: list[PolicyFailure],
    path: str,
) -> None:
    for claim_id, values in polarities.items():
        if values != {"positive", "negative"}:
            failures.append(
                _failure(
                    "formal-validation-case-polarity",
                    f"claim class {claim_id!r} needs positive and negative cases",
                    path,
                )
            )
