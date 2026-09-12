"""Read-only backend preparation at the existing trusted apply boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import cast

from raes_backend_protocols.manifest import BackendManifest, backend_manifest_v2_model
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.backend_preparation import preparation_response_model
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.planning import ChangeAction, PlannedResource, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.realization_preparation import (
    BACKEND_PREPARATION_CONTRACT,
    RealizationPreparation,
    preparation_snapshot_digest,
)
from raes_contracts.realization_structure import validate_realization_value
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_processor.planner import (
    prepared_node_capability_violation,
    prepared_node_collection_binding_violation,
    prepared_node_collection_violation,
    prepared_realization_violation,
)

from .backend_account_credentials import plan_has_account_credentials, value_free_backend_diagnostics
from .backend_call_contracts import _apply_result_contract_violation, _materialize_diagnostics
from .backend_entry_transitions import backend_entry_transition_diagnostics
from .backend_profiles import configured_profile_context, prepared_profile_violation
from .backend_realization_authority import _RealizationApplyContext
from .diagnostics import _failure_diagnostic

_PREPARATION_ADDRESS = "runtime.preparation"
_PREPARATION_INVALID_CODE = "runtime.backend-preparation-invalid"
_MAX_PREPARATION_OPERATIONS = 16384


@dataclass(frozen=True)
class _AdmittedCompletion:
    """The plan one admitted completion selects and the diagnostics it carried."""

    selected: ProvisioningPlan
    diagnostics: list[Diagnostic]


def _preparation_failure(message: str) -> Diagnostic:
    """Build the value-free refusal every preparation failure collapses to."""

    return _failure_diagnostic(_PREPARATION_INVALID_CODE, _PREPARATION_ADDRESS, message)


def _is_admitted_operation(operation: object) -> bool:
    """Report whether one prepared operation carries an exact admitted shape."""

    return (
        type(operation) is ProvisionOp
        and isinstance(operation.action, ChangeAction)
        and isinstance(operation.payload, dict)
        and type(operation.ordering_dependencies) is tuple
        and type(operation.refresh_dependencies) is tuple
        and validate_realization_value(operation.payload, python_carriers=True).conformant
    )


def _require_preparation_operations(response: RealizationPreparation) -> None:
    """Refuse a preparation inventory that is not an exact bounded operation tuple."""

    if type(response.operations) is not tuple or len(response.operations) > _MAX_PREPARATION_OPERATIONS:
        raise ValueError("invalid preparation operation inventory")
    for operation in response.operations:
        if not _is_admitted_operation(operation):
            raise ValueError("invalid preparation operation")


def _selected_plan(plan: ProvisioningPlan, response: RealizationPreparation) -> ProvisioningPlan:
    _require_preparation_operations(response)
    operations = deepcopy(list(preparation_response_model(response).to_runtime().operations))
    resources = {
        operation.address: PlannedResource(
            operation.address,
            RuntimeDomain.PROVISIONING,
            operation.resource_type,
            deepcopy(operation.payload),
            operation.ordering_dependencies,
            operation.refresh_dependencies,
            operation.profile_bindings,
        )
        for operation in operations
        if operation.action is not ChangeAction.DELETE
    }
    return cast("ProvisioningPlan", replace(plan, operations=operations, resources=resources))


def _changed_operation_authority(original: ProvisioningPlan, selected: ProvisioningPlan) -> bool:
    """Report whether preparation altered any submitted operation's authority."""

    candidates = {operation.address: operation for operation in selected.operations}
    for operation in original.operations:
        candidate = candidates.get(operation.address)
        if candidate is None or replace(candidate, payload={}, profile_bindings=()) != replace(
            operation, payload={}, profile_bindings=()
        ):
            return True
    return False


def _projected_apply_result(selected: ProvisioningPlan, previous: RuntimeSnapshot) -> ApplyResult:
    """Project the snapshot the selected completion would establish."""

    entries = dict(previous.entries)
    for operation in selected.operations:
        if operation.action is ChangeAction.DELETE:
            entries.pop(operation.address, None)
        else:
            entries[operation.address] = SnapshotEntry(
                operation.address,
                RuntimeDomain.PROVISIONING,
                operation.resource_type,
                operation.payload,
                ordering_dependencies=operation.ordering_dependencies,
                refresh_dependencies=operation.refresh_dependencies,
                profile_bindings=operation.profile_bindings,
            )
    return ApplyResult(
        True,
        previous.with_entries(entries),
        changed_addresses=[operation.address for operation in selected.actionable_operations],
    )


def _authorized_plan(original: ProvisioningPlan, selected: ProvisioningPlan) -> ProvisioningPlan:
    """Derive the authority the enclosing relation admitted for this transition.

    Extra operation authority is derived only after the enclosing relation admitted
    it. The normal identity/effect/accounting gate still applies.
    """

    candidates = {operation.address: operation for operation in selected.operations}
    original_addresses = {operation.address for operation in original.operations}
    return cast(
        "ProvisioningPlan",
        replace(
            original,
            operations=[
                *(
                    replace(operation, profile_bindings=candidates[operation.address].profile_bindings)
                    for operation in original.operations
                ),
                *(operation for operation in selected.operations if operation.address not in original_addresses),
            ],
        ),
    )


def _transition_violation(
    original: ProvisioningPlan, selected: ProvisioningPlan, previous: RuntimeSnapshot
) -> str | None:
    collection_violation = prepared_node_collection_violation(original, selected, previous)
    if collection_violation:
        return collection_violation
    if _changed_operation_authority(original, selected):
        return "Backend preparation changed submitted operation authority."
    result = _projected_apply_result(selected, previous)
    invalid = _apply_result_contract_violation(result, _PREPARATION_ADDRESS)
    diagnostics = backend_entry_transition_diagnostics(result, previous, _authorized_plan(original, selected))
    return invalid or (diagnostics[0].message if diagnostics else None)


def _require_preparation_contract(plan: ProvisioningPlan, manifest: BackendManifest | None) -> None:
    """Require the selected backend to carry preparation authority for this plan."""

    if manifest is None or BACKEND_PREPARATION_CONTRACT not in manifest.supported_contract_versions:
        raise ValueError("Selected backend does not support the preparation contract.")
    manifest_digest = canonical_json_digest(backend_manifest_v2_model(manifest).model_dump(mode="json"))
    if plan.preparation is None or plan.preparation.manifest_digest != manifest_digest:
        raise ValueError("Preparation authority does not match the selected backend manifest.")
    if prepared_node_collection_binding_violation(plan):
        raise ValueError("Preparation collection authority does not match the submitted membership.")


def _prepared_response(component: object, plan: ProvisioningPlan, previous: RuntimeSnapshot) -> RealizationPreparation:
    """Invoke read-only preparation and require a bound, well-shaped response."""

    prepare = getattr(component, "prepare", None)
    if not callable(prepare):
        raise ValueError("Selected backend does not implement read-only preparation.")
    response = prepare(deepcopy(plan), deepcopy(previous))
    if type(response) is not RealizationPreparation or type(response.success) is not bool:
        raise ValueError("Backend returned an invalid preparation shape.")
    if response.request_digest != runtime_plan_digest(
        plan
    ) or response.predecessor_digest != preparation_snapshot_digest(previous):
        raise ValueError("Backend preparation does not match the submitted request and predecessor.")
    return response


def _admitted_profile_diagnostics(
    component: object, plan: ProvisioningPlan, selected: ProvisioningPlan
) -> list[Diagnostic]:
    """Require installed profile semantics to accept the selected completion."""

    if plan.profile_authority is None:
        return []
    diagnostics, invalid = _materialize_diagnostics(
        component.validate_profiles(deepcopy(selected)),  # type: ignore[attr-defined]
        _PREPARATION_ADDRESS,
    )
    if invalid or any(diagnostic.is_error for diagnostic in diagnostics):
        raise ValueError("Installed profile semantics refused the selected completion.")
    return diagnostics


def _admitted_validation_diagnostics(component: object, selected: ProvisioningPlan) -> list[Diagnostic]:
    """Require the backend's own validation boundary to accept the completion."""

    validate = getattr(component, "validate", None)
    if not callable(validate):
        raise ValueError("Selected backend has no prepared-plan validation boundary.")
    diagnostics, invalid = _materialize_diagnostics(validate(deepcopy(selected)), _PREPARATION_ADDRESS)
    if invalid or any(diagnostic.is_error for diagnostic in diagnostics):
        raise ValueError("Backend cannot apply the admitted completion.")
    return diagnostics


def _admit_backend_completion(
    method: object, plan: ProvisioningPlan, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> _AdmittedCompletion:
    """Admit one backend completion, raising on every refusal."""

    manifest = context.manifest
    _require_preparation_contract(plan, manifest)
    profile_context = configured_profile_context(method, plan, manifest)
    component = getattr(method, "__self__", None)
    response = _prepared_response(component, plan, previous)
    diagnostics, invalid = _materialize_diagnostics(response.diagnostics, _PREPARATION_ADDRESS)
    if invalid or not response.success or any(diagnostic.is_error for diagnostic in diagnostics):
        raise ValueError("Backend did not return a supported completion.")
    selected = _selected_plan(plan, replace(response, diagnostics=tuple(diagnostics)))
    violation = (
        prepared_profile_violation(plan, selected, profile_context)
        or _transition_violation(plan, selected, previous)
        or prepared_node_capability_violation(plan, selected, manifest, previous, context.artifact_availability)
        or prepared_realization_violation(plan, selected, manifest)
    )
    if violation:
        raise ValueError(violation)
    return _AdmittedCompletion(
        selected=selected,
        diagnostics=[
            *diagnostics,
            *_admitted_profile_diagnostics(component, plan, selected),
            *_admitted_validation_diagnostics(component, selected),
        ],
    )


def prepare_backend_apply(
    method: object, plan: ProvisioningPlan, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> tuple[ProvisioningPlan | None, list[Diagnostic]]:
    """Admit one backend completion; all exceptions become value-free failures."""

    try:
        admitted = _admit_backend_completion(method, plan, previous, context)
    except Exception:
        return None, [_preparation_failure("Backend preparation did not establish a valid bound supported completion.")]
    combined = admitted.diagnostics
    if plan_has_account_credentials(plan):
        combined = value_free_backend_diagnostics(combined)
    return admitted.selected, combined


def _unprepared_execution_refusal(plan: ProvisioningPlan) -> Diagnostic | None:
    """Refuse execution that requires negotiated preparation but carries none."""

    if plan.profile_authority is not None:
        return _preparation_failure("Profile execution requires negotiated preparation.")
    if any(getattr(operation, "profile_bindings", ()) for operation in plan.operations):
        return _preparation_failure("Unowned profile bindings are not execution authority.")
    return None


def prepare_backend_invocation(
    method: object,
    args: tuple[object, ...],
    previous: RuntimeSnapshot,
    context: _RealizationApplyContext,
) -> tuple[tuple[object, ...] | None, _RealizationApplyContext, list[Diagnostic]]:
    """Replace only the admitted operation argument; retain the original authority."""

    plan = context.plan
    if plan is None or plan.preparation is None:
        refusal = None if plan is None else _unprepared_execution_refusal(plan)
        return (args, context, []) if refusal is None else (None, context, [refusal])
    selected, diagnostics = prepare_backend_apply(method, plan, previous, context)
    if selected is None:
        return None, context, diagnostics
    return (
        tuple(selected if arg is context.operation_plan else arg for arg in args),
        replace(context, operation_plan=selected, completion_plan=selected),
        diagnostics,
    )


__all__ = ["prepare_backend_apply", "prepare_backend_invocation"]
