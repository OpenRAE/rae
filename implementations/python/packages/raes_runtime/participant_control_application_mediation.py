"""RUN-310 application construction using the owning API-409 state relation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.contracts import ParticipantControlOccurrenceModel
    from raes_contracts.contracts.participant_control_occurrence_v2_policy import (
        ParticipantControlOccurrencePolicyModel,
        ParticipantControlOccurrenceTarget,
        ParticipantControlPolicyStateModel,
    )
    from raes_contracts.contracts.participant_control_occurrence_v2_state import ParticipantControlEpisodeStateV2

    from .control_plane import RuntimeControlPlane
    from .control_plane_security import ControlPlaneIdentity
    from .participant_control_intents import ParticipantControlIntent
    from .participant_control_mediation import PreparedParticipantControlTransition, _BoundControlRequest
    from .participant_control_runtime import ParticipantControlLiveCut


from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_occurrence_v2 import (
    ParticipantControlOccurrenceV2Model,
)
from raes_contracts.contracts.participant_control_occurrence_v2_policy import participant_control_validity_bounds
from raes_contracts.errors import AuthorizationError, ConflictError, EvidenceIntegrityError, InvalidInputError

from .participant_control_operation import ParticipantControlOperationAuthority, participant_control_operation_artifacts
from .participant_control_runtime import admitted_policy, archived_policies, resolve_live_cut
from .participant_control_targets import (
    archived_control_targets,
    cancellation_target_operation,
    control_target_identity,
    external_control_targets,
)


@dataclass(frozen=True)
class _ApplicationHistory:
    policy: ParticipantControlOccurrencePolicyModel
    history: list[dict[str, object]]
    records: list[ParticipantControlOccurrenceModel | ParticipantControlOccurrenceV2Model]
    policies: tuple[ParticipantControlOccurrencePolicyModel, ...]
    historical_targets: tuple[ParticipantControlOccurrenceTarget, ...]
    available_targets: tuple[ParticipantControlOccurrenceTarget, ...]
    episode: list[ParticipantControlOccurrenceV2Model]
    live: ParticipantControlEpisodeStateV2
    archive: object


def prepare_control_application(
    plane: RuntimeControlPlane,
    participant: str,
    intent: ParticipantControlIntent,
    identity: ControlPlaneIdentity,
    bound: _BoundControlRequest,
) -> PreparedParticipantControlTransition:
    """Prepare the same atomic transition used by direct and governed ingress."""

    from .participant_control_mediation import PreparedParticipantControlTransition, _history_head

    context = _application_history(plane, participant, intent)
    policy, history = context.policy, context.history
    historical_targets = context.historical_targets
    available_targets, live = context.available_targets, context.live
    application = intent.application
    transition = policy.transition(intent.declaration_ref)
    if transition is None:
        raise ConflictError("control application names no transition in its admitted episode policy")
    source = policy.state(transition.from_state_ref)
    destination = policy.state(transition.to_state_ref)
    _require_source_controller(identity, participant, source, plane.target_name)
    cut = resolve_live_cut(plane, policy, intent)
    current = plane._mixed_control.policy(bound.specification.address, intent.episode_id)
    bounds = participant_control_validity_bounds(policy, intent.declaration_ref, application.script_step_ref)
    state = plane._snapshot.participant_episode_results.get(participant, {})
    reasons = [
        *_coordinate_reasons(intent, policy, current, live, len(history), state),
        *_authority_reasons(intent, source, destination, cut),
        *_window_reasons(intent, policy, bounds, len(history)),
    ]
    reason = next((code for fails, code in reasons if fails), None)
    candidate, reason = _control_candidate(plane, participant, intent, source, context, bounds, reason)
    trial = context.archive.trial(candidate, policy=policy, available_targets=available_targets)
    if trial.violation is not None:
        raise ConflictError(trial.violation)
    from raes_contracts.immutable_history import append_history

    try:
        appended = append_history(
            plane._snapshot, "participant_control_history", participant, [candidate.model_dump(mode="json")]
        )
    # The history map refuses to extend history that retains opaque legacy records of any participant.
    except ValueError as exc:
        raise EvidenceIntegrityError("retained participant control history does not validate") from exc
    next_snapshot = plane._snapshot.with_entries(dict(plane._snapshot.entries), participant_control_history=appended)
    record, audit = participant_control_operation_artifacts(
        participant_address=participant,
        intent=intent,
        occurrence=candidate,
        accepted=reason is None,
        rejection_reason=reason,
        authority=ParticipantControlOperationAuthority(
            identity=identity, context=bound.context, idempotency_key=bound.idempotency_key
        ),
    )
    from dataclasses import asdict

    payload = {
        "participant_control_occurrence_ref": candidate.event_id,
        "participant_control_available_targets": [
            {**asdict(target), "target_kind": target.target_kind.value}
            for target in available_targets
            if target not in historical_targets
        ],
        "participant_control_live_cut": cut.model_dump(mode="json"),
    }
    if intent.kind == "cancellation":
        from .participant_control_cancellation import cancellation_link

        target_operation = cancellation_target_operation(plane, participant, intent)
        payload.update(cancellation_link(plane, intent, candidate, target_operation=target_operation))
    record = replace(record, result_payload=payload)
    return PreparedParticipantControlTransition(next_snapshot, record, audit, _history_head(history), bound)


def _application_history(
    plane: RuntimeControlPlane, participant: str, intent: ParticipantControlIntent
) -> _ApplicationHistory:
    policy = admitted_policy(plane, participant, intent.episode_id)
    from .participant_control_archive_projection import control_archive_projection

    history = plane._snapshot.participant_control_history.get(participant, ())
    if len(history) >= 1_000_000:
        raise ConflictError("participant control history capacity is exhausted")
    policies = archived_policies(plane, participant)
    historical_targets = archived_control_targets(plane, participant)
    known_identities = {control_target_identity(target) for target in historical_targets}
    fresh_targets = tuple(
        target
        for target in external_control_targets(plane._snapshot, participant, intent.episode_id, len(history), intent)
        if control_target_identity(target) not in known_identities
    )
    available_targets = (*historical_targets, *fresh_targets)
    archive = control_archive_projection(plane, participant, policies=policies, targets=historical_targets)
    from raes_contracts.contracts.participant_control_episode_prefix import ControlEpisodePrefix

    prefix = archive.episodes.get(intent.episode_id, ControlEpisodePrefix(policy, historical_targets))
    return _ApplicationHistory(
        policy, history, archive.records, policies, historical_targets, available_targets, (), prefix.state, archive
    )


def _require_source_controller(
    identity: ControlPlaneIdentity, participant: str, source: ParticipantControlPolicyStateModel, target_name: str
) -> None:
    from .control_plane_security import ControlPlaneRole

    if (
        identity.target_name != target_name
        or identity.roles.isdisjoint({ControlPlaneRole.OPERATOR, ControlPlaneRole.BACKEND})
        or not any(
            subject.participant_address == participant and subject.controller_ref == source.controller_ref
            for subject in identity.participant_control_subjects
        )
    ):
        raise AuthorizationError("participant source controller is not authorized")


def _coordinate_reasons(
    intent: ParticipantControlIntent,
    policy: ParticipantControlOccurrencePolicyModel,
    current: ParticipantControlOccurrencePolicyModel,
    live: ParticipantControlEpisodeStateV2,
    head: int,
    state: dict[str, object],
) -> list[tuple[bool, str]]:
    application = intent.application
    return [
        (state.get("episode_id") != intent.episode_id or state.get("status") != "running", "episode-not-running"),
        (
            application.policy_ref != policy.pin.policy_ref or intent.policy_revision != policy.pin.policy_revision,
            "stale-policy",
        ),
        (
            canonical_json_digest(current.model_dump(mode="json"))
            != canonical_json_digest(policy.model_dump(mode="json")),
            "stale-policy",
        ),
        (application.expected_history_head != head, "stale-history-head"),
        (
            application.prior_state_ref != live.state_ref or intent.expected_state_revision != live.state_revision,
            "stale-state",
        ),
    ]


def _authority_reasons(
    intent: ParticipantControlIntent,
    source: ParticipantControlPolicyStateModel,
    destination: ParticipantControlPolicyStateModel,
    cut: ParticipantControlLiveCut,
) -> list[tuple[bool, str]]:
    application = intent.application
    return [
        (
            cut.request_ref != intent.client_correlation_id or cut.effective_order != application.effective_order,
            "non-increasing-order",
        ),
        (
            not {*source.authority_basis_refs, *destination.authority_basis_refs}
            <= set(cut.active_authority_basis_refs),
            "revoked-authority",
        ),
        (not {*source.scope_refs, *destination.scope_refs} <= set(cut.authorized_scope_refs), "scope-widened"),
        (not set(intent.evidence_refs) <= set(cut.evidence_refs), "missing-evidence"),
        (intent.kind == "handoff" and intent.completion_evidence_ref not in cut.evidence_refs, "missing-evidence"),
    ]


def _window_reasons(
    intent: ParticipantControlIntent,
    policy: ParticipantControlOccurrencePolicyModel,
    bounds: tuple[int, int] | None,
    head: int,
) -> list[tuple[bool, str]]:
    application = intent.application
    return [
        (policy.pin.form == "reusable-policy" and application.script_step_ref is not None, "script-step-mismatch"),
        (bounds is None or not bounds[0] <= application.effective_order <= bounds[1], "late-authority"),
        (intent.expected_state_revision >= 1_000_000 or head >= 1_000_000, "coordinate-out-of-range"),
    ]


def _control_candidate(
    plane: RuntimeControlPlane,
    participant: str,
    intent: ParticipantControlIntent,
    source: ParticipantControlPolicyStateModel,
    context: _ApplicationHistory,
    bounds: tuple[int, int] | None,
    reason: str | None,
) -> tuple[ParticipantControlOccurrenceV2Model, str | None]:
    envelope = _envelope(plane, participant, intent, context.policy, source)
    if reason is None:
        candidate = _occurrence(
            {
                **envelope,
                "occurrence": _accepted_detail(intent, context.policy, source, bounds, len(context.history) + 1),
            }
        )
        trial = context.archive.trial(candidate, policy=context.policy, available_targets=context.available_targets)
        if trial.violation is None:
            return candidate, None
        reason = trial.rejection_code
        if reason is None:
            raise ConflictError("mixed-control candidate does not satisfy its pinned policy")
    return _occurrence(
        {**envelope, "occurrence": _rejected_detail(intent, source, context.live, len(context.history), reason)}
    ), reason


def _occurrence(payload: dict[str, object]) -> ParticipantControlOccurrenceV2Model:
    try:
        return ParticipantControlOccurrenceV2Model.model_validate(payload)
    # The intent model admits values, such as an empty reference, that the occurrence contract refuses.
    except ValidationError as exc:
        raise InvalidInputError("participant control intent does not form a valid control occurrence") from exc


def _envelope(
    plane: RuntimeControlPlane,
    participant: str,
    intent: ParticipantControlIntent,
    policy: ParticipantControlOccurrencePolicyModel,
    source: ParticipantControlPolicyStateModel,
) -> dict[str, object]:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "event_id": f"participant-control.{uuid4()}",
        "schema_name": "participant-control-occurrence",
        "schema_version": "2.0.0",
        "event_type": "participant-control-occurrence",
        "extension_policy": "closed",
        "participant_address": participant,
        "episode_id": intent.episode_id,
        "occurred_at": now,
        "recorded_at": now,
        "ingested_at": now,
        "clock_authority": "runtime.control-plane.clock",
        "ordering_basis": "logical_clock",
        "logical_order_ref": f"effective-order:{intent.application.effective_order}",
        "actor_ref": source.controller_ref,
        "producer_ref": f"runtime.control-plane.{plane.target_name}",
        "provenance_refs": intent.provenance_refs,
        "evidence_refs": intent.evidence_refs,
        "object_marking_refs": intent.object_marking_refs,
        "authorization_scope": source.scope_refs[0],
        "semantics": policy.semantics,
        "policy": policy.pin.model_dump(mode="json"),
    }


def _accepted_detail(
    intent: ParticipantControlIntent,
    policy: ParticipantControlOccurrencePolicyModel,
    source: ParticipantControlPolicyStateModel,
    bounds: tuple[int, int],
    position: int,
) -> dict[str, object]:
    application = intent.application
    detail = {
        "disposition": "accepted",
        "permitted_transition_ref": intent.declaration_ref,
        "kind": intent.kind,
        "prior_state_ref": application.prior_state_ref,
        "expected_state_revision": intent.expected_state_revision,
        "resulting_state_ref": policy.transition(intent.declaration_ref).to_state_ref,
        "resulting_state_revision": intent.expected_state_revision + 1,
        "expected_history_head": application.expected_history_head,
        "occurrence_revision": position,
        "controller_ref": source.controller_ref,
        "authority_basis_refs": source.authority_basis_refs,
        "controlled_scope_refs": source.scope_refs,
        "effective_order": application.effective_order,
        "valid_from_order": bounds[0],
        "valid_until_order": bounds[1],
        "script_step_ref": application.script_step_ref,
        "limitation_refs": intent.limitation_refs,
    }
    # The intent base owns shared request coordinates; kind-specific facts use
    # the existing closed API-409 alternatives rather than a second target DTO.
    from .participant_control_intents import ParticipantControlIntentBase

    common = set(ParticipantControlIntentBase.model_fields) | {"kind"}
    detail.update({key: value for key, value in intent.model_dump(mode="json").items() if key not in common})
    if intent.kind == "proposal":
        detail["admission_status"] = "not-admitted"
    return detail


def _rejected_detail(
    intent: ParticipantControlIntent,
    source: ParticipantControlPolicyStateModel,
    live: ParticipantControlEpisodeStateV2,
    head: int,
    reason: str,
) -> dict[str, object]:
    application = intent.application
    return {
        "disposition": "rejected",
        "occurrence_revision": head + 1,
        "reason_code": reason,
        "attempted": {
            "permitted_transition_ref": intent.declaration_ref,
            "kind": intent.kind,
            "state_ref": application.prior_state_ref,
            "expected_state_revision": intent.expected_state_revision,
            "expected_history_head": application.expected_history_head,
            "effective_order": application.effective_order,
            "controller_ref": source.controller_ref,
            "authority_basis_refs": source.authority_basis_refs,
            "controlled_scope_refs": source.scope_refs,
            "script_step_ref": application.script_step_ref,
        },
        "observed": {
            "state_ref": live.state_ref,
            "state_revision": live.state_revision,
            "last_accepted_order": live.last_order,
            "history_head": head,
        },
        "state_change": "none",
        "limitation_refs": intent.limitation_refs,
    }
