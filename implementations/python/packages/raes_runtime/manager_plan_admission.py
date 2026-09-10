"""Precondition checks for runtime-manager execution plans."""

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ExecutionPlan

from .diagnostics import _failure_diagnostic
from .observation_execution import observation_submission_diagnostic
from .registry import RuntimeTarget

_RUNTIME_APPLY_ADDRESS = "runtime.apply"


def runtime_plan_precondition_diagnostics(
    execution_plan: ExecutionPlan,
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    """Return every deterministic plan-admission failure for a manager apply."""
    diagnostics = _provenance_diagnostics(execution_plan, target, snapshot)
    phase_plans = {
        "provisioning": execution_plan.provisioning,
        "evaluation": execution_plan.evaluation,
        "orchestration": execution_plan.orchestration,
    }
    observation_diagnostic = observation_submission_diagnostic(
        phase_plans[execution_plan.observation_owner.value],
        execution_plan.manifest,
        target.observation_runtime,
        durable_lifecycle_available=False,
    )
    if observation_diagnostic is not None:
        diagnostics.append(observation_diagnostic)
    return diagnostics


def _provenance_diagnostics(
    execution_plan: ExecutionPlan,
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if execution_plan.target_name is None:
        diagnostics.append(
            _failure_diagnostic(
                "runtime.plan-target-unbound",
                _RUNTIME_APPLY_ADDRESS,
                (
                    "Execution plan is not bound to a runtime target. Use "
                    "RuntimeManager.plan() or pass target_name explicitly."
                ),
            )
        )
    elif execution_plan.target_name != target.name:
        diagnostics.append(
            _failure_diagnostic(
                "runtime.plan-target-mismatch",
                _RUNTIME_APPLY_ADDRESS,
                f"Execution plan targets '{execution_plan.target_name}', but manager target is '{target.name}'.",
            )
        )
    if execution_plan.manifest != target.manifest:
        diagnostics.append(
            _failure_diagnostic(
                "runtime.plan-manifest-mismatch",
                _RUNTIME_APPLY_ADDRESS,
                "Execution plan manifest does not match the manager target manifest.",
            )
        )
    if execution_plan.base_snapshot != snapshot:
        diagnostics.append(
            _failure_diagnostic(
                "runtime.plan-snapshot-mismatch",
                _RUNTIME_APPLY_ADDRESS,
                "Execution plan base snapshot does not match the manager snapshot.",
            )
        )
    return diagnostics
