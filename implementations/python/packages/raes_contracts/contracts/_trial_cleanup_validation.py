"""Cross-object validation helpers for trial cleanup contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class CleanupObligationLike(Protocol):
    obligation_id: str
    boundary_refs: list[str]
    action_kind: str
    triggers: list[str]
    requirement: str
    idempotency: str


class CleanupResultLike(Protocol):
    @property
    def status(self) -> str: ...


class CleanupReceiptLike(Protocol):
    @property
    def trial_outcome(self) -> str: ...

    @property
    def cleanup_status(self) -> str: ...

    @property
    def obligation_results(self) -> Mapping[str, CleanupResultLike]: ...


class RetryPolicyLike(Protocol):
    after_effect_policy: str
    reset_obligation_refs: list[str]


def validate_reset_retry_obligations(
    cleanup_obligations: Mapping[str, CleanupObligationLike], retry_policy: RetryPolicyLike
) -> None:
    """Require reset retry policies to identify executable, scope-complete resets."""

    obligation_ids = set(cleanup_obligations)
    unknown_reset_refs = sorted(set(retry_policy.reset_obligation_refs) - obligation_ids)
    if unknown_reset_refs:
        raise ValueError(f"retry policy references unknown reset obligations: {', '.join(unknown_reset_refs)}")
    if retry_policy.after_effect_policy != "reset":
        return

    reset_obligations = [cleanup_obligations[obligation_id] for obligation_id in retry_policy.reset_obligation_refs]
    invalid_reset_refs = sorted(
        obligation.obligation_id
        for obligation in reset_obligations
        if obligation.action_kind != "reset"
        or "retry" not in obligation.triggers
        or obligation.requirement != "required"
    )
    if invalid_reset_refs:
        raise ValueError(
            "reset retry policy references obligations that are not required reset actions triggered by retry: "
            f"{', '.join(invalid_reset_refs)}"
        )

    affected_boundaries = {
        boundary_ref
        for obligation in cleanup_obligations.values()
        if obligation.idempotency != "idempotent"
        for boundary_ref in obligation.boundary_refs
    }
    reset_boundaries = {boundary_ref for obligation in reset_obligations for boundary_ref in obligation.boundary_refs}
    uncovered_boundaries = sorted(affected_boundaries - reset_boundaries)
    if uncovered_boundaries:
        raise ValueError(
            f"reset retry obligations do not cover non-idempotent effect boundaries: {', '.join(uncovered_boundaries)}"
        )


_OUTCOME_TRIGGER = {
    "succeeded": "success",
    "failed": "failure",
    "cancelled": "cancellation",
    "timed-out": "timeout",
    "aborted": "abort",
}
_UNATTEMPTED_RESULT_STATUSES = frozenset({"skipped", "not-triggered"})


def validate_cleanup_receipt_results(
    cleanup_obligations: Mapping[str, CleanupObligationLike], receipt: CleanupReceiptLike
) -> None:
    """Check result coverage and trigger consistency without assuming cleanup succeeded.

    A receipt may truthfully report failed, partial, unsupported, or unverified
    cleanup. Every required obligation owed by the terminal trigger still needs
    an attempted result, and a successful cleanup status still needs every owed
    required result to succeed.
    """

    trigger = _OUTCOME_TRIGGER[receipt.trial_outcome]
    for obligation_id, obligation in sorted(cleanup_obligations.items()):
        if obligation.requirement == "required" and trigger in obligation.triggers:
            _validate_owed_required_result(obligation_id, trigger, receipt)
    for obligation_id, result in sorted(receipt.obligation_results.items()):
        triggered = trigger in cleanup_obligations[obligation_id].triggers
        _validate_result_trigger_consistency(obligation_id, trigger, triggered, result.status)
        if receipt.cleanup_status == "succeeded" and result.status not in {"succeeded", "not-triggered"}:
            raise ValueError(f"succeeded cleanup status cannot include unsuccessful result for '{obligation_id}'")


def _validate_owed_required_result(obligation_id: str, trigger: str, receipt: CleanupReceiptLike) -> None:
    result = receipt.obligation_results.get(obligation_id)
    if result is None or result.status in _UNATTEMPTED_RESULT_STATUSES:
        reported = "no result" if result is None else f"'{result.status}'"
        raise ValueError(
            f"required cleanup obligation '{obligation_id}' is owed for trigger '{trigger}' "
            f"and must report an attempted outcome, not {reported}"
        )
    if receipt.cleanup_status == "succeeded" and result.status != "succeeded":
        raise ValueError(
            f"succeeded cleanup status requires required cleanup obligation '{obligation_id}' "
            f"to succeed for trigger '{trigger}'"
        )


def _validate_result_trigger_consistency(obligation_id: str, trigger: str, triggered: bool, status: str) -> None:
    if triggered and status == "not-triggered":
        raise ValueError(
            f"cleanup obligation '{obligation_id}' is triggered by '{trigger}' and cannot be reported 'not-triggered'"
        )
    if not triggered and status != "not-triggered":
        raise ValueError(
            f"cleanup obligation '{obligation_id}' is not triggered by '{trigger}' "
            "and can only be reported 'not-triggered'"
        )
