"""RUN-310 application construction using the owning API-409 state relation."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import validate_participant_control_occurrence_context
from raes_contracts.contracts.participant_control_occurrence_v2 import (
    ParticipantControlOccurrenceV2Model,
    parse_participant_control_occurrence,
)
from raes_contracts.contracts.participant_control_occurrence_v2_policy import participant_control_validity_bounds
from raes_contracts.contracts.participant_control_occurrence_v2_validation import fold_participant_control_episode_v2

from .participant_control_operation import ParticipantControlOperationAuthority, participant_control_operation_artifacts
from .participant_control_runtime import admitted_policy, archived_policies, resolve_live_cut
from .participant_control_targets import (
    archived_control_targets,
    cancellation_target_operation,
    control_target_identity,
    external_control_targets,
)


def prepare_control_application(plane, participant, intent, identity, bound):
    """Prepare the same atomic transition used by direct and governed ingress."""

    from .participant_control_mediation import PreparedParticipantControlTransition, _history_head

    policy = admitted_policy(plane, participant, intent.episode_id)
    history = list(plane._snapshot.participant_control_history.get(participant, ()))
    if len(history) >= 1_000_000:
        raise ValueError("participant control history capacity is exhausted")
    records = [parse_participant_control_occurrence(payload) for payload in history]
    policies = archived_policies(plane, participant)
    historical_targets = archived_control_targets(plane, participant)
    known_identities = {control_target_identity(target) for target in historical_targets}
    fresh_targets = tuple(
        target
        for target in external_control_targets(plane._snapshot, participant, intent.episode_id, len(history), intent)
        if control_target_identity(target) not in known_identities
    )
    available_targets = (*historical_targets, *fresh_targets)
    declarations = plane._mixed_control.legacy_declarations
    validate_participant_control_occurrence_context(
        records, declarations=declarations, policies=policies, available_targets=historical_targets
    )
    episode = [record for record in records if record.episode_id == intent.episode_id]
    folded = fold_participant_control_episode_v2(episode, policy=policy, available_targets=historical_targets)
    if folded.violation is not None:
        raise ValueError("mixed-control episode history is unverifiable")
    live = folded.state
    application = intent.application
    transition = policy.transition(intent.declaration_ref)
    if transition is None:
        raise ValueError("control application names no transition in its admitted episode policy")
    source = policy.state(transition.from_state_ref)
    destination = policy.state(transition.to_state_ref)
    from .control_plane_security import ControlPlaneRole

    if (
        identity.target_name != plane.target_name
        or identity.roles.isdisjoint({ControlPlaneRole.OPERATOR, ControlPlaneRole.BACKEND})
        or not any(
            subject.participant_address == participant and subject.controller_ref == source.controller_ref
            for subject in identity.participant_control_subjects
        )
    ):
        raise PermissionError("participant source controller is not authorized")
    cut = resolve_live_cut(plane, policy, intent)
    current = plane._mixed_control.policy(bound.specification.address, intent.episode_id)
    bounds = participant_control_validity_bounds(policy, intent.declaration_ref, application.script_step_ref)
    state = plane._snapshot.participant_episode_results.get(participant, {})
    reasons = (
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
        (application.expected_history_head != len(history), "stale-history-head"),
        (
            application.prior_state_ref != live.state_ref or intent.expected_state_revision != live.state_revision,
            "stale-state",
        ),
        (
            cut.request_ref != intent.client_correlation_id or cut.effective_order != application.effective_order,
            "non-increasing-order",
        ),
        (
            not set([*source.authority_basis_refs, *destination.authority_basis_refs])
            <= set(cut.active_authority_basis_refs),
            "revoked-authority",
        ),
        (not set([*source.scope_refs, *destination.scope_refs]) <= set(cut.authorized_scope_refs), "scope-widened"),
        (not set(intent.evidence_refs) <= set(cut.evidence_refs), "missing-evidence"),
        (intent.kind == "handoff" and intent.completion_evidence_ref not in cut.evidence_refs, "missing-evidence"),
        (policy.pin.form == "reusable-policy" and application.script_step_ref is not None, "script-step-mismatch"),
        (bounds is None or not bounds[0] <= application.effective_order <= bounds[1], "late-authority"),
        (intent.expected_state_revision >= 1_000_000 or len(history) >= 1_000_000, "coordinate-out-of-range"),
    )
    reason = next((code for fails, code in reasons if fails), None)
    envelope = _envelope(plane, participant, intent, policy, source)
    candidate = None
    if reason is None:
        candidate = ParticipantControlOccurrenceV2Model.model_validate(
            {**envelope, "occurrence": _accepted_detail(intent, policy, source, bounds, len(history) + 1)}
        )
        trial = fold_participant_control_episode_v2(
            [*episode, candidate], policy=policy, available_targets=available_targets
        )
        if trial.violation is not None:
            reason = trial.rejection_code
            if reason is None:
                raise ValueError("mixed-control candidate does not satisfy its pinned policy")
    if reason is not None:
        candidate = ParticipantControlOccurrenceV2Model.model_validate(
            {**envelope, "occurrence": _rejected_detail(intent, source, live, len(history), reason)}
        )
    validate_participant_control_occurrence_context(
        [*records, candidate], declarations=declarations, policies=policies, available_targets=available_targets
    )
    next_snapshot = plane._snapshot.with_entries(
        dict(plane._snapshot.entries),
        participant_control_history={
            **plane._snapshot.participant_control_history,
            participant: [*history, candidate.model_dump(mode="json")],
        },
    )
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


def _envelope(plane, participant, intent, policy, source):
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


def _accepted_detail(intent, policy, source, bounds, position):
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


def _rejected_detail(intent, source, live, head, reason):
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
