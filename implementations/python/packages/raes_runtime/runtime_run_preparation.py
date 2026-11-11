"""Bind durable run execution to the existing whole-run admission and modules."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from raes_contracts.augmentation_scope import AUGMENTATION_SCOPE_CONTRACT
from raes_contracts.contracts.time_model import validate_time_runtime_state
from raes_processor.compiler.time_model import time_model_contract_model

from .diagnostics import _has_error_diagnostic
from .manager_augmentation import prepare_execution_augmentation
from .runtime_decisions import RunPreparationDecision

if TYPE_CHECKING:
    from raes_processor.models import ExecutionPlan

    from .runtime_decisions import RunPhaseDecision, RunProgramDecision, RuntimeDecision
    from .runtime_run_context import RuntimeRunContext


def prepare_run(
    run: RuntimeRunContext, plan: ExecutionPlan, admission: RunProgramDecision, decisions: dict[str, RuntimeDecision]
) -> tuple[ExecutionPlan, RunPreparationDecision]:
    # The compiler's explicit identities prevail. Otherwise every reconstruction
    # binds the same identity before prospective augmentation is negotiated.
    if AUGMENTATION_SCOPE_CONTRACT in plan.manifest.supported_contract_versions:
        plan = replace(
            plan,
            **{
                domain: replace(
                    getattr(plan, domain),
                    operation_id=getattr(plan, domain).operation_id
                    or str(uuid5(NAMESPACE_URL, admission.decision_id + domain)),
                )
                for domain in ("provisioning", "evaluation", "orchestration")
            },
        )
    key = RunPreparationDecision(run_scope=run._run_scope, execution_id=admission.execution_id, admitted=True)
    prior = decisions.get(key.decision_id)
    if prior is None:
        with run._mutation_authority.external_call():
            plan, previews, diagnostics = run._execution_adapter.call(
                "effect",
                prepare_execution_augmentation,
                plan,
                run._target,
                plan.base_snapshot,
                run._materialization_archive,
                timeout_ms=run._supervision.execution_ms,
            )
        prior = key.model_copy(update={"previews": previews, "admitted": not _has_error_diagnostic(diagnostics)})
        run._store.claim_runtime_decision(prior)
    return plan, prior


def restore_run_modules(run: RuntimeRunContext, plan: ExecutionPlan, phases: dict[int, RunPhaseDecision]) -> None:
    """Restore local bindings from the admitted plan; never initialize a backend."""
    if 1 in phases and phases[1].state == "succeeded":
        declaration = time_model_contract_model(plan.model.time_model)
        if declaration is not None:
            validate_time_runtime_state(declaration, run._snapshot.time_model_state)
        run._time_declaration = declaration
    if 2 in phases and phases[2].state == "succeeded":
        run._participant_execution_policies = tuple(
            spec.autonomous_execution
            for spec in plan.model.behavior_specifications.values()
            if spec.autonomous_execution is not None
        )
        run._participant_execution_time_model = plan.model.time_model
        if run._participant_execution_policies and run._participant_scheduler is None:
            from .participant_scheduler import ParticipantScheduler

            run._participant_scheduler = ParticipantScheduler()
