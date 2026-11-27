"""Executable protocol for an admitted delivery invocation."""

from typing import Protocol

from raes_contracts.contracts.participant_crossing_evidence import ParticipantCrossingEvidence
from raes_contracts.contracts.participant_delivery_invocation import (
    ParticipantDeliveryInvocationContextModel,
    ParticipantDeliveryInvocationOutcomeModel,
)
from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel
from raes_contracts.participant_tool_actions import (
    ParticipantToolActionDecision,
    ParticipantToolActionReceipt,
    ParticipantToolActionRequest,
)

from .participant_invocation_tools import ParticipantInvocationToolActionPort


class ParticipantDeliveryToolActionPort(ParticipantInvocationToolActionPort, Protocol):
    def admit(
        self,
        request: ParticipantToolActionRequest,
        *,
        crossing_evidence: ParticipantCrossingEvidence | None = None,
    ) -> ParticipantToolActionDecision:
        """Admit the exact relation and evidence through the current policy gates."""
        ...

    def dispatch(
        self,
        action_instance_id: str,
        *,
        temporal_evidence: tuple[ParticipantTemporalEvidenceModel, ...] = (),
    ) -> ParticipantToolActionReceipt:
        """Recheck current authority and time before issuing a one-use grant."""
        ...


class ParticipantDeliveryInvocationRuntime(Protocol):
    def invoke_delivery(
        self, invocation: ParticipantDeliveryInvocationContextModel, tools: ParticipantDeliveryToolActionPort
    ) -> ParticipantDeliveryInvocationOutcomeModel:
        """Execute once; tool effects require the port's independent dispatch grant."""
        ...
