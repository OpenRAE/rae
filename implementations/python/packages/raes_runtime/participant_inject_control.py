"""Exact accepted control join using the API-409 owner fold and live-cut owner."""

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_occurrence_v2 import (
    ParticipantControlOccurrenceV2Model,
    parse_participant_control_occurrence,
)
from raes_contracts.contracts.participant_control_occurrence_v2_validation import fold_participant_control_episode_v2

from .participant_control_runtime import admitted_policy, resolve_owner_cut
from .participant_control_targets import archived_control_targets


def require_retained_delivery_control(application, event):
    reference = application.control
    if reference is None:
        if event is not None:
            raise ValueError("disclosure cannot retain a control application")
        return
    if (
        event is None
        or event.event_id != reference.event_id
        or event.episode_id != application.episode_id
        or event.participant_address != application.participant_address
    ):
        raise ValueError("inject delivery retained control identity differs")
    event = ParticipantControlOccurrenceV2Model.model_validate(event.model_dump(mode="json"))
    if (
        event.occurrence.disposition != "accepted"
        or event.occurrence.occurrence_revision != reference.occurrence_revision
        or canonical_json_digest(event.model_dump(mode="json")) != reference.digest
    ):
        raise ValueError("inject delivery retained control is not the accepted application")


def validate_restored_inject_deliveries(plane):
    for record in plane._operations.values():
        content = record.inject_delivery
        if content is None:
            continue
        if plane._inject_delivery is None:
            raise ValueError("retained inject delivery requires its original compiler context")
        application = content.application
        binding = plane._inject_delivery.model.participant_inject_deliveries.get(application.delivery_address)
        if binding is None or canonical_json_digest(binding.spec) != application.delivery_digest:
            raise ValueError("retained inject delivery binding differs")
        if application.control is not None:
            actual = next(
                (
                    item
                    for item in plane._snapshot.participant_control_history.get(application.participant_address, ())
                    if item["event_id"] == application.control.event_id
                ),
                None,
            )
            if actual is None or canonical_json_digest(actual) != application.control.digest:
                raise ValueError("retained inject delivery control history differs")


def require_delivery_control(plane, application, delivery, expected_order, identity):
    if delivery.delivery_kind == "disclosure":
        if application.control is not None:
            raise ValueError("disclosure carries no control authority")
        return
    if delivery.control is None or plane._mixed_control is None or application.control is None:
        raise ValueError("inject delivery exact reusable control binding is unavailable")
    reference, binding = application.control, delivery.control
    records = [
        parse_participant_control_occurrence(item)
        for item in plane._snapshot.participant_control_history.get(application.participant_address, ())
    ]
    event = next((item for item in records if item.event_id == reference.event_id), None)
    if (
        event is None
        or event.schema_version != "2.0.0"
        or event.episode_id != application.episode_id
        or canonical_json_digest(event.model_dump(mode="json")) != reference.digest
    ):
        raise ValueError("inject delivery control occurrence differs")
    detail = event.occurrence
    policy = admitted_policy(plane, application.participant_address, application.episode_id)
    folded = fold_participant_control_episode_v2(
        [item for item in records if item.episode_id == application.episode_id],
        policy=policy,
        available_targets=archived_control_targets(plane, application.participant_address),
    )
    if (
        folded.violation is not None
        or detail.disposition != "accepted"
        or detail.kind != delivery.delivery_kind
        or detail.occurrence_revision != reference.occurrence_revision
    ):
        raise ValueError("inject delivery control is not accepted for this kind")
    lifecycle = folded.state.lifecycle(event.event_id)
    if lifecycle.superseded or lifecycle.replaced or detail.resulting_state_revision != folded.state.state_revision:
        raise ValueError("inject delivery control application is stale")
    if (
        detail.permitted_transition_ref != binding.permitted_transition_address
        or detail.controller_ref != binding.controller_address
        or event.policy.policy_revision != binding.policy_revision
    ):
        raise ValueError("inject delivery control policy or edge differs")
    if not any(
        subject.participant_address == application.participant_address
        and subject.controller_ref == detail.controller_ref
        for subject in identity.participant_control_subjects
    ):
        raise PermissionError("inject delivery source controller is unavailable")
    required_evidence = set(binding.evidence_addresses or binding.evidence_refs)
    if not set(binding.authority_scope_addresses) <= set(detail.controlled_scope_refs) or not required_evidence <= set(
        event.evidence_refs
    ):
        raise ValueError("inject delivery control scope or evidence differs")
    method = getattr(plane._mixed_control.resolver, "resolve_delivery_cut", None)
    if not callable(method):
        raise ValueError("inject delivery live control-cut owner is unavailable")
    try:
        cut = resolve_owner_cut(plane, policy, application, method)
    except Exception:
        raise ValueError("inject delivery live control cut is unavailable") from None
    current = policy.state(folded.state.state_ref)
    if (
        cut.request_ref != application.request_key
        or cut.effective_order != expected_order
        or cut.effective_order < detail.effective_order
        or not detail.valid_from_order <= cut.effective_order <= detail.valid_until_order
        or not current.valid_from_order <= cut.effective_order <= current.valid_until_order
    ):
        raise ValueError("inject delivery control validity is stale")
    if (
        not {*detail.authority_basis_refs, *current.authority_basis_refs} <= set(cut.active_authority_basis_refs)
        or not set(detail.controlled_scope_refs) <= set(cut.authorized_scope_refs)
        or not required_evidence <= set(cut.evidence_refs)
    ):
        raise ValueError("inject delivery authority has been revoked")
