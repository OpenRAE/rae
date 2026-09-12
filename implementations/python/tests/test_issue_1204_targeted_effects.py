"""A native call's domain is not authority over unrelated targets in that domain."""

from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import StubParticipantRuntime
from raes_contracts.participant_episode import ParticipantEpisodeInitializeRequest
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane_execution import apply_authorized_participant_action


@pytest.mark.parametrize("extra", [False, True])
def test_participant_episode_call_is_bound_to_the_requested_participant(extra):
    first, second = "participant.behavior.first", "participant.behavior.second"
    backend = StubParticipantRuntime()
    previous = RuntimeSnapshot()

    def initialize(request, snapshot):
        result = backend.initialize(request, snapshot)
        if extra:
            result = backend.initialize(ParticipantEpisodeInitializeRequest(second), result.snapshot)
            result = replace(result, changed_addresses=[first, second])
        return result

    result = apply_authorized_participant_action(
        method=initialize,
        request=ParticipantEpisodeInitializeRequest(first),
        snapshot=previous,
        address="runtime.participant.initialize",
    )
    assert result.success is not extra, result.diagnostics
    if extra:
        assert result.snapshot == previous
        assert result.changed_addresses == []
    else:
        assert first in result.snapshot.participant_episode_results


@pytest.mark.parametrize("extra", [False, True])
def test_execution_service_control_cannot_change_a_second_scope(extra):
    from raes_contracts.contracts.participant_execution import ParticipantExecutionControlRequestModel
    from raes_runtime.participant_execution_control_boundary import backend_execution_control_method
    from test_issue_898_participant_execution_control import _NativeParticipantRuntime, _service_state

    first, second = "participant.autonomous-execution.first", "participant.autonomous-execution.second"
    previous = RuntimeSnapshot(
        participant_execution_services={
            scope: _service_state(execution_scope_ref=scope, policy_address=scope).model_dump(mode="json")
            for scope in (first, second)
        }
    )
    backend = _NativeParticipantRuntime()

    def control(request, snapshot):
        result = backend.control_execution(request, snapshot)
        if extra:
            result = backend.control_execution(
                request.model_copy(update={"execution_scope_ref": second}), result.snapshot
            )
            result = replace(result, changed_addresses=[first, second])
        return result

    result = backend_execution_control_method(control)(
        ParticipantExecutionControlRequestModel(execution_scope_ref=first, action="start", expected_generation=0),
        previous,
    )
    assert result.success is not extra, result.diagnostics
    if extra:
        assert result.snapshot == previous
        assert result.changed_addresses == []
    else:
        assert result.snapshot.participant_execution_services[first]["observed_lifecycle"] == "running"


@pytest.mark.parametrize("extra", [False, True])
def test_time_control_cannot_advance_an_unrequested_clock(extra):
    from raes_backend_stubs.stubs import create_stub_target
    from raes_runtime import RuntimeManager
    from test_api_421_time_contracts import _scenario

    scenario = _scenario()
    scenario.clocks["other-clock"] = scenario.clocks["scenario-clock"].model_copy(deep=True)
    scenario.time_progression_policies["other-policy"] = scenario.time_progression_policies[
        "scenario-policy"
    ].model_copy(update={"clock_ref": "other-clock"})
    target = create_stub_target()
    manager = RuntimeManager(target)
    assert manager.apply(manager.plan(scenario)).success
    previous = manager.snapshot
    advance = target.time_runtime.advance

    def combined(clock, ticks, microstep, snapshot):
        result = advance(clock, ticks, microstep, snapshot)
        if extra:
            result = advance("time.clock.other-clock", ticks, microstep, result.snapshot)
            result = replace(result, changed_addresses=[clock, "time.clock.other-clock"])
        return result

    target.time_runtime.advance = combined
    result = manager.advance_time("time.clock.scenario-clock", ticks=10)
    assert result.success is not extra, result.diagnostics
    if extra:
        assert result.snapshot == previous
        assert manager.snapshot == previous
    else:
        assert manager.read_time_state().clocks["time.clock.other-clock"].coordinate.tick == 0


@pytest.mark.parametrize("alter_profile", [False, True])
def test_resource_effect_preserves_preexisting_profile_identity(alter_profile):
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import ApplyResult, SnapshotEntry
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
    from test_issue_1204_profile_carrier import _profiles

    address = "provision.node.host"
    authority, _ = _profiles()
    before = SnapshotEntry(
        address, RuntimeDomain.PROVISIONING, "node", {"name": "host", "value": 1}, profile_bindings=authority.bindings
    )
    previous = RuntimeSnapshot(entries={address: before})
    after = replace(
        before, payload={"name": "host", "value": 2}, profile_bindings=() if alter_profile else before.profile_bindings
    )
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, previous.with_entries({address: after}), changed_addresses=[address]),
        previous,
        address="runtime.participant",
        snapshot=previous,
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), resource_targets=frozenset({address})
        ),
    )
    assert result.success is not alter_profile, result.diagnostics
    assert result.snapshot.entries[address].profile_bindings == before.profile_bindings


def test_resource_targets_do_not_grant_another_carrier_owner():
    from raes_contracts.runtime_state import ApplyResult
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

    address = "time.context.extra"
    previous = RuntimeSnapshot()
    candidate = RuntimeSnapshot(
        time_management_contexts={
            address: {
                "context_id": address,
                "mode": "unsupported",
                "unsupported_disclosure": True,
            }
        }
    )
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, candidate),
        previous,
        address="runtime.time",
        snapshot=previous,
        realization=_RealizationApplyContext(effect_owners=frozenset({"time"}), resource_targets=frozenset({address})),
    )
    assert not result.success
    assert result.snapshot == previous
    assert result.diagnostics[0].message == "Backend changed a snapshot carrier outside its runtime-domain authority."


def test_unrelated_profile_cannot_hide_a_boolean_integer_rewrite():
    from raes_contracts.planning import RuntimeDomain
    from raes_contracts.runtime_state import ApplyResult, SnapshotEntry
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext
    from test_issue_1204_profile_carrier import _profiles

    authority, _ = _profiles()
    binding = authority.bindings[0].model_copy(update={"value": {"number": 1}})
    address = "provision.node.host"
    before = SnapshotEntry(address, RuntimeDomain.PROVISIONING, "node", {"name": "host"}, profile_bindings=(binding,))
    previous = RuntimeSnapshot(entries={address: before})
    after = replace(before, profile_bindings=(binding.model_copy(update={"value": {"number": True}}),))
    result = _call_backend_apply(
        lambda *_: ApplyResult(True, previous.with_entries({address: after})),
        previous,
        address="runtime.participant",
        snapshot=previous,
        realization=_RealizationApplyContext(effect_owners=frozenset({"participant"})),
    )
    assert not result.success
    assert type(result.snapshot.entries[address].profile_bindings[0].value["number"]) is int
