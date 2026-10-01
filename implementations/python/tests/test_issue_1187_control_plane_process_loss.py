"""Abrupt owner loss, pre-recovery state cuts, and explicit P0 nonclaims."""

from __future__ import annotations

import pytest
from control_plane_conformance_fixtures import (
    DURABLE_PROFILES,
    inspect_store,
    profile_harness,
    terminal_audits,
    witness_events,
)
from control_plane_crash_fixtures import APPLIED, COMMITTED, CRASH_BOUNDARIES, UNCLAIMED, kill_at
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload

pytestmark = [pytest.mark.control_plane_conformance, pytest.mark.integration]


@pytest.mark.parametrize("profile", DURABLE_PROFILES)
@pytest.mark.parametrize("boundary", CRASH_BOUNDARIES)
def test_process_loss_preserves_atomic_cut_and_classifies_without_replay(profile, boundary, tmp_path) -> None:
    operation_id = kill_at(profile, tmp_path, boundary)
    before_effects = witness_events(tmp_path / "effects.jsonl")
    with inspect_store(tmp_path) as store:
        records = store.load_records()
        state = store.load_snapshot_state()
        expected_snapshot = (
            _snapshot_from_payload(before_effects[-1]["snapshot"]) if boundary in COMMITTED else RuntimeSnapshot()
        )
        assert state.snapshot == expected_snapshot
        assert state.revision == (1 if boundary in COMMITTED else 0)
        if boundary in UNCLAIMED:
            assert records == {}
            assert store.read_audit() == []
        else:
            assert set(records) == {operation_id}
            assert records[operation_id].status.state is (
                OperationState.SUCCEEDED if boundary in COMMITTED else OperationState.RUNNING
            )
            assert len(terminal_audits(store, operation_id)) == (1 if boundary in COMMITTED else 0)
    with profile_harness(profile, tmp_path, observe=True) as harness:
        if boundary in UNCLAIMED:
            assert harness.status(operation_id) is None
            assert harness.store.load_records() == {}
        else:
            expected = OperationState.SUCCEEDED if boundary in APPLIED else OperationState.FAILED
            assert harness.status(operation_id) is expected
            if boundary in APPLIED:
                assert harness.plane.snapshot == _snapshot_from_payload(before_effects[-1]["snapshot"])
            assert harness.submit() == operation_id
            record = harness.store.load_records()[operation_id]
            assert record.status.context.actor_id == "alice"
            audits = terminal_audits(harness.store, operation_id)
            assert len(audits) == 1
            assert audits[0].identity == "alice"
            if boundary not in COMMITTED:
                classification = "effect-applied" if boundary in APPLIED else "effect-absent"
                assert f"runtime.control-plane.recovery-{classification}" in [d.code for d in record.status.diagnostics]
        assert witness_events(tmp_path / "effects.jsonl") == before_effects
    # A second owner must preserve the terminal state, claim and audit, too.
    with profile_harness(profile, tmp_path, observe=True) as harness:
        if boundary not in UNCLAIMED:
            assert harness.submit() == operation_id
            assert len(terminal_audits(harness.store, operation_id)) == 1
        assert witness_events(tmp_path / "effects.jsonl") == before_effects


@pytest.mark.parametrize("profile", DURABLE_PROFILES)
def test_unobservable_applied_effect_is_indeterminate_and_never_replayed(profile, tmp_path) -> None:
    operation_id = kill_at(profile, tmp_path, "after-invoke")
    effects = witness_events(tmp_path / "effects.jsonl")
    assert [event["event"] for event in effects] == ["invoke", "applied"]
    for _ in range(2):
        with profile_harness(profile, tmp_path) as harness:
            assert harness.status(operation_id) is OperationState.INDETERMINATE
            assert harness.submit() == operation_id
            assert len(terminal_audits(harness.store, operation_id)) == 1
            assert witness_events(tmp_path / "effects.jsonl") == effects
            status = harness.store.load_records()[operation_id].status
            assert "runtime.control-plane.recovery-effect-unobservable" in [item.code for item in status.diagnostics]


@pytest.mark.parametrize("profile", DURABLE_PROFILES)
@pytest.mark.parametrize(
    "boundary", ["before-terminal", "after-snapshot", "after-record", "after-audit", "after-terminal"]
)
def test_recovery_itself_can_be_killed_without_partial_state_or_replay(profile, boundary, tmp_path) -> None:
    operation_id = kill_at(profile, tmp_path, "after-invoke")
    effects = witness_events(tmp_path / "effects.jsonl")
    assert kill_at(profile, tmp_path, boundary, recovering=True) == operation_id
    with inspect_store(tmp_path) as store:
        committed = boundary == "after-terminal"
        assert store.load_records()[operation_id].status.state is (
            OperationState.SUCCEEDED if committed else OperationState.RUNNING
        )
        assert store.load_snapshot_state().revision == int(committed)
        assert len(terminal_audits(store, operation_id)) == int(committed)
    with profile_harness(profile, tmp_path, observe=True) as harness:
        assert harness.status(operation_id) is OperationState.SUCCEEDED
        assert harness.submit() == operation_id
        assert harness.snapshot_cut() == ({}, 1)
        assert len(terminal_audits(harness.store, operation_id)) == 1
        assert witness_events(tmp_path / "effects.jsonl") == effects


def test_p0_process_loss_loses_run_and_claim_even_when_external_effect_survives(tmp_path) -> None:
    operation_id = kill_at("P0", tmp_path, "after-response")
    assert [item["event"] for item in witness_events(tmp_path / "effects.jsonl")] == ["invoke", "applied"]
    with profile_harness("P0", tmp_path) as harness:
        assert harness.status(operation_id) is None
        assert harness.store.load_records() == {}
        assert harness.snapshot_cut() == ({}, 0)
        # This explicit new submission demonstrates the nonclaim: P0 has no
        # persisted deduplication and cannot promise exactly-once effects.
        assert harness.submit() != operation_id
        assert [item["event"] for item in witness_events(tmp_path / "effects.jsonl")] == ["invoke", "applied"] * 2
