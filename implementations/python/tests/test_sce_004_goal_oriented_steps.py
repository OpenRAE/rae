"""SCE-004 goal-oriented and tool-flexible workflow step behavior."""

from __future__ import annotations

import textwrap

import pytest
from pydantic import ValidationError
from raes import SDLValidationError
from raes.orchestration import WorkflowStep, WorkflowStepExecutionMode
from raes.parser import parse_sdl
from raes_backend_protocols.capabilities import WorkflowFeature
from raes_contracts.contracts import schema_bundle
from raes_contracts.contracts.execution_state import WorkflowStepAttemptProvenanceModel
from raes_contracts.workflow import (
    WorkflowStepAttemptProvenance,
    WorkflowStepExecutionState,
    WorkflowStepLifecycle,
    WorkflowStepOutcome,
)
from raes_processor.compiler import compile_runtime_model


def test_legacy_workflow_step_remains_scripted() -> None:
    step = WorkflowStep(type="objective", objective="restore-service", on_success="done")

    assert step.execution_mode is WorkflowStepExecutionMode.SCRIPTED


def test_objective_mode_is_command_free_and_scaffolded_mode_is_governed() -> None:
    objective = WorkflowStep(
        type="objective",
        execution_mode="objective",
        objective="restore-service",
        on_success="done",
        capability_refs=["participant.shell"],
        fact_binding_refs=["bindings.service-endpoint"],
    )
    assert objective.capability_refs == ["participant.shell"]

    with pytest.raises(ValidationError, match="does not admit prescribed procedure"):
        WorkflowStep(
            type="objective",
            execution_mode="objective",
            objective="restore-service",
            on_success="done",
            procedure_ref="scripts.restore",
        )

    scaffolded = WorkflowStep(
        type="objective",
        execution_mode="scaffolded",
        objective="restore-service",
        on_success="done",
        scaffold_refs=["participant-context.restore-hints"],
        tool_affordance_refs=["behavior_specifications.operator.tool_affordances.shell"],
        allowed_action_families=["service-recovery"],
    )
    assert scaffolded.scaffold_refs == ["participant-context.restore-hints"]

    with pytest.raises(ValidationError, match="requires governed scaffold"):
        WorkflowStep(
            type="objective",
            execution_mode="scaffolded",
            objective="restore-service",
            on_success="done",
        )


@pytest.mark.parametrize(
    ("execution_mode", "field", "values", "message"),
    [
        ("scaffolded", "scaffold_refs", [""], "governed references must be non-empty"),
        (
            "scaffolded",
            "scaffold_refs",
            ["participant-context.restore-hints", "participant-context.restore-hints"],
            "governed references must be unique",
        ),
        (
            "objective",
            "scaffold_refs",
            ["participant-context.restore-hints"],
            "scaffold_refs are only valid for scaffolded execution mode",
        ),
        (
            "objective",
            "allowed_action_families",
            ["service-recovery"],
            "allowed_action_families are only valid for scaffolded execution mode",
        ),
    ],
)
def test_goal_step_governed_reference_validation(
    execution_mode: str,
    field: str,
    values: list[str],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        WorkflowStep(
            type="objective",
            execution_mode=execution_mode,
            objective="restore-service",
            on_success="done",
            **{field: values},
        )


def test_goal_mode_requires_an_objective_control_step() -> None:
    with pytest.raises(ValidationError, match="only valid for objective or retry"):
        WorkflowStep(type="end", execution_mode="objective")


def test_tool_affordance_constraint_must_resolve() -> None:
    source = textwrap.dedent(
        """
        name: dangling-affordance
        entities:
          operator: {role: blue}
        propositions:
          restored:
            description: The service is restored.
            subjects: [entities.operator]
            basis: declared_state
            predicate: {kind: presence, property: service, semantic_ref: urn:raes:declared-property:service, operator: exists}
        assertions:
          restored: {proposition: restored, role: postcondition, polarity: positive}
        objectives:
          restore-service:
            owner: operator
            success: {assertions: [restored]}
        workflows:
          response:
            start: restore
            steps:
              restore:
                type: objective
                execution_mode: objective
                objective: restore-service
                on_success: done
                tool_affordance_refs: [behavior_specifications.missing.tool_affordances.shell]
              done: {type: end}
        """
    )
    with pytest.raises(SDLValidationError, match="undefined tool affordance"):
        parse_sdl(source)


def _governed_goal_scenario() -> str:
    return textwrap.dedent(
        """
            name: goal-step
            entities:
              operator: {role: blue}
            action_contracts:
              service-recovery:
                semantic_version: 1.0.0
                lifecycle_state: active
                behavioral_granularity: aggregate
                procedure_basis: governed service recovery actions
                realization_profile: backend-declared
                fidelity_claim: preserves objective truth across tool choices
                preconditions:
                  - precondition_id: authorized
                    precondition_class: authority
                    description: operator is authorized to recover the service
                effects:
                  - effect_id: service-recovery-attempt
                    effect_class: intended_effect
                    description: participant attempts governed service recovery
                    target_refs: [entities.operator]
                failure_classes: [backend_error]
            observation_boundaries:
              restore-hints:
                projection_basis: participant-visible recovery scaffold
                observable_refs: [entities.operator]
                redaction_policy: hidden information never projects
                latency_profile: available at step admission
                view_rules:
                  - information_ref: entities.operator
                    boundary_class: scaffold_instruction
                    disposition: observable
                    visibility_basis: authored recovery guidance
            propositions:
              restored:
                description: The service is restored.
                subjects: [entities.operator]
                basis: declared_state
                predicate:
                  kind: presence
                  property: service
                  semantic_ref: urn:raes:declared-property:service
                  operator: exists
            assertions:
              restored: {proposition: restored, role: postcondition, polarity: positive}
            objectives:
              restore-service:
                owner: operator
                targets: [entities.operator]
                success: {assertions: [restored]}
            workflows:
              response:
                start: restore
                steps:
                  restore:
                    type: objective
                    execution_mode: scaffolded
                    objective: restore-service
                    on_success: done
                    scaffold_refs: [restore-hints]
                    allowed_action_families: [service-recovery]
                    capability_refs: [action_contracts]
                    fact_binding_refs: [x-raes:service-endpoint]
                  done: {type: end}
        """
    )


def test_compiler_preserves_goal_realization_contract() -> None:
    scenario = parse_sdl(_governed_goal_scenario())

    model = compile_runtime_model(scenario)
    step = model.workflows["orchestration.workflow.response"].control_steps["restore"]

    assert step.execution_mode == "scaffolded"
    assert step.objective_address == "evaluation.objective.restore-service"
    assert step.scaffold_refs == ("restore-hints",)
    assert step.allowed_action_families == ("service-recovery",)
    assert step.capability_refs == ("action_contracts",)
    assert step.fact_binding_refs == ("x-raes:service-endpoint",)
    assert WorkflowFeature.SCAFFOLDED_STEPS in model.workflows["orchestration.workflow.response"].required_features


@pytest.mark.parametrize(
    ("authored", "dangling", "message"),
    [
        ("scaffold_refs: [restore-hints]", "scaffold_refs: [missing-hints]", "undefined scaffold observation boundary"),
        (
            "allowed_action_families: [service-recovery]",
            "allowed_action_families: [missing-family]",
            "references undefined action contract",
        ),
        (
            "capability_refs: [action_contracts]",
            "capability_refs: [participant.shell]",
            "ungoverned participant capability",
        ),
        (
            "fact_binding_refs: [x-raes:service-endpoint]",
            "fact_binding_refs: [bindings.service-endpoint]",
            "ungoverned runtime-fact binding",
        ),
    ],
)
def test_goal_realization_reference_families_fail_closed(authored: str, dangling: str, message: str) -> None:
    source = _governed_goal_scenario().replace(authored, dangling)
    with pytest.raises(SDLValidationError, match=message):
        parse_sdl(source)


def test_scripted_procedure_must_resolve_to_a_procedure_action_contract() -> None:
    source = _governed_goal_scenario().replace("execution_mode: scaffolded", "execution_mode: scripted")
    for line in (
        "        scaffold_refs: [restore-hints]\n",
        "        allowed_action_families: [service-recovery]\n",
        "        capability_refs: [action_contracts]\n",
        "        fact_binding_refs: [x-raes:service-endpoint]\n",
    ):
        source = source.replace(line, "")
    source = source.replace(
        "        on_success: done\n", "        on_success: done\n        procedure_ref: service-recovery\n"
    )

    parse_sdl(source.replace("behavioral_granularity: aggregate", "behavioral_granularity: procedure"))

    with pytest.raises(SDLValidationError, match="must have procedure behavioral granularity"):
        parse_sdl(source)

    missing_procedure_source = source.replace("procedure_ref: service-recovery", "procedure_ref: missing-procedure")
    with pytest.raises(SDLValidationError, match="references undefined action contract"):
        parse_sdl(missing_procedure_source)


def test_success_provenance_requires_assertion_truth_and_evidence() -> None:
    provenance = WorkflowStepAttemptProvenance(
        step_name="restore",
        execution_mode="objective",
        attempt_id="attempt-1",
        objective_address="evaluation.objective.restore-service",
        selected_action_family="service-recovery",
        selected_tool_ref="tools.systemctl",
        fact_versions=("runtime-fact:service-endpoint@4",),
        outcome="succeeded",
        evidence_refs=("evidence:service-health",),
        assertion_truth_refs=("truth:restored",),
    )
    assert provenance.selected_tool_ref == "tools.systemctl"
    state = WorkflowStepExecutionState(
        lifecycle=WorkflowStepLifecycle.COMPLETED,
        outcome=WorkflowStepOutcome.SUCCEEDED,
        attempts=1,
        attempt_provenance=(provenance,),
    )
    assert state.to_payload()["attempt_provenance"][0]["selected_tool_ref"] == "tools.systemctl"
    step_schema = schema_bundle()["workflow-result-envelope-v1"]["$defs"]["WorkflowStepStateModel"]
    assert "attempt_provenance" in step_schema["properties"]

    with pytest.raises(ValueError, match="evidence-bearing assertion truth"):
        WorkflowStepAttemptProvenance(
            step_name="restore",
            execution_mode="objective",
            attempt_id="attempt-2",
            objective_address="evaluation.objective.restore-service",
            outcome="succeeded",
            participant_report="I fixed it",
        )

    with pytest.raises(ValidationError, match="evidence-bearing assertion truth"):
        WorkflowStepAttemptProvenanceModel.model_validate(
            {
                "step_name": "restore",
                "execution_mode": "objective",
                "attempt_id": "attempt-3",
                "objective_address": "evaluation.objective.restore-service",
                "outcome": "succeeded",
                "participant_report": "I fixed it",
            }
        )
