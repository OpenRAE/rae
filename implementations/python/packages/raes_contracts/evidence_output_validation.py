"""Owning semantic validators for emitted evidence output contracts."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import TypeAdapter

from .contracts.experiment_evidence import ExperimentEvidenceRecordModel
from .contracts.participant_runtime import ParticipantBehaviorHistoryEventModel

_OutputValidator = Callable[[object], object]
_OUTPUT_VALIDATORS: dict[str, _OutputValidator] = {
    "experiment-evidence-record-v1": TypeAdapter(ExperimentEvidenceRecordModel).validate_python,
    "participant-behavior-history-event-stream-v1": TypeAdapter(
        list[ParticipantBehaviorHistoryEventModel]
    ).validate_python,
}


def validate_evidence_output_contract(output_contract: str, document: object) -> None:
    """Run the declared contract's owning semantic validator, or fail closed."""

    validator = _OUTPUT_VALIDATORS.get(output_contract)
    if validator is None:
        raise ValueError("evidence output_contract has no owning semantic validator")
    try:
        validator(document)
    except ValueError as exc:
        raise ValueError("emitted evidence does not satisfy the declared output_contract") from exc


__all__ = ["validate_evidence_output_contract"]
