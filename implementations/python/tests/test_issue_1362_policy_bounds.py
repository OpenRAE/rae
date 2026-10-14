"""Backend willingness cannot substitute for runtime recovery semantics."""

from dataclasses import replace

import pytest
from raes_contracts.execution_policy import EffectiveExecutionPolicy, ExecutionPolicy
from raes_contracts.planning import ChangeAction, PlanOperation, ProvisioningPlan
from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration


def test_authored_budget_caps_the_execution_origin_and_unsupported_clock_is_refused():
    from raes_runtime.operation_policy_admission import execution_budget_ms

    policy = EffectiveExecutionPolicy(
        scope="/nodes/host",
        governing_scope="#/",
        policy=ExecutionPolicy(
            policy_id="bounded",
            response="terminate",
            budget_ms=40,
        ),
    )
    operation = PlanOperation(
        action=ChangeAction.CREATE,
        address="provision.node.host",
        resource_type="node",
        payload={},
        execution_policy=policy,
    )
    plan = ProvisioningPlan(operations=[operation])
    assert execution_budget_ms(plan, OperationSupervisionConfiguration(execution_ms=100)) == 40
    semantic = policy.model_copy(
        update={"policy": policy.policy.model_copy(update={"clock_basis": "semantic", "clock_ref": "semantic-clock"})}
    )
    with pytest.raises(ValueError):
        execution_budget_ms(
            replace(plan, operations=[replace(operation, execution_policy=semantic)]),
            OperationSupervisionConfiguration(),
        )
