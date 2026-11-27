"""SemanticValidator _WorkflowAnalysisMixin (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from raes_contracts.graphs import stable_topological_order
from raes_contracts.propositions import AssertionRole
from raes_contracts.workflow.semantics import workflow_step_semantic_contract

from ..orchestration import Workflow, WorkflowPredicate, WorkflowStep, WorkflowStepType
from ._support import _AvailableStateContext, _CompensationState, _WorkflowBuildState


class _WorkflowAnalysisMixin:
    def _validate_workflow_predicate(
        self,
        workflow_name: str,
        step_name: str,
        predicate: WorkflowPredicate,
        workflow_steps: dict[str, WorkflowStep],
    ) -> list[str]:
        """Validate all references within a workflow predicate."""
        self._validate_predicate_section_refs(workflow_name, step_name, predicate)
        return self._validate_predicate_step_states(workflow_name, step_name, predicate, workflow_steps)

    def _validate_predicate_section_refs(
        self, workflow_name: str, step_name: str, predicate: WorkflowPredicate
    ) -> None:
        predicate_sections = (
            ("assertion", predicate.assertions, self._s.assertions),
            ("objective", predicate.objectives, self._s.objectives),
        )
        for label, refs, section in predicate_sections:
            for ref in refs:
                if self._is_unresolved_var(ref):
                    continue
                if ref not in section:
                    self._err(
                        f"Workflow '{workflow_name}' step "
                        f"'{step_name}' references undefined "
                        f"{label} '{ref}' in predicate"
                    )
                elif label == "assertion" and section[ref].role is not AssertionRole.PRECONDITION:
                    self._err(
                        f"Workflow '{workflow_name}' step '{step_name}' assertion '{ref}' "
                        "in predicate must be a precondition"
                    )

    def _validate_predicate_step_states(
        self,
        workflow_name: str,
        step_name: str,
        predicate: WorkflowPredicate,
        workflow_steps: dict[str, WorkflowStep],
    ) -> list[str]:
        step_refs: list[str] = []
        for step_state in predicate.steps:
            if self._is_unresolved_var(step_state.step):
                continue
            if step_state.step not in workflow_steps:
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' "
                    f"references undefined step state "
                    f"'{step_state.step}' in predicate"
                )
                continue
            if step_state.step == step_name:
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' cannot reference its own state in a predicate"
                )
                continue
            ref_step = workflow_steps[step_state.step]
            contract = workflow_step_semantic_contract(ref_step.type.value)
            if not contract.state_observable:
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' "
                    f"cannot reference non-executable step '{step_state.step}' "
                    "in a predicate"
                )
                continue
            invalid_outcomes = [
                outcome.value for outcome in step_state.outcomes if outcome.value not in contract.observable_outcomes
            ]
            if invalid_outcomes:
                allowed = ", ".join(contract.observable_outcomes)
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' "
                    f"references step '{step_state.step}' with impossible "
                    f"outcomes {invalid_outcomes}; allowed outcomes are: {allowed}"
                )
                continue
            step_refs.append(step_state.step)
        return step_refs

    @staticmethod
    def _is_executable_workflow_step(step: WorkflowStep) -> bool:
        return workflow_step_semantic_contract(step.type.value).state_observable

    def _validate_workflow_target_ref(
        self,
        workflow_name: str,
        step_name: str,
        field_name: str,
        target: str,
        workflow_steps: dict[str, WorkflowStep],
    ) -> str | None:
        if not target or self._is_unresolved_var(target):
            return None
        if target not in workflow_steps:
            self._err(f"Workflow '{workflow_name}' step '{step_name}' {field_name} step '{target}' is not defined")
            return None
        return target

    def _compute_available_step_states(self, ctx: _AvailableStateContext) -> None:
        for step_name in stable_topological_order(ctx.predecessors, key=str):
            step = ctx.workflow_steps[step_name]
            if step_name == ctx.start:
                result: set[str] = set()
            elif step.type == WorkflowStepType.JOIN and ctx.join_targets.get(step_name):
                result = self._join_available_state(step_name, ctx)
            else:
                result = self._incoming_available_state(step_name, ctx)
            ctx.available_memo[step_name] = result

    @staticmethod
    def _edge_available_state(step_name: str, successor: str, ctx: _AvailableStateContext) -> set[str]:
        available = set(ctx.available_memo.get(step_name, ()))
        step = ctx.workflow_steps[step_name]
        if step.type in {
            WorkflowStepType.OBJECTIVE,
            WorkflowStepType.RETRY,
            WorkflowStepType.CALL,
        } or (step.type == WorkflowStepType.PARALLEL and step.on_failure and successor == step.on_failure):
            available.add(step_name)
        return available

    @staticmethod
    def _join_available_state(step_name: str, ctx: _AvailableStateContext) -> set[str]:
        owner = ctx.join_targets[step_name][0]
        result = set(ctx.available_memo.get(owner, ()))
        result.add(owner)
        owner_step = ctx.workflow_steps[owner]
        for branch in owner_step.branches:
            if branch not in ctx.workflow_steps:
                continue
            result.update(ctx.join_states[step_name].get(branch, ()))
        return result

    def _incoming_available_state(self, step_name: str, ctx: _AvailableStateContext) -> set[str]:
        incoming_states: list[set[str]] = []
        for predecessor in ctx.predecessors.get(step_name, set()):
            if predecessor not in ctx.workflow_steps:
                continue
            incoming_states.append(self._edge_available_state(predecessor, step_name, ctx))
        return set.intersection(*incoming_states) if incoming_states else set()

    def _verify_step_terminator_and_compensation(
        self,
        *,
        workflow_name: str,
        step_name: str,
        step: WorkflowStep,
        workflow: Workflow,
        build: _WorkflowBuildState,
        comp: _CompensationState,
    ) -> None:
        """Shared validation for `on-success`/`on-failure` and `compensate_with`.

        OBJECTIVE and CALL workflow steps both carry the same terminator and
        compensation-handling shape, so this method centralizes the
        appended-edge bookkeeping and undefined-workflow error reporting
        for both call sites.
        """
        for field_name, target in (
            ("on-success", step.on_success),
            ("on-failure", step.on_failure),
        ):
            resolved = self._validate_workflow_target_ref(workflow_name, step_name, field_name, target, workflow.steps)
            if resolved is not None:
                build.graph[step_name].append(resolved)
        if step.compensate_with:
            comp.workflows_with_compensation.add(workflow_name)
            if not self._is_unresolved_var(step.compensate_with) and step.compensate_with not in self._s.workflows:
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' "
                    "references undefined compensation workflow "
                    f"'{step.compensate_with}'"
                )
            elif not self._is_unresolved_var(step.compensate_with):
                comp.compensation_graph.setdefault(workflow_name, set()).add(step.compensate_with)
                comp.compensation_targets.add(step.compensate_with)
