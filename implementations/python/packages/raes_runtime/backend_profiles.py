"""Profile host admission at the existing read-only preparation boundary."""

from __future__ import annotations

from copy import deepcopy
from inspect import signature

from raes_backend_protocols.manifest import BackendManifest
from raes_contracts.domain_profiles import DomainProfileResolutionContextModel
from raes_contracts.planning import ChangeAction, ProvisioningPlan
from raes_contracts.realization_profiles import (
    PLAN_PROFILE_CONTRACT,
    profile_authority_violation,
    profile_binding_tree,
    profile_context_digest,
    profile_resource_address,
    profile_selection_violation,
)
from raes_contracts.realization_structure import validate_realization_value


def validate_profile_target(manifest: BackendManifest, provisioner: object) -> None:
    """Fail registration if advertised profile support lacks its pinned local data."""

    if PLAN_PROFILE_CONTRACT not in manifest.supported_contract_versions:
        if manifest.domain_profile_context_digest is not None:
            raise ValueError("Unnegotiated profile context digest")
        return
    from raes_contracts.realization_preparation import BACKEND_PREPARATION_CONTRACT

    context = getattr(provisioner, "domain_profile_context", None)
    if (
        BACKEND_PREPARATION_CONTRACT not in manifest.supported_contract_versions
        or profile_context_digest(context) != manifest.domain_profile_context_digest
        or not callable(getattr(provisioner, "validate_profiles", None))
    ):
        raise ValueError("Advertised profile context does not match configured target")
    try:
        signature(provisioner.validate_profiles).bind(object())
    except (TypeError, ValueError) as exc:
        raise ValueError("Installed profile validator has an incompatible signature") from exc


def _bounded_target_context(component: object) -> DomainProfileResolutionContextModel:
    """Read the target-owned profile context, requiring a bounded admitted shape."""

    context = getattr(component, "domain_profile_context", None)
    if (
        not isinstance(context, DomainProfileResolutionContextModel)
        or not validate_realization_value(context, python_carriers=True).conformant
    ):
        raise ValueError("No bounded configured profile context")
    return deepcopy(context)


def _require_admitted_plan_profiles(
    plan: ProvisioningPlan, context: DomainProfileResolutionContextModel, manifest: BackendManifest
) -> None:
    """Require the plan's profile authority to join the configured target context."""

    if profile_context_digest(context) != manifest.domain_profile_context_digest:
        raise ValueError("Configured profile context no longer matches the admitted manifest")
    if profile_authority_violation(plan.profile_authority, context):
        raise ValueError("Plan profiles are not independently admitted")
    addresses = {op.address for op in plan.operations if op.action is not ChangeAction.DELETE}
    if any(profile_resource_address(binding) not in addresses for binding in plan.profile_authority.bindings):
        raise ValueError("Plan profiles reference an unavailable resource")


def configured_profile_context(
    method: object, plan: ProvisioningPlan, manifest: BackendManifest | None
) -> DomainProfileResolutionContextModel | None:
    """Read target-owned trust/support; a submitted plan cannot supply this."""

    if plan.profile_authority is None:
        if any(op.profile_bindings for op in plan.operations):
            raise ValueError("Unowned profile bindings are not execution authority")
        return None
    if (
        plan.preparation is None
        or manifest is None
        or PLAN_PROFILE_CONTRACT not in manifest.supported_contract_versions
    ):
        raise ValueError("Plan profile host was not negotiated")
    component = getattr(method, "__self__", None)
    validate_profile_target(manifest, component)
    context = _bounded_target_context(component)
    _require_admitted_plan_profiles(plan, context, manifest)
    return context


def _changed_profile_owner(selected: ProvisioningPlan) -> bool:
    """Report whether any selected binding moved away from its own resource."""

    for operation in selected.operations:
        for binding in profile_binding_tree(operation.profile_bindings).values():
            if operation.action is ChangeAction.DELETE or profile_resource_address(binding) != operation.address:
                return True
    return False


def _selected_profile_violation(
    original: ProvisioningPlan,
    selected: ProvisioningPlan,
    context: DomainProfileResolutionContextModel | None,
) -> str | None:
    """Compare selected bindings against the originally admitted profile authority."""

    bindings = tuple(binding for operation in selected.operations for binding in operation.profile_bindings)
    if original.profile_authority is None:
        return "Backend preparation invented profile authority." if bindings else None
    if _changed_profile_owner(selected):
        return "Backend preparation changed a profile owner."
    return profile_selection_violation(original.profile_authority, bindings, context)


def prepared_profile_violation(
    original: ProvisioningPlan,
    selected: ProvisioningPlan,
    context: DomainProfileResolutionContextModel | None,
) -> str | None:
    """Admit all selected bindings, without permitting additional profile owners."""

    try:
        return _selected_profile_violation(original, selected, context)
    except (AttributeError, TypeError, ValueError, RecursionError):
        return "Backend preparation returned invalid profile bindings."
