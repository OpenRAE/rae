"""Measure the public effect-execution boundary with settled retained work."""

import pytest
from governed_effect_runtime_fixtures import effect_plane
from participant_crossing_fixtures import PARTICIPANT, admit, identity


@pytest.mark.parametrize("durable", [False, True])
def test_repeated_drain_returns_recorded_result_without_reloading_all_operations(monkeypatch, tmp_path, durable):
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    plane, _ = effect_plane(store=LocalControlPlaneStore(tmp_path / "ledger") if durable else None)
    caller = identity(audience_bound=True)
    with plane:
        admit(plane, control_identity=caller)
        expected = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert len(expected) == 1

        def full_scan(*args, **kwargs):
            raise AssertionError("settled drain reloaded accumulated operations")

        monkeypatch.setattr(plane._store, "load_records", full_scan)
        from raes_runtime import participant_control_projection

        monkeypatch.setattr(participant_control_projection, "participant_control_evaluation_from_payload", full_scan)
        from raes_contracts.immutable_history import EventHistory

        monkeypatch.setattr(EventHistory, "__iter__", full_scan)
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == expected


@pytest.mark.parametrize("durable", [False, True])
@pytest.mark.parametrize("retained", [8, 64, 512])
def test_atomic_append_visits_only_new_records(tmp_path, durable, retained):
    from issue_1373_workload import measure_atomic_append
    from raes_runtime.control_plane_store import InMemoryControlPlaneStore, LocalControlPlaneStore

    store = LocalControlPlaneStore(tmp_path / "append") if durable else InMemoryControlPlaneStore()
    counts = measure_atomic_append(store, retained)
    assert counts["history_records_visited"] == 0
    assert counts["old_history_index_reads"] == 0
    assert counts["full_operation_loads"] == 0


def test_completed_outcome_cache_preserves_order_with_unresolved_earlier_work():
    from participant_control_runtime_fixtures import _effect_evidence, _handoff_intent
    from raes_runtime.participant_control_effects import ParticipantControlEffectOperation

    plane, owner = effect_plane()
    caller = identity(audience_bound=True)
    with plane:
        admit(plane, control_identity=caller, idempotency_key="earlier")
        owner.effect_id = "effect-2"
        admit(plane, control_identity=caller, idempotency_key="later")
        owner.operation = lambda request, context: (
            None
            if request.effect_id == "effect-1"
            else ParticipantControlEffectOperation(
                kind="handoff",
                intent=_handoff_intent(context, request.target),
                crossing_evidence=_effect_evidence(context),
            )
        )
        first = plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        assert [item.effect_id for item in first] == ["effect-1", "effect-2"]
        assert [item.disposition for item in first] == ["unsupported", "applied"]
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller) == first


@pytest.mark.parametrize("durable", [False, True])
def test_operation_only_commit_does_not_read_stored_history(tmp_path, durable):
    from issue_1373_workload import measure
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_runtime.control_plane_store import InMemoryControlPlaneStore, LocalControlPlaneStore, TerminalCommitMode
    from test_issue_1181_unified_control_plane_mutations import _running_record, _terminal_audit, _terminal_record

    store = LocalControlPlaneStore(tmp_path / "operation-only") if durable else InMemoryControlPlaneStore()
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:issue-1181") if durable else None
    try:
        saved = store.save_snapshot(
            RuntimeSnapshot(evaluation_history={"run": [{"n": n} for n in range(64)]}), expected_revision=0
        )
        running = _running_record()
        store.claim_record(running)
        terminal = _terminal_record(running)
        _, counts = measure(
            lambda: store.commit_terminal_operation(
                saved.snapshot,
                terminal,
                audit_event=_terminal_audit(terminal),
                mode=TerminalCommitMode.OPERATION_ONLY,
                expected_revision=saved.revision,
            ),
            store,
        )
        assert counts["old_history_index_reads"] == 0
    finally:
        if durable:
            store.close()
            lease.close()
