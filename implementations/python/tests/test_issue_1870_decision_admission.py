"""Assignment decisions use one compare-and-append transaction."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import ConflictError
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.runtime_decisions import RunContextDecision


def decision(name):
    return RunContextDecision(run_scope="run:" + name, store_digest="sha256:" + "a" * 64, status="opened")


@pytest.mark.parametrize("durable", [False, True])
def test_expected_decisions_fence_concurrent_capacity_admission(tmp_path, durable):
    store = LocalControlPlaneStore(tmp_path) if durable else InMemoryControlPlaneStore()
    with RuntimeControlPlane(create_stub_target(), store=store):

        def admit(name):
            try:
                store.claim_runtime_decisions((decision(name),), expected_ids=())
            except ConflictError:
                return False
            return True

        with ThreadPoolExecutor(max_workers=2) as workers:
            assert sorted(workers.map(admit, ("one", "two"))) == [False, True]
        assert len(store.load_runtime_decisions()) == 1


@pytest.mark.parametrize("durable", [False, True])
def test_batch_refusal_writes_nothing_and_exact_replay_is_idempotent(tmp_path, durable):
    store = LocalControlPlaneStore(tmp_path) if durable else InMemoryControlPlaneStore()
    with RuntimeControlPlane(create_stub_target(), store=store):
        first, second = decision("one"), decision("two")
        assert store.claim_runtime_decisions((first, second), expected_ids=())
        assert not store.claim_runtime_decisions((first, second), expected_ids=())
        changed = second.model_copy(update={"store_digest": "sha256:" + "b" * 64})
        third = decision("three")
        with pytest.raises(ConflictError):
            store.claim_runtime_decisions((third, changed), expected_ids=(first.decision_id, second.decision_id))
        assert {item.run_scope for item in store.load_runtime_decisions()} == {"run:one", "run:two"}
