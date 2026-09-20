"""Portable evaluation records and pure local consistency checks for API-424."""

from __future__ import annotations

from graphlib import TopologicalSorter
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from .._canonical import canonical_json_digest
from ..json_ingress import parse_bounded_json_object
from .base import ContractModel
from .participant_control_coordinates import ControlRef, ParticipantControlContextModel, require_unique
from .participant_control_effect_composition import validate_control_effect_composition
from .participant_control_results import (
    ControlCompositionModel,
    ControlEffectiveSupportModel,
    ControlMechanismResultModel,
    ControlRealizationBindingModel,
)
from .participant_control_selection import ParticipantControlSelectionModel


def control_digest(record: ContractModel) -> str:
    """JCS digest of the complete portable record, including explicit nulls."""
    return canonical_json_digest(record.model_dump(mode="json"))


class ParticipantControlRequestModel(ContractModel):
    model_config = ConfigDict(frozen=True)
    selection: ParticipantControlSelectionModel
    context: ParticipantControlContextModel

    @model_validator(mode="after")
    def _admitted_scope(self):
        selection, context = self.selection, self.context
        if selection.apparatus != context.apparatus:
            raise ValueError("participant control apparatus binding differs")
        if {state.instance_id for state in context.provider_states} != {b.instance_id for b in selection.bindings}:
            raise ValueError("participant control provider-state coverage is incomplete")
        for binding in selection.bindings:
            if binding.memory_scope != context.memory_scope:
                raise ValueError("participant control memory binding differs")
            if not any(
                (a.participant_address, a.episode_id, a.direction, a.sink_ref, a.phase_ref, a.subject_kind)
                == (
                    context.participant_address,
                    context.episode_id,
                    context.direction,
                    context.sink_ref,
                    context.phase_ref,
                    context.subject.subject_kind,
                )
                for a in binding.applicability
            ):
                raise ValueError("participant control applicability is unresolved")
        bounds = selection.bounds
        if (
            context.depth > bounds.max_depth
            or context.effects_consumed > bounds.max_effects
            or context.attempt > bounds.max_attempts
            or context.order > bounds.expires_at_order
        ):
            raise ValueError("participant control causal bounds are exhausted")
        return self


class ParticipantControlEvaluationModel(ContractModel):
    """Complete contributor record. Eligibility is not authorization or dispatch."""

    model_config = ConfigDict(frozen=True)
    schema_version: Literal["participant-control-evaluation/v1"]
    evaluation_id: ControlRef
    request: ParticipantControlRequestModel
    results: Annotated[tuple[ControlMechanismResultModel, ...], Field(max_length=256)]
    support: Annotated[tuple[ControlEffectiveSupportModel, ...], Field(max_length=64)]
    composition: ControlCompositionModel
    realizations: Annotated[tuple[ControlRealizationBindingModel, ...], Field(max_length=256)]

    @model_validator(mode="after")
    def _evaluation(self):
        validate_evaluation_structure(self)
        return self


def _result_satisfied(result):
    if result.status != "resolved":
        return False
    return result.payload.kind != "decision" or result.payload.disposition == "permit"


def _validate_results(document):
    selection = document.request.selection
    context_digest = control_digest(document.request.context)
    bindings = {binding.instance_id: binding for binding in selection.bindings}
    slots = {slot.slot_id: slot for slot in selection.slots}
    results = {result.slot_id: result for result in document.results}
    require_unique(tuple(result.slot_id for result in document.results))
    require_unique(tuple(result.result_id for result in document.results))
    if results.keys() != slots.keys():
        raise ValueError("every selected slot requires an explicit result or absence record")
    expected_contributors = tuple(
        result.result_id for result in sorted(document.results, key=lambda r: (r.instance_id, r.slot_id))
    )
    if document.composition.contributing_result_ids != expected_contributors:
        raise ValueError("composition must preserve every contributor in canonical order")
    graph = {slot.slot_id: {dep.slot_id for dep in slot.dependencies} for slot in selection.slots}
    satisfied = {}
    for identity in TopologicalSorter(graph).static_order():
        satisfied[identity] = _result_satisfied(results[identity]) and all(satisfied[dep] for dep in graph[identity])
    blockers = set()
    for slot_id, result in results.items():
        slot = slots[slot_id]
        if result.instance_id != slot.instance_id or result.binding_digest != control_digest(
            bindings[slot.instance_id]
        ):
            raise ValueError("mechanism result does not bind the selected instance")
        if result.context_digest != context_digest:
            raise ValueError("mechanism result uses a stale or different exact context")
        if result.payload is not None and result.payload.kind != slot.kind:
            raise ValueError("mechanism result payload does not match its typed slot")
        if result.payload is not None and result.payload.kind == "ifc-fact":
            profiles = {profile.ref for profile in bindings[slot.instance_id].profiles}
            expected = (
                "teaching-influence"
                if result.payload.domain == "teaching-influence-domain/rev1"
                else "participant-boundary-flow-policy-v1"
            )
            if expected not in profiles:
                raise ValueError("IFC fact domain is not selected by its mechanism")
            if expected == "teaching-influence" and set(result.payload.source_refs) != set(
                document.request.context.inputs
            ):
                raise ValueError("teaching propagation must cover every admitted input")
        if slot.role == "mandatory" and not _result_satisfied(result):
            blockers.add("slot:" + slot_id)
        if slot.role == "mandatory" and any(not satisfied[dep.slot_id] for dep in slot.dependencies):
            blockers.add("dependency:" + slot_id)
    return blockers


def _validate_support(document):
    bindings = document.request.selection.bindings
    support = {item.instance_id: item for item in document.support}
    require_unique(tuple(item.instance_id for item in document.support))
    if support.keys() != {binding.instance_id for binding in bindings}:
        raise ValueError("support must cover every selected instance exactly")
    blockers = set()
    for item in document.support:
        if item.context_digest != control_digest(document.request.context):
            raise ValueError("effective support is bound to a different context")
        if item.status != "resolved" or item.effective_level != "exact":
            blockers.add("support:" + item.instance_id)
    return blockers


def validate_evaluation_structure(document):
    blockers = _validate_results(document) | _validate_support(document) | validate_control_effect_composition(document)
    if document.composition.incumbent_gate_disposition != "permit":
        blockers.add("incumbent-gates")
    if tuple(sorted(blockers)) != document.composition.blockers:
        raise ValueError("composition must retain exactly every blocking reason")
    if (document.composition.disposition == "eligible") != (not blockers):
        raise ValueError("composition eligibility disagrees with mandatory obligations")
    if "effect-conflict" in blockers and document.composition.disposition != "conflict":
        raise ValueError("incompatible effects require conflict disposition")


def parse_participant_control_evaluation(source: str | bytes) -> ParticipantControlEvaluationModel:
    """Bound ingress and expose no rejected value in public parse failures."""
    try:
        payload = parse_bounded_json_object(source, max_bytes=1_048_576, max_depth=32)
        return ParticipantControlEvaluationModel.model_validate(payload)
    except (TypeError, ValueError):
        raise ValueError("invalid participant control evaluation") from None
