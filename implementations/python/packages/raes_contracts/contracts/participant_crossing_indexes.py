"""Canonical API-423 stage identity indexes, shared by replay and extension."""

from __future__ import annotations

from collections.abc import Sequence

from .participant_crossing import (
    ParticipantCrossingDecisionModel,
    ParticipantCrossingDeliveryAttemptModel,
    ParticipantCrossingDeliveryModel,
    ParticipantCrossingDisclosureModel,
    ParticipantCrossingObservationModel,
    ParticipantCrossingOccurrenceModel,
    ParticipantCrossingRequestModel,
    ParticipantCrossingTransformationModel,
)

_DELIVERY_ATTEMPT = "delivery attempt"


class _RecordIndexes:
    def __init__(self) -> None:
        self.records_by_event_id: dict[str, ParticipantCrossingOccurrenceModel] = {}
        self.requests_by_id: dict[str, ParticipantCrossingOccurrenceModel] = {}
        self.decisions_by_id: dict[str, ParticipantCrossingOccurrenceModel] = {}
        self.transformations_by_id: dict[str, ParticipantCrossingOccurrenceModel] = {}
        self.disclosures_by_id: dict[str, ParticipantCrossingOccurrenceModel] = {}
        self.attempts_by_id: dict[str, ParticipantCrossingOccurrenceModel] = {}
        self.deliveries_by_id: dict[str, ParticipantCrossingOccurrenceModel] = {}
        self.observations_by_id: dict[str, ParticipantCrossingOccurrenceModel] = {}


def _index_records(
    records: Sequence[ParticipantCrossingOccurrenceModel], indexes: _RecordIndexes | None = None
) -> _RecordIndexes:
    indexes = _RecordIndexes() if indexes is None else indexes
    for record in records:
        existing = indexes.records_by_event_id.setdefault(record.event_id, record)
        if existing != record:
            raise ValueError("participant crossing event identity was reused with different semantics")
        if existing is not record:
            continue
        occurrence = record.occurrence
        if isinstance(occurrence, ParticipantCrossingRequestModel):
            _register_record(indexes.requests_by_id, occurrence.request_id, record, "request")
        elif isinstance(occurrence, ParticipantCrossingDecisionModel):
            _register_record(indexes.decisions_by_id, occurrence.decision_id, record, "decision")
        elif isinstance(occurrence, ParticipantCrossingTransformationModel):
            _register_record(
                indexes.transformations_by_id,
                occurrence.transformation_id,
                record,
                "transformation",
            )
        elif isinstance(occurrence, ParticipantCrossingDisclosureModel):
            _register_record(indexes.disclosures_by_id, occurrence.disclosure_id, record, "disclosure")
        elif isinstance(occurrence, ParticipantCrossingDeliveryAttemptModel):
            _register_record(indexes.attempts_by_id, occurrence.attempt_id, record, _DELIVERY_ATTEMPT)
        elif isinstance(occurrence, ParticipantCrossingDeliveryModel):
            _register_record(indexes.deliveries_by_id, occurrence.delivery_id, record, "delivery")
        elif isinstance(occurrence, ParticipantCrossingObservationModel):
            _register_record(indexes.observations_by_id, occurrence.observation_id, record, "observation")
    return indexes


def _register_record(
    index: dict[str, ParticipantCrossingOccurrenceModel],
    identity: str,
    record: ParticipantCrossingOccurrenceModel,
    label: str,
) -> None:
    existing = index.setdefault(identity, record)
    if existing != record:
        raise ValueError(f"participant crossing {label} identity was reused with different semantics")
