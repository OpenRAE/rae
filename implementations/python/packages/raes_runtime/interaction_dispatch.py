"""Lifecycle modules dispatch through the runtime's sole invocation ledger."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, TypedDict, Unpack, cast

from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, OperationKind, OperationReceipt, OperationState, RuntimeSnapshot

from .backend_calls import _BackendCallContext, _call_backend_apply, _RealizationApplyContext
from .backend_observation_calls import _RuntimePlanApplyRequest
from .control_plane_execution import OperationExecutionRequest, execute_operation
from .control_plane_operation_context import operation_admission_context
from .control_plane_submission import control_plane_plan_diagnostics
from .participant_activity import resolve_participant_activity_controls

if TYPE_CHECKING:
    from .control_plane_configuration import ControlPlaneConfiguration
    from .registry import RuntimeTarget


class InteractionCallOptions(TypedDict, total=False):
    realization: _RealizationApplyContext | None
    call: _BackendCallContext | None
    runtime_composition: bool
    result_validator: Callable[[ApplyResult, RuntimeSnapshot], ApplyResult] | None


class RuntimeInteractionDispatchMixin:
    def _initialize_interaction(self, target: RuntimeTarget, config: ControlPlaneConfiguration) -> None:
        from .registry import RuntimeTargetComponents, _validate_runtime_target_shape

        _validate_runtime_target_shape(
            manifest=target.manifest,
            components=RuntimeTargetComponents(
                provisioner=target.provisioner,
                orchestrator=target.orchestrator,
                evaluator=target.evaluator,
                participant_runtime=target.participant_runtime,
                time_runtime=target.time_runtime,
                observation_runtime=target.observation_runtime,
                recovery_observer=target.recovery_observer,
                operation_provider=getattr(target, "operation_provider", None),
            ),
        )
        self._participant_activity_controls = resolve_participant_activity_controls(config.stochastic_controls)
        self._time_declaration = None
        self._interaction_plan = None
        self._initialize_participant_scheduler()

    def _interaction_plan_call(
        self,
        method: Callable[..., object],
        phase: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
        snapshot: RuntimeSnapshot,
        *,
        request: _RuntimePlanApplyRequest,
    ) -> ApplyResult:
        domain = _phase_domain(phase)
        results = []
        context = operation_admission_context(self, kind=OperationKind(domain.value), request=phase)
        receipt = execute_operation(
            self,
            OperationExecutionRequest(
                domain=domain,
                method=method,
                plan=phase,
                address=request.address,
                diagnostics=[],
                base_snapshot=snapshot,
                idempotency_key="",
                context=context,
                request_fingerprint=context.request_commitment,
                realization=request.realization,
                execute_observation=request.execute_observation,
                result_sink=results.append,
                admission_diagnostics=lambda: control_plane_plan_diagnostics(self, phase, domain),
            ),
        )
        return self._interaction_phase_result(receipt, results)

    def _interaction_backend_call(
        self,
        method: Callable[..., object],
        *args: object,
        address: str,
        snapshot: RuntimeSnapshot,
        **options: Unpack[InteractionCallOptions],
    ) -> ApplyResult:
        """Keep time, stop and inventory callbacks inside one admitted phase."""
        realization = options.pop("realization", None) or _RealizationApplyContext()
        call = options.pop("call", None)
        runtime_composition = options.pop("runtime_composition", False)
        result_validator = options.pop("result_validator", None)
        if options:
            raise TypeError("unsupported interaction callback option")
        native_plan = bool(args and isinstance(args[0], (ProvisioningPlan, OrchestrationPlan, EvaluationPlan)))
        phase = args[0] if native_plan else ProvisioningPlan()
        domain = RuntimeDomain.PARTICIPANT if runtime_composition else realization.stop_domain or _phase_domain(phase)
        context = operation_admission_context(
            self,
            kind=OperationKind(domain.value) if native_plan else OperationKind.COMPOSITION_PHASE,
            request={"phase": address, "plan": phase, "arguments": _interaction_arguments(args, call)},
        )
        results = []

        def invoke(predecessor: RuntimeSnapshot, operation_id: str, attempt_id: str) -> tuple[ApplyResult, None]:
            bound_args = (*args[:-1], predecessor)
            result = (
                method(predecessor)
                if runtime_composition
                else _call_backend_apply(
                    method,
                    *bound_args,
                    address=address,
                    snapshot=predecessor,
                    realization=realization,
                    call=replace(call or _BackendCallContext(), operation_id=operation_id, attempt_id=attempt_id),
                )
            )
            if runtime_composition:
                from .interaction_results import validated_composition_result

                result = validated_composition_result(self, result, predecessor, address)
            if result_validator is not None:
                result = result_validator(result, predecessor)
            return result, None

        receipt = execute_operation(
            self,
            OperationExecutionRequest(
                domain=domain,
                method=method,
                plan=phase,
                address=address,
                diagnostics=[],
                base_snapshot=snapshot,
                idempotency_key="",
                context=context,
                request_fingerprint=context.request_commitment,
                local_executor=None if native_plan else invoke,
                realization=realization,
                execute_observation=False,
                result_sink=results.append,
            ),
        )
        return self._interaction_phase_result(receipt, results)

    def _interaction_phase_result(self, receipt: OperationReceipt, results: list[ApplyResult]) -> ApplyResult:
        self._reload_derived_state()
        status = self.get_operation(receipt.operation_id)
        if status is None:
            return ApplyResult(False, self._snapshot, diagnostics=list(receipt.diagnostics))
        if results and status.state not in {OperationState.ACCEPTED, OperationState.RUNNING}:
            return cast(
                ApplyResult,
                replace(
                    results[0],
                    snapshot=self._snapshot,
                    success=status.state is OperationState.SUCCEEDED,
                    diagnostics=list(status.diagnostics),
                    changed_addresses=list(status.changed_addresses),
                    materialization_attestation=(
                        results[0].materialization_attestation if results[0].snapshot == self._snapshot else None
                    ),
                ),
            )
        return ApplyResult(
            success=status.state is OperationState.SUCCEEDED,
            snapshot=self._snapshot,
            diagnostics=list(status.diagnostics),
            changed_addresses=list(status.changed_addresses),
        )


def _phase_domain(phase: object) -> RuntimeDomain:
    if isinstance(phase, EvaluationPlan):
        return RuntimeDomain.EVALUATION
    if isinstance(phase, OrchestrationPlan):
        return RuntimeDomain.ORCHESTRATION
    return RuntimeDomain.PROVISIONING


def _interaction_arguments(args: tuple[object, ...], call: _BackendCallContext | None) -> list[object]:
    dependencies = () if call is None else call.service_dependencies
    return [
        next(
            ({"installed_service": index} for index, dependency in enumerate(dependencies) if argument is dependency),
            argument,
        )
        for argument in args[:-1]
    ]
