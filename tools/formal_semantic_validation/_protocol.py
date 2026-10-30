"""Protocol validation for the formal-semantic evidence bundle."""

from __future__ import annotations

from pathlib import Path

from tools.formal_semantic_validation._replay import _validate_test_ref
from tools.formal_semantic_validation._shape import (
    _closed_object,
    _failure,
    _hashable,
    _lookup,
    _member,
    _members,
    _stable_ids,
    _string_list,
)
from tools.formal_semantic_validation._types import (
    _ANALYSIS_RULE_KEYS,
    _CLAIM_CLASS_KEYS,
    _PARTICIPANT_KEYS,
    _PROTOCOL_KEYS,
    EVIDENCE_STATUSES,
    REQUIRED_CLAIM_CLASS_IDS,
    REQUIRED_PARTICIPANT_OBLIGATION_IDS,
    _JsonObject,
)
from tools.policy.common import PolicyFailure


def _validate_protocol(repo_root: Path, protocol: _JsonObject, failures: list[PolicyFailure], path: str) -> None:
    if not _closed_object(
        protocol,
        _PROTOCOL_KEYS,
        rule_id="formal-validation-protocol-shape",
        label="protocol",
        failures=failures,
        path=path,
    ):
        return
    _protocol_scope_failures(protocol, failures, path)
    _claim_class_failures(protocol, failures, path)
    _participant_obligation_failures(repo_root, protocol, failures, path)


def _protocol_scope_failures(protocol: _JsonObject, failures: list[PolicyFailure], path: str) -> None:
    expected_issue = _lookup({"1.0.0": 168, "2.0.0": 828}, protocol.get("revision"))
    if (
        expected_issue is None
        or protocol.get("issue_number") != expected_issue
        or protocol.get("requirement_uid") != "ASR-530"
    ):
        failures.append(
            _failure(
                "formal-validation-protocol-scope",
                "protocol must bind a supported revision to its issue and ASR-530",
                path,
            )
        )
    status_values = list(_members(protocol.get("evidence_status_values", [])))
    if not all(_hashable(item) for item in status_values) or set(status_values) != EVIDENCE_STATUSES:
        failures.append(
            _failure(
                "formal-validation-evidence-status",
                "protocol must use the ADR-021 evidence statuses",
                path,
            )
        )
    _closed_object(
        protocol.get("analysis_rules"),
        _ANALYSIS_RULE_KEYS,
        rule_id="formal-validation-analysis-rules",
        label="analysis_rules",
        failures=failures,
        path=path,
    )


def _claim_class_failures(protocol: _JsonObject, failures: list[PolicyFailure], path: str) -> None:
    claim_ids, unique_claim_ids = _stable_ids(protocol.get("claim_classes"), "claim_class_id")
    if claim_ids != REQUIRED_CLAIM_CLASS_IDS or not unique_claim_ids:
        failures.append(
            _failure(
                "formal-validation-claim-coverage",
                "protocol must contain each required claim class exactly once",
                path,
            )
        )
    for item in _members(protocol.get("claim_classes", [])):
        if not _closed_object(
            item,
            _CLAIM_CLASS_KEYS,
            rule_id="formal-validation-claim-shape",
            label="claim class",
            failures=failures,
            path=path,
        ):
            continue
        if not _member(item.get("expected_evidence_status"), EVIDENCE_STATUSES):
            failures.append(
                _failure(
                    "formal-validation-evidence-status",
                    f"invalid expected status for {item.get('claim_class_id')!r}",
                    path,
                )
            )
        for key in ("allowed_evidence", "disallowed_evidence"):
            if not _string_list(item.get(key)):
                failures.append(
                    _failure(
                        "formal-validation-claim-evidence",
                        f"{item.get('claim_class_id')!r} needs non-empty {key}",
                        path,
                    )
                )


def _participant_obligation_failures(
    repo_root: Path,
    protocol: _JsonObject,
    failures: list[PolicyFailure],
    path: str,
) -> None:
    obligation_ids, unique_obligation_ids = _stable_ids(protocol.get("participant_obligations"), "obligation_id")
    if obligation_ids != REQUIRED_PARTICIPANT_OBLIGATION_IDS or not unique_obligation_ids:
        failures.append(
            _failure(
                "formal-validation-participant-coverage",
                "protocol must contain every participant-semantics obligation exactly once",
                path,
            )
        )
    for item in _members(protocol.get("participant_obligations", [])):
        if not _closed_object(
            item,
            _PARTICIPANT_KEYS,
            rule_id="formal-validation-participant-shape",
            label="participant obligation",
            failures=failures,
            path=path,
        ):
            continue
        positive = item.get("positive_test_ref")
        negative = item.get("negative_test_ref")
        if (
            positive == negative
            or not _validate_test_ref(repo_root, positive)
            or not _validate_test_ref(repo_root, negative)
        ):
            failures.append(
                _failure(
                    "formal-validation-participant-fixtures",
                    f"{item.get('obligation_id')!r} needs distinct existing positive and negative test refs",
                    path,
                )
            )
