"""Dispatch a committed provisioning refresh without executing apply."""

from raes_contracts.materialization_inventory import RUNTIME_DESCENDANTS_CONTRACT


def _unsupported_inventory(*_args):
    raise ValueError("inventory refresh is unavailable")


def provisioning_method(target, plan):
    if not plan.inventory_refresh:
        return target.provisioner.apply
    if RUNTIME_DESCENDANTS_CONTRACT not in target.manifest.supported_contract_versions:
        return _unsupported_inventory
    return getattr(target.provisioner, "refresh_inventory", _unsupported_inventory)


def provisioning_validation(target, plan):
    return target.provisioner.validate if plan.preparation is None and not plan.inventory_refresh else None
