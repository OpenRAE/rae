"""Caller-owned effects and accounting for non-resource snapshot carriers."""

from __future__ import annotations

from collections.abc import Mapping

from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisionOp
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .backend_entry_transitions import _PLAN_DOMAINS, _identity_violation, _invalid, _same_resource
from .backend_realization_authority import _RealizationApplyContext
from .backend_snapshot_contracts import SNAPSHOT_CARRIER_OWNERS, SNAPSHOT_RECORD_CARRIERS, snapshot_values_equal

_SNAPSHOT_ADDRESS_PREFIX = "runtime.snapshot."
_OUTSIDE_TARGETS = "Backend changed a snapshot carrier outside the submitted targets."
_OUTSIDE_DOMAIN = "Backend changed a snapshot carrier outside its runtime-domain authority."
_OUTSIDE_OPERATIONS = "Backend changed a snapshot carrier outside the submitted operations."
_REALIZATION_FIELDS = ("realization_envelope", "realization_observations")


def _carrier_address(name: str) -> str:
    """Name the snapshot carrier a refusal is reported against."""

    return _SNAPSHOT_ADDRESS_PREFIX + name.replace("_", "-")


def _changed_keys(before: Mapping[str, object], after: Mapping[str, object]) -> set[str]:
    return {
        key
        for key in before.keys() | after.keys()
        if key not in before or key not in after or not snapshot_values_equal(before[key], after[key])
    }


def _targeted_entry_violation(address: str, before: object, after: object) -> str | None:
    """Check one targeted entry transition against its own prior identity."""

    operation = ProvisionOp(
        ChangeAction.UPDATE,
        address,
        before.resource_type,
        before.payload,
        before.ordering_dependencies,
        before.refresh_dependencies,
        profile_bindings=before.profile_bindings,
    )
    return _identity_violation(operation, after, before.domain)


def _nonplan_entry_refusal(
    address: str, before: object, after: object, context: _RealizationApplyContext
) -> str | None:
    """Name why one unplanned entry change is inadmissible, or None when it is."""

    stopped = before is not None and before.domain == context.stop_domain and after is None
    targeted = address in context.resource_targets and before is not None and after is not None
    if not stopped and not targeted:
        return "Backend changed a resource outside the submitted authority."
    return _targeted_entry_violation(address, before, after) if targeted else None


def _nonplan_entry_change(
    address: str, result: ApplyResult, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> tuple[bool, list[Diagnostic]]:
    """Admit or refuse one entry change made without a submitted plan."""

    before, after = previous.entries.get(address), result.snapshot.entries.get(address)
    if _same_resource(before, after):
        return False, []
    message = _nonplan_entry_refusal(address, before, after, context)
    return message is None, [] if message is None else _invalid(address, message)


def _nonplan_entry_changes(
    result: ApplyResult, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> tuple[set[str], list[Diagnostic]]:
    changed: set[str] = set()
    for address in previous.entries.keys() | result.snapshot.entries.keys():
        admitted, diagnostics = _nonplan_entry_change(address, result, previous, context)
        if diagnostics:
            return set(), diagnostics
        if admitted:
            changed.add(address)
    if result.success and context.stop_domain is not None and result.snapshot.for_domain(context.stop_domain):
        return set(), _invalid("runtime.snapshot", "Backend did not complete the authorized resource transition.")
    return changed, []


def _runtime_owned_violation(
    result: ApplyResult, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> list[Diagnostic]:
    """Refuse any change a backend makes to runtime-owned snapshot state."""

    actual = result.snapshot
    realization_changed = context.plan is None and any(
        not snapshot_values_equal(getattr(previous, name), getattr(actual, name)) for name in _REALIZATION_FIELDS
    )
    checks = (
        (
            not snapshot_values_equal(actual.metadata, previous.metadata),
            "runtime.snapshot.metadata",
            "Backend changed runtime-owned snapshot metadata.",
        ),
        (
            actual.realization_provenance != previous.realization_provenance,
            "runtime.snapshot.realization-provenance",
            "Backend changed runtime-owned realization provenance.",
        ),
        (
            realization_changed,
            "runtime.snapshot.realization",
            "Backend changed realization state outside provisioning authority.",
        ),
    )
    refusal = next(((address, message) for violated, address, message in checks if violated), None)
    return [] if refusal is None else _invalid(*refusal)


def _effect_owners(context: _RealizationApplyContext) -> set[str]:
    """Collect every runtime domain authorized to change a snapshot carrier."""

    plan = context.operation_plan
    owners = set(context.effect_owners)
    if plan is not None:
        owners.update(owner.value for kind, owner in _PLAN_DOMAINS.items() if isinstance(plan, kind))
    if context.stop_domain is not None:
        owners.add(context.stop_domain.value)
    return owners


def _carrier_change_violation(
    name: str,
    changed: set[str],
    *,
    context: _RealizationApplyContext,
    owners: set[str],
    operations: Mapping[str, ProvisionOp],
    planned: bool,
) -> list[Diagnostic]:
    """Refuse one carrier's changes when they leave the submitted authority."""

    if context.effect_targets is not None and not changed <= context.effect_targets:
        return _invalid(_carrier_address(name), _OUTSIDE_TARGETS)
    if changed and SNAPSHOT_CARRIER_OWNERS[name] not in owners:
        return _invalid(_carrier_address(name), _OUTSIDE_DOMAIN)
    unplanned = planned and any(
        address not in operations or operations[address].action is ChangeAction.UNCHANGED for address in changed
    )
    return _invalid(_carrier_address(name), _OUTSIDE_OPERATIONS) if unplanned else []


def _carrier_changes(
    result: ApplyResult,
    previous: RuntimeSnapshot,
    *,
    context: _RealizationApplyContext,
    owners: set[str],
    operations: Mapping[str, ProvisionOp],
    planned: bool,
) -> tuple[set[str], list[Diagnostic]]:
    """Admit every non-entry snapshot carrier change and collect the accounted ones."""

    changes: set[str] = set()
    for name in SNAPSHOT_CARRIER_OWNERS:
        if name == "entries":
            continue
        changed = _changed_keys(getattr(previous, name), getattr(result.snapshot, name))
        diagnostics = _carrier_change_violation(
            name,
            changed,
            context=context,
            owners=owners,
            operations=operations,
            planned=planned,
        )
        if diagnostics:
            return set(), diagnostics
        if name not in SNAPSHOT_RECORD_CARRIERS:
            changes.update(changed)
    return changes, []


def _time_model_changes(
    result: ApplyResult, previous: RuntimeSnapshot, *, context: _RealizationApplyContext, owners: set[str]
) -> tuple[set[str], list[Diagnostic]]:
    """Admit a time-model transition only for its owning domain and targets."""

    if result.snapshot.time_model_state == previous.time_model_state:
        return set(), []
    if "time" not in owners:
        return set(), _invalid("runtime.snapshot.time-model-state", _OUTSIDE_DOMAIN)
    old_clocks = {} if previous.time_model_state is None else previous.time_model_state.clocks
    new_clocks = {} if result.snapshot.time_model_state is None else result.snapshot.time_model_state.clocks
    changed = _changed_keys(old_clocks, new_clocks)
    outside = context.effect_targets is not None and not changed <= context.effect_targets
    return (set(), _invalid("runtime.snapshot.time-model-state", _OUTSIDE_TARGETS)) if outside else (changed, [])


def _accounting_violation(
    result: ApplyResult, changes: set[str], operations: Mapping[str, ProvisionOp]
) -> list[Diagnostic]:
    """Require reported changes and authorized transitions to account for each other."""

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


def _admitted_effect_changes(
    result: ApplyResult,
    previous: RuntimeSnapshot,
    *,
    context: _RealizationApplyContext,
    operations: Mapping[str, ProvisionOp],
) -> tuple[set[str], list[Diagnostic]]:
    """Admit every entry, carrier, and time-model change the caller owns."""

    plan = context.operation_plan
    changes: set[str] = set()
    if plan is None:
        changes, diagnostics = _nonplan_entry_changes(result, previous, context)
        if diagnostics:
            return set(), diagnostics
    owners = _effect_owners(context)
    for collected, diagnostics in (
        _carrier_changes(
            result, previous, context=context, owners=owners, operations=operations, planned=plan is not None
        ),
        _time_model_changes(result, previous, context=context, owners=owners),
    ):
        if diagnostics:
            return set(), diagnostics
        changes.update(collected)
    return changes, []


def backend_effect_transition_diagnostics(
    result: ApplyResult, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> list[Diagnostic]:
    plan = context.operation_plan
    operations = {} if plan is None else {operation.address: operation for operation in plan.operations}
    owned = _runtime_owned_violation(result, previous, context)
    if owned:
        return owned
    changes, diagnostics = _admitted_effect_changes(result, previous, context=context, operations=operations)
    return diagnostics or _accounting_violation(result, changes, operations)
