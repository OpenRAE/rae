"""Shared runtime engine with a compatible fixed default run context."""

from __future__ import annotations

from dataclasses import replace
from threading import Lock, RLock
from typing import TYPE_CHECKING, Unpack

from raes_contracts.assigned_trial import TrialAssignmentControlModel, TrialAssignmentModel, TrialOutcomeModel
from raes_contracts.contracts.trial_controls import required_trial_operation_guarantees
from raes_contracts.errors import ConflictError, EvidenceIntegrityError, NotFoundError
from raes_processor.trial_scheduler import AllocatorGrant

from .control_plane_configuration import ControlPlaneConfiguration, ControlPlaneOptions
from .control_plane_lifecycle import runtime_owned
from .control_plane_operation_context import operation_actor_scope
from .control_plane_security import ControlPlaneIdentity as ControlPlaneIdentity
from .control_plane_store import ControlPlaneOperationRecord
from .control_plane_store import LocalControlPlaneStore as LocalControlPlaneStore
from .participant_control_binding import (
    ParticipantControlResolution,
    ParticipantControlRuntimeBinding,
    ParticipantControlRuntimeResolver,
)
from .participant_control_effects import ParticipantControlEffectRealization
from .registry import RuntimeTarget
from .runtime_assigned_trial import AssignedTrial, assigned_attempt
from .runtime_assignment_decisions import TrialAssignmentDecision
from .runtime_engine import RuntimeEngineResources
from .runtime_experiment_admission import admit_trial
from .runtime_run_context import RuntimeRunContext
from .runtime_trial_decisions import ExperimentCancellationDecision, TrialAttemptDecision
from .runtime_trial_services import call_installed_owner
from .runtime_trial_unit import RuntimeTrialUnit

__all__ = (
    "ControlPlaneIdentity",
    "ControlPlaneOperationRecord",
    "ControlPlaneOptions",
    "LocalControlPlaneStore",
    "ParticipantControlEffectRealization",
    "ParticipantControlResolution",
    "ParticipantControlRuntimeBinding",
    "ParticipantControlRuntimeResolver",
    "RuntimeControlPlane",
    "operation_actor_scope",
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from raes_contracts.contracts import ExperimentStudyModel
    from raes_contracts.trial_unit import TrialUnitRequest, TrialUnitResult
    from raes_processor.trial_realization import TrialRealizationInputs

    from .control_plane_store import ControlPlaneStore
    from .experiment_records import (
        ExperimentEvidenceReader,
        ExperimentRecordArchive,
        ExperimentRecordBundle,
        ExperimentRunMetadata,
    )
    from .runtime_experiment import ExperimentProgress, RuntimeExperiment
    from .runtime_experiment_replacement import ExperimentReplacementBinding
    from .runtime_sequence_authority import RuntimeSequenceOptions
    from .runtime_sequence_reference import RuntimeSequenceReference
    from .runtime_trial_services import TrialOutcomeVerifier, TrialRuntimeServices


class RuntimeControlPlane(RuntimeRunContext):
    """One engine for all workloads; legacy calls use its fixed default run."""

    def __init__(self, target: RuntimeTarget, **options: Unpack[ControlPlaneOptions]) -> None:
        config = ControlPlaneConfiguration(**options)
        engine = RuntimeEngineResources(self, target, config)
        super().__init__(target, config=config, engine=engine)
        self._experiments = {}
        self._assigned_trials = {}
        self._installing_assigned_trials = {}
        self._assigned_trial_locks = {}
        self._assigned_trial_guard = Lock()
        self._sequence_bindings = {}

    @runtime_owned
    def assign_trial(
        self,
        experiment_id: str,
        plan_entry_id: str,
        *,
        owner_id: str,
        grant: AllocatorGrant | None = None,
        identity: object | None = None,
    ) -> TrialAssignmentModel:
        """Atomically assign one original entry; identifiers grant no authority."""
        return self._admitted_experiment(experiment_id).assign(
            plan_entry_id, owner_id, grant or AllocatorGrant(), identity
        )

    @runtime_owned
    def ingest_trial_outcome(
        self, experiment_id: str, outcome: TrialOutcomeModel, *, identity: object | None = None
    ) -> ExperimentProgress:
        """Verify and retain remote facts under the original admission."""
        return self._admitted_experiment(experiment_id).ingest(outcome, identity)

    def verify_assigned_trial_outcome(
        self, verifier: TrialOutcomeVerifier, request: TrialUnitRequest, outcome: TrialOutcomeModel
    ) -> None:
        """Internal bounded call to an explicitly installed original-evidence owner."""
        self._assert_runtime_owner()
        verified = call_installed_owner(
            self._execution_adapter,
            verifier.verify_outcome,
            request,
            outcome,
            timeout_ms=self._supervision.observation_ms,
            failure=EvidenceIntegrityError,
            message="installed owner did not verify the assigned trial outcome",
        )
        if verified is not None:
            raise EvidenceIntegrityError("installed owner did not verify the assigned trial outcome")

    @runtime_owned
    def assigned_trial_control(
        self, experiment_id: str, assignment_digest: str, *, identity: object | None = None
    ) -> TrialAssignmentControlModel:
        """Read retained coordinator intent for delivery by the downstream transport."""
        return self._admitted_experiment(experiment_id).assignment_control(assignment_digest, identity)

    @runtime_owned
    def advance_trial(
        self, experiment_id: str, plan_entry_id: str, *, identity: object | None = None
    ) -> ExperimentProgress:
        """Advance one assigned entry's coordinator policy without dispatching siblings."""
        return self._admitted_experiment(experiment_id).advance_selected(plan_entry_id, identity)

    def apply_assigned_trial_control(
        self, binding: AssignedTrial, control: TrialAssignmentControlModel | None
    ) -> tuple[bool, bool]:
        """Internal host composition; a delivered control cannot establish cessation."""
        self._assert_runtime_owner()
        if self._assigned_trials.get(binding.assignment_digest) is not binding:
            raise ConflictError("assigned trial is not owned by this runtime")
        checked = None
        if control is not None:
            try:
                checked = TrialAssignmentControlModel.reconstruct(control)
            except ValueError:
                raise ConflictError("assigned trial control is invalid") from None
            if checked.assignment_digest != binding.assignment_digest:
                raise ConflictError("control belongs to another assigned trial")
            if checked.cancelled:
                self._store.claim_runtime_decision(
                    ExperimentCancellationDecision(
                        experiment_id=binding.experiment_id,
                        actor_id=binding.owner_id,
                    )
                )
        cancelled = any(
            isinstance(item, ExperimentCancellationDecision) and item.experiment_id == binding.experiment_id
            for item in self._store.load_runtime_decisions()
        )
        return cancelled, bool(checked is not None and checked.prepare_retry and not cancelled)

    @runtime_owned
    def bind_assigned_trial(
        self,
        assignment: TrialAssignmentModel,
        inputs: TrialRealizationInputs,
        *,
        services: TrialRuntimeServices,
        store_factory: Callable[[str], ControlPlaneStore] | None = None,
        identity: object | None = None,
    ) -> AssignedTrial:
        """Install an exact assigned trial, without admitting a worker experiment."""
        binding = AssignedTrial(self, assignment, inputs, store=self._store, services=services, identity=identity)
        key = binding.assignment_digest
        with self._assigned_trial_guard:
            lock = self._assigned_trial_locks.setdefault(key, RLock())
        with lock:
            return self._install_assigned_trial(binding, services, store_factory, identity)

    def _install_assigned_trial(
        self,
        binding: AssignedTrial,
        services: TrialRuntimeServices,
        store_factory: Callable[[str], ControlPlaneStore] | None,
        identity: object | None,
    ) -> AssignedTrial:
        key = binding.assignment_digest
        existing = self._assigned_trials.get(key)
        if existing is not None:
            existing.require_owner(identity)
            existing.require_services(services)
            return existing
        admit_trial(self, binding.realization, binding.request, services)
        controls = binding.request.execution_controls
        required = required_trial_operation_guarantees(controls, binding.request.cleanup_plan.retry_policy)
        scope = "run:" + binding.request.run_id
        try:
            run = self.get_run(scope)
        except NotFoundError:
            run = self.open_run(
                run_scope=scope,
                store=store_factory(binding.request.run_id) if store_factory is not None else None,
                stochastic_controls=tuple(binding.assignment.plan.stochastic_controls.values()),
                required_operation_guarantees=required,
            )
        run.require_operation_guarantees(required)
        attempt = assigned_attempt(binding.assignment)
        records = self._store.load_runtime_decisions()
        self._store.claim_runtime_decisions(
            (attempt, TrialAssignmentDecision(assignment=binding.assignment)),
            expected_ids=tuple(item.decision_id for item in records),
        )
        with self._assigned_trial_guard:
            self._installing_assigned_trials[key] = binding
        try:
            binding.attach(RuntimeTrialUnit(run, binding.request, binding.realization, services, attempt, identity))
            with self._assigned_trial_guard:
                self._assigned_trials[key] = binding
        finally:
            with self._assigned_trial_guard:
                self._installing_assigned_trials.pop(key, None)
        return binding

    def require_trial_admission(self, attempt: TrialAttemptDecision, services: TrialRuntimeServices) -> None:
        """Internal composition check shared by local and selected trial adapters."""
        self._assert_runtime_owner()
        experiment = self._experiments.get(attempt.experiment_id)
        with self._assigned_trial_guard:
            assigned = any(
                item.owns_attempt(attempt, services)
                for item in (*self._assigned_trials.values(), *self._installing_assigned_trials.values())
            )
        if not assigned and (experiment is None or experiment.services is not services):
            raise ConflictError("trial adapter is not bound to its engine admission")
        if attempt not in self._store.load_runtime_decisions():
            raise ConflictError("trial adapter is not bound to its engine admission")

    @runtime_owned
    def bind_workflow(self, **options: Unpack[RuntimeSequenceOptions]) -> RuntimeSequenceReference:
        """Bind exact owned artifacts before submitting reference-only delivery."""
        self._assert_runtime_owner()
        from .runtime_sequence_authority import bind_sequence

        return bind_sequence(self, options)

    @runtime_owned
    def advance_workflow(self, reference: RuntimeSequenceReference, *, identity: object | None) -> str:
        self._assert_runtime_owner()
        from .runtime_sequence_authority import advance_sequence

        return advance_sequence(self, reference, identity)

    @runtime_owned
    def admit_experiment(
        self,
        inputs: TrialRealizationInputs,
        *,
        services: TrialRuntimeServices,
        store_factory: Callable[[str], ControlPlaneStore] | None = None,
        identity: object | None = None,
        replacement: ExperimentReplacementBinding | None = None,
        outcome_verifier: TrialOutcomeVerifier | None = None,
    ) -> str:
        self._assert_runtime_owner()
        from .runtime_experiment import RuntimeExperiment

        experiment = RuntimeExperiment(
            self,
            inputs,
            services=services,
            store_factory=store_factory,
            identity=identity,
            replacement=replacement,
            outcome_verifier=outcome_verifier,
        )
        self._experiments.setdefault(experiment.experiment_id, experiment)
        return experiment.experiment_id

    def _admitted_experiment(self, experiment_id: str) -> RuntimeExperiment:
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            raise NotFoundError("runtime experiment is not admitted")
        return experiment

    @runtime_owned
    def advance_experiment(self, experiment_id: str, *, identity: object | None = None) -> ExperimentProgress:
        self._assert_runtime_owner()
        return self._admitted_experiment(experiment_id).advance(identity)

    @runtime_owned
    def cancel_experiment(self, experiment_id: str, *, identity: object | None = None) -> None:
        self._assert_runtime_owner()
        self._admitted_experiment(experiment_id).cancel(identity)

    @runtime_owned
    def experiment_results(self, experiment_id: str, *, identity: object | None = None) -> tuple[TrialUnitResult, ...]:
        self._assert_runtime_owner()
        return self._admitted_experiment(experiment_id).results(identity)

    @runtime_owned
    def experiment_records(
        self,
        experiment_id: str,
        *,
        identity: object | None = None,
        metadata: Mapping[str, ExperimentRunMetadata] | None = None,
        study: ExperimentStudyModel | None = None,
        evidence_reader: ExperimentEvidenceReader | None = None,
        archive: ExperimentRecordArchive | None = None,
    ) -> ExperimentRecordBundle:
        """Build records for every started run, including unresolved and failed work."""
        self._assert_runtime_owner()
        from .runtime_experiment_records import experiment_records

        return experiment_records(
            self._admitted_experiment(experiment_id),
            identity=identity,
            metadata=metadata,
            study=study,
            evidence_reader=evidence_reader,
            archive=archive,
        )

    @runtime_owned
    def open_run(self, **options: Unpack[ControlPlaneOptions]) -> RuntimeRunContext:
        """Open a fixed run scope without constructing another engine."""
        self._assert_runtime_owner()
        if "run_scope" not in options:
            raise ValueError("a new run requires an explicit run scope")
        for name in ("supervision", "distributed_execution", "profile", "wall_clock"):
            if name in options and options[name] != getattr(self._engine.configuration, name):
                raise ValueError("a run cannot replace engine execution configuration")
        config = replace(self._engine.configuration, **{"store": None, "initial_snapshot": None, **options})
        return self._engine.open_run(config)

    @runtime_owned
    def get_run(self, run_scope: str) -> RuntimeRunContext:
        """Select a retained context without changing the default run."""
        return self._engine.get_run(run_scope)

    @runtime_owned
    def retire_run(self, run_scope: str) -> None:
        """Retain completed run state and release its verified resource use."""
        self._assert_runtime_owner()
        self._engine.retire(self._engine.get_run(run_scope))
