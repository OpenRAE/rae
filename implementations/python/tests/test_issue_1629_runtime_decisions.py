"""Runtime decisions are immutable atomic claims in the existing store."""

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.errors import ConflictError
from raes_runtime import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from raes_runtime.control_plane_store_local import LocalControlPlaneStore


@pytest.mark.parametrize("durable", [False, True])
def test_decision_claim_replays_exactly_and_rejects_changed_store_identity(tmp_path, durable):
    from raes_runtime.runtime_decisions import RunContextDecision

    store = LocalControlPlaneStore(tmp_path) if durable else InMemoryControlPlaneStore()
    with RuntimeControlPlane(create_stub_target(), store=store) as engine:
        decision = RunContextDecision(run_scope="run:one", store_digest="sha256:" + "a" * 64, status="opened")
        assert engine._store.claim_runtime_decision(decision)
        assert not engine._store.claim_runtime_decision(decision)
        changed = decision.model_copy(update={"store_digest": "sha256:" + "b" * 64})
        with pytest.raises(ConflictError, match="conflict"):
            engine._store.claim_runtime_decision(changed)
        assert engine._store.load_runtime_decisions() == (decision,)


def test_local_schema_11_upgrade_preserves_operation_records(tmp_path):
    import sqlite3

    from raes_contracts.planning import ProvisioningPlan
    from raes_runtime.runtime_decisions import RunContextDecision

    store = LocalControlPlaneStore(tmp_path)
    target = create_stub_target()
    with RuntimeControlPlane(target, store=store) as engine:
        engine.submit_provisioning(ProvisioningPlan(), idempotency_key="before-upgrade")
        records = engine._store.load_records()
    with sqlite3.connect(store._database_path) as connection:
        connection.execute("DROP TABLE runtime_decisions")
        connection.execute("UPDATE metadata SET value='11' WHERE key='schema-version'")
    with RuntimeControlPlane(target, store=LocalControlPlaneStore(tmp_path)) as engine:
        assert engine._store.load_records() == records
        assert not engine._store.load_runtime_decisions()
        decision = RunContextDecision(run_scope="run:migrated", store_digest="sha256:" + "f" * 64, status="opened")
        assert engine._store.claim_runtime_decision(decision)
        assert engine._store.load_runtime_decisions() == (decision,)
