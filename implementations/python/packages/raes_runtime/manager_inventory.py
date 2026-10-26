"""Public manager refresh uses the existing isolated backend result boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import uuid4

from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT
from raes_contracts.runtime_state import ApplyResult

from .backend_calls import _BackendCallContext, _call_backend_apply, _RealizationApplyContext
from .diagnostics import _failure_diagnostic
from .manager_lifecycle import manager_owned

if TYPE_CHECKING:
    from raes_processor.models import ExecutionPlan

    from .manager import RuntimeManager


class RuntimeInventoryMixin:
    @manager_owned
    def refresh_inventory(self, execution_plan: ExecutionPlan) -> ApplyResult:
        """Admit a fresh read-only inventory report under the original plan."""
        result = refresh_manager_inventory(self, execution_plan)
        self._snapshot = result.snapshot
        return result


def refresh_manager_inventory(manager: RuntimeManager, execution_plan: ExecutionPlan) -> ApplyResult:
    target = manager._target
    method = getattr(target.provisioner, "refresh_inventory", None)
    if (
        not execution_plan.is_valid
        or execution_plan.target_name != target.name
        or execution_plan.manifest != target.manifest
        or execution_plan.provisioning.materialization_source is None
        or execution_plan.provisioning.materialization_source.target_scope != f"target:{target.name}"
        or RUNTIME_DESCENDANTS_CONTRACT not in target.manifest.supported_contract_versions
        or not callable(method)
    ):
        return ApplyResult(
            False,
            manager.snapshot,
            diagnostics=[
                _failure_diagnostic(
                    "runtime.inventory-refresh-unsupported",
                    "runtime.inventory-refresh",
                    "Inventory refresh requires its original valid target-bound plan and negotiated producer support.",
                )
            ],
        )
    request = replace(execution_plan.provisioning, inventory_refresh=True)
    return _call_backend_apply(
        method,
        request,
        manager.snapshot,
        snapshot=manager.snapshot,
        address="runtime.inventory-refresh",
        realization=_RealizationApplyContext(plan=request, manifest=target.manifest),
        call=_BackendCallContext(
            operation_id=str(uuid4()),
            materialization_archive=manager._materialization_archive,
            information_state_context_resolver=manager._information_state_context_resolver,
        ),
    )
