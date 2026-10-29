"""Authoritative target resolution for RUN-310 supervisory occurrences."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord


from collections.abc import Mapping
from dataclasses import dataclass, fields

from pydantic import TypeAdapter
from raes_contracts.contracts import (
    ParticipantBehaviorHistoryEventModel,
    ParticipantControlOccurrenceModel,
)
from raes_contracts.contracts.participant_control import (
    ParticipantApprovalOccurrenceModel,
    ParticipantControlDisposition,
    ParticipantControlTargetContextModel,
    ParticipantControlTargetKind,
    ParticipantDenialOccurrenceModel,
    ParticipantProposalOccurrenceModel,
)
from raes_contracts.contracts.participant_control_coordinates import ControlCount, ControlPosition, ControlRef
from raes_contracts.contracts.participant_control_occurrence_v2 import (
    ParticipantApprovalOccurrenceV2Model,
    ParticipantDenialOccurrenceV2Model,
    ParticipantProposalOccurrenceV2Model,
    parse_participant_control_occurrence,
)
from raes_contracts.contracts.participant_control_occurrence_v2_policy import ParticipantControlOccurrenceTarget
from raes_contracts.errors import ConflictError, EvidenceIntegrityError, InvalidInputError
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot

from .participant_control_intents import (
    ParticipantApprovalControlIntent,
    ParticipantCancellationControlIntent,
    ParticipantControlIntent,
    ParticipantDenialControlIntent,
    ParticipantExternalDirectionControlIntent,
    ParticipantInterventionControlIntent,
    ParticipantOverrideControlIntent,
    ParticipantProposalControlIntent,
)

_RETAINED_HISTORY_INVALID = "retained participant history does not validate"
_UNBOUND_TARGET = "stored target visibility is not bound to its committed control cut"
_TARGET_FIELDS = frozenset(item.name for item in fields(ParticipantControlOccurrenceTarget))


@dataclass(frozen=True)
class ResolvedParticipantControlTarget:
    """One target whose revision and runtime scope resolved exactly."""

    context: ParticipantControlTargetContextModel
    predecessor_ref: str


def resolve_participant_control_target(
    snapshot: RuntimeSnapshot,
    intent: ParticipantControlIntent,
    *,
    participant_address: str,
) -> tuple[ResolvedParticipantControlTarget | None, str | None]:
    """Resolve an intent target without accepting caller-supplied coordinates."""

    requested = _intent_target(intent)
    if requested is None:
        return None, None
    kind, reference, revision = requested
    matches = [
        candidate
        for candidate in participant_control_targets(snapshot)
        if candidate.context.target_kind is kind
        and candidate.context.target_ref == reference
        and candidate.context.target_revision == revision
        and candidate.context.participant_address == participant_address
        and candidate.context.episode_id == intent.episode_id
    ]
    if len(matches) != 1:
        return None, "invalid-target"
    return matches[0], None


def participant_control_target_contexts(
    snapshot: RuntimeSnapshot,
) -> tuple[ParticipantControlTargetContextModel, ...]:
    """Return all lifecycle targets used by API-409 contextual validation."""

    return tuple(candidate.context for candidate in participant_control_targets(snapshot))


def participant_control_targets(
    snapshot: RuntimeSnapshot,
) -> tuple[ResolvedParticipantControlTarget, ...]:
    """Project control and behavior histories into typed target coordinates."""

    targets: dict[
        tuple[ParticipantControlTargetKind, str, int, str, str],
        ResolvedParticipantControlTarget,
    ] = {}
    for events in snapshot.participant_control_history.values():
        for payload in events:
            _register_control_targets(
                targets,
                _retained_record(parse_participant_control_occurrence, payload),
            )
    for events in snapshot.participant_behavior_history.values():
        for payload in events:
            _register_behavior_targets(
                targets,
                _retained_record(ParticipantBehaviorHistoryEventModel.model_validate, payload),
            )
    return tuple(targets.values())


def _retained_record[RecordT](parse: Callable[[Any], RecordT], payload: object) -> RecordT:
    """Read one retained record; the published readers refuse a record with ValueError."""

    # The readers take a mapping. A restored store can retain any opaque JSON value.
    if not isinstance(payload, Mapping):
        raise EvidenceIntegrityError(_RETAINED_HISTORY_INVALID)
    try:
        return parse(payload)
    # A restored store can retain a record that the history map keeps as opaque legacy data.
    except ValueError as exc:
        raise EvidenceIntegrityError(_RETAINED_HISTORY_INVALID) from exc


def _register_control_targets(
    targets: dict[
        tuple[ParticipantControlTargetKind, str, int, str, str],
        ResolvedParticipantControlTarget,
    ],
    event: ParticipantControlOccurrenceModel,
) -> None:
    occurrence = event.occurrence
    if occurrence.disposition != ParticipantControlDisposition.ACCEPTED:
        return
    _register(
        targets,
        kind=ParticipantControlTargetKind.CONTROL,
        reference=event.event_id,
        revision=occurrence.occurrence_revision,
        participant_address=event.participant_address,
        episode_id=event.episode_id,
        predecessor_ref=event.event_id,
    )
    if isinstance(occurrence, (ParticipantProposalOccurrenceModel, ParticipantProposalOccurrenceV2Model)):
        _register(
            targets,
            kind=ParticipantControlTargetKind.PROPOSAL,
            reference=occurrence.proposal_id,
            revision=occurrence.proposal_revision,
            participant_address=event.participant_address,
            episode_id=event.episode_id,
            predecessor_ref=event.event_id,
        )
    elif isinstance(
        occurrence,
        (
            ParticipantApprovalOccurrenceModel,
            ParticipantDenialOccurrenceModel,
            ParticipantApprovalOccurrenceV2Model,
            ParticipantDenialOccurrenceV2Model,
        ),
    ):
        _register(
            targets,
            kind=ParticipantControlTargetKind.DECISION,
            reference=occurrence.decision_ref,
            revision=occurrence.decision_revision,
            participant_address=event.participant_address,
            episode_id=event.episode_id,
            predecessor_ref=event.event_id,
        )


def _register_behavior_targets(
    targets: dict[
        tuple[ParticipantControlTargetKind, str, int, str, str],
        ResolvedParticipantControlTarget,
    ],
    event: ParticipantBehaviorHistoryEventModel,
) -> None:
    if event.event_type.value != "action_attempted":
        return
    phase = event.lifecycle_phase.value if event.lifecycle_phase is not None else None
    _register(
        targets,
        kind=ParticipantControlTargetKind.ACTION,
        reference=event.action_instance_id,
        revision=1,
        participant_address=event.participant_address,
        episode_id=event.episode_id,
        predecessor_ref=event.action_instance_id,
    )
    admission = event.admission_disposition.value if event.admission_disposition is not None else None
    if phase == "selection_or_admission" and admission == "admitted":
        _register(
            targets,
            kind=ParticipantControlTargetKind.ADMITTED_ACTION,
            reference=event.action_instance_id,
            revision=1,
            participant_address=event.participant_address,
            episode_id=event.episode_id,
            predecessor_ref=event.action_instance_id,
        )
    if phase == "execution_attempt":
        attempt_ref = event.operation_ref or event.action_instance_id
        _register(
            targets,
            kind=ParticipantControlTargetKind.ATTEMPT,
            reference=attempt_ref,
            revision=1,
            participant_address=event.participant_address,
            episode_id=event.episode_id,
            predecessor_ref=attempt_ref,
        )


def _register(
    targets: dict[
        tuple[ParticipantControlTargetKind, str, int, str, str],
        ResolvedParticipantControlTarget,
    ],
    *,
    kind: ParticipantControlTargetKind,
    reference: str,
    revision: int,
    participant_address: str,
    episode_id: str,
    predecessor_ref: str,
) -> None:
    context = ParticipantControlTargetContextModel(
        target_kind=kind,
        target_ref=reference,
        target_revision=revision,
        participant_address=participant_address,
        episode_id=episode_id,
    )
    key = (kind, reference, revision, participant_address, episode_id)
    candidate = ResolvedParticipantControlTarget(context=context, predecessor_ref=predecessor_ref)
    existing = targets.setdefault(key, candidate)
    if existing != candidate:
        raise ConflictError("runtime target identity is ambiguous")


def _intent_target(
    intent: ParticipantControlIntent,
) -> tuple[ParticipantControlTargetKind, str, int] | None:
    target: tuple[ParticipantControlTargetKind, str, int] | None
    if isinstance(intent, ParticipantProposalControlIntent):
        if intent.source_proposal_ref is None:
            target = None
        else:
            if intent.source_proposal_revision is None:
                raise InvalidInputError("proposal intent source reference requires its revision")
            target = (
                ParticipantControlTargetKind.PROPOSAL,
                intent.source_proposal_ref,
                intent.source_proposal_revision,
            )
    elif isinstance(intent, (ParticipantApprovalControlIntent, ParticipantDenialControlIntent)):
        target = (ParticipantControlTargetKind.PROPOSAL, intent.proposal_ref, intent.proposal_revision)
    elif isinstance(intent, ParticipantExternalDirectionControlIntent):
        target = (intent.target_kind, intent.target_ref, intent.target_revision)
    elif isinstance(intent, ParticipantInterventionControlIntent):
        target = (intent.affected_target_kind, intent.affected_occurrence_ref, intent.affected_revision)
    elif isinstance(intent, ParticipantOverrideControlIntent):
        target = (intent.superseded_target_kind, intent.superseded_occurrence_ref, intent.superseded_revision)
    elif isinstance(intent, ParticipantCancellationControlIntent):
        target = (intent.target_kind, intent.target_ref, intent.target_revision)
    else:
        target = None
    return target


def external_control_targets(
    snapshot: RuntimeSnapshot, participant: str, episode: str, history_head: int, intent: ParticipantControlIntent
) -> tuple[ParticipantControlOccurrenceTarget, ...]:
    """Attest targets visible at this cut; API-409 owns internal control targets."""

    requested = _intent_target(intent)
    if requested is None:
        return ()
    return tuple(
        ParticipantControlOccurrenceTarget(
            item.context.target_kind,
            item.context.target_ref,
            item.context.target_revision,
            participant,
            episode,
            history_head,
        )
        for item in participant_control_targets(snapshot)
        if item.context.participant_address == participant
        and item.context.episode_id == episode
        and requested is not None
        and (item.context.target_kind, item.context.target_ref) == requested[:2]
        and item.context.target_kind
        in {
            ParticipantControlTargetKind.ACTION,
            ParticipantControlTargetKind.ADMITTED_ACTION,
            ParticipantControlTargetKind.ATTEMPT,
        }
    )


def archived_control_targets(
    plane: RuntimeControlPlane, participant: str
) -> tuple[ParticipantControlOccurrenceTarget, ...]:
    """Retain the original visibility cut instead of backdating later targets."""
    from .participant_control_operation_index import operation_index

    targets = []
    history = plane._snapshot.participant_control_history
    from raes_contracts.immutable_history import HistoryMap

    events = (
        {} if isinstance(history, HistoryMap) else {event["event_id"]: event for event in history.get(participant, ())}
    )
    for record in operation_index(plane).target_records.values():
        if record.status.state not in {OperationState.SUCCEEDED, OperationState.FAILED}:
            continue
        for payload in _retained_targets(record):
            if payload["participant_address"] == participant:
                if isinstance(history, HistoryMap):
                    event_id = record.result_payload.get("participant_control_occurrence_ref")
                    events = {event_id: history.find(participant, event_id)}
                targets.append(_archived_target(record, payload, events))
    return tuple(targets)


def _retained_targets(record: ControlPlaneOperationRecord) -> tuple[Mapping[str, Any], ...]:
    """Refuse a malformed retained target list before a coordinate reader runs."""

    payloads = (record.result_payload or {}).get("participant_control_available_targets", ())
    if not isinstance(payloads, list | tuple) or not all(
        isinstance(payload, Mapping) and payload.keys() == _TARGET_FIELDS for payload in payloads
    ):
        raise EvidenceIntegrityError(_UNBOUND_TARGET)
    return tuple(payloads)


def _archived_target(
    record: ControlPlaneOperationRecord, payload: Mapping[str, Any], events: dict[str, dict[str, Any]]
) -> ParticipantControlOccurrenceTarget:
    try:
        TypeAdapter(ControlPosition).validate_python(payload["target_revision"])
        TypeAdapter(ControlCount).validate_python(payload["available_at"])
        for field in ("target_ref", "participant_address", "episode_id"):
            TypeAdapter(ControlRef).validate_python(payload[field])
        target = ParticipantControlOccurrenceTarget(
            **{**payload, "target_kind": ParticipantControlTargetKind(payload["target_kind"])}
        )
    # The retained target payload failed its contract coordinates.
    except ValueError as exc:
        raise EvidenceIntegrityError(_UNBOUND_TARGET) from exc
    event = events.get((record.result_payload or {}).get("participant_control_occurrence_ref"))
    if (
        event is None
        or payload["episode_id"] != event["episode_id"]
        or payload["available_at"] != event["occurrence"]["occurrence_revision"] - 1
    ):
        raise EvidenceIntegrityError(_UNBOUND_TARGET)
    return target


def control_target_identity(
    target: ParticipantControlOccurrenceTarget,
) -> tuple[ParticipantControlTargetKind, str, int, str, str]:
    """Return target identity independently of its original visibility position."""

    return (
        target.target_kind,
        target.target_ref,
        target.target_revision,
        target.participant_address,
        target.episode_id,
    )


def cancellation_target_operation(
    plane: RuntimeControlPlane, participant: str, intent: ParticipantCancellationControlIntent
) -> ControlPlaneOperationRecord | None:
    """Join a lifecycle target to its exact operation; native batches stay unsupported."""
    if intent.target_kind not in {ParticipantControlTargetKind.ADMITTED_ACTION, ParticipantControlTargetKind.ATTEMPT}:
        return None
    refs = _cancellation_operation_refs(plane._snapshot, participant, intent)
    if len(refs) != 1:
        return None
    return _scoped_target_operation(plane, participant, next(iter(refs)))


def _cancellation_operation_refs(
    snapshot: RuntimeSnapshot, participant: str, intent: ParticipantCancellationControlIntent
) -> set[str]:
    refs = set()
    for payload in snapshot.participant_behavior_history.get(participant, ()):
        event = ParticipantBehaviorHistoryEventModel.model_validate(payload)
        if event.episode_id != intent.episode_id or event.event_type.value != "action_attempted":
            continue
        matches = (
            event.action_instance_id == intent.target_ref
            if intent.target_kind is ParticipantControlTargetKind.ADMITTED_ACTION
            else event.operation_ref == intent.target_ref
        )
        if matches and event.operation_ref:
            refs.add(event.operation_ref)
    return refs


def _scoped_target_operation(
    plane: RuntimeControlPlane, participant: str, operation_ref: str
) -> ControlPlaneOperationRecord | None:
    record = plane._operations.get(operation_ref)
    if record is None or record.invocation is None:
        return None
    context = record.receipt.context
    if (
        (context.target_scope, context.run_scope) != (plane._target_scope, plane._run_scope)
        or context.operation_kind.value != "participant-action"
        or not any(scope.startswith(f"participant-control:{participant}:") for scope in context.authorization_scope)
    ):
        raise ConflictError("cancellation target has no exact participant execution owner")
    return record


__all__ = (
    "ResolvedParticipantControlTarget",
    "participant_control_target_contexts",
    "resolve_participant_control_target",
)
