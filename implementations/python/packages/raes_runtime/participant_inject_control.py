"""Exact accepted control join using the API-409 owner fold and live-cut owner."""

from __future__ import annotations

from typing import TYPE_CHECKING

import rfc8785
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_occurrence_v2 import (
    ParticipantControlOccurrenceV2Model,
    parse_participant_control_occurrence,
)
from raes_contracts.contracts.participant_control_occurrence_v2_policy import ParticipantControlOccurrencePolicyModel
from raes_contracts.contracts.participant_control_occurrence_v2_state import ParticipantControlEpisodeFoldV2
from raes_contracts.contracts.participant_control_occurrence_v2_validation import fold_participant_control_episode_v2
from raes_contracts.contracts.participant_inject_application import ParticipantInjectApplicationModel
from raes_contracts.errors import AuthorizationError, ConflictError, EvidenceIntegrityError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_processor.models import ParticipantInjectDeliveryRuntime

from .control_plane_security import ControlPlaneIdentity
from .participant_control_runtime import (
    CONTROL_CUT_REFUSALS,
    ParticipantControlLiveCut,
    admitted_policy,
    resolve_owner_cut,
)
from .participant_control_targets import archived_control_targets

if TYPE_CHECKING:
    from .control_plane import RuntimeControlPlane

_LOGGER = get_logger(__name__)
_CUT_UNAVAILABLE = "inject delivery live control cut is unavailable"
_RETAINED_BINDING_DIFFERS = "retained inject delivery binding differs"


def require_retained_delivery_control(
    application: ParticipantInjectApplicationModel, event: ParticipantControlOccurrenceV2Model | None
) -> None:
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


def validate_restored_inject_deliveries(plane: RuntimeControlPlane) -> None:
    for record in plane._operations.values():
        content = record.inject_delivery
        if content is None:
            continue
        if plane._inject_delivery is None:
            raise ConflictError("retained inject delivery requires its original compiler context")
        application = content.application
        binding = plane._inject_delivery.model.participant_inject_deliveries.get(application.delivery_address)
        if binding is None:
            raise EvidenceIntegrityError(_RETAINED_BINDING_DIFFERS)
        try:
            spec_digest = canonical_json_digest(binding.spec)
        # An installed spec can hold a value outside the canonical JSON domain, such as an integer of 2**53 or more.
        except rfc8785.CanonicalizationError as exc:
            raise EvidenceIntegrityError(_RETAINED_BINDING_DIFFERS) from exc
        if spec_digest != application.delivery_digest:
            raise EvidenceIntegrityError(_RETAINED_BINDING_DIFFERS)
        if application.control is not None:
            _require_archived_control(plane, application)


def require_delivery_control(
    plane: RuntimeControlPlane,
    application: ParticipantInjectApplicationModel,
    delivery: ParticipantInjectDeliveryRuntime,
    expected_order: int,
    identity: ControlPlaneIdentity,
) -> None:
    if delivery.delivery_kind == "disclosure":
        if application.control is not None:
            raise ConflictError("disclosure carries no control authority")
        return
    if delivery.control is None or plane._mixed_control is None or application.control is None:
        raise ConflictError("inject delivery exact reusable control binding is unavailable")
    records = [
        parse_participant_control_occurrence(item)
        for item in plane._snapshot.participant_control_history.get(application.participant_address, ())
    ]
    event = _selected_event(records, application)
    policy = admitted_policy(plane, application.participant_address, application.episode_id)
    folded = fold_participant_control_episode_v2(
        [item for item in records if item.episode_id == application.episode_id],
        policy=policy,
        available_targets=archived_control_targets(plane, application.participant_address),
    )
    _require_accepted_event(application, delivery, event, folded)
    _require_policy_binding(delivery, event, folded)
    required_evidence = _require_controller_evidence(application, delivery, event, identity)
    cut = _resolve_live_cut(plane, policy, application)
    current = policy.state(folded.state.state_ref)
    _require_current_validity(application, event, current, cut, expected_order)
    _require_active_grants(event, current, cut, required_evidence)


def _selected_event(
    records: list[object], application: ParticipantInjectApplicationModel
) -> ParticipantControlOccurrenceV2Model:
    reference = application.control
    event = next((item for item in records if item.event_id == reference.event_id), None)
    if (
        event is None
        or event.schema_version != "2.0.0"
        or event.episode_id != application.episode_id
        or canonical_json_digest(event.model_dump(mode="json")) != reference.digest
    ):
        raise ConflictError("inject delivery control occurrence differs")
    return event


def _require_accepted_event(
    application: ParticipantInjectApplicationModel,
    delivery: ParticipantInjectDeliveryRuntime,
    event: ParticipantControlOccurrenceV2Model,
    folded: ParticipantControlEpisodeFoldV2,
) -> None:
    detail = event.occurrence
    if (
        folded.violation is not None
        or detail.disposition != "accepted"
        or detail.kind != delivery.delivery_kind
        or detail.occurrence_revision != application.control.occurrence_revision
    ):
        raise ConflictError("inject delivery control is not accepted for this kind")


def _require_policy_binding(
    delivery: ParticipantInjectDeliveryRuntime,
    event: ParticipantControlOccurrenceV2Model,
    folded: ParticipantControlEpisodeFoldV2,
) -> None:
    detail, binding = event.occurrence, delivery.control
    lifecycle = folded.state.lifecycle(event.event_id)
    if lifecycle.superseded or lifecycle.replaced or detail.resulting_state_revision != folded.state.state_revision:
        raise ConflictError("inject delivery control application is stale")
    if (
        detail.permitted_transition_ref != binding.permitted_transition_address
        or detail.controller_ref != binding.controller_address
        or event.policy.policy_revision != binding.policy_revision
    ):
        raise ConflictError("inject delivery control policy or edge differs")


def _require_controller_evidence(
    application: ParticipantInjectApplicationModel,
    delivery: ParticipantInjectDeliveryRuntime,
    event: ParticipantControlOccurrenceV2Model,
    identity: ControlPlaneIdentity,
) -> set[str]:
    detail, binding = event.occurrence, delivery.control
    if not any(
        subject.participant_address == application.participant_address
        and subject.controller_ref == detail.controller_ref
        for subject in identity.participant_control_subjects
    ):
        raise AuthorizationError("inject delivery source controller is unavailable")
    required = set(binding.evidence_addresses or binding.evidence_refs)
    if not set(binding.authority_scope_addresses) <= set(detail.controlled_scope_refs) or not required <= set(
        event.evidence_refs
    ):
        raise ConflictError("inject delivery control scope or evidence differs")
    return required


def _resolve_live_cut(
    plane: RuntimeControlPlane,
    policy: ParticipantControlOccurrencePolicyModel,
    application: ParticipantInjectApplicationModel,
) -> ParticipantControlLiveCut:
    method = getattr(plane._mixed_control.resolver, "resolve_delivery_cut", None)
    if not callable(method):
        raise ConflictError("inject delivery live control-cut owner is unavailable")
    try:
        return resolve_owner_cut(plane, policy, application, method)
    except CONTROL_CUT_REFUSALS:
        # The owner refused the live cut or ran out of budget: a refusal, not a failure to report.
        pass
    # Isolation: the installed live-cut owner failed outside its refusal contract.
    except Exception as exc:
        _LOGGER.exception("inject delivery live control-cut owner failed", exc_info=foreign_failure_record(exc))
    # Raised after the handler, so the refusal carries no owner exception as its context.
    raise ConflictError(_CUT_UNAVAILABLE)


def _require_current_validity(
    application: ParticipantInjectApplicationModel,
    event: ParticipantControlOccurrenceV2Model,
    current: object,
    cut: ParticipantControlLiveCut,
    expected_order: int,
) -> None:
    detail = event.occurrence
    if (
        cut.request_ref != application.request_key
        or cut.effective_order != expected_order
        or cut.effective_order < detail.effective_order
        or not detail.valid_from_order <= cut.effective_order <= detail.valid_until_order
        or not current.valid_from_order <= cut.effective_order <= current.valid_until_order
    ):
        raise ConflictError("inject delivery control validity is stale")


def _require_active_grants(
    event: ParticipantControlOccurrenceV2Model,
    current: object,
    cut: ParticipantControlLiveCut,
    required_evidence: set[str],
) -> None:
    detail = event.occurrence
    if (
        not {*detail.authority_basis_refs, *current.authority_basis_refs} <= set(cut.active_authority_basis_refs)
        or not set(detail.controlled_scope_refs) <= set(cut.authorized_scope_refs)
        or not required_evidence <= set(cut.evidence_refs)
    ):
        raise ConflictError("inject delivery authority has been revoked")


def _require_archived_control(plane: RuntimeControlPlane, application: ParticipantInjectApplicationModel) -> None:
    actual = next(
        (
            item
            for item in plane._snapshot.participant_control_history.get(application.participant_address, ())
            if item["event_id"] == application.control.event_id
        ),
        None,
    )
    if actual is None or canonical_json_digest(actual) != application.control.digest:
        raise EvidenceIntegrityError("retained inject delivery control history differs")
