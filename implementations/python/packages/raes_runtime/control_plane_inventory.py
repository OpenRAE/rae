"""Dispatch a committed provisioning refresh without executing apply."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT
from raes_contracts.planning import ProvisioningPlan

if TYPE_CHECKING:
    from .registry import RuntimeTarget


def _unsupported_inventory(*_args: object) -> object:
    raise ValueError("inventory refresh is unavailable")


def provisioning_method(target: RuntimeTarget, plan: ProvisioningPlan) -> Callable[..., object]:
    if not plan.inventory_refresh:
        return target.provisioner.apply
    if RUNTIME_DESCENDANTS_CONTRACT not in target.manifest.supported_contract_versions:
        return _unsupported_inventory
    return getattr(target.provisioner, "refresh_inventory", _unsupported_inventory)


def provisioning_validation(
    target: RuntimeTarget, plan: ProvisioningPlan
) -> Callable[[ProvisioningPlan], list[Diagnostic]] | None:
    return target.provisioner.validate if plan.preparation is None and not plan.inventory_refresh else None
