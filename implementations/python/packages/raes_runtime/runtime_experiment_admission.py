"""Read-only complete-entry checks before experiment configuration effects."""

from raes_backend_protocols.trial_control_admission import require_trial_control_capability
from raes_contracts.contracts import BackendOperationCapabilitiesModel
from raes_contracts.contracts.trial_controls import required_trial_operation_guarantees
from raes_contracts.runtime_state import RuntimeSnapshot

from .control_plane_submission import _provisioning_submission_diagnostics
from .manager_plan_admission import runtime_plan_precondition_diagnostics
from .operation_policy_admission import execution_budget_ms


def admit_trial(engine, realized, request, services):
    plan = realized.execution_plan
    if not plan.is_valid or plan.manifest != engine._target.manifest:
        raise ValueError("trial realization does not match the installed target")
    diagnostics = runtime_plan_precondition_diagnostics(
        plan, engine._target, RuntimeSnapshot(), durable_lifecycle_available=engine._store_commits.crash_atomic
    )
    diagnostics.extend(_provisioning_submission_diagnostics(plan.provisioning, RuntimeSnapshot(), plan.manifest))
    if diagnostics:
        raise ValueError("trial plan cannot be admitted by the installed runtime: " + diagnostics[0].code)
    for domain, component in (
        ("provisioning", "provisioner"),
        ("evaluation", "evaluator"),
        ("orchestration", "orchestrator"),
    ):
        phase = getattr(plan, domain)
        execution_budget_ms(phase, engine._supervision)
        if phase.operations and getattr(engine._target, component) is None:
            raise ValueError("trial plan requires an unavailable runtime component")
    require_trial_control_capability(engine._target.manifest, request.execution_controls, request.cleanup_plan)
    required = set(required_trial_operation_guarantees(request.execution_controls, request.cleanup_plan.retry_policy))
    if required:
        provider = engine._target.operation_provider
        if provider is None:
            raise ValueError("trial guarantees require an installed operation provider")
        capabilities = engine._execution_adapter.call(
            "control", provider.operation_capabilities, timeout_ms=engine._supervision.admission_ms
        )
        capabilities = BackendOperationCapabilitiesModel.model_validate(capabilities.model_dump(mode="json"))
        if capabilities.backend_id != engine.target_name or not required <= set(capabilities.guarantees):
            raise ValueError("installed operation provider cannot satisfy trial guarantees")
    policy = request.cleanup_plan.retry_policy
    if policy.max_attempts > 1000:
        raise ValueError("authored retry limit exceeds installed runtime capacity")
    if (
        policy.max_attempts > 1
        and policy.after_effect_policy in {"reset", "compensate"}
        and not callable(getattr(services, "prepare_retry", None))
    ):
        raise ValueError("authored recovery policy requires an installed retry preparation owner")
    engine._execution_adapter.call("control", services.admit, request, timeout_ms=engine._supervision.admission_ms)
