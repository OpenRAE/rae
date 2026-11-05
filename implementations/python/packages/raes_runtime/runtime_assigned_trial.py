"""One selected execution binding inside the shared runtime engine."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from threading import RLock
from typing import TYPE_CHECKING

from raes_contracts.assigned_trial import TrialAssignmentControlModel, TrialAssignmentModel, TrialOutcomeModel
from raes_contracts.errors import AuthorizationError, ConflictError
from raes_contracts.trial_unit import TrialUnitRequest, TrialUnitResult
from raes_processor.trial_realization import realize_admitted_trial_entry
from raes_processor.trial_scheduler import AllocatorGrant, plan_batch_schedule

from .control_plane_operation_context import operation_actor_scope
from .errors import TrialPending
from .runtime_trial_binding import ExperimentProgress, trial_request, trial_terminal_decision
from .runtime_trial_decisions import TrialAttemptDecision, TrialTerminalDecision
from .trial_handoff_conversion import trial_outcome

if TYPE_CHECKING:
    from raes_processor.trial_realization import TrialRealization, TrialRealizationInputs

    import raes_runtime.control_plane

    from .control_plane_store import ControlPlaneStore
    from .runtime_trial_services import TrialRuntimeServices
    from .runtime_trial_unit import RuntimeTrialUnit

_BOUND_IDENTITY = object()


def assigned_attempt(assignment: TrialAssignmentModel) -> TrialAttemptDecision:
    """Build the local ledger decision from the exact portable authorization."""
    return TrialAttemptDecision(
        experiment_id=assignment.experiment_id,
        plan_entry_id=assignment.plan_entry_id,
        run_id=assignment.plan.entries[assignment.plan_entry_id].run_id,
        attempt=assignment.attempt,
        execution_attempt_id=assignment.execution_attempt_id,
        started_at=assignment.started_at,
        deadline=assignment.deadline,
    )


class AssignedTrial:
    """Public bound BackendTrialUnit; transport and host placement are downstream."""

    def __init__(
        self,
        engine: raes_runtime.control_plane.RuntimeControlPlane,
        assignment: TrialAssignmentModel,
        inputs: TrialRealizationInputs,
        *,
        store: ControlPlaneStore,
        services: TrialRuntimeServices,
        identity: object | None,
    ) -> None:
        try:
            self._assignment = TrialAssignmentModel.reconstruct(assignment)
        except ValueError:
            raise ConflictError("assigned trial binding is invalid") from None
        self._engine, self._services = engine, services
        self._store = store
        self._actor_scope = operation_actor_scope(identity)
        self._identity = identity
        self.require_owner(identity)
        if (inputs.plan.plan_id, inputs.plan.plan_digest) != (
            self._assignment.experiment_id,
            self._assignment.root_plan_digest,
        ):
            raise ConflictError("assigned trial inputs differ from the original plan")
        if self._assignment.plan.replacement_origin is None and inputs.plan.model_dump(
            mode="json"
        ) != self._assignment.plan.model_dump(mode="json"):
            raise ConflictError("assigned trial inputs differ from the original plan")
        inputs = replace(inputs, plan=self._assignment.plan)
        if self._assignment.target_scope != "target:" + engine.target_name:
            raise ConflictError("assigned trial target differs from the installed target")
        self._realization = realize_admitted_trial_entry(
            inputs=deepcopy(inputs), plan_entry_id=self._assignment.plan_entry_id, target_name=engine.target_name
        )
        if (self._realization.snapshot_digest, self._realization.processor_plan_refs) != (
            self._assignment.instantiated_sdl_digest,
            self._assignment.processor_plan_refs,
        ):
            raise ConflictError("assigned trial hydration differs from the original commitments")
        self._request = trial_request(
            self._assignment.plan,
            self._assignment.plan_entry_id,
            self._realization,
            self._assignment.execution_attempt_id,
        )
        self._attempt = assigned_attempt(self._assignment)
        self._unit = None
        self._lock = RLock()
        self._progress = (
            "completed"
            if any(
                isinstance(item, TrialTerminalDecision)
                and item.execution_attempt_id == self._attempt.execution_attempt_id
                for item in self._store.load_runtime_decisions()
            )
            else "progress"
        )

    @property
    def realization(self) -> TrialRealization:
        """Detached in-process processor output for installed composition."""
        return deepcopy(self._realization)

    def owns_attempt(self, attempt: TrialAttemptDecision, services: TrialRuntimeServices) -> bool:
        return self._attempt == attempt and self._services is services

    def require_services(self, services: TrialRuntimeServices) -> None:
        if services is not self._services:
            raise ConflictError("assigned trial services differ from the installed owner")

    @property
    def assignment(self) -> TrialAssignmentModel:
        return self._assignment.model_copy(deep=True)

    @property
    def assignment_digest(self) -> str:
        return self._assignment.content_digest

    @property
    def experiment_id(self) -> str:
        return self._assignment.experiment_id

    @property
    def owner_id(self) -> str:
        return self._assignment.owner_id

    @property
    def request(self) -> TrialUnitRequest:
        return trial_request(
            self._assignment.plan,
            self._assignment.plan_entry_id,
            self._realization,
            self._assignment.execution_attempt_id,
        )

    def require_owner(self, identity: object | None) -> None:
        if operation_actor_scope(identity) != self._actor_scope or self._actor_scope[0] != self._assignment.owner_id:
            raise AuthorizationError("assigned trial execution owner does not match")

    def attach(self, unit: RuntimeTrialUnit) -> None:
        if self._unit is not None:
            raise ConflictError("assigned trial execution binding is already installed")
        self._unit = unit

    def outcome(self, *, identity: object | None = None) -> TrialOutcomeModel:
        self.require_owner(identity)
        self._engine.require_trial_admission(self._attempt, self._services)
        # Read the retained cut while an advance may be waiting on native work.
        # Completion is published only after its terminal decision is durable.
        return trial_outcome(self._unit, self._assignment.content_digest, self._progress)

    def advance(
        self, *, identity: object | None = None, control: TrialAssignmentControlModel | None = None
    ) -> ExperimentProgress:
        self.require_owner(identity)
        self._engine.require_trial_admission(self._attempt, self._services)
        with self._lock:
            cancelled, prepare_retry = self._engine.apply_assigned_trial_control(self, control)
            if self._progress != "completed":
                state = self._unit.advance_runtime(cancelled=cancelled)
                if state == "succeeded":
                    self._store.claim_runtime_decision(
                        trial_terminal_decision(
                            self._attempt,
                            self._unit.result(),
                            plan_batch_schedule(self._assignment.plan),
                            self._assignment.plan_entry_id,
                            capture_succeeded=self._unit.capture_succeeded(),
                            reusable=self._unit.reusable(),
                            grant=AllocatorGrant(effective_parallelism=self._assignment.effective_parallelism),
                        )
                    )
                self._progress = "completed" if state == "succeeded" else state
            if prepare_retry:
                policy = self._request.cleanup_plan.retry_policy
                if (
                    self._progress != "completed"
                    or self._unit.result().cleanup_receipt.trial_outcome != "failed"
                    or not self._unit.reusable()
                    or self._attempt.attempt >= policy.max_attempts
                    or policy.after_effect_policy not in {"reset", "compensate"}
                ):
                    raise ConflictError("assigned attempt does not permit retry preparation")
                self._unit.prepare_retry_runtime()
            return ExperimentProgress(
                self._assignment.experiment_id,
                self._progress,
                self._assignment.plan_entry_id,
                self._assignment.execution_attempt_id,
            )

    def execute_trial(self, request: TrialUnitRequest, *, identity: object | None = _BOUND_IDENTITY) -> TrialUnitResult:
        if identity is _BOUND_IDENTITY:
            identity = self._identity
        self.require_owner(identity)
        if replace(request) != self._request:
            raise ConflictError("trial adapter request conflicts with its assigned entry")
        for _ in range(16):
            state = self.advance(identity=identity).state
            if state == "completed":
                return self._unit.result()
            if state != "progress":
                break
        raise TrialPending("assigned trial requires observation or reconciliation")
