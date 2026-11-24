"""Precondition checks for runtime-manager execution plans."""

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.models import ExecutionPlan, RuntimeModel
from raes_processor.planner import descriptor_profile_diagnostics, participant_tool_support_diagnostics

from .diagnostics import _failure_diagnostic
from .mixed_control_admission import reference_mixed_control_diagnostics
from .observation_execution import observation_submission_diagnostic
from .participant_episode_binding import ParticipantEpisodeRuntimeBinding
from .registry import RuntimeTarget

_RUNTIME_APPLY_ADDRESS = "runtime.apply"


def runtime_plan_precondition_diagnostics(
    execution_plan: ExecutionPlan,
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
    *,
    durable_lifecycle_available: bool = False,
    delivery_actions: frozenset[str] = frozenset(),
    participant_episode: ParticipantEpisodeRuntimeBinding | None = None,
) -> list[Diagnostic]:
    """Return every deterministic plan-admission failure for a runtime apply."""
    diagnostics = _provenance_diagnostics(execution_plan, target, snapshot)
    if execution_plan.model.participant_episode_policies and (
        participant_episode is None or not participant_episode.admits_model(execution_plan.model)
    ):
        diagnostics.append(
            Diagnostic(
                code="runtime.participant-episode-binding-unavailable",
                domain="participant",
                address=_RUNTIME_APPLY_ADDRESS,
                message="Authored episode policies require the exact installed episode runtime binding.",
            )
        )
    context = execution_plan.planning_context
    processor = None if context is None else context.processor_manifest
    diagnostics.extend(participant_tool_support_diagnostics(execution_plan.model, target.manifest, processor))
    # A submitted plan cannot supply the profile context; the target owns it (ADR-120).
    diagnostics.extend(
        descriptor_profile_diagnostics(
            execution_plan.model, target.manifest, getattr(target.provisioner, "domain_profile_context", None)
        )
    )
    diagnostics.extend(
        diagnostic
        for diagnostic in reference_participant_driver_diagnostics(
            execution_plan.model, delivery_actions=delivery_actions
        )
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
        durable_lifecycle_available=durable_lifecycle_available,
    )
    if observation_diagnostic is not None:
        diagnostics.append(observation_diagnostic)
    return diagnostics


def reference_participant_driver_diagnostics(
    model: RuntimeModel,
    *,
    delivery_actions: frozenset[str] = frozenset(),
) -> list[Diagnostic]:
    """Reference-driver limits are execution admission, never SDL validity."""

    clocks = {clock.address: clock for clock in model.time_model.clocks}
    progressions = {policy.address: policy for policy in model.time_model.progression_policies}
    diagnostics = []
    driven_actions = set(delivery_actions)
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
                    message=("This shared-time action requires an installed execution driver with its exact binding."),
                )
            )
    diagnostics.extend(reference_mixed_control_diagnostics(model))
    return diagnostics


def _provenance_diagnostics(
    execution_plan: ExecutionPlan,
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    source = execution_plan.provisioning.materialization_source
    if source is not None and source.target_scope is not None and source.target_scope != f"target:{target.name}":
        diagnostics.append(
            _failure_diagnostic(
                "runtime.plan-target-mismatch",
                _RUNTIME_APPLY_ADDRESS,
                "Inventory source context belongs to another runtime target.",
            )
        )
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
