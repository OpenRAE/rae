"""Trusted operation authority and mutable-result boundary regressions."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, SnapshotEntry
from raes_runtime.backend_calls import _call_backend_apply, _call_backend_diagnostics

ADDRESS = "provision.feature.web.lab"
OTHER = "provision.feature.web.other"


def _entry(address=ADDRESS, **updates):
    return replace(
        SnapshotEntry(address, RuntimeDomain.PROVISIONING, "feature-binding", {"name": "lab"}, status="applied"),
        **updates,
    )


def _plan(action):
    return ProvisioningPlan(operations=[ProvisionOp(action, ADDRESS, "feature-binding", {"name": "lab"})])


def _call(plan, previous, candidate, changed):
    return _call_backend_apply(
        lambda *_: ApplyResult(True, candidate, changed_addresses=changed, details={"candidate": "private"}),
        plan,
        previous,
        address="runtime.apply.provisioning",
        snapshot=previous,
    )


def _assert_rejected(result, previous, message):
    assert result.success is False
    assert result.snapshot == previous
    assert result.changed_addresses == []
    assert result.details == {}
    assert [(item.code, item.message) for item in result.diagnostics] == [("runtime.backend-contract-invalid", message)]


@pytest.mark.parametrize("action", list(ChangeAction))
def test_honest_actions_include_equal_payload_refresh_and_status_annotation(action):
    previous = RuntimeSnapshot(entries={} if action is ChangeAction.CREATE else {ADDRESS: _entry()})
    candidate = previous.with_entries(
        {}
        if action is ChangeAction.DELETE
        else {ADDRESS: _entry(status="unchanged" if action is ChangeAction.UNCHANGED else "applied")}
    )
    result = _call(_plan(action), previous, candidate, [] if action is ChangeAction.UNCHANGED else [ADDRESS])
    assert result.success, result.diagnostics
    assert result.snapshot == candidate


@pytest.mark.parametrize("action", [ChangeAction.CREATE, ChangeAction.UPDATE, ChangeAction.DELETE])
def test_successful_action_cannot_omit_accounting(action):
    previous = RuntimeSnapshot(entries={} if action is ChangeAction.CREATE else {ADDRESS: _entry()})
    candidate = previous.with_entries({} if action is ChangeAction.DELETE else {ADDRESS: _entry()})
    result = _call(_plan(action), previous, candidate, [])
    _assert_rejected(result, previous, "Backend omitted an authorized resource change.")


def test_successful_delete_cannot_return_the_predecessor():
    previous = RuntimeSnapshot(entries={ADDRESS: _entry()})
    result = _call(_plan(ChangeAction.DELETE), previous, deepcopy(previous), [ADDRESS])
    _assert_rejected(result, previous, "Backend did not complete the authorized resource transition.")


def test_unchanged_cannot_claim_a_change():
    previous = RuntimeSnapshot(entries={ADDRESS: _entry()})
    result = _call(_plan(ChangeAction.UNCHANGED), previous, deepcopy(previous), [ADDRESS])
    _assert_rejected(result, previous, "Backend reported a resource change without an authorized transition.")


def test_unrelated_predecessor_entry_cannot_disappear():
    previous = RuntimeSnapshot(entries={OTHER: _entry(OTHER)}, metadata={"trusted": [1]})
    candidate = previous.with_entries({ADDRESS: _entry()})
    result = _call(_plan(ChangeAction.CREATE), previous, candidate, [ADDRESS, OTHER])
    _assert_rejected(result, previous, "Backend changed a resource outside the submitted authority.")


def test_backend_cannot_mutate_the_plan_used_for_identity_comparison():
    plan = _plan(ChangeAction.CREATE)
    original = deepcopy(plan)
    previous = RuntimeSnapshot(metadata={"trusted": [1]})

    def mutate(submitted, snapshot):
        submitted.operations[0].payload["name"] = "replacement"
        snapshot.metadata["trusted"].append(2)
        return ApplyResult(
            True, snapshot.with_entries({ADDRESS: _entry(payload={"name": "replacement"})}), changed_addresses=[ADDRESS]
        )

    result = _call_backend_apply(mutate, plan, previous, address="runtime.apply.provisioning", snapshot=previous)
    assert plan == original
    assert previous == RuntimeSnapshot(metadata={"trusted": [1]})
    _assert_rejected(result, previous, "Backend changed a plan-owned resource identity.")


def test_accepted_snapshot_and_details_do_not_alias_backend_objects():
    previous = RuntimeSnapshot()
    candidate = RuntimeSnapshot(entries={ADDRESS: _entry()})
    result = _call(_plan(ChangeAction.CREATE), previous, candidate, [ADDRESS])
    assert result.success, result.diagnostics
    accepted = deepcopy(result.snapshot)
    candidate.entries[ADDRESS].payload["name"] = "later-mutation"
    assert result.snapshot == accepted


def test_backend_validation_cannot_mutate_the_submitted_plan():
    plan = _plan(ChangeAction.CREATE)
    original = deepcopy(plan)

    def validate(submitted):
        submitted.operations[0].payload["name"] = "replacement"
        return []

    assert _call_backend_diagnostics(validate, plan, address="runtime.validate") == []
    assert plan == original


def test_unchanged_resource_cannot_hide_a_boolean_integer_rewrite():
    previous = RuntimeSnapshot(entries={ADDRESS: _entry(payload={"name": "lab", "value": 1})})
    candidate = previous.with_entries({ADDRESS: _entry(payload={"name": "lab", "value": True})})
    plan = ProvisioningPlan(
        operations=[ProvisionOp(ChangeAction.UNCHANGED, ADDRESS, "feature-binding", {"name": "lab", "value": 1})]
    )
    result = _call(plan, previous, candidate, [])
    _assert_rejected(result, previous, "Backend did not complete the authorized resource transition.")


@pytest.mark.parametrize("matches", [True, False])
def test_submitted_operation_and_trusted_authority_are_bound_before_apply(matches):
    from raes_runtime.backend_calls import _RealizationApplyContext

    authority = _plan(ChangeAction.CREATE)
    submitted = deepcopy(authority)
    if not matches:
        submitted.operations[0].payload["name"] = "replacement"
    previous, calls = RuntimeSnapshot(), []

    def backend(request, snapshot):
        calls.append(True)
        return ApplyResult(
            True,
            snapshot.with_entries({ADDRESS: _entry(payload=request.operations[0].payload)}),
            changed_addresses=[ADDRESS],
        )

    result = _call_backend_apply(
        backend,
        submitted,
        previous,
        snapshot=previous,
        address="runtime.authority",
        realization=_RealizationApplyContext(plan=authority),
    )
    assert result.success is matches
    assert len(calls) == int(matches)
    if not matches:
        _assert_rejected(result, previous, "Submitted operation does not match its realization authority.")
