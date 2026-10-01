"""RUN-320 append-only participant-control evaluation history invariants.

Mirrors the RUN-319 crossing and RUN-310 control history guards: the retained
records are complete published API-424 evaluations, keyed by the participant
they were resolved for, and an evaluation identity is never reused or rewritten.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from pydantic import ValidationError

from .contracts.participant_control_composition import ParticipantControlEvaluationModel


def iter_participant_control_evaluation_snapshot_violations(
    history: Mapping[str, Sequence[dict[str, object]]],
) -> list[tuple[str, str]]:
    """Return value-safe violations for one complete evaluation-history snapshot."""

    violations: list[tuple[str, str]] = []
    seen: set[str] = set()
    for participant_address, records in history.items():
        address = f"runtime.snapshot.participant-control-evaluation-history.{participant_address}"
        for payload in records:
            evaluation = _validated(payload, address, violations)
            if evaluation is None:
                continue
            if evaluation.request.context.participant_address != participant_address:
                violations.append(
                    (
                        address,
                        "participant control evaluation history key must equal the resolved participant address",
                    )
                )
            if evaluation.evaluation_id in seen:
                violations.append((address, "participant control evaluation identity must be unique and append-only"))
            seen.add(evaluation.evaluation_id)
    return violations


def _validated(
    payload: dict[str, object],
    address: str,
    violations: list[tuple[str, str]],
) -> ParticipantControlEvaluationModel | None:
    try:
        return ParticipantControlEvaluationModel.model_validate(payload)
    except (TypeError, ValidationError, ValueError):
        # Bounded and value-independent: a rejected record never enters evidence.
        violations.append((address, "participant control evaluation record is not a valid API-424 evaluation"))
        return None


def iter_participant_control_evaluation_transition_violations(
    before: Mapping[str, Sequence[dict[str, object]]],
    after: Mapping[str, Sequence[dict[str, object]]],
) -> Iterator[tuple[str, str]]:
    """Reject any apply result that drops or rewrites a committed evaluation.

    The runtime owns this history: a backend result carries it forward
    unchanged. Appending is the runtime's own commit, so a result that adds,
    removes or edits a record is rejected rather than merged.
    """

    for participant_address, prior in before.items():
        address = f"runtime.snapshot.participant-control-evaluation-history.{participant_address}"
        current = after.get(participant_address)
        if current is None or list(current) != list(prior):
            yield address, "participant control evaluation history is runtime-owned and must be preserved exactly"
    for participant_address in set(after) - set(before):
        address = f"runtime.snapshot.participant-control-evaluation-history.{participant_address}"
        yield address, "participant control evaluation history is runtime-owned and must not be introduced by a result"


__all__ = [
    "iter_participant_control_evaluation_snapshot_violations",
    "iter_participant_control_evaluation_transition_violations",
]
