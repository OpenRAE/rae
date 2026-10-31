"""Bind compiled author intent to ACT-620 disclosure and delivery evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import partial

from pydantic import ValidationError
from raes.participant_control_context import ResolvedControlContextSelection, SDLControlContextConfigurationValidator
from raes_contracts.contracts import ParticipantDecisionSurfaceV2Model
from raes_contracts.contracts.experiment_bindings import ParticipantConfigurationResultModel
from raes_contracts.contracts.participant_control_context import ParticipantControlContextRecordModel
from raes_contracts.participant_control_context import (
    ParticipantControlContextValidationContext,
    validate_control_context_record,
)
from raes_contracts.participant_decision_surface_delivery import (
    ParticipantDecisionSurfaceDeliveryResolverV2,
    deliver_participant_decision_surface_v2,
)

from .participant_exposure_policy import resolve_from_host
from .runtime_model import RuntimeModel

VISIBLE = frozenset({"observable", "discovered", "inferred", "disclosed", "deceptive"})


@dataclass(frozen=True)
class AuthoredParticipantExposureV2:
    """Host-owned ACT-620 records keyed by compiled participant selection slot."""

    records: Mapping[str, ParticipantControlContextRecordModel]
    context: ParticipantControlContextValidationContext
    configuration: ParticipantConfigurationResultModel | None = None


def validate_authored_participant_exposure_v2(
    runtime_model: RuntimeModel,
    surface: ParticipantDecisionSurfaceV2Model,
    *,
    relation: Mapping[str, str],
    authored: AuthoredParticipantExposureV2 | None,
) -> None:
    """Validate the authored join with value-free carrier validation errors."""
    try:
        _validate_authored_participant_exposure_v2(runtime_model, surface, relation=relation, authored=authored)
    except ValidationError:
        raise ValueError("authored-exposure.invalid-carrier") from None


def _validate_authored_participant_exposure_v2(
    runtime_model: RuntimeModel,
    surface: ParticipantDecisionSurfaceV2Model,
    *,
    relation: Mapping[str, str],
    authored: AuthoredParticipantExposureV2 | None,
) -> None:
    """Reject unbound, withheld or unauthorized asset results without private values."""
    try:
        surface = ParticipantDecisionSurfaceV2Model.model_validate(surface.model_dump())
    except ValidationError:
        raise ValueError("authored-exposure.surface-invalid") from None
    participant = runtime_model.participant_behaviors.get(surface.participant_view.participant_address)
    if participant is None:
        raise ValueError("authored-exposure.participant-unresolved")
    selections = {item.slot_id: item for item in participant.control_context}
    if authored is not None and authored.configuration is not None:
        configuration = ParticipantConfigurationResultModel.model_validate(authored.configuration.model_dump())
        if configuration.participant_address != f"agents.{participant.participant_name}":
            raise ValueError("authored-exposure.configuration-participant-mismatch")
        scenario = runtime_model.realization_instance
        if scenario is None:
            raise ValueError("authored-exposure.configuration-owner-required")
        owner = SDLControlContextConfigurationValidator(scenario)
        for value in configuration.configuration.values:
            selected = value.control_context_selection
            if selected is None:
                continue
            if selected.slot_id in selections:
                raise ValueError("authored-exposure.selection-conflict")
            owner.validate_control_context_reference(configuration.participant_address, selected)
            selections[selected.slot_id] = ResolvedControlContextSelection(
                selected.slot_id,
                configuration.participant_address,
                selected.declaration_ref,
                selected.asset_ref,
                "selected",
                configuration.manifest_ref,
            )
    bindings = surface.assurance.exposure_bindings
    visible = set(surface.participant_view.visible_context_refs)
    records = authored.records if authored is not None else {}
    covered: set[str] = set()
    for slot, original_record in records.items():
        record = ParticipantControlContextRecordModel.model_validate(original_record.model_dump())
        selection = selections.get(slot)
        if selection is None or selection.participant_address != f"agents.{participant.participant_name}":
            raise ValueError("authored-exposure.slot-unresolved")
        if selection.disposition != "selected":
            raise ValueError("authored-exposure.withheld")
        if selection.asset_ref != record.asset_ref:
            raise ValueError("authored-exposure.pin-mismatch")
        if relation.get(selection.declaration_address) not in VISIBLE:
            raise ValueError("authored-exposure.source-hidden")
        expected = "delivered" if surface.surface_state == "delivered" else "disclosed"
        if record.disposition != expected or record.item_ref not in visible or record.item_ref in covered:
            raise ValueError("authored-exposure.record-mismatch")
        assert authored is not None
        context = replace(authored.context, surfaces={surface.participant_view.surface_id: surface})
        if surface.surface_state == "projected" and context.record_cut != surface.assurance.derivation_anchor.state_cut:
            raise ValueError("authored-exposure.cut-mismatch")
        if resolve_from_host(
            "control-context",
            "authored-exposure.authority-resolution-failed",
            partial(validate_control_context_record, record, context),
        ):
            raise ValueError("authored-exposure.authority-mismatch")
        covered.add(record.item_ref)
    for selection in selections.values():
        source = "urn:" + selection.asset_ref.asset_digest
        items = {binding.item_ref for binding in bindings if binding.source_ref == source}
        if selection.declaration_address in visible:
            items.add(selection.declaration_address)
        if selection.disposition == "withheld" and items:
            raise ValueError("authored-exposure.withheld")
        if not items.issubset(covered):
            raise ValueError("authored-exposure.record-required")
    if any(ref.startswith("control_context_assets.") and ref not in covered for ref in visible):
        raise ValueError("authored-exposure.asset-unresolved")
    if authored is not None:
        context_view = authored.context.context_views.get(surface.participant_view.context_view_ref)
        if (
            context_view is not None
            and any(layer.source_layer == "participant_control_context_asset" for layer in context_view.source_layers)
            and context_view.payload_ref not in covered
        ):
            raise ValueError("authored-exposure.record-required")


def deliver_authored_participant_decision_surface_v2(
    runtime_model: RuntimeModel,
    surface: ParticipantDecisionSurfaceV2Model,
    *,
    delivery_ref: str,
    resolver: ParticipantDecisionSurfaceDeliveryResolverV2,
    relation: Mapping[str, str],
    authored: AuthoredParticipantExposureV2,
) -> ParticipantDecisionSurfaceV2Model:
    """Bind trusted delivery, then check current ACT-620 authority before release."""
    delivered = deliver_participant_decision_surface_v2(surface, delivery_ref=delivery_ref, resolver=resolver)
    validate_authored_participant_exposure_v2(runtime_model, delivered, relation=relation, authored=authored)
    return delivered
