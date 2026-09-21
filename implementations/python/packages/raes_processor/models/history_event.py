"""The resolved participant-behavior history event record."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from raes.participant_attribution_semantics import (
    OUTCOME_ATTRIBUTION_CANDIDATE_KINDS,
    ParticipantAttributionCandidateKind,
)
from raes.participant_behavior import ParticipantInteractionClass
from raes_contracts.contracts.participant_temporal import ParticipantTemporalAssessmentModel
from raes_contracts.participant_behavior import (
    ParticipantActionResultStatus,
    ParticipantAdmissionDisposition,
    ParticipantBehaviorHistoryEventType,
    ParticipantLifecycleOperationState,
    ParticipantObservationStatus,
    ParticipantPhaseRealization,
    ParticipantRuntimeLifecyclePhase,
    participant_lifecycle_field_violation_messages,
)

from .action_results import ParticipantActionResult
from .attribution import ParticipantAttributionEdge
from .behavior_resources import (
    _PARTICIPANT_TERMINAL_OBSERVATION_STATUSES,
    _observation_point_matches_action_instance,
    _optional_payload_string,
    _participant_observation_status_from_payload,
)
from .history_event_grounding import _event_attribution_grounded_refs
from .history_event_payloads import (
    _participant_action_result_from_payload,
    _participant_admission_disposition_from_payload,
    _participant_attribution_edges_from_payload,
    _participant_behavior_details_from_payload,
    _participant_behavior_event_type_from_payload,
    _participant_behavior_shared_state_refs_from_payload,
    _participant_interaction_class_from_payload,
    _participant_lifecycle_operation_state_from_payload,
    _participant_lifecycle_phase_from_payload,
    _participant_phase_realization_from_payload,
    _participant_temporal_contexts_from_payload,
)
from .history_event_serialization import participant_history_event_payload
from .outcome import ParticipantOutcomeInterpretationRecord, _participant_outcome_interpretation_records_from_payload
from .resources import _PARTICIPANT_ACTION_CONTRACT_PREFIX, _PARTICIPANT_OBSERVATION_BOUNDARY_PREFIX
from .temporal import ParticipantTemporalRuntimeContext


@dataclass(frozen=True)
class ParticipantBehaviorHistoryEvent:
    """Internal normalized participant behavior history event.

    The canonical record keeps actor provenance and compiled behavior-contract
    addresses. Role-neutral interpretation is a projection over those records,
    not a reason to treat raw action names or backend-native logs as behavior
    semantics.
    """

    event_type: ParticipantBehaviorHistoryEventType
    timestamp: str
    participant_address: str
    episode_id: str
    action_instance_id: str
    action_contract_address: str | None = None
    observation_boundary_address: str | None = None
    observation_status: ParticipantObservationStatus | None = None
    actor_provenance: str | None = None
    lifecycle_phase: ParticipantRuntimeLifecyclePhase | None = None
    phase_realization: ParticipantPhaseRealization | None = None
    admission_disposition: ParticipantAdmissionDisposition | None = None
    operation_ref: str | None = None
    operation_state: ParticipantLifecycleOperationState | None = None
    state_transition_kind: str | None = None
    post_state_digest: str | None = None
    joint_action_set_id: str | None = None
    realized_order: int | None = None
    interaction_class: ParticipantInteractionClass | None = None
    interaction_ref: str | None = None
    shared_state_refs: tuple[str, ...] = ()
    action_result: ParticipantActionResult | None = None
    attribution_edges: tuple[ParticipantAttributionEdge, ...] = ()
    outcome_interpretations: tuple[ParticipantOutcomeInterpretationRecord, ...] = ()
    temporal_contexts: tuple[ParticipantTemporalRuntimeContext, ...] = ()
    temporal_assessments: tuple[ParticipantTemporalAssessmentModel, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
    ) -> "ParticipantBehaviorHistoryEvent":
        if not isinstance(payload, Mapping):
            raise TypeError("participant behavior history event must be a mapping")
        missing_keys = [
            key
            for key in (
                "event_type",
                "timestamp",
                "participant_address",
                "episode_id",
                "action_instance_id",
            )
            if key not in payload
        ]
        if missing_keys:
            raise ValueError(
                "participant behavior history event is missing required fields: " + ", ".join(missing_keys)
            )
        return cls(
            event_type=_participant_behavior_event_type_from_payload(payload.get("event_type")),
            timestamp=str(payload.get("timestamp")),
            participant_address=str(payload.get("participant_address")),
            episode_id=str(payload.get("episode_id")),
            action_instance_id=str(payload.get("action_instance_id")),
            action_contract_address=_optional_payload_string(payload, "action_contract_address"),
            observation_boundary_address=_optional_payload_string(payload, "observation_boundary_address"),
            observation_status=_participant_observation_status_from_payload(payload.get("observation_status")),
            actor_provenance=_optional_payload_string(payload, "actor_provenance"),
            lifecycle_phase=_participant_lifecycle_phase_from_payload(payload.get("lifecycle_phase")),
            phase_realization=_participant_phase_realization_from_payload(payload.get("phase_realization")),
            admission_disposition=_participant_admission_disposition_from_payload(payload.get("admission_disposition")),
            operation_ref=_optional_payload_string(payload, "operation_ref"),
            operation_state=_participant_lifecycle_operation_state_from_payload(payload.get("operation_state")),
            state_transition_kind=_optional_payload_string(payload, "state_transition_kind"),
            post_state_digest=_optional_payload_string(payload, "post_state_digest"),
            joint_action_set_id=_optional_payload_string(payload, "joint_action_set_id"),
            realized_order=payload.get("realized_order"),
            interaction_class=_participant_interaction_class_from_payload(payload.get("interaction_class")),
            interaction_ref=_optional_payload_string(payload, "interaction_ref"),
            shared_state_refs=_participant_behavior_shared_state_refs_from_payload(
                payload.get("shared_state_refs", ())
            ),
            action_result=_participant_action_result_from_payload(payload.get("action_result")),
            attribution_edges=_participant_attribution_edges_from_payload(payload.get("attribution_edges", ())),
            outcome_interpretations=_participant_outcome_interpretation_records_from_payload(
                payload.get("outcome_interpretations", ())
            ),
            temporal_contexts=_participant_temporal_contexts_from_payload(payload.get("temporal_contexts", ())),
            temporal_assessments=tuple(
                ParticipantTemporalAssessmentModel.model_validate(item)
                for item in payload.get("temporal_assessments", ())
            ),
            details=_participant_behavior_details_from_payload(payload.get("details", {})),
        )

    def to_payload(self) -> dict[str, Any]:
        return participant_history_event_payload(self)

    def __post_init__(self) -> None:
        self._validate_common_fields()
        self._validate_event_type_fields()

    def _validate_common_fields(self) -> None:
        if not isinstance(self.event_type, ParticipantBehaviorHistoryEventType):
            raise TypeError("event_type must be a ParticipantBehaviorHistoryEventType")
        self._validate_required_string(self.timestamp, "participant behavior timestamp must be a non-empty string")
        self._validate_required_string(
            self.participant_address,
            "participant behavior participant_address must be a non-empty string",
        )
        self._validate_required_string(self.episode_id, "participant behavior episode_id must be a non-empty string")
        self._validate_required_string(self.action_instance_id, "action_instance_id must be a non-empty string")
        self._validate_optional_address(
            self.action_contract_address,
            prefix=_PARTICIPANT_ACTION_CONTRACT_PREFIX,
            message="action_contract_address must be a compiled participant action contract address",
        )
        self._validate_optional_address(
            self.observation_boundary_address,
            prefix=_PARTICIPANT_OBSERVATION_BOUNDARY_PREFIX,
            message="observation_boundary_address must be a compiled participant observation boundary address",
        )
        if self.observation_status is not None and not isinstance(
            self.observation_status,
            ParticipantObservationStatus,
        ):
            raise TypeError("observation_status must be a ParticipantObservationStatus or None")
        self._validate_optional_string(self.actor_provenance, "actor_provenance must be a non-empty string or None")
        self._validate_lifecycle_fields()
        self._validate_optional_state_fields()
        self._validate_realized_order()
        self._validate_interaction_type()
        if not isinstance(self.shared_state_refs, tuple):
            raise TypeError("shared_state_refs must be a tuple")
        for ref in self.shared_state_refs:
            self._validate_required_string(ref, "shared_state_refs entries must be non-empty strings")
        if len(set(self.shared_state_refs)) != len(self.shared_state_refs):
            raise ValueError("shared_state_refs entries must be unique")
        self._validate_interaction_fields()
        self._validate_action_result_type()
        self._validate_attribution_edge_types()
        self._validate_outcome_interpretation_types()
        self._validate_temporal_context_types()
        if not isinstance(self.details, dict):
            raise TypeError("participant behavior details must be a dict")

    def _validate_optional_state_fields(self) -> None:
        self._validate_optional_string(
            self.state_transition_kind,
            "state_transition_kind must be a non-empty string or None",
        )
        self._validate_optional_string(self.post_state_digest, "post_state_digest must be a non-empty string or None")
        self._validate_optional_string(
            self.joint_action_set_id,
            "joint_action_set_id must be a non-empty string or None",
        )

    def _validate_lifecycle_fields(self) -> None:
        self._validate_lifecycle_enum_types()
        self._validate_optional_string(self.operation_ref, "operation_ref must be a non-empty string or None")
        messages = participant_lifecycle_field_violation_messages(
            event_type=self.event_type,
            lifecycle_phase=self.lifecycle_phase,
            phase_realization=self.phase_realization,
            admission_disposition=self.admission_disposition,
            operation_ref=self.operation_ref,
            operation_state=self.operation_state,
        )
        if messages:
            raise ValueError(messages[0])

    def _validate_lifecycle_enum_types(self) -> None:
        expectations = (
            (
                self.lifecycle_phase,
                ParticipantRuntimeLifecyclePhase,
                "lifecycle_phase must be a ParticipantRuntimeLifecyclePhase or None",
            ),
            (
                self.phase_realization,
                ParticipantPhaseRealization,
                "phase_realization must be a ParticipantPhaseRealization or None",
            ),
            (
                self.admission_disposition,
                ParticipantAdmissionDisposition,
                "admission_disposition must be a ParticipantAdmissionDisposition or None",
            ),
            (
                self.operation_state,
                ParticipantLifecycleOperationState,
                "operation_state must be a ParticipantLifecycleOperationState or None",
            ),
        )
        for value, enum_type, message in expectations:
            if value is not None and not isinstance(value, enum_type):
                raise TypeError(message)

    def _validate_realized_order(self) -> None:
        if self.realized_order is not None and (
            not isinstance(self.realized_order, int) or isinstance(self.realized_order, bool) or self.realized_order < 0
        ):
            raise TypeError("realized_order must be a non-negative integer or None")

    def _validate_interaction_type(self) -> None:
        if self.interaction_class is not None and not isinstance(self.interaction_class, ParticipantInteractionClass):
            raise TypeError("interaction_class must be a ParticipantInteractionClass or None")
        self._validate_optional_string(self.interaction_ref, "interaction_ref must be a non-empty string or None")

    def _validate_action_result_type(self) -> None:
        if self.action_result is not None and not isinstance(self.action_result, ParticipantActionResult):
            raise TypeError("action_result must be a ParticipantActionResult or None")

    def _validate_attribution_edge_types(self) -> None:
        if not isinstance(self.attribution_edges, tuple):
            raise TypeError("attribution_edges must be a tuple")
        if any(not isinstance(edge, ParticipantAttributionEdge) for edge in self.attribution_edges):
            raise TypeError("attribution_edges must contain ParticipantAttributionEdge values")
        if len({edge.edge_id for edge in self.attribution_edges}) != len(self.attribution_edges):
            raise ValueError("participant attribution edge_id values must be unique per event")
        if self.attribution_edges and self.event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
            raise ValueError("participant attribution edges are only allowed on observation_emitted events")

    def _validate_outcome_interpretation_types(self) -> None:
        if not isinstance(self.outcome_interpretations, tuple):
            raise TypeError("outcome_interpretations must be a tuple")
        if any(
            not isinstance(record, ParticipantOutcomeInterpretationRecord) for record in self.outcome_interpretations
        ):
            raise TypeError("outcome_interpretations must contain ParticipantOutcomeInterpretationRecord values")
        if len({record.interpretation_id for record in self.outcome_interpretations}) != len(
            self.outcome_interpretations
        ):
            raise ValueError("participant outcome interpretation_id values must be unique per event")
        if self.outcome_interpretations and self.event_type != ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED:
            raise ValueError("participant outcome interpretations are only allowed on observation_emitted events")

    def _validate_temporal_context_types(self) -> None:
        if not isinstance(self.temporal_assessments, tuple) or any(
            not isinstance(item, ParticipantTemporalAssessmentModel) for item in self.temporal_assessments
        ):
            raise TypeError("temporal_assessments must contain typed temporal assessments")
        if not isinstance(self.temporal_contexts, tuple):
            raise TypeError("temporal_contexts must be a tuple")
        if any(not isinstance(context, ParticipantTemporalRuntimeContext) for context in self.temporal_contexts):
            raise TypeError("temporal_contexts must contain ParticipantTemporalRuntimeContext values")
        if len({context.temporal_contract_id for context in self.temporal_contexts}) != len(self.temporal_contexts):
            raise ValueError("participant temporal_contract_id values must be unique per event")

    @staticmethod
    def _validate_required_string(value: object, message: str) -> None:
        if not isinstance(value, str) or not value:
            raise TypeError(message)

    @staticmethod
    def _validate_optional_string(value: object, message: str) -> None:
        if value is not None and (not isinstance(value, str) or not value):
            raise TypeError(message)

    @staticmethod
    def _validate_optional_address(value: str | None, *, prefix: str, message: str) -> None:
        if value is not None and (not isinstance(value, str) or not value.startswith(prefix)):
            raise ValueError(message)

    def _validate_event_type_fields(self) -> None:
        validators = {
            ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED: self._validate_action_attempted_fields,
            ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED: self._validate_state_transition_fields,
            ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED: self._validate_observation_emitted_fields,
        }
        validators[self.event_type]()

    def _validate_interaction_fields(self) -> None:
        self._validate_joint_action_pairing(self.joint_action_set_id, self.realized_order)
        self._validate_interaction_class_consistency(
            self.interaction_class,
            self.interaction_ref,
            self.joint_action_set_id,
            self.shared_state_refs,
        )

    @staticmethod
    def _validate_joint_action_pairing(joint_action_set_id: str | None, realized_order: int | None) -> None:
        if joint_action_set_id is None and realized_order is not None:
            raise ValueError("realized_order requires joint_action_set_id")
        if joint_action_set_id is not None and realized_order is None:
            raise ValueError("joint_action_set_id requires realized_order")

    @staticmethod
    def _validate_interaction_class_consistency(
        interaction_class: ParticipantInteractionClass | None,
        interaction_ref: str | None,
        joint_action_set_id: str | None,
        shared_state_refs: tuple[str, ...],
    ) -> None:
        if interaction_class is None:
            if interaction_ref is not None:
                raise ValueError("interaction_ref requires interaction_class")
            return
        if joint_action_set_id is None:
            raise ValueError("interaction_class requires joint_action_set_id and realized_order")
        if (
            interaction_class
            in {
                ParticipantInteractionClass.COORDINATION,
                ParticipantInteractionClass.INTERFERENCE,
            }
            and interaction_ref is None
        ):
            raise ValueError(f"{interaction_class.value} events require interaction_ref")
        if (
            interaction_class
            in {
                ParticipantInteractionClass.CONTENTION,
                ParticipantInteractionClass.SHARED_STATE_CHANGE,
            }
            and not shared_state_refs
        ):
            raise ValueError(f"{interaction_class.value} events require shared_state_refs")

    def _validate_action_attempted_fields(self) -> None:
        if self.action_contract_address is None:
            raise ValueError("action_attempted events require action_contract_address")
        if self.actor_provenance is None:
            raise ValueError("action_attempted events require actor_provenance")
        if self.observation_boundary_address is not None or self.observation_status is not None:
            raise ValueError("action_attempted events may not report observation fields")
        if self.state_transition_kind is not None or self.post_state_digest is not None:
            raise ValueError("action_attempted events may not report state-transition fields")
        if self.action_result is not None:
            raise ValueError("action_attempted events may not report action_result")

    def _validate_state_transition_fields(self) -> None:
        if self.action_contract_address is None:
            raise ValueError("state_transition_recorded events require action_contract_address")
        if self.state_transition_kind is None:
            raise ValueError("state_transition_recorded events require state_transition_kind")
        if self.post_state_digest is None:
            raise ValueError("state_transition_recorded events require post_state_digest")
        if self.observation_boundary_address is not None or self.observation_status is not None:
            raise ValueError("state_transition_recorded events may not report observation fields")
        if self.action_result is not None:
            raise ValueError("state_transition_recorded events may not report action_result")

    def _validate_observation_emitted_fields(self) -> None:
        if self.action_contract_address is None:
            raise ValueError("observation_emitted events require action_contract_address")
        if self.observation_boundary_address is None:
            raise ValueError("observation_emitted events require observation_boundary_address")
        if self.observation_status is None:
            raise ValueError("observation_emitted events require observation_status")
        if self.observation_status == ParticipantObservationStatus.TERMINAL and self.post_state_digest is None:
            raise ValueError("terminal observation_emitted events require post_state_digest")
        if self.state_transition_kind is not None:
            raise ValueError("observation_emitted events may not report state_transition_kind")
        if self.action_result is not None:
            self._validate_action_result_scope()
        self._validate_attribution_edges()
        self._validate_outcome_interpretations()

    def _validate_action_result_scope(self) -> None:
        if self.action_result is None:
            return
        if self.action_result.participant_address != self.participant_address:
            raise ValueError("action_result participant_address must match event participant_address")
        if self.action_result.episode_id != self.episode_id:
            raise ValueError("action_result episode_id must match event episode_id")
        if self.action_result.action_instance_id != self.action_instance_id:
            raise ValueError("action_result action_instance_id must match event action_instance_id")
        if self.action_result.action_contract_address != self.action_contract_address:
            raise ValueError("action_result action_contract_address must match event action_contract_address")
        if (
            self.observation_status in _PARTICIPANT_TERMINAL_OBSERVATION_STATUSES
            and self.action_result.status == ParticipantActionResultStatus.ACCEPTED
        ):
            raise ValueError("terminal observation action_result must report a terminal status")

    def _validate_attribution_edges(self) -> None:
        for edge in self.attribution_edges:
            if edge.participant_address != self.participant_address:
                raise ValueError("attribution edge participant_address must match event participant_address")
            if edge.episode_id != self.episode_id:
                raise ValueError("attribution edge episode_id must match event episode_id")
            if self.action_result is not None:
                if edge.observation_point != self.action_result.observation_point:
                    raise ValueError("attribution edge observation_point must match action_result observation_point")
            elif not _observation_point_matches_action_instance(edge.observation_point, self.action_instance_id):
                raise ValueError("attribution edge observation_point must be anchored to action_instance_id")
            self._validate_attribution_candidate_grounding(edge)

    def _validate_outcome_interpretations(self) -> None:
        for record in self.outcome_interpretations:
            if record.participant_address != self.participant_address:
                raise ValueError("outcome interpretation participant_address must match event participant_address")
            if record.episode_id != self.episode_id:
                raise ValueError("outcome interpretation episode_id must match event episode_id")
            if self.action_result is not None:
                if record.observation_point != self.action_result.observation_point:
                    raise ValueError(
                        "outcome interpretation observation_point must match action_result observation_point"
                    )
            elif not _observation_point_matches_action_instance(record.observation_point, self.action_instance_id):
                raise ValueError("outcome interpretation observation_point must be anchored to action_instance_id")

    def _validate_attribution_candidate_grounding(self, edge: ParticipantAttributionEdge) -> None:
        allowed_action_refs = {self.action_instance_id}
        if self.action_contract_address is not None:
            allowed_action_refs.add(self.action_contract_address)
        if edge.cause_candidate.candidate_kind == ParticipantAttributionCandidateKind.ACTION:
            if edge.cause_candidate.ref not in allowed_action_refs:
                raise ValueError("attribution edge action cause_candidate must match the event action")
        elif edge.cause_candidate.ref not in self._attribution_grounded_refs():
            raise ValueError(f"attribution edge cause_candidate {edge.cause_candidate.ref!r} is not grounded")

        if edge.effect_candidate.candidate_kind in OUTCOME_ATTRIBUTION_CANDIDATE_KINDS:
            return
        if edge.effect_candidate.ref not in self._attribution_grounded_refs():
            raise ValueError(f"attribution edge effect_candidate {edge.effect_candidate.ref!r} is not grounded")

    def _attribution_grounded_refs(self) -> set[str]:
        return _event_attribution_grounded_refs(self)
