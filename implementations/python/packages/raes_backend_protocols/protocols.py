"""Runtime execution protocols."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from raes_contracts.contracts import (
    ParticipantTemporalRuntimeContextModel,
)
from raes_contracts.contracts.participant_execution import (
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.domain_profiles import DomainProfileResolutionContextModel
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest, ParticipantActionApplyResult
from raes_contracts.participant_episode import (
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeResetRequest,
    ParticipantEpisodeRestartRequest,
    ParticipantEpisodeTerminateRequest,
)
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
from raes_contracts.realization_preparation import RealizationPreparation
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

if TYPE_CHECKING:
    from raes_contracts.contracts.time_model import TimeModelDeclarationModel, TimeRuntimeStateModel


class Provisioner(Protocol):
    """Applies provisioning plans to the target environment."""

    def validate(self, plan: ProvisioningPlan) -> list[Diagnostic]:
        """Return planner/runtime diagnostics for an apply attempt."""
        ...

    def apply(
        self,
        plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Apply provisioning reconciliation operations."""
        ...


class PreparingProvisioner(Provisioner, Protocol):
    """Opt-in read-only joint selection before ordinary provisioning apply."""

    def prepare(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> RealizationPreparation:
        """Select one supported completion without mutating resources or collecting evidence."""
        ...


class ProfilePreparingProvisioner(PreparingProvisioner, Protocol):
    """Explicitly negotiated, installed profile semantics over selected plans."""

    domain_profile_context: DomainProfileResolutionContextModel

    def validate_profiles(self, plan: ProvisioningPlan) -> list[Diagnostic]:
        """Read-only semantic validation of the full core/profile conjunction."""
        ...


class Orchestrator(Protocol):
    """Loads and starts the orchestration graph."""

    def start(
        self,
        plan: OrchestrationPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Start or refresh orchestration state."""
        ...

    def status(self) -> dict[str, object]:
        """Return current orchestration status."""
        ...

    def results(self) -> dict[str, dict[str, object]]:
        """Return most recent workflow execution state envelope."""
        ...

    def history(self) -> dict[str, list[dict[str, object]]]:
        """Return workflow execution history events."""
        ...

    def stop(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Stop orchestration and clear orchestration state."""
        ...


class Evaluator(Protocol):
    """Loads and starts the evaluation graph."""

    def start(
        self,
        plan: EvaluationPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Start or refresh evaluation state."""
        ...

    def status(self) -> dict[str, object]:
        """Return current evaluator status."""
        ...

    def results(self) -> dict[str, dict[str, object]]:
        """Return most recent evaluation results."""
        ...

    def history(self) -> dict[str, list[dict[str, object]]]:
        """Return evaluation history events."""
        ...

    def stop(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Stop evaluation and clear evaluation state."""
        ...


class ParticipantRuntime(Protocol):
    """Drives participant episode lifecycle transitions (RUN-311).

    The four control methods map 1:1 to the ``ParticipantEpisodeControlAction``
    enum. Each method is idempotent from the caller's perspective — the
    control plane routes duplicate submissions through its idempotency
    record store before reaching the backend. The backend is responsible
    for mutating ``RuntimeSnapshot.participant_episode_results`` and
    ``RuntimeSnapshot.participant_episode_history`` in a way that stays
    consistent with the RUN-311 invariants enforced by
    ``iter_participant_episode_snapshot_violations``.
    """

    def initialize(
        self,
        request: ParticipantEpisodeInitializeRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Create the first episode for a participant (sequence_number=0)."""
        ...

    def reset(
        self,
        request: ParticipantEpisodeResetRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Start a new episode instance from a non-terminal predecessor.

        Must allocate a new ``episode_id`` and increment
        ``sequence_number``, preserving the stable participant identity and
        linking back to the prior ``episode_id`` via ``previous_episode_id``.
        """
        ...

    def restart(
        self,
        request: ParticipantEpisodeRestartRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Start a new episode instance from a terminated predecessor.

        Must allocate a new ``episode_id`` and increment
        ``sequence_number``, preserving the stable participant identity and
        linking back to the prior ``episode_id`` via ``previous_episode_id``.
        """
        ...

    def terminate(
        self,
        request: ParticipantEpisodeTerminateRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Drive the current episode to ``TERMINATED`` with the given reason."""
        ...

    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Admit one implementation-bound participant action attempt."""
        ...

    def status(self) -> dict[str, object]:
        """Return current participant runtime status."""
        ...

    def results(self) -> dict[str, dict[str, object]]:
        """Return the most recent participant episode result envelopes."""
        ...

    def history(self) -> dict[str, list[dict[str, object]]]:
        """Return participant episode history events."""
        ...


class AutonomousParticipantRuntime(ParticipantRuntime, Protocol):
    """Participant runtime that can bind and execute autonomous policy actions."""

    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult:
        """Execute one autonomous action and commit its typed terminal observation."""
        ...

    def bind_autonomous_action(
        self,
        participant_address: str,
        action_contract_address: str,
        observation_boundary_address: str,
        participant_implementation_ref: str,
        action_instance_id: str,
        temporal_contexts: tuple[ParticipantTemporalRuntimeContextModel, ...],
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionAdmissionRequest:
        """Resolve run-selected apparatus and native target binding for one due action."""
        ...


class ControlledAutonomousParticipantRuntime(AutonomousParticipantRuntime, Protocol):
    """Autonomous runtime with portable lifecycle, readback, and bounded overlap."""

    def control_execution(
        self,
        request: ParticipantExecutionControlRequestModel,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Perform and observe one generation-fenced native lifecycle operation.

        Implementations own scheduler and shared-time coordination for the
        scope. Merely editing portable readback fields is non-conformant.
        """
        ...

    def execution_state(
        self,
        execution_scope_ref: str,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantExecutionServiceStateModel:
        """Return typed execution-service health and readiness."""
        ...

    def admit_actions_concurrently(
        self,
        requests: tuple[ParticipantActionAdmissionRequest, ...],
        snapshot: RuntimeSnapshot,
        max_workers: int,
    ) -> tuple[ParticipantActionApplyResult, ...]:
        """Execute native actions with a finite overlap bound."""
        ...


class TimeRuntime(Protocol):
    """Materializes and controls one admitted portable shared-time model."""

    def initialize(
        self,
        declaration: TimeModelDeclarationModel,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Materialize clock authorities and publish typed initial readback."""
        ...

    def advance(
        self,
        clock_address: str,
        ticks: int,
        microstep: int,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Advance one admitted clock exactly."""
        ...

    def pause(self, clock_address: str, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Pause one admitted clock."""
        ...

    def resume(self, clock_address: str, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Resume one admitted clock."""
        ...

    def jump(
        self,
        clock_address: str,
        tick: int,
        microstep: int,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Apply one declared discontinuity."""
        ...

    def reset(
        self,
        clock_address: str,
        replay: bool,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Apply declared reset or replay semantics."""
        ...

    def state(self, snapshot: RuntimeSnapshot) -> TimeRuntimeStateModel:
        """Return typed clock state bound to the admitted declaration digest."""
        ...


class CoordinatedParticipantResetRuntime(ParticipantRuntime, Protocol):
    """Participant runtime capable of one atomic multi-participant reset."""

    def reset_many(
        self,
        requests: tuple[ParticipantEpisodeResetRequest, ...],
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Reset every requested participant or leave all native state unchanged."""
        ...


class CoordinatedParticipantTimeRuntime(TimeRuntime, Protocol):
    """Shared-time runtime capable of an atomic participant/time reset."""

    def reset_with_participants(
        self,
        clock_address: str,
        replay: bool,
        participant_runtime: CoordinatedParticipantResetRuntime,
        participant_requests: tuple[ParticipantEpisodeResetRequest, ...],
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Atomically reset shared time and the bound participant episodes.

        Implementations must prepare all native changes before commit. A
        failed result must leave both the shared clock and every participant
        backend at the predecessor state; a successful result must expose all
        changes in one coherent snapshot.
        """
        ...
