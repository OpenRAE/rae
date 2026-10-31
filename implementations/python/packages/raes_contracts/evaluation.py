"""Shared evaluation runtime result contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from raes_contracts._validation import (
    enum_value,
    require_dict,
    require_non_empty_string,
    require_optional_bool,
    require_optional_int,
    require_optional_numeric,
    require_optional_string,
    require_strings,
)
from raes_contracts.versions import EVALUATION_STATE_SCHEMA_VERSION


class EvaluationResultStatus(str, Enum):
    """Portable lifecycle for evaluator-observable results."""

    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class EvaluationHistoryEventType(str, Enum):
    """Portable evaluator history event kinds."""

    EVALUATION_STARTED = "evaluation_started"
    EVALUATION_UPDATED = "evaluation_updated"
    EVALUATION_READY = "evaluation_ready"
    EVALUATION_FAILED = "evaluation_failed"


_EVALUATION_NON_RESULT_STATUSES = {
    EvaluationResultStatus.PENDING,
    EvaluationResultStatus.RUNNING,
    EvaluationResultStatus.FAILED,
}


def _validate_evaluation_values(
    *,
    status: EvaluationResultStatus,
    passed: bool | None,
    score: float | int | None,
    max_score: int | None,
    context: str,
) -> None:
    if status in _EVALUATION_NON_RESULT_STATUSES and (passed is not None or score is not None or max_score is not None):
        raise ValueError(f"pending/running/failed {context} may not report result values")
    if status == EvaluationResultStatus.READY and passed is None and score is None:
        raise ValueError(f"ready {context} must report passed or score")
    if max_score is not None and score is None:
        raise ValueError(f"{context} may not report max_score without score")


def _optional_fixed_max_score(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError("evaluation result contract fixed_max_score must be an int or None")
    return raw


def _optional_bool(raw: object) -> bool | None:
    return raw if isinstance(raw, bool) else None


def _optional_number(raw: object) -> float | int | None:
    return raw if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None


def _optional_int(raw: object) -> int | None:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else None


def _optional_string(raw: object) -> str | None:
    return str(raw) if raw is not None else None


def _details_mapping(raw: object) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, Mapping) else {}


def _evidence_refs(raw: object, *, context: str) -> tuple[str, ...]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Iterable):
        raise TypeError(f"{context} evidence_refs must be an iterable of strings")
    evidence_ref_items = list(raw)
    evidence_refs = tuple(str(ref) for ref in evidence_ref_items if isinstance(ref, str))
    if len(evidence_refs) != len(evidence_ref_items):
        raise TypeError(f"{context} evidence_refs must contain only strings")
    return evidence_refs


@dataclass(frozen=True)
class EvaluationResultContract:
    """Compiled contract for validating evaluator result envelopes."""

    state_schema_version: str = EVALUATION_STATE_SCHEMA_VERSION
    resource_type: str = ""
    supports_passed: bool = False
    supports_score: bool = False
    fixed_max_score: int | None = None

    def __post_init__(self) -> None:
        _validate_result_contract_identity(self)
        _validate_result_contract_capabilities(self)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> EvaluationResultContract:
        if not isinstance(payload, Mapping):
            raise TypeError("evaluation result contract must be a mapping")
        return cls(
            state_schema_version=str(payload.get("state_schema_version", EVALUATION_STATE_SCHEMA_VERSION)),
            resource_type=str(payload.get("resource_type", "")),
            supports_passed=bool(payload.get("supports_passed", False)),
            supports_score=bool(payload.get("supports_score", False)),
            fixed_max_score=_optional_fixed_max_score(payload.get("fixed_max_score")),
        )


def _validate_result_contract_identity(contract: EvaluationResultContract) -> None:
    if not isinstance(contract.state_schema_version, str) or not contract.state_schema_version:
        raise TypeError("evaluation result contract state_schema_version must be a non-empty string")
    if not isinstance(contract.resource_type, str) or not contract.resource_type:
        raise TypeError("evaluation result contract resource_type must be a non-empty string")


def _validate_result_contract_capabilities(contract: EvaluationResultContract) -> None:
    if not isinstance(contract.supports_passed, bool):
        raise TypeError("evaluation result contract supports_passed must be a bool")
    if not isinstance(contract.supports_score, bool):
        raise TypeError("evaluation result contract supports_score must be a bool")
    if contract.fixed_max_score is not None:
        _validate_fixed_max_score(contract)


def _validate_fixed_max_score(contract: EvaluationResultContract) -> None:
    if isinstance(contract.fixed_max_score, bool) or not isinstance(contract.fixed_max_score, int):
        raise TypeError("evaluation result contract fixed_max_score must be an int or None")
    if contract.fixed_max_score < 0:
        raise ValueError("evaluation result contract fixed_max_score must be >= 0")
    if not contract.supports_score:
        raise ValueError("evaluation result contract fixed_max_score requires supports_score")


@dataclass(frozen=True)
class EvaluationExecutionContract:
    """Compiled contract for validating evaluator history/state transitions."""

    state_schema_version: str = EVALUATION_STATE_SCHEMA_VERSION
    resource_type: str = ""
    allowed_statuses: tuple[str, ...] = (
        EvaluationResultStatus.PENDING.value,
        EvaluationResultStatus.RUNNING.value,
        EvaluationResultStatus.READY.value,
        EvaluationResultStatus.FAILED.value,
    )
    history_event_types: tuple[str, ...] = (
        EvaluationHistoryEventType.EVALUATION_STARTED.value,
        EvaluationHistoryEventType.EVALUATION_UPDATED.value,
        EvaluationHistoryEventType.EVALUATION_READY.value,
        EvaluationHistoryEventType.EVALUATION_FAILED.value,
    )
    requires_start_event: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.state_schema_version, str) or not self.state_schema_version:
            raise TypeError("evaluation execution contract state_schema_version must be a non-empty string")
        if not isinstance(self.resource_type, str) or not self.resource_type:
            raise TypeError("evaluation execution contract resource_type must be a non-empty string")
        if any(not isinstance(status, str) for status in self.allowed_statuses):
            raise TypeError("evaluation execution contract allowed_statuses must be strings")
        if any(not isinstance(event_type, str) for event_type in self.history_event_types):
            raise TypeError("evaluation execution contract history_event_types must be strings")
        if not isinstance(self.requires_start_event, bool):
            raise TypeError("evaluation execution contract requires_start_event must be a bool")

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> EvaluationExecutionContract:
        if not isinstance(payload, Mapping):
            raise TypeError("evaluation execution contract must be a mapping")
        return cls(
            state_schema_version=str(payload.get("state_schema_version", EVALUATION_STATE_SCHEMA_VERSION)),
            resource_type=str(payload.get("resource_type", "")),
            allowed_statuses=tuple(
                str(status)
                for status in payload.get(
                    "allowed_statuses",
                    (
                        EvaluationResultStatus.PENDING.value,
                        EvaluationResultStatus.RUNNING.value,
                        EvaluationResultStatus.READY.value,
                        EvaluationResultStatus.FAILED.value,
                    ),
                )
            ),
            history_event_types=tuple(
                str(event_type)
                for event_type in payload.get(
                    "history_event_types",
                    (
                        EvaluationHistoryEventType.EVALUATION_STARTED.value,
                        EvaluationHistoryEventType.EVALUATION_UPDATED.value,
                        EvaluationHistoryEventType.EVALUATION_READY.value,
                        EvaluationHistoryEventType.EVALUATION_FAILED.value,
                    ),
                )
            ),
            requires_start_event=bool(payload.get("requires_start_event", True)),
        )


@dataclass(frozen=True)
class EvaluationHistoryEvent:
    """Internal normalized evaluator history event."""

    event_type: EvaluationHistoryEventType
    timestamp: str
    status: EvaluationResultStatus
    passed: bool | None = None
    score: float | int | None = None
    max_score: int | None = None
    detail: str | None = None
    evidence_refs: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> EvaluationHistoryEvent:
        if not isinstance(payload, Mapping):
            raise TypeError("evaluation history event must be a mapping")
        missing_keys = [key for key in ("event_type", "timestamp", "status") if key not in payload]
        if missing_keys:
            raise ValueError("evaluation history event is missing required fields: " + ", ".join(missing_keys))
        score_raw = payload.get("score")
        max_score_raw = payload.get("max_score")
        return cls(
            event_type=(enum_value(EvaluationHistoryEventType, payload["event_type"])),
            timestamp=str(payload["timestamp"]),
            status=(enum_value(EvaluationResultStatus, payload["status"])),
            passed=_optional_bool(payload.get("passed")),
            score=_optional_number(score_raw),
            max_score=_optional_int(max_score_raw),
            detail=_optional_string(payload.get("detail")),
            evidence_refs=_evidence_refs(payload.get("evidence_refs", ()), context="evaluation history event"),
            details=_details_mapping(payload.get("details", {})),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "passed": self.passed,
            "score": self.score,
            "max_score": self.max_score,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
            "details": dict(self.details),
        }

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EvaluationHistoryEventType):
            raise TypeError("event_type must be an EvaluationHistoryEventType")
        if not isinstance(self.status, EvaluationResultStatus):
            raise TypeError("status must be an EvaluationResultStatus")
        require_non_empty_string(self.timestamp, "timestamp")
        require_optional_bool(self.passed, "passed")
        require_optional_numeric(self.score, "score")
        require_optional_int(self.max_score, "max_score")
        require_optional_string(self.detail, "detail")
        require_strings(self.evidence_refs, "evidence_refs")
        require_dict(self.details, "details")
        _validate_evaluation_values(
            status=self.status,
            passed=self.passed,
            score=self.score,
            max_score=self.max_score,
            context="evaluation history events",
        )


@dataclass(frozen=True)
class EvaluationExecutionState:
    """Internal normalized execution state for one evaluator-observable resource."""

    state_schema_version: str = EVALUATION_STATE_SCHEMA_VERSION
    resource_type: str = ""
    run_id: str = ""
    status: EvaluationResultStatus = EvaluationResultStatus.PENDING
    observed_at: str = ""
    updated_at: str = ""
    passed: bool | None = None
    score: float | int | None = None
    max_score: int | None = None
    detail: str | None = None
    evidence_refs: tuple[str, ...] = ()

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> EvaluationExecutionState:
        if not isinstance(payload, Mapping):
            raise TypeError("evaluation result payload must be a mapping")
        missing_keys = [
            key
            for key in (
                "state_schema_version",
                "resource_type",
                "run_id",
                "status",
                "observed_at",
                "updated_at",
            )
            if key not in payload
        ]
        if missing_keys:
            raise ValueError("evaluation result payload is missing required fields: " + ", ".join(missing_keys))
        score_raw = payload.get("score")
        max_score_raw = payload.get("max_score")
        return cls(
            state_schema_version=str(payload["state_schema_version"]),
            resource_type=str(payload["resource_type"]),
            run_id=str(payload["run_id"]),
            status=(enum_value(EvaluationResultStatus, payload["status"])),
            observed_at=str(payload["observed_at"]),
            updated_at=str(payload["updated_at"]),
            passed=_optional_bool(payload.get("passed")),
            score=_optional_number(score_raw),
            max_score=_optional_int(max_score_raw),
            detail=_optional_string(payload.get("detail")),
            evidence_refs=_evidence_refs(payload.get("evidence_refs", ()), context="evaluation result"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "state_schema_version": self.state_schema_version,
            "resource_type": self.resource_type,
            "run_id": self.run_id,
            "status": self.status.value,
            "observed_at": self.observed_at,
            "updated_at": self.updated_at,
            "passed": self.passed,
            "score": self.score,
            "max_score": self.max_score,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
        }

    def __post_init__(self) -> None:
        require_non_empty_string(self.state_schema_version, "evaluation result state_schema_version")
        require_non_empty_string(self.resource_type, "evaluation result resource_type")
        require_non_empty_string(self.run_id, "evaluation result run_id")
        if not isinstance(self.status, EvaluationResultStatus):
            raise TypeError("status must be an EvaluationResultStatus")
        require_non_empty_string(self.observed_at, "observed_at")
        require_non_empty_string(self.updated_at, "updated_at")
        require_optional_bool(self.passed, "passed")
        require_optional_numeric(self.score, "score")
        require_optional_int(self.max_score, "max_score")
        require_optional_string(self.detail, "detail")
        require_strings(self.evidence_refs, "evidence_refs")
        _validate_evaluation_values(
            status=self.status,
            passed=self.passed,
            score=self.score,
            max_score=self.max_score,
            context="evaluation results",
        )
        # The checks above make score an int or a float and max_score an int. Python compares those exactly,
        # so the check needs no float conversion, which overflows for an int beyond the float range.
        if self.score is not None and self.max_score is not None and self.score > self.max_score:
            raise ValueError("evaluation result score may not exceed max_score")


def validate_evaluation_result(
    contract: EvaluationResultContract,
    state: EvaluationExecutionState,
) -> list[str]:
    """Return contract violations for one evaluator result envelope."""

    violations = _evaluation_result_identity_violations(contract, state)
    violations.extend(_evaluation_passed_contract_violations(contract, state))
    violations.extend(_evaluation_score_contract_violations(contract, state))
    return violations


def _evaluation_result_identity_violations(
    contract: EvaluationResultContract,
    state: EvaluationExecutionState,
) -> list[str]:
    violations: list[str] = []
    if state.resource_type != contract.resource_type:
        violations.append(
            f"Result resource_type {state.resource_type!r} does not match compiled contract {contract.resource_type!r}."
        )
    if state.state_schema_version != contract.state_schema_version:
        violations.append(
            "Result state_schema_version "
            f"{state.state_schema_version!r} does not match compiled contract "
            f"{contract.state_schema_version!r}."
        )
    return violations


def _evaluation_passed_contract_violations(
    contract: EvaluationResultContract,
    state: EvaluationExecutionState,
) -> list[str]:
    violations: list[str] = []
    if not contract.supports_passed and state.passed is not None:
        violations.append("Result may not report 'passed' for this resource type.")
    if contract.supports_passed and state.status == EvaluationResultStatus.READY and state.passed is None:
        violations.append("Ready result must report 'passed' for this resource type.")
    return violations


def _evaluation_score_contract_violations(
    contract: EvaluationResultContract,
    state: EvaluationExecutionState,
) -> list[str]:
    violations: list[str] = []
    if not contract.supports_score and (state.score is not None or state.max_score is not None):
        violations.append("Result may not report score fields for this resource type.")
    if contract.supports_score and state.status == EvaluationResultStatus.READY and state.score is None:
        violations.append("Ready result must report 'score' for this resource type.")
    if (
        contract.fixed_max_score is not None
        and state.status == EvaluationResultStatus.READY
        and state.max_score != contract.fixed_max_score
    ):
        violations.append(f"Ready result must report max_score {contract.fixed_max_score} for this resource type.")
    return violations


__all__ = (
    "EvaluationExecutionContract",
    "EvaluationExecutionState",
    "EvaluationHistoryEvent",
    "EvaluationHistoryEventType",
    "EvaluationResultContract",
    "EvaluationResultStatus",
    "validate_evaluation_result",
)
