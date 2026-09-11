"""Atomic RUN-319 mediation for participant retrieval serialization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import TypeVar, cast
from uuid import uuid4

from raes_contracts.contracts import ParticipantFlowSinkKind
from raes_contracts.contracts.base import ContractModel
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingDirection,
    ParticipantCrossingInteractionKind,
    ParticipantCrossingOccurrenceModel,
    ParticipantCrossingOperation,
    ParticipantCrossingSubjectKind,
    ParticipantCrossingSubjectReferenceModel,
)
from raes_contracts.contracts.participant_crossing_validation import (
    validate_participant_crossing_occurrence_context,
)
from raes_contracts.runtime_state import OperationState

from .participant_crossing_commit import commit_prepared_crossing, participant_crossing_permitted
from .participant_crossing_mediation import (
    ParticipantCrossingEvidence,
    ParticipantCrossingIntent,
    PreparedParticipantCrossing,
    prepare_participant_crossing,
)
from .participant_crossing_projection import RuntimeRevisionPath, stable_projection_subject
from .participant_crossing_records import _expected_history_heads
from .participant_flow_sink import (
    ParticipantFlowSinkDecision,
    flow_sink_audit_details,
    resolve_participant_flow_sink_decision,
)

_ViewT = TypeVar("_ViewT", bound=ContractModel)

_PROJECTION_NOT_PERMITTED = "participant projection was not permitted"


@dataclass(frozen=True)
class ParticipantViewSerialization:
    """Exact projection and authorization context for one egress operation."""

    participant_address: str
    episode_id: str
    subject_kind: ParticipantCrossingSubjectKind
    interaction_kind: ParticipantCrossingInteractionKind
    projection_ref: str
    identity: object
    crossing_evidence: ParticipantCrossingEvidence | None
    idempotency_key: str
    runtime_owned_revision_paths: tuple[RuntimeRevisionPath, ...] = ()

    def with_crossing_evidence(
        self,
        crossing_evidence: ParticipantCrossingEvidence,
    ) -> ParticipantViewSerialization:
        """Return this immutable context with trusted evidence attached."""

        return ParticipantViewSerialization(
            participant_address=self.participant_address,
            episode_id=self.episode_id,
            subject_kind=self.subject_kind,
            interaction_kind=self.interaction_kind,
            projection_ref=self.projection_ref,
            identity=self.identity,
            crossing_evidence=crossing_evidence,
            idempotency_key=self.idempotency_key,
            runtime_owned_revision_paths=self.runtime_owned_revision_paths,
        )


def serialize_participant_view(
    control_plane: object,
    view: _ViewT,
    serialization: ParticipantViewSerialization,
) -> _ViewT:
    """Return a view only after its exact governed projection is committed."""

    if serialization.crossing_evidence is None:
        raise ValueError("configured participant egress requires crossing evidence")
    with control_plane._participant_control_lock:
        control_plane._reload_derived_state_if_unpinned()
        subject = _view_subject(
            view,
            participant_address=serialization.participant_address,
            episode_id=serialization.episode_id,
            subject_kind=serialization.subject_kind,
            runtime_owned_revision_paths=serialization.runtime_owned_revision_paths,
        )
        canonical = ParticipantCrossingIntent.model_validate(
            {
                **serialization.crossing_evidence.model_dump(mode="json"),
                "participant_address": serialization.participant_address,
                "episode_id": serialization.episode_id,
                "direction": ParticipantCrossingDirection.EGRESS,
                "interaction_kind": serialization.interaction_kind,
                "subject": subject,
                "controller_ref": "runtime.control-plane.participant-retrieval",
                "authority_basis_refs": ["runtime.authority:participant-projection"],
                "requested_operation": ParticipantCrossingOperation.PROJECTION,
                "action_or_projection_ref": serialization.projection_ref,
                "effective_order": _next_effective_order(control_plane, serialization.participant_address),
                "order_model": "logical_clock",
            },
        )
        prepared = prepare_participant_crossing(
            control_plane,
            canonical,
            identity=serialization.identity,
            idempotency_key=serialization.idempotency_key,
            incumbent_carrier=view,
        )
        if prepared.existing_receipt is not None:
            if prepared.record.status.state is not OperationState.SUCCEEDED:
                raise PermissionError(_PROJECTION_NOT_PERMITTED)
            if prepared.record.result_payload is None:
                raise ValueError("idempotent participant projection is missing its governed result")
            return type(view).model_validate(prepared.record.result_payload)
        if not participant_crossing_permitted(prepared):
            prepared = _with_opacity_egress_observation(
                control_plane,
                prepared,
                delivered=False,
            )
            commit_prepared_crossing(control_plane, prepared)
            raise PermissionError(_PROJECTION_NOT_PERMITTED)

        sink_decision = _enforce_egress_flow_sink(control_plane, prepared)

        governed = _governed_egress_view(control_plane, prepared, view, serialization, subject)
        prepared = _with_opacity_egress_observation(
            control_plane,
            prepared,
            delivered=True,
        )
        if sink_decision is not None:
            prepared = _with_flow_sink_permitted_audit(prepared, sink_decision)
        prepared = cast(
            PreparedParticipantCrossing,
            replace(
                prepared,
                record=replace(
                    prepared.record,
                    result_payload=governed.model_dump(mode="json"),
                ),
            ),
        )
        commit_prepared_crossing(control_plane, prepared)
        return governed


def _governed_egress_view(
    control_plane: object,
    prepared: PreparedParticipantCrossing,
    view: _ViewT,
    serialization: ParticipantViewSerialization,
    subject: ParticipantCrossingSubjectReferenceModel,
) -> _ViewT:
    """Return the trusted governed projection, revalidating any egress transformation."""

    if prepared.governed_subject == subject:
        return view
    transformer = getattr(control_plane._crossing_policy_resolver, "transform_egress", None)
    if not callable(transformer):
        raise ValueError("transformed participant egress requires a trusted view transformer")
    candidate = transformer(prepared.intent, prepared.governed_subject, view)
    if not isinstance(candidate, type(view)):
        raise ValueError("participant egress transformation returned an invalid governed view")
    actual = _view_subject(
        candidate,
        participant_address=serialization.participant_address,
        episode_id=serialization.episode_id,
        subject_kind=prepared.governed_subject.subject_kind,
        runtime_owned_revision_paths=serialization.runtime_owned_revision_paths,
    )
    if actual != prepared.governed_subject:
        raise ValueError("trusted egress transformation does not match its governed identity")
    return candidate


def _enforce_egress_flow_sink(
    control_plane: object,
    prepared: PreparedParticipantCrossing,
) -> ParticipantFlowSinkDecision | None:
    """Resolve the SEM-233 permit; commit a denial and refuse serialization on non-permit."""

    sink_decision = resolve_participant_flow_sink_decision(
        control_plane,
        prepared,
        sink_kind=ParticipantFlowSinkKind.PARTICIPANT_OUTPUT,
    )
    if sink_decision is not None and not sink_decision.permitted:
        denied = _with_flow_sink_denied_audit(
            _with_opacity_egress_observation(control_plane, prepared, delivered=False),
            sink_decision,
        )
        commit_prepared_crossing(control_plane, denied)
        raise PermissionError(_PROJECTION_NOT_PERMITTED)
    return sink_decision


def _with_flow_sink_permitted_audit(
    prepared: PreparedParticipantCrossing,
    decision: ParticipantFlowSinkDecision,
) -> PreparedParticipantCrossing:
    """Fold the permitted SEM-233 reference into the committed egress audit."""

    return cast(
        PreparedParticipantCrossing,
        replace(
            prepared,
            audit_event=replace(
                prepared.audit_event,
                details={**prepared.audit_event.details, **flow_sink_audit_details(decision)},
            ),
        ),
    )


def _with_flow_sink_denied_audit(
    prepared: PreparedParticipantCrossing,
    decision: ParticipantFlowSinkDecision,
) -> PreparedParticipantCrossing:
    """Record a SEM-233 final-sink denial in the atomic egress audit event."""

    return cast(
        PreparedParticipantCrossing,
        replace(
            prepared,
            audit_event=replace(
                prepared.audit_event,
                allowed=False,
                reason="flow-sink-denied",
                details={**prepared.audit_event.details, **flow_sink_audit_details(decision)},
            ),
        ),
    )


def _with_opacity_egress_observation(
    control_plane: object,
    prepared: PreparedParticipantCrossing,
    *,
    delivered: bool,
) -> PreparedParticipantCrossing:
    """Append supported delivery/observation facts to the same atomic write."""

    decision = prepared.decision
    if decision is None or getattr(decision.occurrence, "opacity_enforcement", None) is None:
        return prepared
    participant_address = prepared.intent.participant_address
    history = list(prepared.next_snapshot.participant_crossing_history.get(participant_address, ()))
    if not history:
        raise ValueError("opacity egress decision is missing its prepared crossing history")
    predecessor = ParticipantCrossingOccurrenceModel.model_validate(history[-1])
    records = _egress_observation_records(
        prepared,
        predecessor,
        delivered=delivered,
    )
    candidate = [
        *history,
        *(record.model_dump(mode="json", exclude_none=True) for record in records),
    ]
    next_snapshot = prepared.next_snapshot.with_entries(
        dict(prepared.next_snapshot.entries),
        participant_crossing_history={
            **prepared.next_snapshot.participant_crossing_history,
            participant_address: candidate,
        },
    )
    context = control_plane._crossing_policy_resolver.validation_context(
        control_plane._snapshot,
        participant_address,
    )
    validate_participant_crossing_occurrence_context(
        [ParticipantCrossingOccurrenceModel.model_validate(item) for item in candidate],
        known_subjects=context.known_subjects,
        policies=context.policies,
        known_evidence_refs=context.known_evidence_refs,
        known_authority_basis_refs=context.known_authority_basis_refs,
    )
    return cast(
        PreparedParticipantCrossing,
        replace(
            prepared,
            next_snapshot=next_snapshot,
            record=replace(
                prepared.record,
                result_history_heads=_expected_history_heads(next_snapshot, participant_address),
            ),
        ),
    )


def _egress_observation_records(
    prepared: PreparedParticipantCrossing,
    predecessor: ParticipantCrossingOccurrenceModel,
    *,
    delivered: bool,
) -> list[ParticipantCrossingOccurrenceModel]:
    decision = prepared.decision
    assert decision is not None
    decision_detail = decision.occurrence
    decision_id = getattr(decision_detail, "decision_id", None)
    if not isinstance(decision_id, str):
        raise ValueError("opacity egress decision is missing its decision identity")
    previous_detail = predecessor.occurrence
    policy = previous_detail.policy
    next_order = previous_detail.effective_order + 1
    common = {
        "direction": previous_detail.direction.value,
        "interaction_kind": previous_detail.interaction_kind.value,
        "audience_scope_ref": previous_detail.audience_scope_ref,
        "subject": previous_detail.subject.model_dump(mode="json", exclude_none=True),
        "controller_ref": previous_detail.controller_ref,
        "authority_basis_refs": list(previous_detail.authority_basis_refs),
        "policy": policy.model_dump(mode="json"),
        "effective_order": next_order,
        "order_model": previous_detail.order_model,
        "backend_posture": previous_detail.backend_posture.value,
        "loss_and_limitations": list(previous_detail.loss_and_limitations),
    }
    envelope = predecessor.model_dump(
        mode="json",
        exclude={"event_id", "predecessor_event_refs", "logical_order_ref", "occurrence"},
        exclude_none=True,
    )
    envelope["logical_order_ref"] = f"{policy.decision_cut_ref}:order:{next_order}"
    attempt_id = f"crossing-delivery-attempt.{uuid4()}"
    attempt_event_id = f"crossing-occurrence.delivery-attempted.{uuid4()}"
    owning_ref = previous_detail.subject.subject_ref
    attempt = ParticipantCrossingOccurrenceModel.model_validate(
        {
            **envelope,
            "event_id": attempt_event_id,
            "predecessor_event_refs": [predecessor.event_id],
            "occurrence": {
                **common,
                "stage": "delivery-attempted",
                "decision_ref": decision_id,
                "attempt_id": attempt_id,
                "owning_occurrence_ref": owning_ref,
                "disposition": "attempted" if delivered else "withheld",
            },
        }
    )
    if not delivered:
        return [attempt]
    delivery_order = next_order + 1
    delivery_id = f"crossing-delivery.{uuid4()}"
    delivery_event_id = f"crossing-occurrence.delivered.{uuid4()}"
    delivery = ParticipantCrossingOccurrenceModel.model_validate(
        {
            **envelope,
            "event_id": delivery_event_id,
            "logical_order_ref": f"{policy.decision_cut_ref}:order:{delivery_order}",
            "predecessor_event_refs": [attempt_event_id],
            "occurrence": {
                **common,
                "stage": "delivered",
                "effective_order": delivery_order,
                "decision_ref": decision_id,
                "attempt_ref": attempt_id,
                "delivery_id": delivery_id,
                "owning_occurrence_ref": owning_ref,
                "delivery_order": delivery_order,
                "disposition": "delivered",
            },
        }
    )
    observation_order = delivery_order + 1
    observed = ParticipantCrossingOccurrenceModel.model_validate(
        {
            **envelope,
            "event_id": f"crossing-occurrence.observed.{uuid4()}",
            "logical_order_ref": f"{policy.decision_cut_ref}:order:{observation_order}",
            "predecessor_event_refs": [delivery_event_id],
            "occurrence": {
                **common,
                "stage": "observed",
                "effective_order": observation_order,
                "decision_ref": decision_id,
                "delivery_ref": delivery_id,
                "observation_id": f"crossing-observation.{uuid4()}",
                "owning_observation_ref": owning_ref,
                "observation_order": observation_order,
            },
        }
    )
    return [attempt, delivery, observed]


def _view_subject(
    view: ContractModel,
    *,
    participant_address: str,
    episode_id: str,
    subject_kind: ParticipantCrossingSubjectKind,
    runtime_owned_revision_paths: tuple[RuntimeRevisionPath, ...] = (),
) -> ParticipantCrossingSubjectReferenceModel:
    payload = view.model_dump(mode="json")
    payload.pop("generated_at", None)
    view_ref = payload.get("view_id")
    if not isinstance(view_ref, str) or not view_ref:
        raise ValueError("participant projection requires an exact view identity")
    encoded = json.dumps(
        stable_projection_subject(payload, runtime_owned_revision_paths),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return ParticipantCrossingSubjectReferenceModel(
        subject_kind=subject_kind,
        contract_id=f"{subject_kind.value}-v1",
        subject_ref=view_ref,
        subject_digest=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        participant_address=participant_address,
        episode_id=episode_id,
    )


def _next_effective_order(control_plane: object, participant_address: str) -> int:
    histories = (
        control_plane._snapshot.participant_behavior_history,
        control_plane._snapshot.participant_control_history,
        control_plane._snapshot.participant_crossing_history,
    )
    return sum(len(history.get(participant_address, ())) for history in histories) + 1


__all__ = ("ParticipantViewSerialization", "serialize_participant_view")
