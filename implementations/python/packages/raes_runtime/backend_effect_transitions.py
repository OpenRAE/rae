"""Caller-owned effects and accounting for non-resource snapshot carriers."""

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisionOp
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_entry_transitions import _PLAN_DOMAINS, _identity_violation, _invalid, _same_resource
from .backend_realization_authority import _RealizationApplyContext
from .backend_snapshot_contracts import SNAPSHOT_CARRIER_OWNERS, SNAPSHOT_RECORD_CARRIERS, snapshot_values_equal


def _changed_keys(before: dict, after: dict) -> set[str]:
    return {
        key
        for key in before.keys() | after.keys()
        if key not in before or key not in after or not snapshot_values_equal(before[key], after[key])
    }


def _nonplan_entry_changes(
    result: ApplyResult, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> tuple[set[str], list[Diagnostic]]:
    changed: set[str] = set()
    for address in previous.entries.keys() | result.snapshot.entries.keys():
        before, after = previous.entries.get(address), result.snapshot.entries.get(address)
        if _same_resource(before, after):
            continue
        stopped = before is not None and before.domain == context.stop_domain and after is None
        targeted = address in context.resource_targets and before is not None and after is not None
        if not stopped and not targeted:
            return set(), _invalid(address, "Backend changed a resource outside the submitted authority.")
        if targeted:
            operation = ProvisionOp(
                ChangeAction.UPDATE,
                address,
                before.resource_type,
                before.payload,
                before.ordering_dependencies,
                before.refresh_dependencies,
                profile_bindings=before.profile_bindings,
            )
            if message := _identity_violation(operation, after, before.domain):
                return set(), _invalid(address, message)
        changed.add(address)
    if result.success and context.stop_domain is not None and result.snapshot.for_domain(context.stop_domain):
        return set(), _invalid("runtime.snapshot", "Backend did not complete the authorized resource transition.")
    return changed, []


def backend_effect_transition_diagnostics(
    result: ApplyResult, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> list[Diagnostic]:
    actual = result.snapshot
    plan = context.operation_plan
    owners = set(context.effect_owners)
    operations = {} if plan is None else {operation.address: operation for operation in plan.operations}
    if plan is not None:
        owners.update(owner.value for kind, owner in _PLAN_DOMAINS.items() if isinstance(plan, kind))
    if context.stop_domain is not None:
        owners.add(context.stop_domain.value)
    if not snapshot_values_equal(actual.metadata, previous.metadata):
        return _invalid("runtime.snapshot.metadata", "Backend changed runtime-owned snapshot metadata.")
    if actual.realization_provenance != previous.realization_provenance:
        return _invalid(
            "runtime.snapshot.realization-provenance", "Backend changed runtime-owned realization provenance."
        )
    if context.plan is None and any(
        not snapshot_values_equal(getattr(previous, name), getattr(actual, name))
        for name in ("realization_envelope", "realization_observations")
    ):
        return _invalid(
            "runtime.snapshot.realization", "Backend changed realization state outside provisioning authority."
        )
    changes: set[str] = set()
    if plan is None:
        changes, diagnostics = _nonplan_entry_changes(result, previous, context)
        if diagnostics:
            return diagnostics
    for name, owner in SNAPSHOT_CARRIER_OWNERS.items():
        if name == "entries":
            continue
        changed = _changed_keys(getattr(previous, name), getattr(actual, name))
        if context.effect_targets is not None and not changed <= context.effect_targets:
            return _invalid(
                "runtime.snapshot." + name.replace("_", "-"),
                "Backend changed a snapshot carrier outside the submitted targets.",
            )
        if changed and owner not in owners:
            return _invalid(
                "runtime.snapshot." + name.replace("_", "-"),
                "Backend changed a snapshot carrier outside its runtime-domain authority.",
            )
        if plan is not None and any(
            address not in operations or operations[address].action is ChangeAction.UNCHANGED for address in changed
        ):
            return _invalid(
                "runtime.snapshot." + name.replace("_", "-"),
                "Backend changed a snapshot carrier outside the submitted operations.",
            )
        if name not in SNAPSHOT_RECORD_CARRIERS:
            changes.update(changed)
    if actual.time_model_state != previous.time_model_state:
        if "time" not in owners:
            return _invalid(
                "runtime.snapshot.time-model-state",
                "Backend changed a snapshot carrier outside its runtime-domain authority.",
            )
        old_clocks = {} if previous.time_model_state is None else previous.time_model_state.clocks
        new_clocks = {} if actual.time_model_state is None else actual.time_model_state.clocks
        changed = _changed_keys(old_clocks, new_clocks)
        if context.effect_targets is not None and not changed <= context.effect_targets:
            return _invalid(
                "runtime.snapshot.time-model-state",
                "Backend changed a snapshot carrier outside the submitted targets.",
            )
        changes.update(changed)
    reported = set(result.changed_addresses)
    if changes - reported:
        return _invalid("runtime.changed-addresses", "Backend omitted a snapshot carrier change.")
    accounted = changes | {
        address for address, operation in operations.items() if operation.action is not ChangeAction.UNCHANGED
    }
    if reported - accounted:
        return _invalid(
            "runtime.changed-addresses", "Backend reported a change without an authorized snapshot transition."
        )
    return []
