"""Runtime manager for compiled SDL runtime plans."""

from collections.abc import Iterable
from dataclasses import dataclass

from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.contracts import (
    ExperimentStochasticControlModel,
    ParticipantInformationStateContextResolver,
)
from raes_contracts.contracts.time_model import TimeModelDeclarationModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.models import ExecutionPlan
from raes_processor.planner import plan, snapshot_delete_order

from .apply_failure import maybe_synthesize_failure, rollback_services
from .backend_calls import _BackendCallContext, _call_backend_apply, _call_backend_diagnostics, _RealizationApplyContext
from .backend_observation_calls import _apply_runtime_plan_with_observation, _RuntimePlanApplyRequest
from .diagnostics import _failure_diagnostic, _has_error_diagnostic
from .manager_plan_admission import runtime_plan_precondition_diagnostics
from .participant_activity import resolve_participant_activity_controls
from .participant_execution_control import RuntimeParticipantExecutionMixin
from .participant_information_state_validation import require_participant_information_state_snapshot
from .registry import RuntimeTarget as _RuntimeTarget
from .registry import _validate_runtime_target_shape
from .time_control import RuntimeTimeControlMixin

_RUNTIME_APPLY_ADDRESS, _APPLY_EVALUATOR_ADDRESS = "runtime.apply", "runtime.apply.evaluator"
_APPLY_ORCHESTRATOR_ADDRESS = "runtime.apply.orchestrator"
_APPLY_PHASE_FAILED, _DESTROY_PHASE_FAILED = "runtime.apply-phase-failed", "runtime.destroy-phase-failed"
_ROLLBACK_EVALUATOR_ADDRESS = "runtime.rollback.evaluator"
_ROLLBACK_ORCHESTRATOR_ADDRESS = "runtime.rollback.orchestrator"


@dataclass
class _RuntimeApplyState:
    working_snapshot: RuntimeSnapshot
    diagnostics: list[Diagnostic]
    changed_addresses: list[str]
    details: dict[str, object]
    started_evaluator: bool = False
    failure: ApplyResult | None = None


class RuntimeManager(RuntimeParticipantExecutionMixin, RuntimeTimeControlMixin):
    """Plans and executes SDL runtime work against a target."""

    def __init__(
        self,
        target: _RuntimeTarget,
        *,
        initial_snapshot: RuntimeSnapshot | None = None,
        stochastic_controls: Iterable[ExperimentStochasticControlModel] = (),
        information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
    ) -> None:
        _validate_runtime_target_shape(
            manifest=target.manifest,
            provisioner=target.provisioner,
            orchestrator=target.orchestrator,
            evaluator=target.evaluator,
            participant_runtime=target.participant_runtime,
            time_runtime=target.time_runtime,
            observation_runtime=target.observation_runtime,
        )
        self._target = target
        self._snapshot = initial_snapshot if initial_snapshot is not None else RuntimeSnapshot()
        self._information_state_context_resolver = information_state_context_resolver
        require_participant_information_state_snapshot(self._snapshot, information_state_context_resolver)
        self._participant_activity_controls = resolve_participant_activity_controls(stochastic_controls)
        self._time_declaration: TimeModelDeclarationModel | None = None
        self._initialize_participant_scheduler()

    @property
    def snapshot(self) -> RuntimeSnapshot:
        return self._snapshot

    def plan(
        self,
        scenario: object,
        snapshot: RuntimeSnapshot | None = None,
        *,
        parameters: dict[str, object] | None = None,
        profile: str | None = None,
        artifact_availability: ArtifactAvailabilityContext | None = None,
        profile_authority=None,
    ) -> ExecutionPlan:
        model = compile_scenario_runtime_model(
            scenario, parameters=parameters, profile=profile, profile_authority=profile_authority
        )
        effective_snapshot = snapshot if snapshot is not None else self._snapshot
        return plan(
            model,
            self._target.manifest,
            effective_snapshot,
            target_name=self._target.name,
            artifact_availability=artifact_availability,
            profile_context=getattr(self._target.provisioner, "domain_profile_context", None),
        )

    def apply(self, execution_plan: ExecutionPlan) -> ApplyResult:
        driver_precondition = self._participant_driver_apply_precondition()
        if driver_precondition is not None:
            return driver_precondition
        diagnostics: list[Diagnostic] = list(execution_plan.diagnostics)
        self._time_declaration = None

        precondition_failure = self._apply_precondition_failure(execution_plan, diagnostics)
        if precondition_failure is not None:
            return precondition_failure

        state = _RuntimeApplyState(
            working_snapshot=execution_plan.base_snapshot,
            diagnostics=diagnostics,
            changed_addresses=[],
            details={},
        )
        self._run_apply_phases(execution_plan, state)
        if state.failure is None:
            self._finalize_participant_driver_apply(state)
        return state.failure

    def _run_apply_phases(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> None:
        self._apply_provisioning_phase(execution_plan, state)
        if state.failure is None:
            self._apply_time_phase(execution_plan, state)
        if state.failure is None:
            self._apply_participant_execution_phase(execution_plan, state)
        if state.failure is None:
            self._apply_evaluation_phase(execution_plan, state)
        if state.failure is None:
            self._apply_orchestration_phase(execution_plan, state)
        if state.failure is None:
            participant_started = self._start_participant_execution_phase(execution_plan, state)
            if not participant_started:
                self._rollback_failed_participant_start(execution_plan, state)

    def _rollback_failed_participant_start(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> None:
        services_to_rollback = []
        if execution_plan.orchestration.actionable_operations and self._target.orchestrator is not None:
            services_to_rollback.append(
                (_ROLLBACK_ORCHESTRATOR_ADDRESS, self._target.orchestrator, RuntimeDomain.ORCHESTRATION)
            )
        if state.started_evaluator and self._target.evaluator is not None:
            services_to_rollback.append((_ROLLBACK_EVALUATOR_ADDRESS, self._target.evaluator, RuntimeDomain.EVALUATION))
        rollback_result = rollback_services(
            state.working_snapshot,
            services_to_rollback,
            information_state_context_resolver=self._information_state_context_resolver,
        )
        self._record_phase_result(state, rollback_result)
        self._fail_apply_state(state)

    def _apply_provisioning_phase(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> None:
        provision_result = _apply_runtime_plan_with_observation(
            self._target,
            self._target.provisioner.apply,
            execution_plan.provisioning,
            state.working_snapshot,
            request=_RuntimePlanApplyRequest(
                address="runtime.apply.provisioning",
                execute_observation=execution_plan.observation_owner is RuntimeDomain.PROVISIONING,
                realization=_RealizationApplyContext(
                    requirements=execution_plan.model.realization_requirements,
                    plan=execution_plan.provisioning,
                    manifest=execution_plan.manifest,
                    artifact_availability=execution_plan.artifact_availability,
                ),
                information_state_context_resolver=self._information_state_context_resolver,
            ),
        )
        self._record_phase_result(state, provision_result)
        if not provision_result.success:
            maybe_synthesize_failure(
                state.diagnostics,
                result=provision_result,
                code=_APPLY_PHASE_FAILED,
                address="runtime.apply.provisioning",
                message="Provisioning apply failed.",
            )
            self._fail_apply_state(state)

    def _apply_evaluation_phase(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> None:
        if execution_plan.evaluation.actionable_operations and self._target.evaluator is not None:
            evaluation_result = _apply_runtime_plan_with_observation(
                self._target,
                self._target.evaluator.start,
                execution_plan.evaluation,
                state.working_snapshot,
                request=_RuntimePlanApplyRequest(
                    address=_APPLY_EVALUATOR_ADDRESS,
                    execute_observation=execution_plan.observation_owner is RuntimeDomain.EVALUATION,
                    information_state_context_resolver=self._information_state_context_resolver,
                ),
            )
            self._record_phase_result(state, evaluation_result)
            if evaluation_result.success:
                state.started_evaluator = True
            else:
                maybe_synthesize_failure(
                    state.diagnostics,
                    result=evaluation_result,
                    code=_APPLY_PHASE_FAILED,
                    address=_APPLY_EVALUATOR_ADDRESS,
                    message="Evaluator failed to start.",
                )
                rollback_result = rollback_services(
                    state.working_snapshot,
                    [(_ROLLBACK_EVALUATOR_ADDRESS, self._target.evaluator, RuntimeDomain.EVALUATION)],
                    information_state_context_resolver=self._information_state_context_resolver,
                )
                self._record_phase_result(state, rollback_result)
                self._fail_apply_state(state)

    def _apply_orchestration_phase(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> None:
        if execution_plan.orchestration.actionable_operations and self._target.orchestrator is not None:
            orchestration_result = _apply_runtime_plan_with_observation(
                self._target,
                self._target.orchestrator.start,
                execution_plan.orchestration,
                state.working_snapshot,
                request=_RuntimePlanApplyRequest(
                    address=_APPLY_ORCHESTRATOR_ADDRESS,
                    execute_observation=execution_plan.observation_owner is RuntimeDomain.ORCHESTRATION,
                    information_state_context_resolver=self._information_state_context_resolver,
                ),
            )
            self._record_phase_result(state, orchestration_result)
            if not orchestration_result.success:
                maybe_synthesize_failure(
                    state.diagnostics,
                    result=orchestration_result,
                    code=_APPLY_PHASE_FAILED,
                    address=_APPLY_ORCHESTRATOR_ADDRESS,
                    message="Orchestrator failed to start.",
                )
                services_to_rollback = [
                    (_ROLLBACK_ORCHESTRATOR_ADDRESS, self._target.orchestrator, RuntimeDomain.ORCHESTRATION),
                ]
                if state.started_evaluator and self._target.evaluator is not None:
                    services_to_rollback.append(
                        (_ROLLBACK_EVALUATOR_ADDRESS, self._target.evaluator, RuntimeDomain.EVALUATION)
                    )
                rollback_result = rollback_services(
                    state.working_snapshot,
                    services_to_rollback,
                    information_state_context_resolver=self._information_state_context_resolver,
                )
                self._record_phase_result(state, rollback_result)
                self._fail_apply_state(state)

    @staticmethod
    def _record_phase_result(state: _RuntimeApplyState, result: ApplyResult) -> None:
        state.diagnostics.extend(result.diagnostics)
        state.changed_addresses.extend(result.changed_addresses)
        state.working_snapshot = result.snapshot
        state.details.update(result.details)

    def _fail_apply_state(self, state: _RuntimeApplyState) -> None:
        self._time_declaration = None
        self._snapshot = state.working_snapshot
        state.failure = ApplyResult(
            success=False,
            snapshot=self._snapshot,
            diagnostics=state.diagnostics,
            changed_addresses=list(dict.fromkeys(state.changed_addresses)),
            details=state.details,
        )

    def _apply_precondition_failure(
        self,
        execution_plan: ExecutionPlan,
        diagnostics: list[Diagnostic],
    ) -> ApplyResult | None:
        precondition_diagnostics = runtime_plan_precondition_diagnostics(
            execution_plan,
            self._target,
            self._snapshot,
        )
        diagnostics.extend(precondition_diagnostics)
        failure = None
        if precondition_diagnostics or not execution_plan.is_valid:
            failure = ApplyResult(
                success=False,
                snapshot=self._snapshot,
                diagnostics=diagnostics,
            )
        elif execution_plan.evaluation.actionable_operations and self._target.evaluator is None:
            diagnostics.append(
                _failure_diagnostic(
                    "runtime.apply-missing-evaluator",
                    _APPLY_EVALUATOR_ADDRESS,
                    "Execution plan requires an evaluator, but the target does not provide one.",
                )
            )
            failure = ApplyResult(
                success=False,
                snapshot=self._snapshot,
                diagnostics=diagnostics,
            )
        elif execution_plan.orchestration.actionable_operations and self._target.orchestrator is None:
            diagnostics.append(
                _failure_diagnostic(
                    "runtime.apply-missing-orchestrator",
                    _APPLY_ORCHESTRATOR_ADDRESS,
                    "Execution plan requires an orchestrator, but the target does not provide one.",
                )
            )
            failure = ApplyResult(
                success=False,
                snapshot=self._snapshot,
                diagnostics=diagnostics,
            )
        elif execution_plan.provisioning.preparation is None:
            validation = _call_backend_diagnostics(
                self._target.provisioner.validate,
                execution_plan.provisioning,
                address="runtime.apply.provisioning.validate",
            )
            diagnostics.extend(validation)
            if _has_error_diagnostic(validation):
                failure = ApplyResult(
                    success=False,
                    snapshot=self._snapshot,
                    diagnostics=diagnostics,
                )
        return failure

    def status(self) -> dict[str, object]:
        info: dict[str, object] = {
            "backend": self._target.name,
            "resources": len(self._snapshot.entries),
            "domains": {
                RuntimeDomain.PROVISIONING.value: len(self._snapshot.for_domain(RuntimeDomain.PROVISIONING)),
                RuntimeDomain.ORCHESTRATION.value: len(self._snapshot.for_domain(RuntimeDomain.ORCHESTRATION)),
                RuntimeDomain.EVALUATION.value: len(self._snapshot.for_domain(RuntimeDomain.EVALUATION)),
            },
        }
        if self._target.orchestrator is not None:
            info["orchestrator"] = self._target.orchestrator.status()
            info["orchestration_results"] = self._target.orchestrator.results()
            info["orchestration_history"] = self._target.orchestrator.history()
        if self._target.evaluator is not None:
            info["evaluator"] = self._target.evaluator.status()
            info["evaluation_results"] = self._target.evaluator.results()
            info["evaluation_history"] = self._target.evaluator.history()
        if self._target.time_runtime is not None and self._snapshot.time_model_state is not None:
            info["time_model_state"] = self.read_time_state().model_dump(mode="json")
        if self._participant_execution_policies:
            info["participant_clock_driver"] = self.participant_clock_driver_status()
        return info

    def destroy(self) -> ApplyResult:
        if not self._stop_participant_clock_driver():
            return ApplyResult(
                success=False,
                snapshot=self._snapshot,
                diagnostics=[
                    Diagnostic(
                        code="runtime.participant-clock-driver-stop-timeout",
                        domain="participant",
                        address="runtime.destroy",
                        message="Destroy did not start because the participant clock driver is still active.",
                    )
                ],
            )
        diagnostics: list[Diagnostic] = []
        changed_addresses: list[str] = []
        working_snapshot = self._snapshot
        phases_succeeded = True

        if self._target.orchestrator is not None:
            stop_result = _call_backend_apply(
                self._target.orchestrator.stop,
                working_snapshot,
                address="runtime.destroy.orchestrator",
                snapshot=working_snapshot,
                realization=_RealizationApplyContext(stop_domain=RuntimeDomain.ORCHESTRATION),
                call=_BackendCallContext(
                    information_state_context_resolver=self._information_state_context_resolver,
                ),
            )
            diagnostics.extend(stop_result.diagnostics)
            changed_addresses.extend(stop_result.changed_addresses)
            working_snapshot = stop_result.snapshot
            if not stop_result.success:
                phases_succeeded = False
                maybe_synthesize_failure(
                    diagnostics,
                    result=stop_result,
                    code=_DESTROY_PHASE_FAILED,
                    address="runtime.destroy.orchestrator",
                    message="Orchestrator stop failed.",
                )

        if self._target.evaluator is not None:
            stop_result = _call_backend_apply(
                self._target.evaluator.stop,
                working_snapshot,
                address="runtime.destroy.evaluator",
                snapshot=working_snapshot,
                realization=_RealizationApplyContext(stop_domain=RuntimeDomain.EVALUATION),
                call=_BackendCallContext(
                    information_state_context_resolver=self._information_state_context_resolver,
                ),
            )
            diagnostics.extend(stop_result.diagnostics)
            changed_addresses.extend(stop_result.changed_addresses)
            working_snapshot = stop_result.snapshot
            if not stop_result.success:
                phases_succeeded = False
                maybe_synthesize_failure(
                    diagnostics,
                    result=stop_result,
                    code=_DESTROY_PHASE_FAILED,
                    address="runtime.destroy.evaluator",
                    message="Evaluator stop failed.",
                )

        provisioning_entries = working_snapshot.for_domain(RuntimeDomain.PROVISIONING)
        delete_plan = ProvisioningPlan(
            resources={},
            operations=[
                ProvisionOp(
                    action=ChangeAction.DELETE,
                    address=address,
                    resource_type=provisioning_entries[address].resource_type,
                    payload=provisioning_entries[address].payload,
                    ordering_dependencies=(provisioning_entries[address].ordering_dependencies),
                    refresh_dependencies=(provisioning_entries[address].refresh_dependencies),
                )
                for address in snapshot_delete_order(provisioning_entries)
            ],
            realization_envelope=working_snapshot.realization_envelope,
        )
        provision_result = _call_backend_apply(
            self._target.provisioner.apply,
            delete_plan,
            working_snapshot,
            address="runtime.destroy.provisioning",
            snapshot=working_snapshot,
            call=_BackendCallContext(
                information_state_context_resolver=self._information_state_context_resolver,
            ),
        )
        diagnostics.extend(provision_result.diagnostics)
        changed_addresses.extend(provision_result.changed_addresses)
        working_snapshot = provision_result.snapshot
        if not provision_result.success:
            phases_succeeded = False
            maybe_synthesize_failure(
                diagnostics,
                result=provision_result,
                code=_DESTROY_PHASE_FAILED,
                address="runtime.destroy.provisioning",
                message="Provisioning destroy failed.",
            )

        self._snapshot = working_snapshot
        return ApplyResult(
            success=phases_succeeded and not _has_error_diagnostic(diagnostics),
            snapshot=self._snapshot,
            diagnostics=diagnostics,
            changed_addresses=changed_addresses,
        )
