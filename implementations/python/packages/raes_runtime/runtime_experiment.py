"""Optional experiment accounting composed inside the common runtime engine."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
from threading import RLock
from typing import TYPE_CHECKING

from raes_contracts.assigned_trial import (
    TrialAssignmentControlModel,
    TrialAssignmentModel,
    TrialOutcomeModel,
    trial_attempt_id,
)
from raes_contracts.contracts import AdmittedTrialPlanModel
from raes_contracts.contracts.admitted_trial_plan_ingress import revalidate_admitted_trial_plan
from raes_contracts.contracts.trial_controls import required_trial_operation_guarantees
from raes_contracts.errors import (
    AuthorizationError,
    ConflictError,
    EvidenceIntegrityError,
    InvalidInputError,
    NotFoundError,
)
from raes_processor.trial_realization import TrialRealizationInputs, realize_admitted_trial_entry
from raes_processor.trial_scheduler import (
    AllocatorGrant,
    ScheduledEntry,
    plan_batch_schedule,
)

from .control_plane_operation_context import operation_actor_scope
from .control_plane_store import InMemoryControlPlaneStore
from .errors import RuntimeBudgetExhaustedError
from .runtime_assignment_decisions import TrialAssignmentDecision, TrialOutcomeDecision
from .runtime_experiment_admission import admit_trial
from .runtime_experiment_progress import advance_experiment, advance_trial_slot, record_trial_terminal, retry_permission
from .runtime_remote_trial import (
    RemoteTrialUnit,
    latest_trial_outcome,
    require_outcome_extension,
    validate_remote_outcome,
)
from .runtime_resource_ownership import ledger_identity
from .runtime_run_driver import program_decision
from .runtime_trial_binding import ExperimentProgress as ExperimentProgress
from .runtime_trial_binding import TrialSlot as TrialSlot
from .runtime_trial_binding import trial_request
from .runtime_trial_decisions import (
    ExperimentCancellationDecision,
    ExperimentDecision,
    TrialAttemptDecision,
    TrialReplacementDecision,
    TrialTerminalDecision,
)
from .runtime_trial_services import require_trial_services
from .runtime_trial_unit import RuntimeTrialUnit

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from raes_contracts.trial_unit import TrialUnitResult

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneStore
    from .runtime_decisions import RuntimeDecision
    from .runtime_experiment_replacement import ExperimentReplacementBinding
    from .runtime_run_context import RuntimeRunContext
    from .runtime_trial_services import TrialOutcomeVerifier, TrialRuntimeServices


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
        outcome_verifier: TrialOutcomeVerifier | None = None,
    ) -> None:
        require_trial_services(services)
        self.engine, self.services = engine, services
        self.store = engine._store
        self.outcome_verifier = outcome_verifier
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
        self.store.claim_runtime_decision(self.admission)

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
        return trial_attempt_id(self.experiment_id, entry_id, ordinal)

    def assign(
        self, entry_id: str, owner_id: str, grant: AllocatorGrant, identity: object | None
    ) -> TrialAssignmentModel:
        self._authorize(identity)
        if type(grant.effective_parallelism) is not int:
            raise InvalidInputError("allocator parallelism requires an integer")
        if grant.effective_parallelism == 1 and (grant.isolation_proof_ref is not None or grant.lease_evidence_refs):
            raise InvalidInputError("serial allocator grants cannot claim parallel isolation or leases")
        records = self.store.load_runtime_decisions()
        entry_attempts = sorted(
            (
                item
                for item in records
                if isinstance(item, TrialAttemptDecision)
                and item.experiment_id == self.experiment_id
                and item.plan_entry_id == entry_id
            ),
            key=lambda item: item.attempt,
        )
        latest = entry_attempts[-1] if entry_attempts else None
        existing = next(
            (
                item.assignment
                for item in records
                if isinstance(item, TrialAssignmentDecision)
                and latest is not None
                and item.assignment.execution_attempt_id == latest.execution_attempt_id
            ),
            None,
        )
        if existing is not None:
            proof_ref = grant.isolation_proof_ref or self.schedule.isolation_proof_ref
            if (
                existing.owner_id,
                existing.effective_parallelism,
                existing.lease_evidence_refs,
                existing.isolation_proof_ref,
            ) != (
                owner_id,
                grant.effective_parallelism,
                tuple(grant.lease_evidence_refs),
                proof_ref if grant.effective_parallelism > 1 else None,
            ):
                raise ConflictError("entry already has a different assignment")
            return TrialAssignmentModel.reconstruct(existing)
        if any(
            isinstance(item, ExperimentCancellationDecision) and item.experiment_id == self.experiment_id
            for item in records
        ):
            raise ConflictError("experiment cancellation prevents assignment")
        slots = self._slots(records)
        slot = next((item for item in slots if item.entry.plan_entry_id == entry_id), None)
        if slot is None:
            raise NotFoundError("entry does not belong to the admitted experiment")
        attempts = {
            item.plan_entry_id
            for item in records
            if isinstance(item, TrialAttemptDecision) and item.experiment_id == self.experiment_id
        }
        if latest is not None:
            if not any(
                isinstance(item, TrialAssignmentDecision) and item.assignment.plan_entry_id == entry_id
                for item in records
            ):
                raise ConflictError("entry already has a runtime-owned attempt")
            attempt = latest
        else:
            first = next((item for item in slots if item.entry.plan_entry_id not in attempts), None)
            if first is None or first.entry.plan_entry_id != entry_id:
                raise ConflictError("assignment must preserve canonical dispatch order")
            attempt = self._new_attempt(slot, 1)
        if not 1 <= grant.effective_parallelism <= self.schedule.admitted_parallelism_ceiling:
            raise ConflictError("allocator grant exceeds admitted parallelism")
        proof = grant.isolation_proof_ref or self.schedule.isolation_proof_ref
        if grant.effective_parallelism > 1 and (
            proof != self.schedule.isolation_proof_ref or not grant.lease_evidence_refs
        ):
            raise ConflictError("parallel assignment requires the admitted proof and live allocator decision")
        if grant.effective_parallelism > 1 and entry_id not in self.plan.isolation_proof.plan_entry_ids:
            raise ConflictError("parallel assignment entry is outside the admitted isolation proof")
        occupied = self._occupied_entries(records, slots, excluding=entry_id, identity=identity)
        if occupied >= grant.effective_parallelism:
            raise ConflictError("admitted assignment capacity is occupied")
        assignment = TrialAssignmentModel(
            plan=slot.plan,
            plan_entry_id=entry_id,
            execution_attempt_id=attempt.execution_attempt_id,
            attempt=attempt.attempt,
            started_at=attempt.started_at,
            deadline=attempt.deadline,
            target_scope="target:" + self.engine.target_name,
            owner_id=owner_id,
            instantiated_sdl_digest=slot.realization.snapshot_digest,
            processor_plan_refs=slot.realization.processor_plan_refs,
            effective_parallelism=grant.effective_parallelism,
            isolation_proof_ref=proof if grant.effective_parallelism > 1 else None,
            lease_evidence_refs=tuple(grant.lease_evidence_refs) if grant.effective_parallelism > 1 else (),
        )
        candidates = (
            (TrialAssignmentDecision(assignment=assignment),)
            if latest is not None
            else (
                attempt,
                TrialAssignmentDecision(assignment=assignment),
            )
        )
        self.store.claim_runtime_decisions(candidates, expected_ids=tuple(item.decision_id for item in records))
        return assignment

    def _occupied_entries(self, records, slots, *, excluding: str, identity: object | None) -> int:
        terminals = {item.execution_attempt_id: item for item in records if isinstance(item, TrialTerminalDecision)}
        cancelled = any(
            isinstance(item, ExperimentCancellationDecision) and item.experiment_id == self.experiment_id
            for item in records
        )
        latest = {}
        for item in records:
            if isinstance(item, TrialAttemptDecision) and item.experiment_id == self.experiment_id:
                if item.plan_entry_id not in latest or latest[item.plan_entry_id].attempt < item.attempt:
                    latest[item.plan_entry_id] = item
        occupied = 0
        for slot in slots:
            attempt = latest.get(slot.entry.plan_entry_id)
            if attempt is None or slot.entry.plan_entry_id == excluding:
                continue
            terminal = terminals.get(attempt.execution_attempt_id)
            if terminal is None or not terminal.reusable:
                occupied += 1
                continue
            unit = self._unit(slot, attempt, identity)
            if isinstance(unit, RemoteTrialUnit):
                outcome = unit.outcome()
                if outcome is not None and any(
                    item.status.state.value in {"accepted", "running", "indeterminate"} for item in outcome.operations
                ):
                    occupied += 1
                    continue
            if not cancelled and retry_permission(unit, terminal) != "not-permitted":
                occupied += 1
        return occupied

    def ingest(self, outcome: TrialOutcomeModel, identity: object | None) -> ExperimentProgress:
        self._authorize(identity)
        try:
            outcome = TrialOutcomeModel.reconstruct(outcome)
        except ValueError:
            raise EvidenceIntegrityError("assigned trial outcome is invalid") from None
        records = self.store.load_runtime_decisions()
        assignment = next(
            (
                item.assignment
                for item in records
                if isinstance(item, TrialAssignmentDecision)
                and item.assignment.experiment_id == self.experiment_id
                and item.assignment.content_digest == outcome.assignment_digest
            ),
            None,
        )
        if assignment is None:
            raise EvidenceIntegrityError("trial outcome does not resolve to a retained assignment")
        slot = next(item for item in self._slots(records) if item.entry.plan_entry_id == assignment.plan_entry_id)
        attempt = next(
            item
            for item in records
            if isinstance(item, TrialAttemptDecision) and item.execution_attempt_id == assignment.execution_attempt_id
        )
        unit = self._unit(slot, attempt, identity)
        validate_remote_outcome(unit.request, assignment, outcome)
        previous = latest_trial_outcome(records, assignment.content_digest)
        if previous is None or previous.outcome != outcome:
            if previous is not None:
                require_outcome_extension(previous.outcome, outcome)
            verifier = self.outcome_verifier
            if verifier is None or not callable(getattr(verifier, "verify_outcome", None)):
                raise ConflictError("remote trial outcomes require an installed native evidence verifier")
            self.engine.verify_assigned_trial_outcome(verifier, unit.request, outcome)
            self.store.claim_runtime_decisions(
                (TrialOutcomeDecision(outcome=outcome, sequence=1 if previous is None else previous.sequence + 1),),
                expected_ids=tuple(item.decision_id for item in records),
            )
        if outcome.progress == "completed" and not any(
            isinstance(item, TrialTerminalDecision) and item.execution_attempt_id == attempt.execution_attempt_id
            for item in records
        ):
            record_trial_terminal(
                self,
                slot,
                unit,
                grant=AllocatorGrant(
                    effective_parallelism=assignment.effective_parallelism,
                    lease_evidence_refs=assignment.lease_evidence_refs,
                    isolation_proof_ref=assignment.isolation_proof_ref,
                ),
            )
        return self._progress(outcome.progress, slot.entry, attempt)

    def assignment_control(self, assignment_digest: str, identity: object | None) -> TrialAssignmentControlModel:
        self._authorize(identity)
        records = self.store.load_runtime_decisions()
        assignment = next(
            (
                item.assignment
                for item in records
                if isinstance(item, TrialAssignmentDecision)
                and item.assignment.experiment_id == self.experiment_id
                and item.assignment.content_digest == assignment_digest
            ),
            None,
        )
        if assignment is None:
            raise NotFoundError("assignment does not belong to this experiment")
        cancelled = any(
            isinstance(item, ExperimentCancellationDecision) and item.experiment_id == self.experiment_id
            for item in records
        )
        terminal = next(
            (
                item
                for item in records
                if isinstance(item, TrialTerminalDecision)
                and item.execution_attempt_id == assignment.execution_attempt_id
            ),
            None,
        )
        prepare_retry = False
        if terminal is not None and not cancelled:
            slot = next(item for item in self._slots(records) if item.entry.plan_entry_id == assignment.plan_entry_id)
            attempt = next(
                item
                for item in records
                if isinstance(item, TrialAttemptDecision)
                and item.execution_attempt_id == assignment.execution_attempt_id
            )
            prepare_retry = retry_permission(self._unit(slot, attempt, identity), terminal) == "prepare"
        return TrialAssignmentControlModel(
            assignment_digest=assignment_digest,
            cancelled=cancelled,
            prepare_retry=prepare_retry,
        )

    def advance_selected(self, entry_id: str, identity: object | None) -> ExperimentProgress:
        self._authorize(identity)
        records = self.store.load_runtime_decisions()
        slots = self._slots(records)
        slot = next((item for item in slots if item.entry.plan_entry_id == entry_id), None)
        if slot is None:
            raise NotFoundError("entry does not belong to this experiment")
        if not any(
            isinstance(item, TrialAssignmentDecision)
            and item.assignment.plan_entry_id in {entry_id, slot.root_entry_id}
            for item in records
        ):
            raise ConflictError("selected progress requires an assigned entry")
        cancelled = any(
            isinstance(item, ExperimentCancellationDecision) and item.experiment_id == self.experiment_id
            for item in records
        )
        terminals = {item.execution_attempt_id: item for item in records if isinstance(item, TrialTerminalDecision)}
        progress = advance_trial_slot(self, slot, records, terminals, cancelled, identity)
        known = {item.entry.plan_entry_id for item in slots}
        for child in self._slots(self.store.load_runtime_decisions()):
            if child.entry.plan_entry_id not in known and child.root_entry_id == slot.root_entry_id:
                return ExperimentProgress(self.experiment_id, "ready", child.entry.plan_entry_id)
        return progress or ExperimentProgress(self.experiment_id, "completed", entry_id)

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
            records = self.store.load_runtime_decisions()
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
        self.store.claim_runtime_decision(
            ExperimentCancellationDecision(
                experiment_id=self.experiment_id,
                actor_id=self.admission.actor_id,
            )
        )
        # Controls use their existing independent authority; acknowledgement does
        # not mark the attempt stopped or release its resources.
        run_scopes = {
            "run:" + record.run_id
            for record in self.store.load_runtime_decisions()
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
        run.require_operation_guarantees(required)
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
        attempt = self._new_attempt(slot, ordinal)
        self.store.claim_runtime_decision(attempt)
        return attempt

    def _new_attempt(self, slot: TrialSlot, ordinal: int) -> TrialAttemptDecision:
        entry = slot.entry
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
            assigned = next(
                (
                    item.assignment
                    for item in self.store.load_runtime_decisions()
                    if isinstance(item, TrialAssignmentDecision)
                    and item.assignment.execution_attempt_id == attempt.execution_attempt_id
                ),
                None,
            )
            if assigned is not None:
                unit = RemoteTrialUnit(slot, attempt, assigned, self.store)
                self._units[attempt.execution_attempt_id] = unit
                return unit
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
        self._authorize(identity)
        with self._advance_lease():
            return advance_experiment(self, identity)

    def _progress(self, state: str, entry: ScheduledEntry, attempt: TrialAttemptDecision) -> ExperimentProgress:
        return ExperimentProgress(self.experiment_id, state, entry.plan_entry_id, attempt.execution_attempt_id)
