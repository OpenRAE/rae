"""Participant behavior runtime enums and derived constant tables.

Split out of ``participant_behavior.py`` (file-size governance). The public
enums are re-exported from ``participant_behavior``; importers should continue
to use ``raes_contracts.participant_behavior``.
"""

from __future__ import annotations

from enum import Enum


class ParticipantBehaviorHistoryEventType(str, Enum):
    """Portable history event kinds for participant behavior semantics."""

    ACTION_ATTEMPTED = "action_attempted"
    STATE_TRANSITION_RECORDED = "state_transition_recorded"
    OBSERVATION_EMITTED = "observation_emitted"


class ParticipantObservationStatus(str, Enum):
    """Terminal interpretation of a participant observation event."""

    TERMINAL = "terminal"
    ORPHANED_ACTION = "orphaned_action"


class ParticipantActionPreconditionStatus(str, Enum):
    """Runtime resolution state for one SEM-211 action precondition."""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNRESOLVED = "unresolved"


class ParticipantActionResultStatus(str, Enum):
    """Portable local status for a SEM-211 participant action attempt."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHHELD = "withheld"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"
    UNKNOWN = "unknown"


class ParticipantRuntimeLifecyclePhase(str, Enum):
    """RUN-306 observable participant runtime lifecycle phases."""

    INTENT_OR_PROPOSAL = "intent_or_proposal"
    SELECTION_OR_ADMISSION = "selection_or_admission"
    EXECUTION_ATTEMPT = "execution_attempt"
    OBSERVATION_EMISSION = "observation_emission"
    STATE_UPDATE_COMMIT = "state_update_commit"


class ParticipantPhaseRealization(str, Enum):
    """RUN-306 realization modes for an observable lifecycle phase."""

    OBSERVED = "observed"
    RUNTIME_MEDIATED = "runtime_mediated"
    EXTERNALLY_SUPPLIED = "externally_supplied"
    OPAQUE = "opaque"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class ParticipantAdmissionDisposition(str, Enum):
    """RUN-306 selection/admission disposition values."""

    ADMITTED = "admitted"
    REJECTED = "rejected"
    WITHHELD = "withheld"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ParticipantLifecycleOperationState(str, Enum):
    """RUN-306 operation states for execution-attempt records."""

    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


_PARTICIPANT_BEHAVIOR_HISTORY_KEY = "runtime.snapshot.participant-behavior-history"
_PARTICIPANT_RUNTIME_METADATA_KEY = "runtime.snapshot.metadata"
_RESERVED_RUNTIME_STATE_KEYS = frozenset(
    {
        "participant_episode_results",
        "participant_episode_history",
        "participant_behavior_history",
        "information_state_history",
        "participant_outcome_history",
        "shared_state_records",
        "shared_state_history",
    }
)
_REQUIRED_BEHAVIOR_EVENT_FIELDS = (
    "event_type",
    "timestamp",
    "participant_address",
    "episode_id",
    "action_instance_id",
)
_OPTIONAL_NON_EMPTY_STRING_FIELDS = (
    "action_contract_address",
    "observation_boundary_address",
    "actor_provenance",
    "state_transition_kind",
    "post_state_digest",
    "joint_action_set_id",
    "interaction_ref",
    "operation_ref",
)


def _enum_values(enum_type: type[Enum]) -> frozenset[str]:
    return frozenset(str(item.value) for item in enum_type.__members__.values())


_PARTICIPANT_BEHAVIOR_EVENT_TYPE_VALUES = _enum_values(ParticipantBehaviorHistoryEventType)
_PARTICIPANT_OBSERVATION_STATUS_VALUES = _enum_values(ParticipantObservationStatus)
_PARTICIPANT_RUNTIME_LIFECYCLE_PHASE_VALUES = _enum_values(ParticipantRuntimeLifecyclePhase)
_PARTICIPANT_PHASE_REALIZATION_VALUES = _enum_values(ParticipantPhaseRealization)
_PARTICIPANT_ADMISSION_DISPOSITION_VALUES = _enum_values(ParticipantAdmissionDisposition)
_PARTICIPANT_LIFECYCLE_OPERATION_STATE_VALUES = _enum_values(ParticipantLifecycleOperationState)
_ACTION_ATTEMPTED_LIFECYCLE_PHASE_VALUES = frozenset(
    {
        ParticipantRuntimeLifecyclePhase.INTENT_OR_PROPOSAL.value,
        ParticipantRuntimeLifecyclePhase.SELECTION_OR_ADMISSION.value,
        ParticipantRuntimeLifecyclePhase.EXECUTION_ATTEMPT.value,
    }
)
_LIFECYCLE_ENUM_FIELDS = (
    ("lifecycle_phase", _PARTICIPANT_RUNTIME_LIFECYCLE_PHASE_VALUES),
    ("phase_realization", _PARTICIPANT_PHASE_REALIZATION_VALUES),
    ("admission_disposition", _PARTICIPANT_ADMISSION_DISPOSITION_VALUES),
    ("operation_state", _PARTICIPANT_LIFECYCLE_OPERATION_STATE_VALUES),
)
_LIFECYCLE_PHASE_BY_EVENT_TYPE = {
    ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED.value: _ACTION_ATTEMPTED_LIFECYCLE_PHASE_VALUES,
    ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED.value: frozenset(
        {ParticipantRuntimeLifecyclePhase.STATE_UPDATE_COMMIT.value}
    ),
    ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED.value: frozenset(
        {ParticipantRuntimeLifecyclePhase.OBSERVATION_EMISSION.value}
    ),
}
_LIFECYCLE_PHASE_BY_EVENT_TYPE_MESSAGES = {
    ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED.value: (
        "action_attempted lifecycle_phase must be one of intent_or_proposal, selection_or_admission, execution_attempt"
    ),
    ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED.value: (
        "state_transition_recorded lifecycle_phase must be state_update_commit"
    ),
    ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED.value: (
        "observation_emitted lifecycle_phase must be observation_emission"
    ),
}
