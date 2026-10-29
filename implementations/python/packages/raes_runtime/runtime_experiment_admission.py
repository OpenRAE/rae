"""Read-only complete-entry checks before experiment configuration effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_backend_protocols.trial_control_admission import require_trial_control_capability
from raes_contracts.contracts import BackendOperationCapabilitiesModel
from raes_contracts.contracts.trial_controls import required_trial_operation_guarantees
from raes_contracts.errors import ConflictError, InvalidInputError, OperationalError
from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_submission import _provisioning_submission_diagnostics
from .manager_plan_admission import runtime_plan_precondition_diagnostics
from .operation_policy_admission import execution_budget_ms
from .runtime_trial_services import call_installed_owner

if TYPE_CHECKING:
    from raes_contracts.trial_unit import TrialUnitRequest
    from raes_processor.trial_realization import TrialRealization

    from .control_plane import RuntimeControlPlane
    from .runtime_trial_services import TrialRuntimeServices


def admit_trial(
    engine: RuntimeControlPlane, realized: TrialRealization, request: TrialUnitRequest, services: TrialRuntimeServices
) -> None:
    _require_plan(engine, realized)
    require_trial_control_capability(engine._target.manifest, request.execution_controls, request.cleanup_plan)
    _require_operation_guarantees(engine, request)
    _require_retry_owner(request, services)
    call_installed_owner(
        engine._execution_adapter,
        services.admit,
        request,
        timeout_ms=engine._supervision.admission_ms,
        failure=ConflictError,
        message="installed trial services refused the trial",
    )


def _require_plan(engine: RuntimeControlPlane, realized: TrialRealization) -> None:
    plan = realized.execution_plan
    if not plan.is_valid or plan.manifest != engine._target.manifest:
        raise ConflictError("trial realization does not match the installed target")
    diagnostics = runtime_plan_precondition_diagnostics(
        plan, engine._target, RuntimeSnapshot(), durable_lifecycle_available=engine._store_commits.crash_atomic
    )
    diagnostics.extend(_provisioning_submission_diagnostics(plan.provisioning, RuntimeSnapshot(), plan.manifest))
    if diagnostics:
        raise ConflictError("trial plan cannot be admitted by the installed runtime: " + diagnostics[0].code)
    for domain, component in (
        ("provisioning", "provisioner"),
        ("evaluation", "evaluator"),
        ("orchestration", "orchestrator"),
    ):
        phase = getattr(plan, domain)
        execution_budget_ms(phase, engine._supervision)
        if phase.operations and getattr(engine._target, component) is None:
            raise ConflictError("trial plan requires an unavailable runtime component")


def _require_operation_guarantees(engine: RuntimeControlPlane, request: TrialUnitRequest) -> None:
    required = set(required_trial_operation_guarantees(request.execution_controls, request.cleanup_plan.retry_policy))
    if required:
        provider = engine._target.operation_provider
        if provider is None:
            raise ConflictError("trial guarantees require an installed operation provider")
        capabilities = call_installed_owner(
            engine._execution_adapter,
            provider.operation_capabilities,
            timeout_ms=engine._supervision.admission_ms,
            failure=OperationalError,
            message="installed operation provider capabilities are unavailable",
        )
        if not isinstance(capabilities, BackendOperationCapabilitiesModel):
            raise InvalidInputError("provider returned an invalid operation carrier")
        # The capability model refuses with ValueError; this admission owns the refusal (E9).
        try:
            capabilities = BackendOperationCapabilitiesModel.model_validate(capabilities.model_dump(mode="json"))
        except ValueError as exc:
            raise InvalidInputError("provider returned an invalid operation carrier") from exc
        if capabilities.backend_id != engine.target_name or not required <= set(capabilities.guarantees):
            raise ConflictError("installed operation provider cannot satisfy trial guarantees")


def _require_retry_owner(request: TrialUnitRequest, services: TrialRuntimeServices) -> None:
    policy = request.cleanup_plan.retry_policy
    if policy.max_attempts > 1000:
        raise ConflictError("authored retry limit exceeds installed runtime capacity")
    if (
        policy.max_attempts > 1
        and policy.after_effect_policy in {"reset", "compensate"}
        and not callable(getattr(services, "prepare_retry", None))
    ):
        raise ConflictError("authored recovery policy requires an installed retry preparation owner")
