"""Participant outcome source/target/interpretation records."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from raes.participant_outcome_semantics import OutcomeInterpretationSourceLayer, OutcomeInterpretationTargetLayer

from .behavior_resources import (
    _optional_payload_string,
    _tuple_of_non_empty_strings,
    _validate_optional_string,
    _validate_required_address,
    _validate_required_string,
)
from .resources import _PARTICIPANT_OUTCOME_RULE_PREFIX


def _outcome_source_layer_from_payload(value: object) -> OutcomeInterpretationSourceLayer:
    if isinstance(value, OutcomeInterpretationSourceLayer):
        return value
    return OutcomeInterpretationSourceLayer(str(value))


def _outcome_target_layer_from_payload(value: object) -> OutcomeInterpretationTargetLayer:
    if isinstance(value, OutcomeInterpretationTargetLayer):
        return value
    return OutcomeInterpretationTargetLayer(str(value))


@dataclass(frozen=True)
class ParticipantOutcomeSourceRecord:
    """Runtime source observed for a SEM-215 outcome interpretation."""

    source_id: str
    source_layer: OutcomeInterpretationSourceLayer
    ref: str
    observed_value: str
    evidence_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ParticipantOutcomeSourceRecord:
        if not isinstance(payload, Mapping):
            raise TypeError("participant outcome source record must be a mapping")
        missing = [key for key in ("source_id", "source_layer", "ref", "observed_value") if key not in payload]
        if missing:
            raise ValueError("participant outcome source record is missing required fields: " + ", ".join(missing))
        return cls(
            source_id=str(payload.get("source_id")),
            source_layer=_outcome_source_layer_from_payload(payload.get("source_layer")),
            ref=str(payload.get("ref")),
            observed_value=str(payload.get("observed_value")),
            evidence_refs=_tuple_of_non_empty_strings(payload.get("evidence_refs", ()), field_name="evidence_refs"),
            provenance_refs=_tuple_of_non_empty_strings(
                payload.get("provenance_refs", ()),
                field_name="provenance_refs",
            ),
            diagnostics=_tuple_of_non_empty_strings(payload.get("diagnostics", ()), field_name="diagnostics"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_layer": self.source_layer.value,
            "ref": self.ref,
            "observed_value": self.observed_value,
            "evidence_refs": list(self.evidence_refs),
            "provenance_refs": list(self.provenance_refs),
            "diagnostics": list(self.diagnostics),
        }

    def __post_init__(self) -> None:
        _validate_required_string(self.source_id, "participant outcome source_id must be a non-empty string")
        if not isinstance(self.source_layer, OutcomeInterpretationSourceLayer):
            raise TypeError("source_layer must be an OutcomeInterpretationSourceLayer")
        _validate_required_string(self.ref, "participant outcome source ref must be a non-empty string")
        _validate_required_string(
            self.observed_value,
            "participant outcome source observed_value must be a non-empty string",
        )
        _tuple_of_non_empty_strings(self.evidence_refs, field_name="evidence_refs")
        _tuple_of_non_empty_strings(self.provenance_refs, field_name="provenance_refs")
        _tuple_of_non_empty_strings(self.diagnostics, field_name="diagnostics")


@dataclass(frozen=True)
class ParticipantOutcomeTargetRecord:
    """Runtime target interpretation produced by a SEM-215 rule."""

    target_id: str
    target_layer: OutcomeInterpretationTargetLayer
    ref: str
    interpreted_value: str
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    governance_ref: str | None = None
    diagnostics: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ParticipantOutcomeTargetRecord:
        if not isinstance(payload, Mapping):
            raise TypeError("participant outcome target record must be a mapping")
        missing = [
            key
            for key in (
                "target_id",
                "target_layer",
                "ref",
                "interpreted_value",
                "evidence_refs",
                "limitations",
            )
            if key not in payload
        ]
        if missing:
            raise ValueError("participant outcome target record is missing required fields: " + ", ".join(missing))
        return cls(
            target_id=str(payload.get("target_id")),
            target_layer=_outcome_target_layer_from_payload(payload.get("target_layer")),
            ref=str(payload.get("ref")),
            interpreted_value=str(payload.get("interpreted_value")),
            evidence_refs=_tuple_of_non_empty_strings(payload.get("evidence_refs"), field_name="evidence_refs"),
            limitations=_tuple_of_non_empty_strings(payload.get("limitations"), field_name="limitations"),
            governance_ref=_optional_payload_string(payload, "governance_ref"),
            diagnostics=_tuple_of_non_empty_strings(payload.get("diagnostics", ()), field_name="diagnostics"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_layer": self.target_layer.value,
            "ref": self.ref,
            "interpreted_value": self.interpreted_value,
            "evidence_refs": list(self.evidence_refs),
            "limitations": list(self.limitations),
            "governance_ref": self.governance_ref,
            "diagnostics": list(self.diagnostics),
        }

    def __post_init__(self) -> None:
        _validate_required_string(self.target_id, "participant outcome target_id must be a non-empty string")
        if not isinstance(self.target_layer, OutcomeInterpretationTargetLayer):
            raise TypeError("target_layer must be an OutcomeInterpretationTargetLayer")
        _validate_required_string(self.ref, "participant outcome target ref must be a non-empty string")
        _validate_required_string(
            self.interpreted_value,
            "participant outcome target interpreted_value must be a non-empty string",
        )
        if not _tuple_of_non_empty_strings(self.evidence_refs, field_name="evidence_refs"):
            raise ValueError("participant outcome targets require evidence_refs")
        if not _tuple_of_non_empty_strings(self.limitations, field_name="limitations"):
            raise ValueError("participant outcome targets require limitations")
        _validate_optional_string(self.governance_ref, "governance_ref must be a non-empty string or None")
        _tuple_of_non_empty_strings(self.diagnostics, field_name="diagnostics")
        if self.target_layer == OutcomeInterpretationTargetLayer.REWARD_SIGNAL and self.governance_ref is None:
            raise ValueError("reward_signal outcome targets require governance_ref")


def _participant_outcome_source_records_from_payload(value: object) -> tuple[ParticipantOutcomeSourceRecord, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise TypeError("outcome source_bindings must be a list of source records")
    return tuple(ParticipantOutcomeSourceRecord.from_payload(item) for item in value)


def _participant_outcome_target_records_from_payload(value: object) -> tuple[ParticipantOutcomeTargetRecord, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise TypeError("outcome target_bindings must be a list of target records")
    return tuple(ParticipantOutcomeTargetRecord.from_payload(item) for item in value)


def _validate_outcome_source_bindings(source_bindings: tuple[ParticipantOutcomeSourceRecord, ...]) -> None:
    if not isinstance(source_bindings, tuple):
        raise TypeError("source_bindings must be a tuple")
    if not source_bindings:
        raise ValueError("participant outcome interpretations require source_bindings")
    if any(not isinstance(source, ParticipantOutcomeSourceRecord) for source in source_bindings):
        raise TypeError("source_bindings must contain ParticipantOutcomeSourceRecord values")
    if len({source.source_id for source in source_bindings}) != len(source_bindings):
        raise ValueError("participant outcome source_id values must be unique")


def _validate_outcome_target_bindings(target_bindings: tuple[ParticipantOutcomeTargetRecord, ...]) -> None:
    if not isinstance(target_bindings, tuple):
        raise TypeError("target_bindings must be a tuple")
    if not target_bindings:
        raise ValueError("participant outcome interpretations require target_bindings")
    if any(not isinstance(target, ParticipantOutcomeTargetRecord) for target in target_bindings):
        raise TypeError("target_bindings must contain ParticipantOutcomeTargetRecord values")
    if len({target.target_id for target in target_bindings}) != len(target_bindings):
        raise ValueError("participant outcome target_id values must be unique")


@dataclass(frozen=True)
class ParticipantOutcomeInterpretationRecord:
    """Provenance-bearing SEM-215 interpretation of participant-local outcomes."""

    interpretation_id: str
    rule_address: str
    participant_address: str
    episode_id: str
    observation_point: str
    source_bindings: tuple[ParticipantOutcomeSourceRecord, ...]
    target_bindings: tuple[ParticipantOutcomeTargetRecord, ...]
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ParticipantOutcomeInterpretationRecord:
        if not isinstance(payload, Mapping):
            raise TypeError("participant outcome interpretation record must be a mapping")
        missing = [
            key
            for key in (
                "interpretation_id",
                "rule_address",
                "participant_address",
                "episode_id",
                "observation_point",
                "source_bindings",
                "target_bindings",
                "evidence_refs",
                "limitations",
            )
            if key not in payload
        ]
        if missing:
            raise ValueError(
                "participant outcome interpretation record is missing required fields: " + ", ".join(missing)
            )
        return cls(
            interpretation_id=str(payload.get("interpretation_id")),
            rule_address=str(payload.get("rule_address")),
            participant_address=str(payload.get("participant_address")),
            episode_id=str(payload.get("episode_id")),
            observation_point=str(payload.get("observation_point")),
            source_bindings=_participant_outcome_source_records_from_payload(payload.get("source_bindings")),
            target_bindings=_participant_outcome_target_records_from_payload(payload.get("target_bindings")),
            evidence_refs=_tuple_of_non_empty_strings(payload.get("evidence_refs"), field_name="evidence_refs"),
            limitations=_tuple_of_non_empty_strings(payload.get("limitations"), field_name="limitations"),
            diagnostics=_tuple_of_non_empty_strings(payload.get("diagnostics", ()), field_name="diagnostics"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "interpretation_id": self.interpretation_id,
            "rule_address": self.rule_address,
            "participant_address": self.participant_address,
            "episode_id": self.episode_id,
            "observation_point": self.observation_point,
            "source_bindings": [source.to_payload() for source in self.source_bindings],
            "target_bindings": [target.to_payload() for target in self.target_bindings],
            "evidence_refs": list(self.evidence_refs),
            "limitations": list(self.limitations),
            "diagnostics": list(self.diagnostics),
        }

    def __post_init__(self) -> None:
        _validate_required_string(
            self.interpretation_id,
            "participant outcome interpretation_id must be a non-empty string",
        )
        _validate_required_address(
            self.rule_address,
            prefix=_PARTICIPANT_OUTCOME_RULE_PREFIX,
            message="rule_address must be a compiled participant outcome interpretation rule address",
        )
        _validate_required_string(
            self.participant_address,
            "participant outcome participant_address must be a non-empty string",
        )
        _validate_required_string(self.episode_id, "participant outcome episode_id must be a non-empty string")
        _validate_required_string(
            self.observation_point,
            "participant outcome observation_point must be a non-empty string",
        )
        _validate_outcome_source_bindings(self.source_bindings)
        _validate_outcome_target_bindings(self.target_bindings)
        if not _tuple_of_non_empty_strings(self.evidence_refs, field_name="evidence_refs"):
            raise ValueError("participant outcome interpretations require evidence_refs")
        if not _tuple_of_non_empty_strings(self.limitations, field_name="limitations"):
            raise ValueError("participant outcome interpretations require limitations")
        _tuple_of_non_empty_strings(self.diagnostics, field_name="diagnostics")


def _participant_outcome_interpretation_records_from_payload(
    value: object,
) -> tuple[ParticipantOutcomeInterpretationRecord, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise TypeError("outcome_interpretations must be a list of interpretation records")
    return tuple(ParticipantOutcomeInterpretationRecord.from_payload(item) for item in value)
