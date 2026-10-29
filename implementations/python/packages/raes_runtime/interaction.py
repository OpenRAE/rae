"""Runtime manager for compiled SDL runtime plans."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import TypedDict, Unpack

from raes_contracts.augmentation_preparation import AugmentationPreparation
from raes_contracts.contracts import (
    ArtifactAvailabilityContext,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.immutable_history import mutable_history_value
from raes_contracts.materialization import MaterializationSubmission
from raes_contracts.planning import PlanScope, RuntimeDomain
from raes_contracts.realization_profiles import PlanProfileAuthority
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.models import ExecutionPlan
from raes_processor.planner import plan

from .apply_failure import maybe_synthesize_failure
from .backend_calls import _BackendCallContext, _call_backend_diagnostics, _RealizationApplyContext
from .backend_observation_calls import _RuntimePlanApplyRequest
from .control_plane_lifecycle import runtime_owned
from .diagnostics import _failure_diagnostic, _has_error_diagnostic
from .interaction_dispatch import RuntimeInteractionDispatchMixin
from .interaction_evaluation import RuntimeInteractionEvaluationMixin
from .manager_augmentation import prepare_execution_augmentation
from .manager_destroy import _DestroyPhaseMixin
from .manager_inventory import RuntimeInventoryMixin
from .manager_lifecycle import RuntimeManagerLifecycleMixin, manager_owned
from .manager_plan_admission import reference_participant_driver_diagnostics, runtime_plan_precondition_diagnostics

_RUNTIME_APPLY_ADDRESS, _APPLY_EVALUATOR_ADDRESS = "runtime.apply", "runtime.apply.evaluator"
_APPLY_ORCHESTRATOR_ADDRESS = "runtime.apply.orchestrator"
_APPLY_PHASE_FAILED, _DESTROY_PHASE_FAILED = "runtime.apply-phase-failed", "runtime.destroy-phase-failed"
_ROLLBACK_EVALUATOR_ADDRESS = "runtime.rollback.evaluator"
_ROLLBACK_ORCHESTRATOR_ADDRESS = "runtime.rollback.orchestrator"


class InteractionPlanningOptions(TypedDict, total=False):
    run_scope: PlanScope | None
    refresh_evaluation: bool


@dataclass
class _RuntimeApplyState:
    working_snapshot: RuntimeSnapshot
    diagnostics: list[Diagnostic]
    changed_addresses: list[str]
    details: dict[str, object]
    failure: ApplyResult | None = None
    materialization_attestation: MaterializationSubmission | None = None
    augmentation_previews: dict[RuntimeDomain, AugmentationPreparation] = field(default_factory=dict)
    phase_key: str = ""
    identity: object | None = None


class RuntimeInteractionMixin(
    RuntimeInteractionDispatchMixin,
    RuntimeInteractionEvaluationMixin,
    _DestroyPhaseMixin,
    RuntimeManagerLifecycleMixin,
    RuntimeInventoryMixin,
):
    """Plans and executes SDL runtime work against a target."""

    @runtime_owned
    def plan(
        self,
        scenario: object,
        snapshot: RuntimeSnapshot | None = None,
        *,
        parameters: dict[str, object] | None = None,
        profile: str | None = None,
        artifact_availability: ArtifactAvailabilityContext | None = None,
        profile_authority: PlanProfileAuthority | None = None,
        **options: Unpack[InteractionPlanningOptions],
    ) -> ExecutionPlan:
        run_scope = options.pop("run_scope", None)
        refresh_evaluation = options.pop("refresh_evaluation", False)
        if options:
            raise TypeError("unsupported interaction planning option")
        model = compile_scenario_runtime_model(
            scenario, parameters=parameters, profile=profile, profile_authority=profile_authority
        )
        effective_snapshot = snapshot if snapshot is not None else self.snapshot
        # The manager owns target selection; fold it into the run/instantiation
        # identity supplied by the caller so the planner receives a single scope.
        scope = PlanScope(
            target_name=self._target.name,
            run_id=run_scope.run_id if run_scope is not None else None,
            instantiation_id=run_scope.instantiation_id if run_scope is not None else None,
        )
        execution_plan = plan(
            model,
            self._target.manifest,
            effective_snapshot,
            scope=scope,
            artifact_availability=artifact_availability,
            refresh_evaluation=refresh_evaluation,
            profile_context=getattr(self._target.provisioner, "domain_profile_context", None),
        )
        return replace(
            execution_plan, diagnostics=[*execution_plan.diagnostics, *reference_participant_driver_diagnostics(model)]
        )

    @manager_owned
    def apply(self, execution_plan: ExecutionPlan) -> ApplyResult:
        diagnostics: list[Diagnostic] = list(execution_plan.diagnostics)

        precondition_failure = self._apply_precondition_failure(execution_plan, diagnostics)
        if precondition_failure is not None:
            return precondition_failure
        driver_precondition = self._participant_driver_apply_precondition()
        if driver_precondition is not None:
            return driver_precondition
        self._time_declaration = None

        self.register_planner_produced_plan(execution_plan)
        self._interaction_plan = deepcopy(execution_plan)
        return self._apply_prepared_execution(execution_plan, diagnostics)

    def _apply_prepared_execution(self, execution_plan: ExecutionPlan, diagnostics: list[Diagnostic]) -> ApplyResult:
        with self._mutation_authority.external_call():
            execution_plan, previews, scope_diagnostics = self._execution_adapter.call(
                "effect",
                prepare_execution_augmentation,
                execution_plan,
                self._target,
                self._snapshot,
                self._materialization_archive,
                timeout_ms=self._supervision.execution_ms,
            )
        self.register_planner_produced_plan(execution_plan)
        diagnostics.extend(scope_diagnostics)
        if _has_error_diagnostic(scope_diagnostics):
            return ApplyResult(success=False, snapshot=self._snapshot, diagnostics=diagnostics)

        state = _RuntimeApplyState(
            working_snapshot=execution_plan.base_snapshot,
            diagnostics=diagnostics,
            changed_addresses=[],
            details={},
            augmentation_previews=previews,
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
        from .runtime_run_driver import APPLICATION_PHASES

        for phase in APPLICATION_PHASES:
            if state.failure is not None:
                break
            getattr(self, phase)(execution_plan, state)

    def _apply_participant_start_phase(self, execution_plan: ExecutionPlan, state: _RuntimeApplyState) -> None:
        if not self._start_participant_execution_phase(execution_plan, state):
            self._fail_apply_state(state)

    def _apply_provisioning_phase(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> None:
        provision_result = self._interaction_plan_call(
            self._target.provisioner.apply,
            execution_plan.provisioning,
            state.working_snapshot,
            idempotency_key=state.phase_key,
            identity=state.identity,
            request=_RuntimePlanApplyRequest(
                materialization_archive=self._materialization_archive,
                address="runtime.apply.provisioning",
                execute_observation=execution_plan.observation_owner is RuntimeDomain.PROVISIONING,
                realization=_RealizationApplyContext(
                    requirements=execution_plan.model.realization_requirements,
                    plan=execution_plan.provisioning,
                    manifest=execution_plan.manifest,
                    artifact_availability=execution_plan.artifact_availability,
                    expected_augmentation=state.augmentation_previews.get(RuntimeDomain.PROVISIONING),
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
            evaluation_result = self._interaction_plan_call(
                self._target.evaluator.start,
                execution_plan.evaluation,
                state.working_snapshot,
                idempotency_key=state.phase_key,
                identity=state.identity,
                request=_RuntimePlanApplyRequest(
                    materialization_archive=self._materialization_archive,
                    address=_APPLY_EVALUATOR_ADDRESS,
                    execute_observation=execution_plan.observation_owner is RuntimeDomain.EVALUATION,
                    realization=_RealizationApplyContext(
                        manifest=execution_plan.manifest,
                        expected_augmentation=state.augmentation_previews.get(RuntimeDomain.EVALUATION),
                    ),
                    information_state_context_resolver=self._information_state_context_resolver,
                ),
            )
            self._record_phase_result(state, evaluation_result)
            if not evaluation_result.success:
                maybe_synthesize_failure(
                    state.diagnostics,
                    result=evaluation_result,
                    code=_APPLY_PHASE_FAILED,
                    address=_APPLY_EVALUATOR_ADDRESS,
                    message="Evaluator failed to start.",
                )
                self._fail_apply_state(state)

    def _apply_orchestration_phase(
        self,
        execution_plan: ExecutionPlan,
        state: _RuntimeApplyState,
    ) -> None:
        if execution_plan.orchestration.actionable_operations and self._target.orchestrator is not None:
            orchestration_result = self._interaction_plan_call(
                self._target.orchestrator.start,
                execution_plan.orchestration,
                state.working_snapshot,
                idempotency_key=state.phase_key,
                identity=state.identity,
                request=_RuntimePlanApplyRequest(
                    materialization_archive=self._materialization_archive,
                    address=_APPLY_ORCHESTRATOR_ADDRESS,
                    execute_observation=execution_plan.observation_owner is RuntimeDomain.ORCHESTRATION,
                    realization=_RealizationApplyContext(
                        manifest=execution_plan.manifest,
                        expected_augmentation=state.augmentation_previews.get(RuntimeDomain.ORCHESTRATION),
                    ),
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
                self._fail_apply_state(state)

    @staticmethod
    def _record_phase_result(state: _RuntimeApplyState, result: ApplyResult) -> None:
        if result.materialization_attestation is not None:
            state.materialization_attestation = result.materialization_attestation
        state.diagnostics.extend(result.diagnostics)
        state.changed_addresses.extend(result.changed_addresses)
        state.working_snapshot = result.snapshot
        state.details.update(result.details)

    def _fail_apply_state(self, state: _RuntimeApplyState) -> None:
        self._time_declaration = None
        state.failure = ApplyResult(
            success=False,
            snapshot=self._snapshot,
            diagnostics=state.diagnostics,
            changed_addresses=list(dict.fromkeys(state.changed_addresses)),
            details=state.details,
            materialization_attestation=state.materialization_attestation,
        )

    def _apply_precondition_failure(
        self,
        execution_plan: ExecutionPlan,
        diagnostics: list[Diagnostic],
    ) -> ApplyResult | None:
        from raes_contracts.runtime_state import OperationKind

        from .control_plane_operation_context import operation_admission_context
        from .operation_policy_admission import execution_budget_ms

        for domain in (RuntimeDomain.PROVISIONING, RuntimeDomain.EVALUATION, RuntimeDomain.ORCHESTRATION):
            phase = getattr(execution_plan, domain.value)
            operation_admission_context(self, kind=OperationKind(domain.value), request=phase)
            try:
                execution_budget_ms(phase, self._supervision)
            except ValueError:
                diagnostics.append(
                    _failure_diagnostic(
                        "runtime.control-plane.execution-policy-unsupported",
                        "runtime.apply",
                        "The selected execution policy cannot be enforced by this runtime composition.",
                    )
                )
                return ApplyResult(False, self._snapshot, diagnostics=diagnostics)
        precondition_diagnostics = runtime_plan_precondition_diagnostics(
            execution_plan,
            self._target,
            self._snapshot,
            durable_lifecycle_available=self._store_commits.crash_atomic,
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
            with self._mutation_authority.external_call():
                validation = self._execution_adapter.call(
                    "effect",
                    _call_backend_diagnostics,
                    self._target.provisioner.validate,
                    execution_plan.provisioning,
                    address="runtime.apply.provisioning.validate",
                    timeout_ms=self._supervision.execution_ms,
                )
            diagnostics.extend(validation)
            if _has_error_diagnostic(validation):
                failure = ApplyResult(
                    success=False,
                    snapshot=self._snapshot,
                    diagnostics=diagnostics,
                )
        return failure

    @manager_owned
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
            with self._mutation_authority.external_call():
                info["orchestrator"] = self._execution_adapter.call(
                    "control",
                    self._target.orchestrator.status,
                    timeout_ms=self._supervision.observation_ms,
                )
            info["orchestration_results"] = deepcopy(self._snapshot.orchestration_results)
            info["orchestration_history"] = mutable_history_value(self._snapshot.orchestration_history)
        if self._target.evaluator is not None:
            with self._mutation_authority.external_call():
                info["evaluator"] = self._execution_adapter.call(
                    "control",
                    self._target.evaluator.status,
                    timeout_ms=self._supervision.observation_ms,
                )
            info["evaluation_results"] = deepcopy(self._snapshot.evaluation_results)
            info["evaluation_history"] = mutable_history_value(self._snapshot.evaluation_history)
        if self._target.time_runtime is not None and self._snapshot.time_model_state is not None:
            info["time_model_state"] = self.read_time_state().model_dump(mode="json")
        if self._participant_execution_policies:
            info["participant_clock_driver"] = self.participant_clock_driver_status()
        return info

    @manager_owned
    def destroy(self) -> ApplyResult:
        refusal = self._clock_driver_stop_refusal()
        if refusal is not None:
            return refusal
        diagnostics: list[Diagnostic] = []
        changed_addresses: list[str] = []
        working_snapshot = self._snapshot
        phases_succeeded = True
        service_phases = (
            (
                self._target.orchestrator,
                "runtime.destroy.orchestrator",
                RuntimeDomain.ORCHESTRATION,
                "Orchestrator stop failed.",
            ),
            (
                self._target.evaluator,
                "runtime.destroy.evaluator",
                RuntimeDomain.EVALUATION,
                "Evaluator stop failed.",
            ),
        )
        for service, address, domain, message in service_phases:
            stop_result = self._stop_service_phase(service, working_snapshot, address=address, domain=domain)
            if stop_result is None:
                continue
            diagnostics.extend(stop_result.diagnostics)
            changed_addresses.extend(stop_result.changed_addresses)
            working_snapshot = stop_result.snapshot
            if not stop_result.success:
                phases_succeeded = False
                maybe_synthesize_failure(
                    diagnostics,
                    result=stop_result,
                    code=_DESTROY_PHASE_FAILED,
                    address=address,
                    message=message,
                )
                return ApplyResult(
                    success=False,
                    snapshot=working_snapshot,
                    diagnostics=diagnostics,
                    changed_addresses=list(dict.fromkeys(changed_addresses)),
                )
        provision_result = self._interaction_backend_call(
            self._target.provisioner.apply,
            self._destroy_delete_plan(working_snapshot),
            working_snapshot,
            address="runtime.destroy.provisioning",
            snapshot=working_snapshot,
            call=_BackendCallContext(
                information_state_context_resolver=self._information_state_context_resolver,
            ),
        )
        diagnostics.extend(provision_result.diagnostics)
        changed_addresses.extend(provision_result.changed_addresses)
        if not provision_result.success:
            phases_succeeded = False
            maybe_synthesize_failure(
                diagnostics,
                result=provision_result,
                code=_DESTROY_PHASE_FAILED,
                address="runtime.destroy.provisioning",
                message="Provisioning destroy failed.",
            )
        return ApplyResult(
            success=phases_succeeded and not _has_error_diagnostic(diagnostics),
            snapshot=self._snapshot,
            diagnostics=diagnostics,
            changed_addresses=changed_addresses,
        )
