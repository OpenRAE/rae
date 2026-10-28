"""Optional experiment accounting composed inside the common runtime engine."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import NAMESPACE_URL, uuid5

from raes_contracts.admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from raes_contracts.contracts import AdmittedTrialPlanModel
from raes_contracts.contracts.trial_controls import required_trial_operation_guarantees
from raes_contracts.runtime_state import OperationKind
from raes_contracts.trial_unit import TrialUnitRequest
from raes_processor.trial_realization import TrialRealization, realize_admitted_trial_entry
from raes_processor.trial_scheduler import (
    AttemptOutcome,
    BatchSchedule,
    ScheduledEntry,
    build_batch_execution_receipt,
    plan_batch_schedule,
)

from .control_plane_mutation import control_plane_mutation
from .control_plane_operation_context import operation_actor_scope
from .control_plane_store import InMemoryControlPlaneStore
from .runtime_decisions import RunContextDecision
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


def trial_request(plan, entry_id, realization, attempt_id):
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
    def __init__(self, engine, inputs, *, services, store_factory=None, identity=None, replacement=None):
        required = ("admit", "configure", "observe", "capture", "cleanup", "stop", "verify")
        if services is None or not all(callable(getattr(services, name, None)) for name in required):
            raise ValueError("experiment requires installed trial services")
        self.engine, self.inputs, self.services = engine, deepcopy(inputs), services
        self.identity, self._lock, self.replacement = identity, RLock(), replacement
        self.plan = revalidate_admitted_trial_plan(self.inputs.plan)
        self.schedule = plan_batch_schedule(self.plan)
        self.experiment_id = self.plan.plan_id
        self.store_factory = store_factory
        self.durable = ledger_identity(engine._store)[0] != "in-memory-ledger"
        if self.durable and not callable(store_factory):
            raise ValueError("durable experiments require an explicit durable run store factory")
        if self.plan.replacement_policy is not None and replacement is None:
            raise ValueError("admitted replacement policy requires its compilation and archive owners")
        if replacement is not None:
            from .runtime_experiment_replacement import ExperimentReplacementBinding

            if not isinstance(replacement, ExperimentReplacementBinding):
                raise TypeError("replacement requires a typed owner binding")
            replacement.require_root(self.plan)
        if len(self.schedule.entries) > 4096:
            raise ValueError("experiment exceeds installed runtime entry capacity")
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

    def _attempt_id(self, entry_id, ordinal):
        return "attempt:" + str(uuid5(NAMESPACE_URL, self.experiment_id + ":" + entry_id + ":" + str(ordinal)))

    def _authorize(self, identity):
        if operation_actor_scope(identity) != (self.admission.actor_id, self.admission.authorization_scope):
            raise PermissionError("experiment actor does not match its admitted scope")

    @contextmanager
    def _advance_lease(self):
        if not self._lock.acquire(timeout=self.engine._supervision.admission_ms / 1000):
            raise TimeoutError("experiment progress admission is busy")
        try:
            yield
        finally:
            self._lock.release()

    def results(self, identity):
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

    def cancel(self, identity):
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
            for record in run._store.load_records().values():
                if (
                    record.status.state.value in {"accepted", "running", "indeterminate"}
                    and record.invocation is not None
                ):
                    if record.status.context.actor_id == self.admission.actor_id:
                        try:
                            run.cancel_operation(
                                record.receipt.operation_id,
                                control_id="cancel:" + record.receipt.operation_id,
                                identity=identity,
                            )
                        except ValueError:
                            # Unsupported cancellation preserves pending/unknown
                            # state; observation remains required before cleanup.
                            continue

    def _run(self, entry, plan):
        scope = "run:" + entry.run_id
        controls = plan.entries[entry.plan_entry_id].execution_controls
        required = required_trial_operation_guarantees(
            controls, plan.cleanup_plans[controls.cleanup_plan_ref].retry_policy
        )
        try:
            run = self.engine.get_run(scope)
        except ValueError:
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
            raise ValueError("trial operation guarantees differ from the fixed run binding")
        return run

    def _attempt(self, slot, ordinal, records):
        entry = slot.entry
        for record in records:
            if (
                isinstance(record, TrialAttemptDecision)
                and record.experiment_id == self.experiment_id
                and record.plan_entry_id == entry.plan_entry_id
                and record.attempt == ordinal
            ):
                return record
        now = datetime.now(UTC)
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

    def _slots(self, records):
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
                realized = realize_admitted_trial_entry(
                    inputs=replace(self.inputs, plan=child.plan),
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

    def _unit(self, slot, attempt, identity):
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

    def advance(self, identity):
        self._authorize(identity)
        with self._advance_lease():
            records = self.engine._store.load_runtime_decisions()
            cancelled = any(
                isinstance(record, ExperimentCancellationDecision) and record.experiment_id == self.experiment_id
                for record in records
            )
            terminals = {
                record.execution_attempt_id: record for record in records if isinstance(record, TrialTerminalDecision)
            }
            retired = {
                record.run_scope
                for record in records
                if isinstance(record, RunContextDecision) and record.status == "retired"
            }
            for slot in self._slots(records):
                entry = slot.entry
                if "run:" + entry.run_id in retired:
                    continue
                existing = sorted(
                    (
                        record
                        for record in records
                        if isinstance(record, TrialAttemptDecision)
                        and record.experiment_id == self.experiment_id
                        and record.plan_entry_id == entry.plan_entry_id
                    ),
                    key=lambda record: record.attempt,
                )
                if cancelled and not existing:
                    return ExperimentProgress(self.experiment_id, "cancelled")
                attempt = existing[-1] if existing else self._attempt(slot, 1, records)
                for prior_attempt in existing:
                    self._unit(slot, prior_attempt, identity)
                unit = self._unit(slot, attempt, identity)
                run = unit.run
                terminal = terminals.get(attempt.execution_attempt_id)
                if terminal is not None:
                    if not terminal.reusable:
                        return self._progress("cleanup-failed", entry, attempt)
                    if not cancelled:
                        retry = self._retry(unit, terminal)
                        if retry == "ready":
                            attempt = self._attempt(slot, attempt.attempt + 1, records)
                            return self._progress("progress", entry, attempt)
                        if retry != "not-permitted":
                            return self._progress(retry, entry, attempt)
                    from .runtime_experiment_replacement import archive_and_replace

                    allocated = archive_and_replace(self, slot, unit, records, allow_replacement=not cancelled)
                    self.engine.retire_run(run._run_scope)
                    if allocated:
                        return self._progress("progress", entry, attempt)
                    continue
                run._engine.reserve(run)
                with (
                    run._runtime_call(),
                    run._resource_claim.runtime_call(self.engine),
                    control_plane_mutation(run, OperationKind.COMPOSITION_PHASE),
                ):
                    state = unit.advance(cancelled=cancelled)
                if state == "succeeded":
                    result = unit.result()
                    receipt = build_batch_execution_receipt(
                        slot.schedule,
                        entry.plan_entry_id,
                        receipt_id="batch:" + attempt.execution_attempt_id,
                        outcome=AttemptOutcome(
                            execution_attempt_id=attempt.execution_attempt_id,
                            trial_outcome=result.cleanup_receipt.trial_outcome,
                            cleanup_receipt_ref=result.cleanup_receipt.receipt_id,
                            operation_refs=tuple(receipt.operation_id for receipt in result.operation_receipts),
                            attempt_deadline=attempt.deadline,
                        ),
                    )
                    self.engine._store.claim_runtime_decision(
                        TrialTerminalDecision(
                            execution_attempt_id=attempt.execution_attempt_id,
                            receipt=receipt,
                            capture_status="succeeded" if unit.capture_succeeded() else "failed",
                            reusable=unit.reusable(),
                        )
                    )
                    state = "progress"
                return self._progress(state, entry, attempt)
            return ExperimentProgress(self.experiment_id, "cancelled" if cancelled else "completed")

    def _retry(self, unit, terminal):
        policy = unit.request.cleanup_plan.retry_policy
        if terminal.receipt.trial_outcome != "failed" or unit.attempt.attempt >= policy.max_attempts:
            return "not-permitted"
        observed = unit.observations()
        execution, cleanup = observed["execution"].observation, observed["cleanup"].observation
        if not execution.ceased or not terminal.reusable:
            return "not-permitted"
        if execution.effects_absent:
            return "ready"
        if policy.after_effect_policy == "idempotent":
            return "ready" if cleanup.idempotent_effects else "not-permitted"
        if policy.after_effect_policy in {"reset", "compensate"}:
            run = unit.run
            run._engine.reserve(run)
            with (
                run._runtime_call(),
                run._resource_claim.runtime_call(self.engine),
                control_plane_mutation(run, OperationKind.COMPOSITION_PHASE),
            ):
                state = unit.prepare_retry()
            if state != "succeeded":
                return state if state in {"pending", "indeterminate"} else "cleanup-failed"
            retry = unit.observations().get("retry")
            return "ready" if retry is not None and retry.observation.ready else "cleanup-failed"
        return "not-permitted"

    def _progress(self, state, entry, attempt):
        return ExperimentProgress(self.experiment_id, state, entry.plan_entry_id, attempt.execution_attempt_id)
