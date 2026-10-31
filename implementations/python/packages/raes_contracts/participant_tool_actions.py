"""Issue #1740 carriers for tool actions hosted by an active autonomous invocation.

A tool action is a separate participant action of the participant that runs the
enclosing invocation. These carriers cross the participant-runtime boundary;
every value in a request or outcome is untrusted until the runtime port admits it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from raes_contracts.contracts.participant_runtime import (
    ParticipantActionResultModel,
    ParticipantBehaviorHistoryEventModel,
    ParticipantInvocationToolContextModel,
    ParticipantObservationDetailsModel,
)

from .contracts import participant_binding_validation as _binding_validation
from .contracts.participant_invocation_tools import INVOCATION_TOOL_ACTIONS_SEMANTICS
from .digests import sha256_digest, sha256_hex
from .participant_behavior import (
    ParticipantAdmissionDisposition,
    ParticipantBehaviorHistoryEventType,
    ParticipantObservationStatus,
    ParticipantPhaseRealization,
    ParticipantRuntimeLifecyclePhase,
)
from .participant_binding_events import participant_implementation_actor_provenance

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest

_TOOL_CALL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TOOL_ACTION_ID_PREFIX = "participant-tool-action-"


class ParticipantToolActionRefusal(StrEnum):
    """Fixed, value-free reasons a port refuses a tool-action operation."""

    INVOCATION_INACTIVE = "invocation_inactive"
    INVOCATION_CLOSED = "invocation_closed"
    INVOCATION_MISMATCH = "invocation_mismatch"
    BINDING_UNKNOWN = "binding_unknown"
    BINDING_AMBIGUOUS = "binding_ambiguous"
    OBSERVATION_BOUNDARY_UNBOUND = "observation_boundary_unbound"
    TARGET_UNBOUND = "target_unbound"
    TEMPORAL_BINDING_UNSUPPORTED = "temporal_binding_unsupported"
    EXECUTION_OFFER_MISSING = "execution_offer_missing"
    EXECUTION_OFFER_AMBIGUOUS = "execution_offer_ambiguous"
    RESOURCE_GOVERNANCE_UNSUPPORTED = "resource_governance_unsupported"
    CROSSING_MEDIATION_UNSUPPORTED = "crossing_mediation_unsupported"
    LEDGER_UNAVAILABLE = "ledger_unavailable"
    EFFECT_ADMISSION_CLOSED = "effect_admission_closed"
    UNRESOLVED_EFFECTS = "unresolved_effects"
    SEMANTIC_CONFLICT = "semantic_conflict"
    ADMISSION_LIMIT_EXHAUSTED = "admission_limit_exhausted"
    CONCURRENCY_LIMIT_EXHAUSTED = "concurrency_limit_exhausted"
    REQUEST_CONFLICT = "request_conflict"
    ACTION_UNKNOWN = "action_unknown"
    STATE_CONFLICT = "state_conflict"
    OUTCOME_INVALID = "outcome_invalid"
    OUTCOME_CONFLICT = "outcome_conflict"


class ParticipantToolActionSettlement(StrEnum):
    """How an admitted tool action ended."""

    COMPLETED = "completed"
    WITHHELD = "withheld"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True)
class ParticipantToolActionRequest:
    """One exact participant/tool-to-action binding submitted before tool effects."""

    tool_call_id: str
    invocation_action_instance_id: str
    participant_address: str
    episode_id: str
    participant_implementation_ref: str
    tool_affordance_address: str
    action_contract_address: str
    observation_boundary_address: str
    target_addresses: tuple[str, ...]
    execution_scope_ref: str
    execution_generation: int

    def __post_init__(self) -> None:
        _require_tool_call_id(self.tool_call_id)
        for field_name in _REQUEST_TEXT_FIELDS:
            _binding_validation.require_non_empty(getattr(self, field_name), field_name)
        _require_targets(self.target_addresses)
        _require_generation(self.execution_generation)


_REQUEST_TEXT_FIELDS = (
    "invocation_action_instance_id",
    "participant_address",
    "episode_id",
    "participant_implementation_ref",
    "tool_affordance_address",
    "action_contract_address",
    "observation_boundary_address",
    "execution_scope_ref",
)


def _require_tool_call_id(tool_call_id: object) -> None:
    if not isinstance(tool_call_id, str) or _TOOL_CALL_ID.fullmatch(tool_call_id) is None:
        raise ValueError("tool_call_id must be 1-128 characters of [A-Za-z0-9._:-] starting alphanumeric")


def _require_targets(targets: object) -> None:
    if not isinstance(targets, tuple) or any(not isinstance(target, str) or not target for target in targets):
        raise TypeError("target_addresses must be a tuple of non-empty strings")
    if not targets or len(targets) != len(set(targets)):
        raise ValueError("target_addresses must be non-empty and unique")


def _require_generation(generation: object) -> None:
    if type(generation) is not int:
        raise TypeError("execution_generation must be an int")
    if generation < 0:
        raise ValueError("execution_generation must be non-negative")


@dataclass(frozen=True)
class ParticipantToolActionDecision:
    """Admission decision for one tool request; refused decisions carry no action id."""

    tool_call_id: str
    admitted: bool
    action_instance_id: str | None = None
    refusal: ParticipantToolActionRefusal | None = None


@dataclass(frozen=True)
class ParticipantToolActionReceipt:
    """Result of dispatch, completion, cancellation or unknown-effect reporting."""

    action_instance_id: str
    accepted: bool
    refusal: ParticipantToolActionRefusal | None = None
    settlement: ParticipantToolActionSettlement | None = None


def tool_action_instance_id(
    invocation_action_instance_id: str,
    *,
    episode_id: str,
    execution_generation: int,
    tool_call_id: str,
) -> str:
    """Derive the runtime-issued identity of one tool call inside one invocation.

    Episode and generation take part because an outer action identity can repeat
    after a shared-clock reset; a durable child identity must not.
    """

    identity = "\0".join((invocation_action_instance_id, episode_id, str(execution_generation), tool_call_id)).encode()
    return TOOL_ACTION_ID_PREFIX + sha256_hex(identity)


@dataclass(frozen=True)
class ParticipantToolActionRecord:
    """Settled tool action ready for portable history."""

    request: ParticipantToolActionRequest
    action_instance_id: str
    admission_ordinal: int
    settlement: ParticipantToolActionSettlement
    action_result: ParticipantActionResultModel
    admitted_at: str
    settled_at: str


def participant_tool_action_events(
    outer: ParticipantActionAdmissionRequest,
    record: ParticipantToolActionRecord,
) -> tuple[ParticipantBehaviorHistoryEventModel, ...]:
    """Build the ordered three-event history of one settled tool action."""

    request = record.request
    context = ParticipantInvocationToolContextModel(
        semantics=INVOCATION_TOOL_ACTIONS_SEMANTICS,
        invocation_action_instance_id=outer.action_instance_id,
        invocation_action_contract_address=outer.action_contract_address,
        tool_affordance_address=request.tool_affordance_address,
        tool_call_id=request.tool_call_id,
        admission_ordinal=record.admission_ordinal,
        settlement=record.settlement.value,
        execution_scope_ref=request.execution_scope_ref,
        execution_generation=request.execution_generation,
    )
    temporal_contexts = [
        context_model for context_model in outer.temporal_contexts if context_model.shared_time is None
    ]
    post_state_digest = sha256_digest(
        f"{record.action_instance_id}\0{record.settlement.value}\0{record.action_result.status}".encode()
    )
    common = {
        "participant_address": request.participant_address,
        "episode_id": request.episode_id,
        "action_instance_id": record.action_instance_id,
        "action_contract_address": request.action_contract_address,
        "phase_realization": ParticipantPhaseRealization.RUNTIME_MEDIATED,
        "temporal_contexts": temporal_contexts,
        "invocation_tool_context": context,
    }
    observation_status = (
        ParticipantObservationStatus.ORPHANED_ACTION
        if record.settlement is ParticipantToolActionSettlement.INDETERMINATE
        else ParticipantObservationStatus.TERMINAL
    )
    return (
        ParticipantBehaviorHistoryEventModel(
            event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
            timestamp=record.admitted_at,
            actor_provenance=participant_implementation_actor_provenance(outer.implementation_selection),
            lifecycle_phase=ParticipantRuntimeLifecyclePhase.SELECTION_OR_ADMISSION,
            admission_disposition=ParticipantAdmissionDisposition.ADMITTED,
            **common,
        ),
        ParticipantBehaviorHistoryEventModel(
            event_type=ParticipantBehaviorHistoryEventType.STATE_TRANSITION_RECORDED,
            timestamp=record.settled_at,
            lifecycle_phase=ParticipantRuntimeLifecyclePhase.STATE_UPDATE_COMMIT,
            state_transition_kind="participant_tool_action_settled",
            post_state_digest=post_state_digest,
            **common,
        ),
        ParticipantBehaviorHistoryEventModel(
            event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
            timestamp=record.settled_at,
            observation_boundary_address=request.observation_boundary_address,
            observation_status=observation_status,
            lifecycle_phase=ParticipantRuntimeLifecyclePhase.OBSERVATION_EMISSION,
            post_state_digest=post_state_digest,
            action_result=record.action_result,
            details=ParticipantObservationDetailsModel(evidence_refs=list(record.action_result.evidence_refs)),
            **common,
        ),
    )


__all__ = (
    "INVOCATION_TOOL_ACTIONS_SEMANTICS",
    "TOOL_ACTION_ID_PREFIX",
    "ParticipantToolActionDecision",
    "ParticipantToolActionReceipt",
    "ParticipantToolActionRecord",
    "ParticipantToolActionRefusal",
    "ParticipantToolActionRequest",
    "ParticipantToolActionSettlement",
    "participant_tool_action_events",
    "tool_action_instance_id",
)
