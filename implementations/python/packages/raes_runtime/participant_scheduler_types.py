"""Shared mutable and immutable state for autonomous scheduler operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_contracts.timestamps import WallClock, utc_now
from raes_processor.models import CompiledTimeModel, ParticipantAutonomousExecutionRuntime

from .participant_activity import ParticipantActivityRandomControl

if TYPE_CHECKING:
    from .participant_invocation_tool_actions import (
        InvocationToolActionConfiguration,
        ParticipantInvocationToolActions,
    )


@dataclass
class SchedulerRunState:
    """Mutable aggregate for one deterministic scheduler pass."""

    working: RuntimeSnapshot
    diagnostics: list[Diagnostic]
    changed: list[str]
    failure: ApplyResult | None = None
    invocation_tools: InvocationToolActionConfiguration | None = None
    tool_sessions: list[ParticipantInvocationToolActions] = field(default_factory=list)
    deferred_cancellation: BaseException | None = None
    wall_clock: WallClock = utc_now

    def result(self) -> ApplyResult:
        return self.failure or ApplyResult(
            success=True,
            snapshot=self.working,
            diagnostics=self.diagnostics,
            changed_addresses=list(dict.fromkeys(self.changed)),
        )


@dataclass(frozen=True)
class _DueActionContext:
    policy: ParticipantAutonomousExecutionRuntime
    time_model: CompiledTimeModel
    participant_runtime: object
    participant_address: str
    key: str
    current_tick: int
    cadence_ticks: int
    activity_control: ParticipantActivityRandomControl | None = None
