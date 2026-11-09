"""Lifecycle modules dispatch through the runtime's sole invocation ledger."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, TypedDict, Unpack, cast

from raes_contracts.operation_lifecycle import OperationAdmissionContext
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
    operation_aware: bool
    result_validator: Callable[[ApplyResult, RuntimeSnapshot], ApplyResult] | None
    idempotency_key: str
    identity: object | None


@dataclass(frozen=True)
class ComposedOperation:
    """Identity and admitted context of the operation that runs one composition method."""

    operation_id: str
    context: OperationAdmissionContext


@dataclass(frozen=True)
class _InteractionInvocation:
    address: str
    realization: _RealizationApplyContext
    call: _BackendCallContext | None
    runtime_composition: bool
    result_validator: Callable[[ApplyResult, RuntimeSnapshot], ApplyResult] | None
    cancelled: list[tuple[ApplyResult, RuntimeSnapshot]]
    context: OperationAdmissionContext | None = None
    operation_aware: bool = False


def _cancellation_reader(
    plane: object, cancelled: list[tuple[ApplyResult, RuntimeSnapshot]], address: str
) -> Callable[[], ApplyResult | None]:
    """Read the last state that a composition method settled before a cancellation."""

    def cancellation_result() -> ApplyResult | None:
        if not cancelled:
            return None
        from .interaction_results import validated_composition_result

        settled, predecessor = cancelled[-1]
        return validated_composition_result(plane, settled, predecessor, address)

    return cancellation_result


def _interaction_invoker(
    plane: object, method: Callable[..., object], args: tuple[object, ...], invocation: _InteractionInvocation
) -> Callable[[RuntimeSnapshot, str, str], tuple[ApplyResult, None]]:
    """Return the local executor that applies one interaction callback at its predecessor state."""

    def invoke(predecessor: RuntimeSnapshot, operation_id: str, attempt_id: str) -> tuple[ApplyResult, None]:
        if invocation.runtime_composition:
            from .interaction_results import validated_composition_result

            def sink(value: ApplyResult) -> None:
                invocation.cancelled.append((value, predecessor))

            settled = (
                method(predecessor, sink, ComposedOperation(operation_id, invocation.context))
                if invocation.operation_aware
                else method(predecessor, sink)
            )
            result = validated_composition_result(plane, settled, predecessor, invocation.address)
        else:
            call = replace(invocation.call or _BackendCallContext(), operation_id=operation_id, attempt_id=attempt_id)
            result = _call_backend_apply(
                method,
                *args[:-1],
                predecessor,
                address=invocation.address,
                snapshot=predecessor,
                realization=invocation.realization,
                call=call,
            )
        if invocation.result_validator is not None:
            result = invocation.result_validator(result, predecessor)
        return result, None

    return invoke


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
        idempotency_key: str = "",
        identity: object | None = None,
    ) -> ApplyResult:
        domain = _phase_domain(phase)
        results = []
        context = operation_admission_context(self, kind=OperationKind(domain.value), request=phase, identity=identity)
        receipt = execute_operation(
            self,
            OperationExecutionRequest(
                domain=domain,
                method=method,
                plan=phase,
                address=request.address,
                diagnostics=[],
                base_snapshot=snapshot,
                idempotency_key=idempotency_key,
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
        operation_aware = options.pop("operation_aware", False)
        result_validator = options.pop("result_validator", None)
        idempotency_key = options.pop("idempotency_key", "")
        identity = options.pop("identity", None)
        if options:
            raise TypeError("unsupported interaction callback option")
        native_plan = bool(args and isinstance(args[0], (ProvisioningPlan, OrchestrationPlan, EvaluationPlan)))
        phase = args[0] if native_plan else ProvisioningPlan()
        domain = RuntimeDomain.PARTICIPANT if runtime_composition else realization.stop_domain or _phase_domain(phase)
        context = operation_admission_context(
            self,
            kind=OperationKind(domain.value) if native_plan else OperationKind.COMPOSITION_PHASE,
            request={"phase": address, "plan": phase, "arguments": _interaction_arguments(args, call)},
            identity=identity,
        )
        results = []
        # A composition method reports the state that it settled before a cancellation, with its predecessor.
        cancelled: list[tuple[ApplyResult, RuntimeSnapshot]] = []
        invoke = _interaction_invoker(
            self,
            method,
            args,
            _InteractionInvocation(
                address,
                realization,
                call,
                runtime_composition,
                result_validator,
                cancelled,
                context=context,
                operation_aware=operation_aware,
            ),
        )
        receipt = execute_operation(
            self,
            OperationExecutionRequest(
                domain=domain,
                method=method,
                plan=phase,
                address=address,
                diagnostics=[],
                base_snapshot=snapshot,
                idempotency_key=idempotency_key,
                context=context,
                request_fingerprint=context.request_commitment,
                local_executor=None if native_plan else invoke,
                realization=realization,
                execute_observation=False,
                result_sink=results.append,
                cancellation_result=_cancellation_reader(self, cancelled, address) if runtime_composition else None,
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
