"""Bind reporting to the incumbent supervised operation and attempt identities."""

from dataclasses import replace

from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT
from raes_contracts.planning import ProvisioningPlan


def inventory_operation_plan(plan, manifest, binding):
    if isinstance(plan, ProvisioningPlan) and RUNTIME_DESCENDANTS_CONTRACT in manifest.supported_contract_versions:
        return replace(plan, operation_id=binding.operation_id, inventory_attempt_id=binding.attempt_id)
    return plan
