"""Reproduce fixed-output save and execution work; run as a standalone module."""

import json
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

from raes_contracts.immutable_history import HISTORY_FIELDS, EventHistory, append_history
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.control_plane_store import InMemoryControlPlaneStore, LocalControlPlaneStore


def measure(call, store):
    from raes_runtime import participant_control_projection

    cut = store.load_snapshot_state().snapshot
    old_records = {
        id(history._entries[position][0])
        for field in HISTORY_FIELDS
        for history in getattr(cut, field).values()
        for position in range(len(history))
    }
    counts = dict(history_records_visited=0, old_history_index_reads=0, full_operation_loads=0, evaluations_parsed=0)
    original_getitem = EventHistory.__getitem__
    original_iter = EventHistory.__iter__
    original_load = store.load_records
    original_parse = participant_control_projection.participant_control_evaluation_from_payload

    def getitem(history, position):
        if isinstance(position, int):
            normalized = position if position >= 0 else len(history) + position
            if 0 <= normalized < len(history) and id(history._entries[normalized][0]) in old_records:
                counts["old_history_index_reads"] += 1
        return original_getitem(history, position)

    def iterate(history):
        for record in original_iter(history):
            counts["history_records_visited"] += 1
            yield record

    def load(*args, **kwargs):
        counts["full_operation_loads"] += 1
        return original_load(*args, **kwargs)

    def parse(payload):
        counts["evaluations_parsed"] += 1
        return original_parse(payload)

    with ExitStack() as stack:
        stack.enter_context(patch.object(EventHistory, "__iter__", iterate))
        stack.enter_context(patch.object(EventHistory, "__getitem__", getitem))
        stack.enter_context(patch.object(store, "load_records", load))
        stack.enter_context(
            patch.object(participant_control_projection, "participant_control_evaluation_from_payload", parse)
        )
        start = perf_counter()
        result = call()
        elapsed = perf_counter() - start
    return result, {**counts, "elapsed_ms": round(elapsed * 1000, 3)}


def measure_atomic_append(store, retained):
    from test_issue_1181_unified_control_plane_mutations import _running_record, _terminal_audit, _terminal_record

    lease = (
        store.admit_runtime(target_scope="target:stub", run_scope="run:issue-1181")
        if hasattr(store, "admit_runtime")
        else None
    )
    try:
        before = store.save_snapshot(
            RuntimeSnapshot(evaluation_history={"run": [{"n": n} for n in range(retained)]}), expected_revision=0
        )
        running = _running_record()
        store.claim_record(running)
        terminal = _terminal_record(running)
        snapshot = before.snapshot.with_entries(
            {}, evaluation_history=append_history(before.snapshot, "evaluation_history", "run", [{"n": retained}])
        )
        result, counts = measure(
            lambda: store.commit_participant_transition(
                expected_history_heads={},
                expected_revision=before.revision,
                snapshot=snapshot,
                record=terminal,
                audit_event=_terminal_audit(terminal),
            ),
            store,
        )
        assert len(result.snapshot.evaluation_history["run"]) == retained + 1
        return dict(retained_records=retained, appended_records=1, **counts)
    finally:
        if hasattr(store, "close"):
            store.close()
        if lease is not None:
            lease.close()


def measure_execution(store):
    from governed_effect_runtime_fixtures import EffectResolver, effect_plane
    from participant_crossing_fixtures import PARTICIPANT, admit, identity

    resolver = EffectResolver()
    resolver.selection = resolver.selection.model_copy(
        update={"bounds": resolver.selection.bounds.model_copy(update={"max_attempts": 256})}
    )
    plane, _ = effect_plane(resolver, store=store)
    caller = identity(audience_bound=True)
    rows = []
    with plane:
        for step in range(1, 33):
            admit(plane, control_identity=caller, idempotency_key=f"measurement-{step}")
            if step not in {1, 8, 32}:
                continue
            plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
            outcomes, counts = measure(
                lambda: plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller), plane._store
            )
            projection = plane._control_state_projection
            rows.append(
                dict(
                    evaluations=len(projection.evaluations),
                    operations=len(plane._operations),
                    roots=len(projection.roots),
                    claims=sum(len(root.claims) for root in projection.roots.values()),
                    provider_edges=sum(len(chain) for chain in projection.provider_chains.values()),
                    pending=sum(len(items) for items in projection.pending.values()),
                    outcomes=len(outcomes),
                    **counts,
                )
            )
    return rows


def main():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for durable in (False, True):
            provider = "sqlite" if durable else "memory"
            execution_store = LocalControlPlaneStore(root / "execution") if durable else InMemoryControlPlaneStore()
            print(
                json.dumps(
                    dict(provider=provider, boundary="public_execution", rows=measure_execution(execution_store))
                ),
                flush=True,
            )
            rows = [
                measure_atomic_append(
                    LocalControlPlaneStore(root / f"append-{size}") if durable else InMemoryControlPlaneStore(), size
                )
                for size in (8, 64, 512)
            ]
            print(json.dumps(dict(provider=provider, boundary="atomic_append", rows=rows)), flush=True)


if __name__ == "__main__":
    main()
