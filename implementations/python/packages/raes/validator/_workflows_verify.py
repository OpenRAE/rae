"""SemanticValidator _WorkflowVerifyMixin (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from raes_contracts.controlled_vocabularies import (
    validate_controlled_vocabulary_scope_values,
    validate_controlled_vocabulary_value,
)
from raes_contracts.graphs import has_cycle

from ..orchestration import WorkflowStepType
from ..participant_behavior import ParticipantActionGranularity, ParticipantInformationBoundaryClass
from ..participant_behavior_specification import tool_affordance_reference
from ..semantics.workflow import branch_closure
from ._support import _AvailableStateContext, _CompensationState, _WorkflowBuildState


class _WorkflowVerifyMixin:
    def _verify_workflows(self) -> None:
        comp = _CompensationState(
            call_graph={workflow_name: set() for workflow_name in self._s.workflows},
            compensation_graph={workflow_name: set() for workflow_name in self._s.workflows},
        )
        for workflow_name, workflow in self._s.workflows.items():
            with self._owner(("workflows", workflow_name)):
                self._verify_workflow(workflow_name, workflow, comp)
        self._verify_workflow_call_cycles(comp)
        self._verify_compensation_targets(comp)

    def _verify_workflow(self, workflow_name: str, workflow: object, comp: _CompensationState) -> None:
        if not self._is_unresolved_var(workflow.start) and workflow.start not in workflow.steps:
            self._err(f"Workflow '{workflow_name}' start step '{workflow.start}' is not defined")
        build = self._build_workflow_step_graph(workflow_name, workflow, comp)
        self._verify_workflow_join_targets(workflow_name, workflow, build.join_targets)
        self._verify_workflow_unreferenced_joins(workflow_name, workflow, build.join_targets)
        if build.graph and has_cycle(build.graph):
            self._err(f"Workflow '{workflow_name}' graph contains a cycle")
        if self._is_unresolved_var(workflow.start) or workflow.start not in workflow.steps:
            return
        reachable = self._reachable_steps(workflow, build.graph)
        self._verify_workflow_reachability(workflow_name, workflow, reachable)
        predecessors = self._build_predecessors(build.graph, reachable)
        self._verify_parallel_join_closures(workflow_name, workflow, build.graph, predecessors, reachable)
        self._verify_predicate_available_state(workflow_name, workflow, build, predecessors, reachable)
        self._verify_parallel_branch_convergence(workflow_name, workflow, build.graph)

    # ------------------------------------------------------------------
    # Per-step edge collection
    # ------------------------------------------------------------------

    def _build_workflow_step_graph(
        self, workflow_name: str, workflow: object, comp: _CompensationState
    ) -> _WorkflowBuildState:
        build = _WorkflowBuildState(graph={step_name: [] for step_name in workflow.steps})
        for step_name, step in workflow.steps.items():
            if "." in step_name:
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' cannot "
                    "contain '.' because objective windows use "
                    "'<workflow>.<step>' syntax"
                )
            self._collect_step_edges(workflow_name, workflow, step_name, step, build, comp)
            if step_name not in build.graph:
                build.graph[step_name] = []
        return build

    def _collect_step_edges(
        self,
        workflow_name: str,
        workflow: object,
        step_name: str,
        step: object,
        build: _WorkflowBuildState,
        comp: _CompensationState,
    ) -> None:
        if step.type == WorkflowStepType.OBJECTIVE:
            self._collect_objective_step(workflow_name, workflow, step_name, step, build, comp)
        elif step.type == WorkflowStepType.DECISION:
            self._collect_decision_step(workflow_name, workflow, step_name, step, build)
        elif step.type == WorkflowStepType.SWITCH:
            self._collect_switch_step(workflow_name, workflow, step_name, step, build)
        elif step.type == WorkflowStepType.PARALLEL:
            self._collect_parallel_step(workflow_name, workflow, step_name, step, build)
        elif step.type == WorkflowStepType.JOIN:
            self._collect_join_step(workflow_name, workflow, step_name, step, build)
        elif step.type == WorkflowStepType.RETRY:
            self._collect_retry_step(workflow_name, workflow, step_name, step, build)
        elif step.type == WorkflowStepType.CALL:
            self._collect_call_step(workflow_name, workflow, step_name, step, build, comp)
        elif step.type == WorkflowStepType.END:
            build.graph[step_name] = []

    def _collect_objective_step(
        self,
        workflow_name: str,
        workflow: object,
        step_name: str,
        step: object,
        build: _WorkflowBuildState,
        comp: _CompensationState,
    ) -> None:
        if not self._is_unresolved_var(step.objective) and step.objective not in self._s.objectives:
            self._err(
                f"Workflow '{workflow_name}' step '{step_name}' references undefined objective '{step.objective}'"
            )
        self._verify_workflow_step_realization_refs(workflow_name, step_name, step)
        self._verify_step_terminator_and_compensation(
            workflow_name=workflow_name, step_name=step_name, step=step, workflow=workflow, build=build, comp=comp
        )

    def _collect_decision_step(
        self, workflow_name: str, workflow: object, step_name: str, step: object, build: _WorkflowBuildState
    ) -> None:
        build.predicate_step_refs[step_name] = self._validate_workflow_predicate(
            workflow_name, step_name, step.when, workflow.steps
        )
        for branch_label, branch_ref in (("then", step.then_step), ("else", step.else_step)):
            resolved = self._validate_workflow_target_ref(
                workflow_name, step_name, branch_label, branch_ref, workflow.steps
            )
            if resolved is not None:
                build.graph[step_name].append(resolved)

    def _collect_switch_step(
        self, workflow_name: str, workflow: object, step_name: str, step: object, build: _WorkflowBuildState
    ) -> None:
        aggregated_refs: list[str] = []
        for case_index, case in enumerate(step.cases):
            aggregated_refs.extend(
                self._validate_workflow_predicate(
                    workflow_name, f"{step_name}.case[{case_index}]", case.when, workflow.steps
                )
            )
            resolved = self._validate_workflow_target_ref(
                workflow_name, step_name, f"case[{case_index}] next", case.next_step, workflow.steps
            )
            if resolved is not None:
                build.graph[step_name].append(resolved)
        build.predicate_step_refs[step_name] = aggregated_refs
        resolved_default = self._validate_workflow_target_ref(
            workflow_name, step_name, "default", step.default_step, workflow.steps
        )
        if resolved_default is not None:
            build.graph[step_name].append(resolved_default)

    def _collect_parallel_step(
        self, workflow_name: str, workflow: object, step_name: str, step: object, build: _WorkflowBuildState
    ) -> None:
        for branch_ref in step.branches:
            resolved = self._validate_workflow_target_ref(
                workflow_name, step_name, "branch", branch_ref, workflow.steps
            )
            if resolved is not None:
                build.graph[step_name].append(resolved)
        resolved_join = self._validate_workflow_target_ref(workflow_name, step_name, "join", step.join, workflow.steps)
        if resolved_join is not None:
            build.join_targets[resolved_join].append(step_name)
        resolved_failure = self._validate_workflow_target_ref(
            workflow_name, step_name, "on-failure", step.on_failure, workflow.steps
        )
        if resolved_failure is not None:
            build.graph[step_name].append(resolved_failure)

    def _collect_join_step(
        self, workflow_name: str, workflow: object, step_name: str, step: object, build: _WorkflowBuildState
    ) -> None:
        resolved = self._validate_workflow_target_ref(workflow_name, step_name, "next", step.next, workflow.steps)
        if resolved is not None:
            build.graph[step_name].append(resolved)

    def _collect_retry_step(
        self, workflow_name: str, workflow: object, step_name: str, step: object, build: _WorkflowBuildState
    ) -> None:
        if not self._is_unresolved_var(step.objective) and step.objective not in self._s.objectives:
            self._err(
                f"Workflow '{workflow_name}' step '{step_name}' references undefined objective '{step.objective}'"
            )
        self._verify_workflow_step_realization_refs(workflow_name, step_name, step)
        for field_name, target in (("on-success", step.on_success), ("on-exhausted", step.on_exhausted)):
            resolved = self._validate_workflow_target_ref(workflow_name, step_name, field_name, target, workflow.steps)
            if resolved is not None:
                build.graph[step_name].append(resolved)

    def _verify_workflow_step_realization_refs(
        self,
        workflow_name: str,
        step_name: str,
        step: object,
    ) -> None:
        self._verify_workflow_step_action_contract_ref(
            workflow_name,
            step_name,
            "procedure_ref",
            step.procedure_ref,
            ParticipantActionGranularity.PROCEDURE,
        )
        self._verify_workflow_step_action_families(workflow_name, step_name, step)
        self._verify_workflow_step_scaffold_refs(workflow_name, step_name, step)
        self._verify_workflow_step_tool_affordance_refs(workflow_name, step_name, step)
        self._verify_workflow_step_capability_refs(workflow_name, step_name, step)
        self._verify_workflow_step_fact_binding_refs(workflow_name, step_name, step)

    def _verify_workflow_step_action_families(self, workflow_name: str, step_name: str, step: object) -> None:
        for ref in step.allowed_action_families:
            self._verify_workflow_step_action_contract_ref(
                workflow_name,
                step_name,
                "allowed_action_families",
                ref,
                ParticipantActionGranularity.AGGREGATE,
            )

    def _verify_workflow_step_scaffold_refs(self, workflow_name: str, step_name: str, step: object) -> None:
        scaffold_boundary_classes = {
            ParticipantInformationBoundaryClass.INSTRUCTION,
            ParticipantInformationBoundaryClass.STARTER_FILE,
            ParticipantInformationBoundaryClass.SCAFFOLD_INSTRUCTION,
            ParticipantInformationBoundaryClass.SUBTASK_GUIDANCE,
        }
        for ref in step.scaffold_refs:
            if self._is_unresolved_var(ref):
                continue
            boundary = self._s.observation_boundaries.get(ref)
            if boundary is None:
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' references undefined scaffold "
                    f"observation boundary '{ref}'"
                )
                continue
            if not any(rule.boundary_class in scaffold_boundary_classes for rule in boundary.view_rules):
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' scaffold observation boundary '{ref}' "
                    "does not declare an instruction, starter-file, scaffold-instruction, or subtask-guidance view rule"
                )

    def _verify_workflow_step_tool_affordance_refs(self, workflow_name: str, step_name: str, step: object) -> None:
        available_refs = {
            tool_affordance_reference(spec_name, affordance_id)
            for spec_name, behavior_spec in self._s.behavior_specifications.items()
            for affordance_id in behavior_spec.tool_affordances
        }
        for ref in step.tool_affordance_refs:
            if self._is_unresolved_var(ref):
                continue
            if ref not in available_refs:
                self._err(f"Workflow '{workflow_name}' step '{step_name}' references undefined tool affordance '{ref}'")

    def _verify_workflow_step_capability_refs(self, workflow_name: str, step_name: str, step: object) -> None:
        for ref in step.capability_refs:
            if self._is_unresolved_var(ref):
                continue
            if not self._governed_capability_ref(ref):
                # The vocabulary error text repeats the term, so the message states the rule (E7).
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' references ungoverned participant "
                    f"capability '{ref}': it is neither a listed term nor an accepted extension term of the "
                    "participant runtime behavior or interaction feature vocabularies"
                )

    @staticmethod
    def _governed_capability_ref(ref: str) -> bool:
        for vocabulary_id in (
            "participant-runtime-behavior-features",
            "participant-runtime-interaction-features",
        ):
            try:
                validate_controlled_vocabulary_value(vocabulary_id, ref)
            except ValueError:
                continue
            return True
        return False

    def _verify_workflow_step_fact_binding_refs(self, workflow_name: str, step_name: str, step: object) -> None:
        for ref in step.fact_binding_refs:
            if self._is_unresolved_var(ref):
                continue
            try:
                validate_controlled_vocabulary_scope_values("workflows.steps.fact_binding_refs", [ref])
            except ValueError:
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' references ungoverned runtime-fact "
                    f"binding '{ref}': it is neither a listed term nor an accepted extension term of the "
                    "workflow step fact-binding vocabulary"
                )

    def _verify_workflow_step_action_contract_ref(
        self,
        workflow_name: str,
        step_name: str,
        field_name: str,
        ref: str,
        expected_granularity: ParticipantActionGranularity,
    ) -> None:
        if not ref or self._is_unresolved_var(ref):
            return
        action_contract = self._s.action_contracts.get(ref)
        if action_contract is None:
            self._err(
                f"Workflow '{workflow_name}' step '{step_name}' {field_name} references undefined "
                f"action contract '{ref}'"
            )
            return
        if action_contract.behavioral_granularity != expected_granularity:
            self._err(
                f"Workflow '{workflow_name}' step '{step_name}' {field_name} action contract '{ref}' "
                f"must have {expected_granularity.value} behavioral granularity"
            )

    def _collect_call_step(
        self,
        workflow_name: str,
        workflow: object,
        step_name: str,
        step: object,
        build: _WorkflowBuildState,
        comp: _CompensationState,
    ) -> None:
        if not self._is_unresolved_var(step.workflow) and step.workflow not in self._s.workflows:
            self._err(f"Workflow '{workflow_name}' step '{step_name}' references undefined workflow '{step.workflow}'")
        elif not self._is_unresolved_var(step.workflow):
            comp.call_graph.setdefault(workflow_name, set()).add(step.workflow)
        self._verify_step_terminator_and_compensation(
            workflow_name=workflow_name, step_name=step_name, step=step, workflow=workflow, build=build, comp=comp
        )

    # ------------------------------------------------------------------
    # Per-workflow structural checks
    # ------------------------------------------------------------------

    def _verify_workflow_join_targets(
        self, workflow_name: str, workflow: object, join_targets: dict[str, list[str]]
    ) -> None:
        for join_step, sources in join_targets.items():
            if self._is_unresolved_var(join_step):
                continue
            join_def = workflow.steps.get(join_step)
            if join_def is not None and join_def.type != WorkflowStepType.JOIN:
                self._err(
                    f"Workflow '{workflow_name}' step '{join_step}' is used as a parallel join but is not a join step"
                )
            if len(sources) > 1:
                self._err(
                    f"Workflow '{workflow_name}' join step '{join_step}' may only be targeted by one parallel step"
                )

    def _verify_workflow_unreferenced_joins(
        self, workflow_name: str, workflow: object, join_targets: dict[str, list[str]]
    ) -> None:
        for step_name, step in workflow.steps.items():
            if step.type != WorkflowStepType.JOIN:
                continue
            if not join_targets.get(step_name, []):
                self._err(f"Workflow '{workflow_name}' join step '{step_name}' is not referenced by any parallel step")

    @staticmethod
    def _reachable_steps(workflow: object, graph: dict[str, list[str]]) -> set[str]:
        reachable: set[str] = set()
        stack = [workflow.start]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            stack.extend(graph.get(current, []))
        return reachable

    def _verify_workflow_reachability(self, workflow_name: str, workflow: object, reachable: set[str]) -> None:
        unreachable = sorted(set(workflow.steps) - reachable)
        if unreachable:
            self._err(f"Workflow '{workflow_name}' contains unreachable steps: " + ", ".join(unreachable))

    @staticmethod
    def _build_predecessors(graph: dict[str, list[str]], reachable: set[str]) -> dict[str, set[str]]:
        predecessors: dict[str, set[str]] = {step_name: set() for step_name in reachable}
        for source, edges in graph.items():
            if source not in reachable:
                continue
            for target in edges:
                if target in reachable:
                    predecessors[target].add(source)
        return predecessors

    def _verify_parallel_join_closures(
        self,
        workflow_name: str,
        workflow: object,
        graph: dict[str, list[str]],
        predecessors: dict[str, set[str]],
        reachable: set[str],
    ) -> None:
        for _step_name, step in workflow.steps.items():
            if step.type != WorkflowStepType.PARALLEL:
                continue
            if self._is_unresolved_var(step.join) or step.join not in workflow.steps or step.join not in reachable:
                continue
            allowed_predecessors = branch_closure(
                graph,
                branches=(branch for branch in step.branches if branch in reachable and branch in workflow.steps),
                join_step=step.join,
            )
            foreign_predecessors = sorted(
                predecessor
                for predecessor in predecessors.get(step.join, set())
                if predecessor not in allowed_predecessors
            )
            if foreign_predecessors:
                self._err(
                    f"Workflow '{workflow_name}' join step '{step.join}' "
                    "may only be entered from the owning parallel's branch "
                    "closure; unexpected predecessors: " + ", ".join(foreign_predecessors)
                )

    def _verify_predicate_available_state(
        self,
        workflow_name: str,
        workflow: object,
        build: _WorkflowBuildState,
        predecessors: dict[str, set[str]],
        reachable: set[str],
    ) -> None:
        ctx = _AvailableStateContext(
            workflow_steps=workflow.steps,
            graph=build.graph,
            predecessors=predecessors,
            start=workflow.start,
            join_targets=build.join_targets,
        )
        for step_name, refs in build.predicate_step_refs.items():
            if step_name not in reachable:
                continue
            ctx.visiting = set()
            available_before = self._available_step_state_before(step_name, ctx)
            self._verify_predicate_refs_available(workflow_name, step_name, refs, available_before)

    def _verify_predicate_refs_available(
        self, workflow_name: str, step_name: str, refs: list[str], available_before: set[str]
    ) -> None:
        for ref_name in refs:
            if self._is_unresolved_var(ref_name):
                continue
            if ref_name not in available_before:
                self._err(
                    f"Workflow '{workflow_name}' step '{step_name}' "
                    f"references step state '{ref_name}' that is not "
                    "guaranteed to be known before this predicate"
                )

    def _verify_parallel_branch_convergence(
        self, workflow_name: str, workflow: object, graph: dict[str, list[str]]
    ) -> None:
        for step_name, step in workflow.steps.items():
            if step.type != WorkflowStepType.PARALLEL:
                continue
            if self._is_unresolved_var(step.join) or step.join not in workflow.steps:
                continue
            for branch_ref in step.branches:
                if self._is_unresolved_var(branch_ref) or branch_ref not in workflow.steps:
                    continue
                if not self._all_paths_reach_join(branch_ref, step.join, graph, memo={}, visiting=set()):
                    self._err(
                        f"Workflow '{workflow_name}' parallel step "
                        f"'{step_name}' requires every explicit branch path "
                        f"from '{branch_ref}' to converge on join "
                        f"'{step.join}'"
                    )

    # ------------------------------------------------------------------
    # Cross-workflow checks
    # ------------------------------------------------------------------

    def _verify_workflow_call_cycles(self, comp: _CompensationState) -> None:
        call_only = {
            workflow_name: sorted(callee for callee in callees if callee in comp.call_graph)
            for workflow_name, callees in comp.call_graph.items()
        }
        if call_only and has_cycle(call_only):
            self._err("Workflow call graph contains a cycle")
        combined = {
            workflow_name: sorted(
                comp.call_graph.get(workflow_name, set()) | comp.compensation_graph.get(workflow_name, set())
            )
            for workflow_name in self._s.workflows
        }
        if combined and has_cycle(combined):
            self._err("Combined workflow call/compensation graph contains a cycle")

    def _verify_compensation_targets(self, comp: _CompensationState) -> None:
        for workflow_name in sorted(comp.compensation_targets):
            if workflow_name in comp.workflows_with_compensation:
                with self._owner(("workflows", workflow_name)):
                    self._err(
                        f"Workflow '{workflow_name}' cannot be used as a compensation "
                        "workflow because it also declares compensate-with steps"
                    )
