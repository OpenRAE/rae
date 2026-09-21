"""ACT-618 v2 reports retain local meaning independently of downstream results."""

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, StrictInt, model_validator
from raes.participant_local_outcome import OutcomeAttainment, OutcomeCategory, OutcomeKnowledge
from raes.participant_outcome_semantics import OutcomeInterpretationRule

from ..addressing import CompiledAddress
from .base import ContractModel, NonEmptyString, PrefixedDigestString
from .participant_envelopes import ParticipantRuntimeBaseEnvelopeModel
from .participant_views import ParticipantOutcomeReportModel, ParticipantOutcomeReportStateRelationshipModel


class ParticipantOutcomeObservationRefModel(ContractModel):
    """An exact, immutable observation in the participant behavior history."""

    action_instance_id: NonEmptyString
    observation_point: NonEmptyString
    content_digest: PrefixedDigestString


class ParticipantOutcomeReportV2Model(ParticipantRuntimeBaseEnvelopeModel):
    """Local state at an exact history cut; v1 records are never upgraded implicitly."""

    schema_name: Literal["raes.participant_runtime.outcome_report"]
    schema_version: Literal["2.0.0"]
    event_type: Literal["participant_outcome_report"]
    participant_address: CompiledAddress
    episode_id: NonEmptyString
    outcome_id: NonEmptyString
    interpretation_rule_ref: CompiledAddress
    rule_digest: PrefixedDigestString
    rule_spec: OutcomeInterpretationRule
    revision: StrictInt = Field(ge=1)
    predecessor_event_ref: NonEmptyString | None
    behavior_history_length: StrictInt = Field(ge=0)
    behavior_history_digest: PrefixedDigestString
    observation_refs: list[ParticipantOutcomeObservationRefModel]
    excluded_observation_refs: list[NonEmptyString] = Field(default_factory=list)
    correction_basis: NonEmptyString | None = None
    category: OutcomeCategory
    attainment: OutcomeAttainment
    knowledge: OutcomeKnowledge
    freshness: Literal["current_at_recorded_cut"]
    state_relationships: list[ParticipantOutcomeReportStateRelationshipModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _local_state_shape(self) -> "ParticipantOutcomeReportV2Model":
        if self.rule_spec.local_outcome is None or self.category != self.rule_spec.local_outcome.category:
            raise ValueError("local outcome category requires its versioned definition")
        if self.knowledge in {"conflicting", "withheld"} and self.attainment != "undetermined":
            raise ValueError("conflicting or withheld evidence cannot establish attainment")
        if (self.revision == 1) != (self.predecessor_event_ref is None):
            raise ValueError("outcome revision requires the exact predecessor")
        self._require_correction_shape()
        return self

    def _require_correction_shape(self) -> None:
        refs = [ref.observation_point for ref in self.observation_refs]
        if len(set(refs)) != len(refs) or len(set(self.excluded_observation_refs)) != len(
            self.excluded_observation_refs
        ):
            raise ValueError("outcome observation identities must be unique")
        if not set(self.excluded_observation_refs) <= set(refs):
            raise ValueError("outcome correction references must resolve in its history cut")
        if self.excluded_observation_refs and self.correction_basis is None:
            raise ValueError("outcome corrections require an explicit basis")


def decode_participant_outcome_report(
    payload: Mapping[str, Any],
) -> ParticipantOutcomeReportModel | ParticipantOutcomeReportV2Model:
    """Read an exact supported version; migration requires new observations."""
    version = payload.get("schema_version")
    if version == "1.0.0":
        return ParticipantOutcomeReportModel.model_validate(payload)
    if version == "2.0.0":
        return ParticipantOutcomeReportV2Model.model_validate(payload)
    raise ValueError("participant outcome report version is unsupported")
