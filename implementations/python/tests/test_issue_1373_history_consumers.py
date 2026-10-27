"""Stored immutable streams retain closure, shared-state and concurrency checks."""

from copy import deepcopy
from types import MappingProxyType

from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane_store_revision import SnapshotState


def test_stored_closure_survives_snapshot_updates_and_backend_validation():
    from raes_runtime.participant_result_contracts import participant_episode_closure_contract_diagnostics
    from test_sem_222_episode_termination_semantics import (
        _ADDRESS,
        _closure_payload,
        _terminal_history,
        _terminal_result,
    )

    original = RuntimeSnapshot(
        participant_episode_results=_terminal_result(),
        participant_episode_history=_terminal_history(),
        participant_episode_closure_records={_ADDRESS: [_closure_payload()]},
    )
    stored = SnapshotState(original, 1).snapshot.with_entries({})
    assert participant_episode_closure_contract_diagnostics(stored) == []
    _unchanged_backend_result(stored)


def test_stored_shared_state_and_joint_action_keep_their_reference_joins():
    from raes_runtime.participant_result_contracts import participant_runtime_state_contract_diagnostics
    from test_run_308_concurrent_participant_execution import _snapshot_payload

    payload = _snapshot_payload()
    stored = SnapshotState(
        RuntimeSnapshot(**{key: value for key, value in payload.items() if key != "schema_version"}), 1
    ).snapshot.with_entries({})
    assert participant_runtime_state_contract_diagnostics(stored) == []
    _unchanged_backend_result(stored)


def _unchanged_backend_result(snapshot):
    from raes_contracts.runtime_state import ApplyResult
    from raes_runtime.backend_calls import _call_backend_apply, _RealizationApplyContext

    result = _call_backend_apply(
        lambda _, current: ApplyResult(True, current.with_entries(dict(current.entries))),
        object(),
        snapshot,
        address="runtime.control-plane.retained-history",
        snapshot=snapshot,
        realization=_RealizationApplyContext(effect_owners=frozenset({"participant"})),
    )
    assert result.success, result.diagnostics


def test_shared_history_has_no_mutable_base_containers_or_caller_owned_children():
    from raes_contracts.immutable_history import HistoryMap

    child = {"values": [1]}
    history = HistoryMap("evaluation_history", {"run": [MappingProxyType({"nested": child})]})
    digest = history["run"].prefix_digest(1)
    copied = deepcopy(history)
    child["values"].append(2)
    raw = copied["run"]._entries[0][0]
    try:
        dict.__setitem__(raw, "changed", True)
    except TypeError:
        pass
    else:
        raise AssertionError("shared retained storage exposed a mutable base dictionary")
    assert copied["run"][0] == {"nested": {"values": [1]}}
    assert copied["run"].prefix_digest(1) == digest


def test_caller_constructed_readonly_views_are_not_trusted_resource_values():
    from raes_contracts.realization_structure import validate_realization_value

    mutable = []
    wrapper = MappingProxyType({"child": mutable})
    assert not validate_realization_value(wrapper, python_carriers=True).conformant
