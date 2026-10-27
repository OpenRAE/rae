"""Fresh evaluation preserves the interaction's compiled context and authority."""

from raes_contracts.planning import PlanScope
from raes_processor.planner import plan
from raes_processor.planner.mixed_control_admission import MixedControlPlanningAdmission

from .control_plane_evaluation import evaluation_request
from .control_plane_execution import execute_operation
from .control_plane_supervised_execution import _existing_supervised_receipt
from .manager_lifecycle import manager_owned


class RuntimeInteractionEvaluationMixin:
    @manager_owned
    def evaluate(self, execution_plan=None, *, idempotency_key="", identity=None):
        """Evaluate later evidence without applying or restarting other domains.

        Reuse an idempotency key only to retry the exact evaluation request.
        Use a new key for each new evidence collection.
        """
        execution = execution_plan or self._interaction_plan
        if execution is None or not execution.is_valid:
            raise ValueError("evaluation requires a valid composite execution plan")
        if execution.target_name != self._target.name or execution.manifest != self._target.manifest:
            raise ValueError("evaluation plan does not match the runtime target")
        # Bind the logical request to its immutable original planning input.
        # Current state controls the command only after durable replay resolution.
        original = self._plan_evaluation_refresh(execution, execution.base_snapshot)
        request_identity = {"interaction_evaluation": execution.evaluation, "compiled_evaluation": original.evaluation}
        options = dict(idempotency_key=idempotency_key, identity=identity, request_identity=request_identity)
        request = evaluation_request(self, original.evaluation, **options)
        receipt = _existing_supervised_receipt(self, request)
        if receipt is not None:
            return receipt
        refreshed = self._plan_evaluation_refresh(execution, self._snapshot)
        self.register_planner_produced_plan(refreshed)
        return execute_operation(self, evaluation_request(self, refreshed.evaluation, **options))

    def _plan_evaluation_refresh(self, execution, snapshot):
        context = execution.planning_context
        if context is None:
            raise ValueError("evaluation requires its original planning context")

        def apparatus_default(requirement, _manifest):
            key = (requirement.address, requirement.field_path, requirement.requirement_kind)
            return context.apparatus_decisions[key]

        refreshed = plan(
            context.model,
            self._target.manifest,
            snapshot,
            scope=PlanScope(
                target_name=self._target.name,
                run_id=execution.evaluation.run_id,
                instantiation_id=execution.evaluation.instantiation_id,
            ),
            artifact_availability=execution.artifact_availability,
            apparatus_realization_default=apparatus_default,
            profile_context=context.profile_context,
            mixed_control_admission=(
                None
                if context.mixed_control_model is None
                else MixedControlPlanningAdmission(context.mixed_control_model)
            ),
            refresh_evaluation=True,
        )
        if not refreshed.is_valid:
            raise ValueError("evaluation refresh could not be planned")
        return refreshed
