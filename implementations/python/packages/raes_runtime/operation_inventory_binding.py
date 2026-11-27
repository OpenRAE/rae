"""Bind native phases and inventory reports to admitted operation identities."""

from dataclasses import replace

from raes_backend_protocols.capabilities import BackendManifest
from raes_contracts.contracts import BackendOperationBindingModel
from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan


def inventory_operation_plan(plan: object, manifest: BackendManifest, binding: BackendOperationBindingModel) -> object:
    if isinstance(plan, (ProvisioningPlan, OrchestrationPlan, EvaluationPlan)):
        plan = replace(plan, operation_id=binding.operation_id)
    if isinstance(plan, ProvisioningPlan) and RUNTIME_DESCENDANTS_CONTRACT in manifest.supported_contract_versions:
        return replace(plan, inventory_attempt_id=binding.attempt_id)
    return plan
