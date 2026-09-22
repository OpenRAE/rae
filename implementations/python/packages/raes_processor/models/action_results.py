"""Resolved participant action precondition/effect/result records."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from raes.participant_behavior import ParticipantEffectClass, ParticipantFailureClass, ParticipantPreconditionClass
from raes_contracts.contracts.participant_resource_budgets import ParticipantResourceMeasurementModel
from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel
from raes_contracts.participant_behavior import ParticipantActionPreconditionStatus, ParticipantActionResultStatus

from .behavior_resources import (
    _observation_point_matches_action_instance,
    _tuple_of_non_empty_strings,
    _validate_required_address,
    _validate_required_string,
)
from .resources import _PARTICIPANT_ACTION_CONTRACT_PREFIX


@dataclass(frozen=True)
class ParticipantActionPreconditionResult:
    """Resolved applicability state for one typed SEM-211 precondition."""

    precondition_id: str
    precondition_class: ParticipantPreconditionClass
    status: ParticipantActionPreconditionStatus
    participant_address: str
    episode_id: str
    action_contract_address: str
    observation_point: str
    support_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ParticipantActionPreconditionResult":
        if not isinstance(payload, Mapping):
            raise TypeError("participant action precondition result must be a mapping")
        missing = [
            key
            for key in (
                "precondition_id",
                "precondition_class",
                "status",
                "participant_address",
                "episode_id",
                "action_contract_address",
                "observation_point",
            )
            if key not in payload
        ]
        if missing:
            raise ValueError("participant action precondition result is missing required fields: " + ", ".join(missing))
        precondition_class_raw = payload.get("precondition_class")
        status_raw = payload.get("status")
        return cls(
            precondition_id=str(payload.get("precondition_id")),
            precondition_class=(
                precondition_class_raw
                if isinstance(precondition_class_raw, ParticipantPreconditionClass)
                else ParticipantPreconditionClass(str(precondition_class_raw))
            ),
            status=(
                status_raw
                if isinstance(status_raw, ParticipantActionPreconditionStatus)
                else ParticipantActionPreconditionStatus(str(status_raw))
            ),
            participant_address=str(payload.get("participant_address")),
            episode_id=str(payload.get("episode_id")),
            action_contract_address=str(payload.get("action_contract_address")),
            observation_point=str(payload.get("observation_point")),
            support_refs=_tuple_of_non_empty_strings(payload.get("support_refs", ()), field_name="support_refs"),
            evidence_refs=_tuple_of_non_empty_strings(payload.get("evidence_refs", ()), field_name="evidence_refs"),
            diagnostics=_tuple_of_non_empty_strings(payload.get("diagnostics", ()), field_name="diagnostics"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "precondition_id": self.precondition_id,
            "precondition_class": self.precondition_class.value,
            "status": self.status.value,
            "participant_address": self.participant_address,
            "episode_id": self.episode_id,
            "action_contract_address": self.action_contract_address,
            "observation_point": self.observation_point,
            "support_refs": list(self.support_refs),
            "evidence_refs": list(self.evidence_refs),
            "diagnostics": list(self.diagnostics),
        }

    def __post_init__(self) -> None:
        _validate_required_string(
            self.precondition_id,
            "precondition_id must be a non-empty string",
        )
        if not isinstance(self.precondition_class, ParticipantPreconditionClass):
            raise TypeError("precondition_class must be a ParticipantPreconditionClass")
        if not isinstance(self.status, ParticipantActionPreconditionStatus):
            raise TypeError("status must be a ParticipantActionPreconditionStatus")
        _validate_required_string(
            self.participant_address,
            "participant action precondition participant_address must be a non-empty string",
        )
        _validate_required_string(
            self.episode_id,
            "participant action precondition episode_id must be a non-empty string",
        )
        _validate_required_address(
            self.action_contract_address,
            prefix=_PARTICIPANT_ACTION_CONTRACT_PREFIX,
            message="action_contract_address must be a compiled participant action contract address",
        )
        _validate_required_string(
            self.observation_point,
            "observation_point must be a non-empty string",
        )
        _tuple_of_non_empty_strings(self.support_refs, field_name="support_refs")
        _tuple_of_non_empty_strings(self.evidence_refs, field_name="evidence_refs")
        _tuple_of_non_empty_strings(self.diagnostics, field_name="diagnostics")


@dataclass(frozen=True)
class ParticipantActionEffectResult:
    """Realized effect entry for a SEM-211 participant action result."""

    effect_id: str
    effect_class: ParticipantEffectClass
    description: str
    target_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ParticipantActionEffectResult":
        if not isinstance(payload, Mapping):
            raise TypeError("participant action effect result must be a mapping")
        missing = [key for key in ("effect_id", "effect_class", "description") if key not in payload]
        if missing:
            raise ValueError("participant action effect result is missing required fields: " + ", ".join(missing))
        effect_class_raw = payload.get("effect_class")
        return cls(
            effect_id=str(payload.get("effect_id")),
            effect_class=(
                effect_class_raw
                if isinstance(effect_class_raw, ParticipantEffectClass)
                else ParticipantEffectClass(str(effect_class_raw))
            ),
            description=str(payload.get("description")),
            target_refs=_tuple_of_non_empty_strings(payload.get("target_refs", ()), field_name="target_refs"),
            evidence_refs=_tuple_of_non_empty_strings(payload.get("evidence_refs", ()), field_name="evidence_refs"),
            diagnostics=_tuple_of_non_empty_strings(payload.get("diagnostics", ()), field_name="diagnostics"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "effect_id": self.effect_id,
            "effect_class": self.effect_class.value,
            "description": self.description,
            "target_refs": list(self.target_refs),
            "evidence_refs": list(self.evidence_refs),
            "diagnostics": list(self.diagnostics),
        }

    def __post_init__(self) -> None:
        _validate_required_string(self.effect_id, "effect_id must be a non-empty string")
        if not isinstance(self.effect_class, ParticipantEffectClass):
            raise TypeError("effect_class must be a ParticipantEffectClass")
        _validate_required_string(
            self.description,
            "participant action effect description must be a non-empty string",
        )
        _tuple_of_non_empty_strings(self.target_refs, field_name="target_refs")
        _tuple_of_non_empty_strings(self.evidence_refs, field_name="evidence_refs")
        _tuple_of_non_empty_strings(self.diagnostics, field_name="diagnostics")
        if self.effect_class not in {ParticipantEffectClass.NO_EFFECT, ParticipantEffectClass.UNKNOWN_EFFECT}:
            if not self.target_refs and not self.evidence_refs:
                raise ValueError(f"{self.effect_class.value} effects require target_refs or evidence_refs")


_PARTICIPANT_ACTION_FAILURE_STATUSES = frozenset(
    {
        ParticipantActionResultStatus.REJECTED,
        ParticipantActionResultStatus.WITHHELD,
        ParticipantActionResultStatus.FAILED,
        ParticipantActionResultStatus.PARTIAL_SUCCESS,
        ParticipantActionResultStatus.UNKNOWN,
    }
)
_PARTICIPANT_ACTION_SUCCESS_STATUSES = frozenset(
    {
        ParticipantActionResultStatus.ACCEPTED,
        ParticipantActionResultStatus.SUCCEEDED,
        ParticipantActionResultStatus.PARTIAL_SUCCESS,
    }
)
_PARTICIPANT_ACTION_TERMINAL_EFFECT_STATUSES = frozenset(
    {
        ParticipantActionResultStatus.SUCCEEDED,
        ParticipantActionResultStatus.PARTIAL_SUCCESS,
    }
)


def _validate_action_result_required_fields(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError("participant action result must be a mapping")
    missing = [
        key
        for key in (
            "status",
            "participant_address",
            "episode_id",
            "action_instance_id",
            "action_contract_address",
            "observation_point",
        )
        if key not in payload
    ]
    if missing:
        raise ValueError("participant action result is missing required fields: " + ", ".join(missing))


def _ensure_iterable_of_item_payloads(value: object, message: str) -> None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        raise TypeError(message)


def _coerce_action_result_status(status_raw: object) -> ParticipantActionResultStatus:
    if isinstance(status_raw, ParticipantActionResultStatus):
        return status_raw
    return ParticipantActionResultStatus(str(status_raw))


def _coerce_action_result_failure_class(failure_raw: object) -> ParticipantFailureClass | None:
    if failure_raw is None:
        return None
    if isinstance(failure_raw, ParticipantFailureClass):
        return failure_raw
    return ParticipantFailureClass(str(failure_raw))


@dataclass(frozen=True)
class ParticipantActionResult:
    """Typed SEM-211 local result for a participant action attempt."""

    status: ParticipantActionResultStatus
    participant_address: str
    episode_id: str
    action_instance_id: str
    action_contract_address: str
    observation_point: str
    preconditions: tuple[ParticipantActionPreconditionResult, ...] = ()
    effects: tuple[ParticipantActionEffectResult, ...] = ()
    failure_class: ParticipantFailureClass | None = None
    observations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    temporal_evidence: tuple[ParticipantTemporalEvidenceModel, ...] = ()
    resource_measurements: tuple[ParticipantResourceMeasurementModel, ...] = ()

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ParticipantActionResult":
        _validate_action_result_required_fields(payload)
        status_raw = payload.get("status")
        failure_raw = payload.get("failure_class")
        preconditions_raw = payload.get("preconditions", ())
        effects_raw = payload.get("effects", ())
        _ensure_iterable_of_item_payloads(
            preconditions_raw, "preconditions must be a list of participant action precondition results"
        )
        _ensure_iterable_of_item_payloads(effects_raw, "effects must be a list of participant action effect results")
        return cls(
            status=_coerce_action_result_status(status_raw),
            temporal_evidence=tuple(
                ParticipantTemporalEvidenceModel.model_validate(item) for item in payload.get("temporal_evidence", ())
            ),
            resource_measurements=tuple(
                ParticipantResourceMeasurementModel.model_validate(item)
                for item in payload.get("resource_measurements", ())
            ),
            participant_address=str(payload.get("participant_address")),
            episode_id=str(payload.get("episode_id")),
            action_instance_id=str(payload.get("action_instance_id")),
            action_contract_address=str(payload.get("action_contract_address")),
            observation_point=str(payload.get("observation_point")),
            preconditions=tuple(ParticipantActionPreconditionResult.from_payload(item) for item in preconditions_raw),
            effects=tuple(ParticipantActionEffectResult.from_payload(item) for item in effects_raw),
            failure_class=_coerce_action_result_failure_class(failure_raw),
            observations=_tuple_of_non_empty_strings(payload.get("observations", ()), field_name="observations"),
            evidence_refs=_tuple_of_non_empty_strings(payload.get("evidence_refs", ()), field_name="evidence_refs"),
            diagnostics=_tuple_of_non_empty_strings(payload.get("diagnostics", ()), field_name="diagnostics"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            **(
                {
                    "temporal_evidence": [
                        item.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
                        for item in self.temporal_evidence
                    ]
                }
                if self.temporal_evidence
                else {}
            ),
            **(
                {"resource_measurements": [item.model_dump(mode="json") for item in self.resource_measurements]}
                if self.resource_measurements
                else {}
            ),
            "participant_address": self.participant_address,
            "episode_id": self.episode_id,
            "action_instance_id": self.action_instance_id,
            "action_contract_address": self.action_contract_address,
            "observation_point": self.observation_point,
            "preconditions": [item.to_payload() for item in self.preconditions],
            "effects": [item.to_payload() for item in self.effects],
            "failure_class": self.failure_class.value if self.failure_class is not None else None,
            "observations": list(self.observations),
            "evidence_refs": list(self.evidence_refs),
            "diagnostics": list(self.diagnostics),
        }

    def __post_init__(self) -> None:
        self._validate_identity_fields()
        self._validate_preconditions_collection()
        self._validate_effects_collection()
        self._validate_failure_class_and_strings()
        self._validate_scope()
        self._validate_fail_closed()

    def _validate_identity_fields(self) -> None:
        if not isinstance(self.resource_measurements, tuple) or any(
            not isinstance(item, ParticipantResourceMeasurementModel) for item in self.resource_measurements
        ):
            raise TypeError("resource_measurements must contain typed resource measurements")
        if len({item.budget_state_ref for item in self.resource_measurements}) != len(self.resource_measurements):
            raise ValueError("resource measurements require unique budget state refs")
        if not isinstance(self.temporal_evidence, tuple) or any(
            not isinstance(item, ParticipantTemporalEvidenceModel) for item in self.temporal_evidence
        ):
            raise TypeError("temporal_evidence must contain typed temporal evidence")
        if not isinstance(self.status, ParticipantActionResultStatus):
            raise TypeError("status must be a ParticipantActionResultStatus")
        _validate_required_string(
            self.participant_address,
            "participant action result participant_address must be a non-empty string",
        )
        _validate_required_string(
            self.episode_id,
            "participant action result episode_id must be a non-empty string",
        )
        _validate_required_string(
            self.action_instance_id,
            "participant action result action_instance_id must be a non-empty string",
        )
        _validate_required_address(
            self.action_contract_address,
            prefix=_PARTICIPANT_ACTION_CONTRACT_PREFIX,
            message="action_contract_address must be a compiled participant action contract address",
        )
        _validate_required_string(
            self.observation_point,
            "observation_point must be a non-empty string",
        )
        if not _observation_point_matches_action_instance(self.observation_point, self.action_instance_id):
            raise ValueError("action result observation_point must be anchored to action_instance_id")

    def _validate_preconditions_collection(self) -> None:
        if not isinstance(self.preconditions, tuple):
            raise TypeError("preconditions must be a tuple")
        if not self.preconditions:
            raise ValueError("participant action results require precondition results")
        if any(not isinstance(item, ParticipantActionPreconditionResult) for item in self.preconditions):
            raise TypeError("preconditions must contain ParticipantActionPreconditionResult values")
        if len({item.precondition_id for item in self.preconditions}) != len(self.preconditions):
            raise ValueError("precondition result ids must be unique")

    def _validate_effects_collection(self) -> None:
        if not isinstance(self.effects, tuple):
            raise TypeError("effects must be a tuple")
        if any(not isinstance(item, ParticipantActionEffectResult) for item in self.effects):
            raise TypeError("effects must contain ParticipantActionEffectResult values")
        if len({item.effect_id for item in self.effects}) != len(self.effects):
            raise ValueError("effect result ids must be unique")

    def _validate_failure_class_and_strings(self) -> None:
        if self.failure_class is not None and not isinstance(self.failure_class, ParticipantFailureClass):
            raise TypeError("failure_class must be a ParticipantFailureClass or None")
        _tuple_of_non_empty_strings(self.observations, field_name="observations")
        _tuple_of_non_empty_strings(self.evidence_refs, field_name="evidence_refs")
        _tuple_of_non_empty_strings(self.diagnostics, field_name="diagnostics")

    def _validate_scope(self) -> None:
        for precondition in self.preconditions:
            if precondition.participant_address != self.participant_address:
                raise ValueError("precondition participant_address must match action result participant_address")
            if precondition.episode_id != self.episode_id:
                raise ValueError("precondition episode_id must match action result episode_id")
            if precondition.action_contract_address != self.action_contract_address:
                raise ValueError(
                    "precondition action_contract_address must match action result action_contract_address"
                )
            if not _observation_point_matches_action_instance(precondition.observation_point, self.action_instance_id):
                raise ValueError("precondition observation_point must be anchored to action result action_instance_id")

    def _validate_fail_closed(self) -> None:
        blocked = [
            item
            for item in self.preconditions
            if item.status
            in {
                ParticipantActionPreconditionStatus.UNSATISFIED,
                ParticipantActionPreconditionStatus.UNRESOLVED,
            }
        ]
        self._validate_blocked_preconditions(blocked)
        self._validate_no_failure_class_for_success()
        self._validate_terminal_effects_present()
        self._validate_failure_status_requires_failure_class()

    def _validate_blocked_preconditions(self, blocked: list[ParticipantActionPreconditionResult]) -> None:
        if blocked and self.status in _PARTICIPANT_ACTION_SUCCESS_STATUSES:
            raise ValueError("unsatisfied or unresolved preconditions fail closed")
        if blocked and self.failure_class is None:
            raise ValueError("unsatisfied or unresolved preconditions require a portable failure_class")

    def _validate_no_failure_class_for_success(self) -> None:
        if self.status == ParticipantActionResultStatus.SUCCEEDED:
            if self.failure_class is not None:
                raise ValueError("succeeded action results may not report failure_class")
        if self.status == ParticipantActionResultStatus.ACCEPTED and self.failure_class is not None:
            raise ValueError("accepted action results may not report failure_class")

    def _validate_terminal_effects_present(self) -> None:
        if self.status in _PARTICIPANT_ACTION_TERMINAL_EFFECT_STATUSES:
            if not self.effects:
                raise ValueError(f"{self.status.value} action results require declared effects")

    def _validate_failure_status_requires_failure_class(self) -> None:
        if self.status in _PARTICIPANT_ACTION_FAILURE_STATUSES and self.failure_class is None:
            raise ValueError(f"{self.status.value} action results require a portable failure_class")
