"""Read-only backend preparation at the existing trusted apply boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.backend_preparation import preparation_response_model
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


def _selected_plan(plan: ProvisioningPlan, response: RealizationPreparation) -> ProvisioningPlan:
    if type(response.operations) is not tuple or len(response.operations) > 16384:
        raise ValueError("invalid preparation operation inventory")
    for operation in response.operations:
        if (
            type(operation) is not ProvisionOp
            or not isinstance(operation.action, ChangeAction)
            or not isinstance(operation.payload, dict)
            or type(operation.ordering_dependencies) is not tuple
            or type(operation.refresh_dependencies) is not tuple
            or not validate_realization_value(operation.payload, python_carriers=True).conformant
        ):
            raise ValueError("invalid preparation operation")
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
    return replace(plan, operations=operations, resources=resources)


def _transition_violation(
    original: ProvisioningPlan, selected: ProvisioningPlan, previous: RuntimeSnapshot
) -> str | None:
    collection_violation = prepared_node_collection_violation(original, selected, previous)
    if collection_violation:
        return collection_violation
    candidates = {operation.address: operation for operation in selected.operations}
    for operation in original.operations:
        candidate = candidates.get(operation.address)
        if candidate is None or replace(candidate, payload={}, profile_bindings=()) != replace(
            operation, payload={}, profile_bindings=()
        ):
            return "Backend preparation changed submitted operation authority."
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
    result = ApplyResult(
        True,
        previous.with_entries(entries),
        changed_addresses=[operation.address for operation in selected.actionable_operations],
    )
    invalid = _apply_result_contract_violation(result, "runtime.preparation")
    if invalid:
        return invalid
    original_addresses = {operation.address for operation in original.operations}
    # Extra operation authority is derived only after the enclosing relation
    # admitted it. The normal identity/effect/accounting gate still applies.
    authorized = replace(
        original,
        operations=[
            *(
                replace(operation, profile_bindings=candidates[operation.address].profile_bindings)
                for operation in original.operations
            ),
            *(operation for operation in selected.operations if operation.address not in original_addresses),
        ],
    )
    diagnostics = backend_entry_transition_diagnostics(result, previous, authorized)
    return diagnostics[0].message if diagnostics else None


def prepare_backend_apply(
    method: object, plan: ProvisioningPlan, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> tuple[ProvisioningPlan | None, list]:
    """Admit one backend completion; all exceptions become value-free failures."""

    try:
        manifest = context.manifest
        if manifest is None or BACKEND_PREPARATION_CONTRACT not in manifest.supported_contract_versions:
            raise ValueError("Selected backend does not support the preparation contract.")
        manifest_digest = canonical_json_digest(backend_manifest_v2_model(manifest).model_dump(mode="json"))
        if plan.preparation is None or plan.preparation.manifest_digest != manifest_digest:
            raise ValueError("Preparation authority does not match the selected backend manifest.")
        if prepared_node_collection_binding_violation(plan):
            raise ValueError("Preparation collection authority does not match the submitted membership.")
        profile_context = configured_profile_context(method, plan, manifest)
        component = getattr(method, "__self__", None)
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
        diagnostics, invalid = _materialize_diagnostics(response.diagnostics, "runtime.preparation")
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
        profile_diagnostics = []
        if plan.profile_authority is not None:
            profile_diagnostics, invalid = _materialize_diagnostics(
                component.validate_profiles(deepcopy(selected)), "runtime.preparation"
            )
            if invalid or any(diagnostic.is_error for diagnostic in profile_diagnostics):
                raise ValueError("Installed profile semantics refused the selected completion.")
        validate = getattr(component, "validate", None)
        if not callable(validate):
            raise ValueError("Selected backend has no prepared-plan validation boundary.")
        validation_diagnostics, invalid = _materialize_diagnostics(validate(deepcopy(selected)), "runtime.preparation")
        if invalid or any(diagnostic.is_error for diagnostic in validation_diagnostics):
            raise ValueError("Backend cannot apply the admitted completion.")
    except Exception:
        return None, [
            _failure_diagnostic(
                "runtime.backend-preparation-invalid",
                "runtime.preparation",
                "Backend preparation did not establish a valid bound supported completion.",
            )
        ]
    combined = [*diagnostics, *profile_diagnostics, *validation_diagnostics]
    if plan_has_account_credentials(plan):
        combined = value_free_backend_diagnostics(combined)
    return selected, combined


def prepare_backend_invocation(method, args, previous, context):
    """Replace only the admitted operation argument; retain the original authority."""

    if context.plan is None:
        return args, context, []
    if context.plan.profile_authority is not None and context.plan.preparation is None:
        return (
            None,
            context,
            [
                _failure_diagnostic(
                    "runtime.backend-preparation-invalid",
                    "runtime.preparation",
                    "Profile execution requires negotiated preparation.",
                )
            ],
        )
    if context.plan.preparation is None:
        if any(getattr(op, "profile_bindings", ()) for op in context.plan.operations):
            return (
                None,
                context,
                [
                    _failure_diagnostic(
                        "runtime.backend-preparation-invalid",
                        "runtime.preparation",
                        "Unowned profile bindings are not execution authority.",
                    )
                ],
            )
        return args, context, []
    selected, diagnostics = prepare_backend_apply(method, context.plan, previous, context)
    if selected is None:
        return None, context, diagnostics
    return (
        tuple(selected if arg is context.operation_plan else arg for arg in args),
        replace(context, operation_plan=selected, completion_plan=selected),
        diagnostics,
    )


__all__ = ["prepare_backend_apply", "prepare_backend_invocation"]
