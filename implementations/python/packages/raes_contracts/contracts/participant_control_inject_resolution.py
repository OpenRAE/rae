"""Resolve inject requests against exact incumbent delivery and application owners."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes.participant_inject_delivery import ParticipantInjectDelivery

from .participant_control_applicability import control_digest
from .participant_control_coordinates import ParticipantControlContextModel
from .participant_control_effects import ControlInjectEffectModel
from .participant_inject_application import ParticipantInjectContentModel

if TYPE_CHECKING:
    from .participant_control_resolution import (
        ParticipantControlValidationContext,
        ParticipantControlValidationContextV2,
    )


def _validate_inject(
    target: ControlInjectEffectModel,
    cut: ParticipantControlContextModel,
    context: ParticipantControlValidationContext | ParticipantControlValidationContextV2,
) -> None:
    delivery = context.inject_deliveries.get(target.delivery_ref.ref)
    if delivery is None or control_digest(delivery) != target.delivery_ref.digest:
        raise ValueError("inject request has no exact owning delivery")
    if delivery.control is not None:
        _validate_control_inject(target, cut, context, delivery)
        return
    canonical = getattr(context, "inject_coordinates", {}).get(target.delivery_ref.ref)
    if canonical is not None:
        if (canonical, target.episode_id, delivery.delivery_policy.audience_scope_ref) != (
            target,
            cut.episode_id,
            cut.audience_ref,
        ):
            raise ValueError("inject request canonical owner coordinates differ")
        return
    expected = (
        target.participant_address,
        target.inject_ref,
        target.event_ref,
        target.script_ref,
        target.story_ref,
        target.source_item_ref,
        target.result_item_ref,
        target.disclosure_ref.ref,
    )
    observed = (
        delivery.participant_ref,
        delivery.inject_ref,
        delivery.occurrence.event_ref,
        delivery.occurrence.script_ref,
        delivery.occurrence.story_ref,
        delivery.source_item_ref,
        delivery.result_item_ref,
        delivery.delivery_policy.disclosure_basis_ref,
    )
    if (
        expected != observed
        or target.episode_id != cut.episode_id
        or delivery.delivery_policy.audience_scope_ref != cut.audience_ref
    ):
        raise ValueError("inject request owner coordinates differ")


def _validate_control_inject(
    target: ControlInjectEffectModel,
    cut: ParticipantControlContextModel,
    context: ParticipantControlValidationContext | ParticipantControlValidationContextV2,
    delivery: ParticipantInjectDelivery,
) -> None:
    application = getattr(context, "inject_applications", {}).get(target.delivery_ref.ref)
    canonical = getattr(context, "inject_coordinates", {}).get(target.delivery_ref.ref)
    if application is None or canonical != target or application.application.control is None:
        raise ValueError(
            "inject request cannot join a mixed-control-policy-occurrence/rev1 delivery binding "
            "without its exact owner application"
        )
    application = ParticipantInjectContentModel.model_validate(application.model_dump(mode="json"))
    selected = application.application
    if (
        selected.delivery_address != target.delivery_ref.ref
        or selected.delivery_digest != target.delivery_ref.digest
        or (
            application.participant_address,
            application.episode_id,
            application.disclosed_item.artifact_id,
            application.visibility_projection_ref,
        )
        != (target.participant_address, cut.episode_id, target.result_item_ref, target.disclosure_ref.ref)
    ):
        raise ValueError("inject request exact owner application differs")
