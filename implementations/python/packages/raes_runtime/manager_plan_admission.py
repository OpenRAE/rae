"""Precondition checks for runtime-manager execution plans."""

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ExecutionPlan, RuntimeModel

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
    diagnostics.extend(
        diagnostic
        for diagnostic in reference_participant_driver_diagnostics(execution_plan.model)
        if diagnostic not in execution_plan.diagnostics
    )
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


def reference_participant_driver_diagnostics(model: RuntimeModel) -> list[Diagnostic]:
    """Reference-driver limits are execution admission, never SDL validity."""

    clocks = {clock.address: clock for clock in model.time_model.clocks}
    progressions = {policy.address: policy for policy in model.time_model.progression_policies}
    diagnostics = []
    driven_actions = set()
    for specification in model.behavior_specifications.values():
        policy = specification.autonomous_execution
        if policy is None:
            continue
        driven_actions.update(policy.action_contract_addresses)
        progression = progressions[policy.progression_policy_address]
        clock = clocks[policy.clock_address]
        if progression.advancement_mode == "externally_paced" or (
            progression.advancement_mode in {"real_time", "dilated"} and clock.authority_kind != "runtime"
        ):
            diagnostics.append(
                Diagnostic(
                    code="runtime.participant-clock-driver-unsupported",
                    domain="participant",
                    address=policy.address,
                    message=(
                        "This valid clock policy requires a transition driver unavailable in the reference runtime; "
                        "it is not a backend-wide semantic requirement."
                    ),
                )
            )
    for action in model.action_contracts.values():
        if action.address not in driven_actions and any(
            temporal.get("shared_time_binding") for temporal in action.spec.get("temporal_contracts", ())
        ):
            diagnostics.append(
                Diagnostic(
                    code="runtime.participant-temporal-driver-unsupported",
                    domain="participant",
                    address=action.address,
                    message=(
                        "The reference runtime enforces explicit shared-time action bindings through autonomous policies; "
                        "this manual action requires another execution driver."
                    ),
                )
            )
    return diagnostics


def _provenance_diagnostics(
    execution_plan: ExecutionPlan,
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if execution_plan.model.materialization_description is not None or any(
        phase.purpose != "execution"
        for phase in (execution_plan.provisioning, execution_plan.orchestration, execution_plan.evaluation)
    ):
        diagnostics.append(
            _failure_diagnostic(
                "runtime.descriptive-plan",
                _RUNTIME_APPLY_ADDRESS,
                "Materialization descriptions require explicit derivation before execution.",
            )
        )
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
