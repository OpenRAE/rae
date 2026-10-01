"""Independent FM3 lifecycle oracle against each reference store implementation."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from control_plane_conformance_fixtures import RUN_SCOPE, TARGET_SCOPE, inspect_store
from hypothesis import given, settings
from hypothesis import strategies as st
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
)
from raes_runtime.control_plane_store import ControlPlaneOperationRecord, InMemoryControlPlaneStore

pytestmark = pytest.mark.control_plane_conformance

# This oracle is transcribed from the FM3 model, not imported from the runtime
# predicate under test. Exact carrier retries are checked separately.
LEGAL = {
    ("accepted", "running"),
    ("accepted", "cancelled"),
    ("accepted", "indeterminate"),
    ("running", "succeeded"),
    ("running", "failed"),
    ("running", "cancelled"),
    ("running", "indeterminate"),
}
NONTERMINAL = {OperationState.ACCEPTED, OperationState.RUNNING}


def _record(state: OperationState, kind: OperationKind = OperationKind.PROVISIONING) -> ControlPlaneOperationRecord:
    context = OperationAdmissionContext(
        actor_id="alice",
        authorization_scope=("role:operator",),
        target_scope=TARGET_SCOPE,
        run_scope=RUN_SCOPE,
        operation_kind=kind,
        request_commitment=f"sha256:{'a' * 64}",
    )
    receipt = OperationReceipt(
        operation_id="conformance-operation",
        domain=RuntimeDomain.PROVISIONING,
        submitted_at="2026-09-20T00:00:00Z",
        accepted=True,
        context=context,
    )
    return ControlPlaneOperationRecord(
        receipt=receipt,
        status=OperationStatus(
            operation_id=receipt.operation_id,
            domain=receipt.domain,
            state=state,
            submitted_at=receipt.submitted_at,
            updated_at=receipt.submitted_at,
            context=context,
        ),
        idempotency_key="conformance-key",
        request_fingerprint=context.request_commitment,
    )


@contextmanager
def _store(profile: str, path: Path):
    if profile == "P0":
        yield InMemoryControlPlaneStore()
    else:
        with inspect_store(path) as store:
            yield store


def _cut(store):
    return deepcopy((store.load_snapshot_state(), store.load_records(), store.read_audit()))


def _seed(store, state: OperationState, kind=OperationKind.PROVISIONING):
    record = _record(state, kind)
    if state in NONTERMINAL:
        store.claim_record(record)
    else:
        store.claim_record(_record(OperationState.RUNNING, kind))
        store.commit_terminal_operation(RuntimeSnapshot(), record, expected_revision=0)
    return record


def _persist(store, candidate, snapshot, revision):
    if candidate.status.state in NONTERMINAL:
        store.save_record(candidate)
    else:
        store.commit_terminal_operation(snapshot, candidate, expected_revision=revision)


def _exercise_sequence(store, current, sequence):
    for index, state in enumerate(sequence, start=1):
        candidate = replace(
            current,
            status=replace(current.status, state=state, diagnostics=[], updated_at=f"2026-09-20T00:01:{index:02d}Z"),
        )
        before = _cut(store)
        snapshot = replace(before[0].snapshot, metadata={"step": index})

        if (current.status.state.value, state.value) in LEGAL:
            _persist(store, candidate, snapshot, before[0].revision)
            after = _cut(store)
            _persist(store, candidate, snapshot, before[0].revision)  # Exact retry is a no-op.
            assert _cut(store) == after
            assert store.load_records()[current.receipt.operation_id] == candidate
            assert candidate.status.context == current.status.context
            current = candidate
        else:
            try:
                _persist(store, candidate, snapshot, before[0].revision)
            except ValueError:
                pass
            else:
                raise AssertionError("illegal transition was accepted")
            assert _cut(store) == before


@pytest.mark.parametrize("profile", ["P0", "P1"])
@pytest.mark.parametrize("source,target", list(product(OperationState, repeat=2)))
def test_every_lifecycle_transition_preserves_the_full_atomic_cut(profile, source, target, tmp_path) -> None:
    with _store(profile, tmp_path) as store:
        _exercise_sequence(store, _seed(store, source), [target])


@pytest.mark.fuzz
@pytest.mark.parametrize("profile", ["P0", "P1"])
@settings(max_examples=40, deadline=None, derandomize=True)
@given(sequence=st.lists(st.sampled_from(list(OperationState)), min_size=1, max_size=12))
def test_generated_lifecycle_sequences_never_rewrite_terminal_history(profile, sequence) -> None:
    with TemporaryDirectory(prefix="control-plane-sequence-") as directory, _store(profile, Path(directory)) as store:
        _exercise_sequence(store, _seed(store, OperationState.ACCEPTED), sequence)


@pytest.mark.parametrize("profile", ["P0", "P1"])
@pytest.mark.parametrize("kind", list(OperationKind))
def test_each_operation_kind_commits_one_immutable_actor_bound_terminal_cut(profile, kind, tmp_path) -> None:
    with _store(profile, tmp_path) as store:
        _exercise_sequence(
            store, _seed(store, OperationState.RUNNING, kind), [OperationState.SUCCEEDED, OperationState.FAILED]
        )
        events = store.read_audit()
        assert len(events) == 1
        assert (events[0].action, events[0].identity, events[0].target) == (
            f"{kind.value}_terminal",
            "alice",
            TARGET_SCOPE,
        )


@pytest.mark.parametrize("profile", ["P0", "P1"])
def test_lifecycle_oracle_detects_removed_transition_enforcement(profile, tmp_path, monkeypatch) -> None:
    import raes_runtime.control_plane_store as contracts

    with _store(profile, tmp_path) as store:
        current = _seed(store, OperationState.SUCCEEDED)
        monkeypatch.setattr(contracts, "is_operation_transition_allowed", lambda *_args: True)
        with pytest.raises(AssertionError, match="illegal transition was accepted"):
            _exercise_sequence(store, current, [OperationState.RUNNING])
