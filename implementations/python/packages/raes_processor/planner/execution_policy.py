"""Expose requested policy unchanged and reject unsupported selected realizations."""

from dataclasses import replace
from typing import TypeVar

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.execution_policy import execution_policy_capability_gaps
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan

from ..models.runtime_model import RuntimeModel

DomainPlan = TypeVar("DomainPlan", ProvisioningPlan, OrchestrationPlan, EvaluationPlan)


def attach_execution_policies(
    model: RuntimeModel, manifest: BackendManifest, domain_plan: DomainPlan
) -> tuple[DomainPlan, list[Diagnostic]]:
    diagnostics = []
    operations = []
    for operation in domain_plan.operations:
        policies = model.execution_policies.get(operation.address, ())
        if policies:
            operation = replace(operation, execution_policy=policies[0], execution_policy_scopes=policies[1:])
        operations.append(operation)
        for effective in policies:
            gaps = execution_policy_capability_gaps(effective.policy, manifest.execution_policy)
            code = gaps[0] if gaps else None
            if code:
                diagnostics.append(
                    Diagnostic(
                        code="execution-policy." + code,
                        domain="provisioning"
                        if operation.address.startswith("provision.")
                        else operation.address.split(".")[0],
                        address=operation.address,
                        message=(
                            "The selected realization cannot establish the requested execution policy; "
                            "no alternative is authorized."
                        ),
                    )
                )
    return replace(
        domain_plan, operations=operations, diagnostics=[*domain_plan.diagnostics, *diagnostics]
    ), diagnostics
