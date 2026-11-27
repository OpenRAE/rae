"""Issue #1740 protocols for tool actions hosted by an active autonomous invocation."""

from __future__ import annotations

from typing import Protocol

from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.participant_tool_actions import (
    ParticipantToolActionDecision,
    ParticipantToolActionReceipt,
    ParticipantToolActionRequest,
)

from .protocols import AutonomousParticipantRuntime


class ParticipantInvocationToolActionPort(Protocol):
    """Runtime-owned admission port for the tool actions of one autonomous invocation.

    The runtime issues one port for each outer invocation and closes it before
    the outer result is settled. Every method is thread-safe and never calls
    back into the runtime manager, so a harness can use the port from any
    thread while the outer ``admit_action`` call waits.
    """

    @property
    def invocation_action_instance_id(self) -> str: ...

    @property
    def participant_address(self) -> str: ...

    @property
    def episode_id(self) -> str: ...

    @property
    def participant_implementation_ref(self) -> str: ...

    @property
    def execution_scope_ref(self) -> str: ...

    @property
    def execution_generation(self) -> int: ...

    @property
    def observation_point(self) -> str: ...

    @property
    def closed(self) -> bool: ...

    def admit(self, request: ParticipantToolActionRequest) -> ParticipantToolActionDecision:
        """Admit or refuse one exact tool binding before any tool effect."""
        ...

    def dispatch(self, action_instance_id: str) -> ParticipantToolActionReceipt:
        """Consume the one-use dispatch grant; start tool effects only when accepted."""
        ...

    def complete(
        self,
        action_instance_id: str,
        outcome: ParticipantActionResultModel,
    ) -> ParticipantToolActionReceipt:
        """Record the terminal typed outcome of one dispatched tool action."""
        ...

    def cancel(self, action_instance_id: str) -> ParticipantToolActionReceipt:
        """Withhold an admitted tool action before dispatch."""
        ...

    def report_unknown(self, action_instance_id: str, failure_class: str) -> ParticipantToolActionReceipt:
        """Record that a dispatched tool action has unknown native effects."""
        ...


class InvocationToolActionParticipantRuntime(AutonomousParticipantRuntime, Protocol):
    """Autonomous runtime that hosts tool actions inside an active invocation."""

    def attach_invocation_tool_actions(self, port: ParticipantInvocationToolActionPort) -> None:
        """Receive the port for the invocation named by ``port.invocation_action_instance_id``.

        The runtime calls this before the matching ``admit_action`` call. The
        participant runtime gives the port only to the harness that runs that
        invocation and must drop it after the invocation returns.
        """
        ...


__all__ = (
    "InvocationToolActionParticipantRuntime",
    "ParticipantInvocationToolActionPort",
)
