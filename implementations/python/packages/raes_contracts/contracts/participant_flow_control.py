"""Closed portable relation aggregate for SEM-233 participant boundary flow control."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes.participant_mixed_control_vocabulary import MixedControlTransitionKind

from ..graphs import has_cycle
from ..versions import PARTICIPANT_FLOW_CONTROL_RELATION_V1_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .participant_crossing_vocab import ParticipantCrossingSubjectKind
from .participant_flow_control_relation_validation import (
    validate_derivation,
    validate_release,
    validate_sink_decision,
)
from .participant_flow_control_semantics import (
    PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST,
    FlowSubjectKey,
    ParticipantBoundaryFlowPolicyProfileModel,
    ParticipantEffectiveFlowLabelModel,
    ParticipantFlowBindingKind,
    ParticipantFlowCoordinateResult,
    ParticipantFlowDeclassificationModel,
    ParticipantFlowDerivationModel,
    ParticipantFlowEndorsementModel,
    ParticipantFlowFinalDisposition,
    ParticipantFlowLabelResolutionStatus,
    ParticipantFlowPolicyCutReferenceModel,
    ParticipantFlowProfileReferenceModel,
    ParticipantFlowRelationTargetKind,
    ParticipantFlowRelease,
    ParticipantFlowReleaseKind,
    ParticipantFlowRuleReferenceModel,
    ParticipantFlowSinkDecisionModel,
    ParticipantFlowSinkKind,
    ParticipantFlowSubjectKind,
    ParticipantFlowSubjectReferenceModel,
    _require_canonical_refs,
    participant_flow_coordinate_disposition,
)
from .schema_invariants import _add_raes_invariant


class ParticipantFlowRelationTargetReferenceModel(ContractModel):
    target_kind: ParticipantFlowRelationTargetKind
    target_ref: NonEmptyString


class ParticipantFlowCarrierBindingBaseModel(ContractModel):
    binding_id: NonEmptyString
    profile: ParticipantFlowProfileReferenceModel
    policy: ParticipantFlowPolicyCutReferenceModel
    relation_target: ParticipantFlowRelationTargetReferenceModel
    source_participant_address: NonEmptyString
    source_episode_id: NonEmptyString
    target_participant_address: NonEmptyString
    target_episode_id: NonEmptyString
    crossing_refs: tuple[NonEmptyString, ...] = ()
    memory_predecessor_refs: tuple[NonEmptyString, ...] = ()

    @field_validator("crossing_refs", "memory_predecessor_refs")
    @classmethod
    def _validate_canonical_refs(cls, values: tuple[str, ...], info: object) -> tuple[str, ...]:
        _require_canonical_refs(values, getattr(info, "field_name", "binding refs"))
        return values

    @model_validator(mode="after")
    def _validate_cross_scope_state(self) -> ParticipantFlowCarrierBindingBaseModel:
        cross_scope = (
            self.source_participant_address,
            self.source_episode_id,
        ) != (
            self.target_participant_address,
            self.target_episode_id,
        )
        if cross_scope and (not self.crossing_refs or not self.memory_predecessor_refs):
            raise ValueError("cross-scope bindings require crossing and memory predecessor refs")
        return self


class ParticipantRuntimeFactFlowBindingModel(ParticipantFlowCarrierBindingBaseModel):
    kind: Literal[ParticipantFlowBindingKind.RUNTIME_FACT]
    plane_ref: NonEmptyString
    declaration_ref: NonEmptyString
    fact_version_ref: NonEmptyString
    sink_ref: NonEmptyString
    binding_event_ref: NonEmptyString


class ParticipantActionArgumentFlowBindingModel(ParticipantFlowCarrierBindingBaseModel):
    kind: Literal[ParticipantFlowBindingKind.ACTION_ARGUMENT]
    action_contract_address: NonEmptyString
    proposal_ref: NonEmptyString
    normalized_argument_name: NonEmptyString
    action_admission_ref: NonEmptyString


class ParticipantControlOccurrenceFlowBindingModel(ParticipantFlowCarrierBindingBaseModel):
    kind: Literal[ParticipantFlowBindingKind.PARTICIPANT_CONTROL]
    event_id: NonEmptyString
    occurrence_kind: MixedControlTransitionKind
    occurrence_revision: int = Field(ge=1)
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    controller_ref: NonEmptyString
    authority_basis_refs: tuple[NonEmptyString, ...] = Field(min_length=1)
    control_policy_revision: NonEmptyString
    occurrence_identity_ref: NonEmptyString
    related_occurrence_refs: tuple[NonEmptyString, ...]
    predecessor_event_refs: tuple[NonEmptyString, ...]

    @field_validator("authority_basis_refs", "related_occurrence_refs", "predecessor_event_refs")
    @classmethod
    def _validate_canonical_refs(cls, values: tuple[str, ...], info: object) -> tuple[str, ...]:
        _require_canonical_refs(values, getattr(info, "field_name", "control binding refs"))
        return values


class ParticipantCrossingOccurrenceFlowBindingModel(ParticipantFlowCarrierBindingBaseModel):
    kind: Literal[ParticipantFlowBindingKind.PARTICIPANT_CROSSING]
    event_id: NonEmptyString
    stage: Literal[
        "requested",
        "decided",
        "transformed",
        "disclosed",
        "delivery-attempted",
        "delivered",
        "observed",
        "audited",
    ]
    stage_identity_ref: NonEmptyString
    related_stage_refs: tuple[NonEmptyString, ...]
    participant_address: NonEmptyString
    episode_id: NonEmptyString
    subject_kind: ParticipantCrossingSubjectKind
    subject_contract_id: NonEmptyString
    subject_ref: NonEmptyString
    subject_revision: NonEmptyString | None = None
    subject_digest: PrefixedDigestString | None = None
    crossing_policy_id: NonEmptyString
    crossing_policy_revision: NonEmptyString
    crossing_policy_digest: PrefixedDigestString
    crossing_policy_decision_ref: NonEmptyString
    crossing_decision_cut_ref: NonEmptyString
    predecessor_event_refs: tuple[NonEmptyString, ...]

    @model_validator(mode="after")
    def _subject_identity(self) -> ParticipantCrossingOccurrenceFlowBindingModel:
        if self.subject_revision is None and self.subject_digest is None:
            raise ValueError("flow crossing subject requires a revision or digest")
        return self

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(handler(core_schema))
        schema["anyOf"] = [
            {"required": [name], "properties": {name: {"type": "string"}}}
            for name in ("subject_revision", "subject_digest")
        ]
        return schema

    @field_validator("related_stage_refs", "predecessor_event_refs")
    @classmethod
    def _validate_canonical_refs(cls, values: tuple[str, ...], info: object) -> tuple[str, ...]:
        _require_canonical_refs(values, getattr(info, "field_name", "crossing binding refs"))
        return values


ParticipantFlowCarrierBinding = Annotated[
    ParticipantRuntimeFactFlowBindingModel
    | ParticipantActionArgumentFlowBindingModel
    | ParticipantControlOccurrenceFlowBindingModel
    | ParticipantCrossingOccurrenceFlowBindingModel,
    Field(discriminator="kind"),
]


class ParticipantFlowControlRelationModel(ContractModel):
    """Aggregate portable SEM-233 label, release, sink, and carrier relation."""

    schema_version: Literal[PARTICIPANT_FLOW_CONTROL_RELATION_V1_SCHEMA_VERSION] = (
        PARTICIPANT_FLOW_CONTROL_RELATION_V1_SCHEMA_VERSION
    )
    document_id: NonEmptyString
    document_revision: NonEmptyString
    profile: ParticipantFlowProfileReferenceModel
    labels: tuple[ParticipantEffectiveFlowLabelModel, ...] = Field(min_length=1, max_length=256)
    derivations: tuple[ParticipantFlowDerivationModel, ...] = Field(min_length=1, max_length=256)
    releases: tuple[ParticipantFlowRelease, ...] = Field(min_length=1, max_length=256)
    sink_decisions: tuple[ParticipantFlowSinkDecisionModel, ...] = Field(min_length=1, max_length=256)
    bindings: tuple[ParticipantFlowCarrierBinding, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _validate_relation_graph(self) -> ParticipantFlowControlRelationModel:
        labels = _unique_by_id(self.labels, "label_id", "label")
        derivations = _unique_by_id(self.derivations, "derivation_id", "derivation")
        releases = _unique_by_id(self.releases, "release_id", "release")
        decisions = _unique_by_id(self.sink_decisions, "decision_id", "sink decision")
        _unique_by_id(self.bindings, "binding_id", "carrier binding")
        self._validate_profile_coordinates()
        self._validate_derivations(labels)
        self._validate_releases(labels)
        self._validate_lineage_graph()
        self._validate_sink_decisions(labels, releases)
        self._validate_binding_targets(labels, derivations, releases, decisions)
        return self

    def _validate_profile_coordinates(self) -> None:
        records = (*self.labels, *self.derivations, *self.releases, *self.sink_decisions, *self.bindings)
        if any(record.profile != self.profile for record in records):
            raise ValueError("every flow relation record must use the document's exact profile")

    def _validate_derivations(self, labels: dict[str, ParticipantEffectiveFlowLabelModel]) -> None:
        graph: dict[FlowSubjectKey, set[FlowSubjectKey]] = {}
        for derivation in self.derivations:
            input_keys, result_key = validate_derivation(derivation, labels)
            for source_key in input_keys:
                graph.setdefault(source_key, set()).add(result_key)
        _reject_cycles(graph)

    def _validate_releases(self, labels: dict[str, ParticipantEffectiveFlowLabelModel]) -> None:
        for release in self.releases:
            validate_release(release, labels)

    def _validate_lineage_graph(self) -> None:
        produced = [
            *(_subject_key(derivation.result_subject) for derivation in self.derivations),
            *(_subject_key(release.result_subject) for release in self.releases),
        ]
        if len(produced) != len(set(produced)):
            raise ValueError("every derivation and release requires a globally fresh result identity")

        graph: dict[FlowSubjectKey, set[FlowSubjectKey]] = {}
        for derivation in self.derivations:
            result = _subject_key(derivation.result_subject)
            for item in derivation.inputs:
                graph.setdefault(_subject_key(item.subject), set()).add(result)
        for release in self.releases:
            graph.setdefault(_subject_key(release.source_subject), set()).add(_subject_key(release.result_subject))
        _reject_cycles(graph)

    def _validate_sink_decisions(
        self,
        labels: dict[str, ParticipantEffectiveFlowLabelModel],
        releases: dict[str, ParticipantFlowRelease],
    ) -> None:
        for decision in self.sink_decisions:
            validate_sink_decision(decision, labels, releases)

    def _validate_binding_targets(
        self,
        labels: dict[str, ParticipantEffectiveFlowLabelModel],
        derivations: dict[str, ParticipantFlowDerivationModel],
        releases: dict[str, ParticipantFlowRelease],
        decisions: dict[str, ParticipantFlowSinkDecisionModel],
    ) -> None:
        indexes: dict[ParticipantFlowRelationTargetKind, dict[str, object]] = {
            ParticipantFlowRelationTargetKind.LABEL: labels,
            ParticipantFlowRelationTargetKind.DERIVATION: derivations,
            ParticipantFlowRelationTargetKind.RELEASE: releases,
            ParticipantFlowRelationTargetKind.SINK_DECISION: decisions,
        }
        for binding in self.bindings:
            target = indexes[binding.relation_target.target_kind].get(binding.relation_target.target_ref)
            if target is None:
                raise ValueError("carrier binding relation target must resolve")
            if binding.policy != target.policy:
                raise ValueError("carrier binding target must use its exact policy and cut")
            if binding.relation_target.target_kind == ParticipantFlowRelationTargetKind.LABEL:
                label = labels[binding.relation_target.target_ref]
                if (
                    binding.target_participant_address,
                    binding.target_episode_id,
                ) != (
                    label.subject.participant_address,
                    label.subject.episode_id,
                ):
                    raise ValueError("carrier binding target scope must match its effective label")
                source_ref = _binding_source_ref(binding)
                if source_ref not in label.influence_refs:
                    raise ValueError("carrier binding cannot erase its upstream influence")

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "participant-flow-control-resolved-context",
            "Every label, derivation, release, sink decision, and carrier binding must resolve an exact SEM-233 "
            "profile and exact incumbent runtime-fact, API-409, API-423, action-admission, capability, authority, "
            "and history decision state before it can be trusted.",
            validator="raes_contracts.contracts.validate_participant_flow_control_resolved_context",
            inputs=[
                {"contract_id": "participant-flow-control-relation-v1", "instance_path": "#"},
                {"contract_id": "runtime-fact-binding-plane-v1", "instance_path": "#"},
                {"contract_id": "participant-control-occurrence-v1", "instance_path": "#"},
                {"contract_id": "participant-crossing-occurrence-v1", "instance_path": "#"},
            ],
        )
        return json_schema


def _unique_by_id(items: tuple[object, ...], field_name: str, label: str) -> dict[str, object]:
    indexed: dict[str, object] = {}
    for item in items:
        identity = getattr(item, field_name)
        if identity in indexed:
            raise ValueError(f"{label} identity was reused")
        indexed[identity] = item
    return indexed


def _subject_key(subject: ParticipantFlowSubjectReferenceModel) -> FlowSubjectKey:
    return (
        subject.subject_kind,
        subject.subject_ref,
        subject.subject_revision,
        subject.participant_address,
        subject.episode_id,
    )


def _reject_cycles(graph: dict[FlowSubjectKey, set[FlowSubjectKey]]) -> None:
    if has_cycle(graph):
        raise ValueError("flow derivation cycle is not allowed")


def _binding_source_ref(binding: ParticipantFlowCarrierBinding) -> str:
    if isinstance(binding, ParticipantRuntimeFactFlowBindingModel):
        return binding.fact_version_ref
    if isinstance(binding, ParticipantActionArgumentFlowBindingModel):
        return f"{binding.proposal_ref}:{binding.normalized_argument_name}"
    return binding.event_id


__all__ = [
    "PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST",
    "ParticipantBoundaryFlowPolicyProfileModel",
    "ParticipantEffectiveFlowLabelModel",
    "ParticipantFlowBindingKind",
    "ParticipantFlowControlRelationModel",
    "ParticipantFlowCoordinateResult",
    "ParticipantFlowDeclassificationModel",
    "ParticipantFlowDerivationModel",
    "ParticipantFlowEndorsementModel",
    "ParticipantFlowFinalDisposition",
    "ParticipantFlowLabelResolutionStatus",
    "ParticipantFlowPolicyCutReferenceModel",
    "ParticipantFlowProfileReferenceModel",
    "ParticipantFlowReleaseKind",
    "ParticipantFlowRelationTargetKind",
    "ParticipantFlowRuleReferenceModel",
    "ParticipantFlowSinkDecisionModel",
    "ParticipantFlowSinkKind",
    "ParticipantFlowSubjectKind",
    "ParticipantFlowSubjectReferenceModel",
    "participant_flow_coordinate_disposition",
]
