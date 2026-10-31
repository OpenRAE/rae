"""Optional experiment accounting composed inside the common runtime engine."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
from threading import RLock
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from raes_contracts.admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from raes_contracts.contracts import AdmittedTrialPlanModel
from raes_contracts.contracts.trial_controls import required_trial_operation_guarantees
from raes_contracts.errors import AuthorizationError, ConflictError, InvalidInputError, NotFoundError
from raes_contracts.trial_unit import TrialUnitRequest
from raes_processor.trial_realization import TrialRealization, TrialRealizationInputs, realize_admitted_trial_entry
from raes_processor.trial_scheduler import (
    BatchSchedule,
    ScheduledEntry,
    plan_batch_schedule,
)

from .control_plane_operation_context import operation_actor_scope
from .control_plane_store import InMemoryControlPlaneStore
from .errors import RuntimeBudgetExhaustedError
from .runtime_experiment_admission import admit_trial
from .runtime_resource_ownership import ledger_identity
from .runtime_run_driver import program_decision
from .runtime_trial_decisions import (
    ExperimentCancellationDecision,
    ExperimentDecision,
    TrialAttemptDecision,
    TrialReplacementDecision,
    TrialTerminalDecision,
)
from .runtime_trial_unit import RuntimeTrialUnit

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from raes_contracts.trial_unit import TrialUnitResult

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneStore
    from .runtime_decisions import RuntimeDecision
    from .runtime_experiment_replacement import ExperimentReplacementBinding
    from .runtime_run_context import RuntimeRunContext
    from .runtime_trial_services import TrialRuntimeServices


@dataclass(frozen=True)
class ExperimentProgress:
    experiment_id: str
    state: str
    plan_entry_id: str | None = None
    execution_attempt_id: str | None = None


@dataclass(frozen=True)
class TrialSlot:
    plan: AdmittedTrialPlanModel
    schedule: BatchSchedule
    entry: ScheduledEntry
    realization: TrialRealization
    root_entry_id: str


def trial_request(
    plan: AdmittedTrialPlanModel, entry_id: str, realization: TrialRealization, attempt_id: str
) -> TrialUnitRequest:
    return TrialUnitRequest(
        plan=plan,
        plan_entry_id=entry_id,
        execution_attempt_id=attempt_id,
        instantiated_sdl_digest=realization.snapshot_digest,
        provisioning_plan=realization.provisioning_plan,
        orchestration_plan=realization.orchestration_plan,
        evaluation_plan=realization.evaluation_plan,
    )


class RuntimeExperiment:
    def __init__(
        self,
        engine: RuntimeControlPlane,
        inputs: TrialRealizationInputs,
        *,
        services: TrialRuntimeServices,
        store_factory: Callable[[str], ControlPlaneStore] | None = None,
        identity: object | None = None,
        replacement: ExperimentReplacementBinding | None = None,
    ) -> None:
        required = ("admit", "configure", "observe", "capture", "cleanup", "stop", "verify")
        if services is None or not all(callable(getattr(services, name, None)) for name in required):
            raise ValueError("experiment requires installed trial services")
        self.engine, self.services = engine, services
        self.inputs: TrialRealizationInputs = deepcopy(inputs)
        self.identity, self._lock, self.replacement = identity, RLock(), replacement
        self.plan = revalidate_admitted_trial_plan(self.inputs.plan)
        self.schedule = plan_batch_schedule(self.plan)
        self.experiment_id = self.plan.plan_id
        self.store_factory = store_factory
        self.durable = ledger_identity(engine._store)[0] != "in-memory-ledger"
        self._validate_owners()
        self.realizations = {}
        self._units = {}
        self._children = {}
        commitments = []
        for entry in self.schedule.entries:
            realized = realize_admitted_trial_entry(
                inputs=self.inputs, plan_entry_id=entry.plan_entry_id, target_name=engine.target_name
            )
            request = trial_request(self.plan, entry.plan_entry_id, realized, self._attempt_id(entry.plan_entry_id, 1))
            admit_trial(engine, realized, request, services)
            self.realizations[entry.plan_entry_id] = realized
            commitments.append(
                program_decision(engine, realized.execution_plan, entry.plan_entry_id, identity).plan_digest
            )
        actor, scopes = operation_actor_scope(identity)
        self.admission = ExperimentDecision(
            experiment_id=self.experiment_id,
            plan_digest=self.plan.plan_digest,
            realization_digests=tuple(commitments),
            actor_id=actor,
            authorization_scope=scopes,
        )
        engine._store.claim_runtime_decision(self.admission)

    def _validate_owners(self) -> None:
        if self.durable and not callable(self.store_factory):
            raise ValueError("durable experiments require an explicit durable run store factory")
        if self.plan.replacement_policy is not None and self.replacement is None:
            raise ValueError("admitted replacement policy requires its compilation and archive owners")
        if self.replacement is not None:
            from .runtime_experiment_replacement import ExperimentReplacementBinding

            if not isinstance(self.replacement, ExperimentReplacementBinding):
                raise TypeError("replacement requires a typed owner binding")
            self.replacement.require_root(self.plan)
        if len(self.schedule.entries) > 4096:
            raise ConflictError("experiment exceeds installed runtime entry capacity")

    def _attempt_id(self, entry_id: str, ordinal: int) -> str:
        return "attempt:" + str(uuid5(NAMESPACE_URL, self.experiment_id + ":" + entry_id + ":" + str(ordinal)))

    def _authorize(self, identity: object | None) -> None:
        if operation_actor_scope(identity) != (self.admission.actor_id, self.admission.authorization_scope):
            raise AuthorizationError("experiment actor does not match its admitted scope")

    @contextmanager
    def _advance_lease(self) -> Iterator[None]:
        if not self._lock.acquire(timeout=self.engine._supervision.admission_ms / 1000):
            raise RuntimeBudgetExhaustedError("experiment progress admission is busy")
        try:
            yield
        finally:
            self._lock.release()

    def results(self, identity: object | None) -> tuple[TrialUnitResult, ...]:
        self._authorize(identity)
        with self._advance_lease():
            records = self.engine._store.load_runtime_decisions()
            terminals = {record.execution_attempt_id for record in records if isinstance(record, TrialTerminalDecision)}
            results = []
            for slot in self._slots(records):
                attempts = sorted(
                    (
                        record
                        for record in records
                        if isinstance(record, TrialAttemptDecision)
                        and record.experiment_id == self.experiment_id
                        and record.plan_entry_id == slot.entry.plan_entry_id
                        and record.execution_attempt_id in terminals
                    ),
                    key=lambda record: record.attempt,
                )
                results.extend(self._unit(slot, attempt, identity).result() for attempt in attempts)
            return tuple(results)

    def cancel(self, identity: object | None) -> None:
        self._authorize(identity)
        self.engine._store.claim_runtime_decision(
            ExperimentCancellationDecision(
                experiment_id=self.experiment_id,
                actor_id=self.admission.actor_id,
            )
        )
        # Controls use their existing independent authority; acknowledgement does
        # not mark the attempt stopped or release its resources.
        run_scopes = {
            "run:" + record.run_id
            for record in self.engine._store.load_runtime_decisions()
            if isinstance(record, TrialAttemptDecision) and record.experiment_id == self.experiment_id
        }
        for run in self.engine._engine.contexts():
            if run._run_scope not in run_scopes:
                continue
            self._cancel_run(run, identity)

    def _cancel_run(self, run: RuntimeRunContext, identity: object | None) -> None:
        for record in run._store.load_records().values():
            if (
                record.status.state.value in {"accepted", "running", "indeterminate"}
                and record.invocation is not None
                and record.status.context.actor_id == self.admission.actor_id
            ):
                try:
                    run.cancel_operation(
                        record.receipt.operation_id,
                        control_id="cancel:" + record.receipt.operation_id,
                        identity=identity,
                    )
                except ConflictError, InvalidInputError:
                    # Unsupported cancellation preserves pending/unknown state.
                    continue

    def _run(self, entry: ScheduledEntry, plan: AdmittedTrialPlanModel) -> RuntimeRunContext:
        scope = "run:" + entry.run_id
        controls = plan.entries[entry.plan_entry_id].execution_controls
        required = required_trial_operation_guarantees(
            controls, plan.cleanup_plans[controls.cleanup_plan_ref].retry_policy
        )
        try:
            run = self.engine.get_run(scope)
        except NotFoundError:
            store = self.store_factory(entry.run_id) if self.store_factory is not None else InMemoryControlPlaneStore()
            if self.durable and ledger_identity(store)[0] == "in-memory-ledger":
                raise ValueError("durable experiments require an explicit durable run store factory") from None
            run = self.engine.open_run(
                run_scope=scope,
                store=store,
                stochastic_controls=tuple(plan.stochastic_controls.values()),
                required_operation_guarantees=required,
            )
        if run._required_operation_guarantees != required:
            raise ConflictError("trial operation guarantees differ from the fixed run binding")
        return run

    def _attempt(self, slot: TrialSlot, ordinal: int, records: tuple[RuntimeDecision, ...]) -> TrialAttemptDecision:
        entry = slot.entry
        for record in records:
            if (
                isinstance(record, TrialAttemptDecision)
                and record.experiment_id == self.experiment_id
                and record.plan_entry_id == entry.plan_entry_id
                and record.attempt == ordinal
            ):
                return record
        now = self.engine.wall_clock()
        controls = slot.plan.entries[entry.plan_entry_id].execution_controls
        attempt = TrialAttemptDecision(
            experiment_id=self.experiment_id,
            plan_entry_id=entry.plan_entry_id,
            run_id=entry.run_id,
            attempt=ordinal,
            execution_attempt_id=self._attempt_id(entry.plan_entry_id, ordinal),
            started_at=now.isoformat(),
            deadline=(now + timedelta(seconds=controls.attempt_timeout_seconds)).isoformat(),
        )
        self.engine._store.claim_runtime_decision(attempt)
        return attempt

    def _slots(self, records: tuple[RuntimeDecision, ...]) -> tuple[TrialSlot, ...]:
        roots = tuple(
            TrialSlot(self.plan, self.schedule, entry, self.realizations[entry.plan_entry_id], entry.plan_entry_id)
            for entry in self.schedule.entries
        )
        ranks = {entry.plan_entry_id: entry.dispatch_ordinal for entry in self.schedule.entries}
        children = sorted(
            (
                record
                for record in records
                if isinstance(record, TrialReplacementDecision) and record.experiment_id == self.experiment_id
            ),
            key=lambda record: (ranks[record.root_entry_id], record.ordinal),
        )
        for child in children:
            if child.decision_id not in self._children:
                schedule = plan_batch_schedule(child.plan)
                (entry,) = schedule.entries
                child_inputs = TrialRealizationInputs(
                    plan=child.plan,
                    family=self.inputs.family,
                    experiment=self.inputs.experiment,
                    task=self.inputs.task,
                    capture_specs=self.inputs.capture_specs,
                    apparatus_manifests=self.inputs.apparatus_manifests,
                    realization_envelope=self.inputs.realization_envelope,
                    backend_key=self.inputs.backend_key,
                    participant_manifests=self.inputs.participant_manifests,
                )
                realized = realize_admitted_trial_entry(
                    inputs=child_inputs,
                    plan_entry_id=entry.plan_entry_id,
                    target_name=self.engine.target_name,
                )
                request = trial_request(
                    child.plan, entry.plan_entry_id, realized, self._attempt_id(entry.plan_entry_id, 1)
                )
                admit_trial(self.engine, realized, request, self.services)
                self._children[child.decision_id] = TrialSlot(
                    child.plan, schedule, entry, realized, child.root_entry_id
                )
        return (*roots, *(self._children[child.decision_id] for child in children))

    def _unit(self, slot: TrialSlot, attempt: TrialAttemptDecision, identity: object | None) -> RuntimeTrialUnit:
        unit = self._units.get(attempt.execution_attempt_id)
        if unit is None:
            run = self._run(slot.entry, slot.plan)
            unit = RuntimeTrialUnit(
                run,
                trial_request(slot.plan, slot.entry.plan_entry_id, slot.realization, attempt.execution_attempt_id),
                slot.realization,
                self.services,
                attempt,
                identity,
            )
            self._units[attempt.execution_attempt_id] = unit
        return unit

    def advance(self, identity: object | None) -> ExperimentProgress:
        from .runtime_experiment_progress import advance_experiment

        self._authorize(identity)
        with self._advance_lease():
            return advance_experiment(self, identity)

    def _progress(self, state: str, entry: ScheduledEntry, attempt: TrialAttemptDecision) -> ExperimentProgress:
        return ExperimentProgress(self.experiment_id, state, entry.plan_entry_id, attempt.execution_attempt_id)
