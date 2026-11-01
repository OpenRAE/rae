"""Snapshot and transition invariants for ACT-604 information-state history."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from raes_contracts.contracts.participant_information_state import (
    ParticipantInformationStateContextResolver,
    ParticipantInformationStateRecordModel,
    validate_participant_information_state_resolved_context,
)

Violation = tuple[str, str]


@dataclass
class _SnapshotHistoryValidationContext:
    trusted_history: Mapping[str, list[dict[str, object]]]
    known_event_ids: set[str]
    known_state_refs: set[str]
    information_state_context_resolver: ParticipantInformationStateContextResolver | None
    context_scope: object | None


def _history_entry_violation(
    address: str,
    participant_address: object,
    raw_records: object,
) -> Violation | None:
    violation = None
    if not isinstance(participant_address, str) or not participant_address:
        violation = (address, "information_state_history keys must be non-empty strings")
    elif not isinstance(raw_records, Sequence) or isinstance(raw_records, (str, bytes, bytearray)):
        violation = (f"{address}.{participant_address}", "information_state_history entries must be lists")
    return violation


def _validated_history_record(
    raw_record: object,
    record_path: str,
) -> tuple[ParticipantInformationStateRecordModel | None, Violation | None]:
    record = None
    violation = None
    if not isinstance(raw_record, Mapping):
        violation = (record_path, "information-state history record must be a mapping")
    else:
        try:
            record = ParticipantInformationStateRecordModel.model_validate(raw_record)
        except ValidationError:
            violation = (record_path, "information-state history record failed contract validation")
    return record, violation


def _record_identity_violations(
    record: ParticipantInformationStateRecordModel,
    *,
    participant_address: str,
    record_path: str,
    known_event_ids: set[str],
    known_state_refs: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    if record.participant_address != participant_address:
        violations.append((record_path, "information-state history map key must equal embedded participant_address"))
    if record.event_id in known_event_ids:
        violations.append((record_path, "information-state history event_id values must be unique"))
    known_event_ids.add(record.event_id)
    if record.information_state_ref in known_state_refs:
        violations.append((record_path, "information_state_ref values must be unique across snapshot history"))
    known_state_refs.add(record.information_state_ref)
    return violations


def _record_lineage_violations(
    record: ParticipantInformationStateRecordModel,
    *,
    record_path: str,
    participant_prior_refs: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    missing_predecessors = sorted(set(record.predecessor_information_state_refs) - participant_prior_refs)
    if missing_predecessors:
        violations.append(
            (record_path, "predecessor_information_state_refs must resolve to earlier participant history records")
        )
    if (
        record.supersedes_information_state_ref is not None
        and record.supersedes_information_state_ref not in participant_prior_refs
    ):
        violations.append(
            (record_path, "supersedes_information_state_ref must resolve to an earlier participant history record")
        )
    participant_prior_refs.add(record.information_state_ref)
    return violations


def _record_context_violation(
    record: ParticipantInformationStateRecordModel,
    *,
    record_path: str,
    trusted_prefix_member: bool,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None,
    context_scope: object | None,
) -> Violation | None:
    violation = None
    if not trusted_prefix_member:
        if information_state_context_resolver is None:
            violation = (record_path, "participant information-state context resolver is required")
        else:
            try:
                validate_participant_information_state_resolved_context(
                    record,
                    information_state_context_resolver,
                    context_scope,
                )
            except TypeError, ValueError:
                violation = (record_path, "information-state contextual validation failed")
    return violation


def _participant_history_violations(
    raw_records: Sequence[object],
    *,
    participant_address: str,
    participant_path: str,
    validation: _SnapshotHistoryValidationContext,
) -> list[Violation]:
    violations: list[Violation] = []
    participant_prior_refs: set[str] = set()
    for index, raw_record in enumerate(raw_records):
        record_path = f"{participant_path}[{index}]"
        record, contract_violation = _validated_history_record(raw_record, record_path)
        if contract_violation is not None:
            violations.append(contract_violation)
            continue
        assert record is not None
        violations.extend(
            _record_identity_violations(
                record,
                participant_address=participant_address,
                record_path=record_path,
                known_event_ids=validation.known_event_ids,
                known_state_refs=validation.known_state_refs,
            )
        )
        violations.extend(
            _record_lineage_violations(
                record,
                record_path=record_path,
                participant_prior_refs=participant_prior_refs,
            )
        )
        context_violation = _record_context_violation(
            record,
            record_path=record_path,
            trusted_prefix_member=index < len(validation.trusted_history.get(participant_address, [])),
            information_state_context_resolver=validation.information_state_context_resolver,
            context_scope=validation.context_scope,
        )
        if context_violation is not None:
            violations.append(context_violation)
    return violations


def iter_participant_information_state_snapshot_violations(
    information_state_history: object,
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
    context_scope: object | None = None,
    trusted_history: Mapping[str, list[dict[str, object]]] | None = None,
) -> Iterator[Violation]:
    """Yield fixed-message violations for one first-class snapshot history."""

    address = "runtime.snapshot.information-state-history"
    if not isinstance(information_state_history, Mapping):
        yield address, "information_state_history must be a mapping"
    else:
        validation = _SnapshotHistoryValidationContext(
            trusted_history=trusted_history or {},
            known_event_ids=set(),
            known_state_refs=set(),
            information_state_context_resolver=information_state_context_resolver,
            context_scope=context_scope,
        )
        for participant_address, raw_records in information_state_history.items():
            entry_violation = _history_entry_violation(address, participant_address, raw_records)
            if entry_violation is not None:
                yield entry_violation
                continue
            assert isinstance(participant_address, str)
            assert isinstance(raw_records, Sequence) and not isinstance(raw_records, (str, bytes, bytearray))
            participant_path = f"{address}.{participant_address}"
            yield from _participant_history_violations(
                raw_records,
                participant_address=participant_address,
                participant_path=participant_path,
                validation=validation,
            )


def iter_participant_information_state_history_transition_violations(
    previous_history: Mapping[str, list[dict[str, object]]],
    next_history: Mapping[str, list[dict[str, object]]],
) -> Iterator[Violation]:
    """Require durable information-state histories to preserve an exact prefix."""

    address = "runtime.snapshot.information-state-history"
    for participant_address, previous_records in previous_history.items():
        participant_path = f"{address}.{participant_address}"
        if participant_address not in next_history:
            yield participant_path, "information-state history was removed"
            continue
        next_records = next_history[participant_address]
        if len(next_records) < len(previous_records):
            yield participant_path, ("information_state_history shrank and must be append-only")
            continue
        if next_records[: len(previous_records)] != previous_records:
            yield participant_path, "information_state_history must be append-only"


__all__ = (
    "iter_participant_information_state_history_transition_violations",
    "iter_participant_information_state_snapshot_violations",
)
