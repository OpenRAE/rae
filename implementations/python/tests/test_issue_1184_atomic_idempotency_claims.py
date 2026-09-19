"""CP-7 atomic, scoped idempotency and authoritative-read regressions."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
import raes_runtime.control_plane as control_plane_module
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
)
from raes_contracts.workflow import WorkflowExecutionState, WorkflowStatus
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_operation_context import (
    legacy_operation_request_commitment,
    operation_admission_context,
)
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from raes_runtime.control_plane_store import ControlPlaneOperationRecord, InMemoryControlPlaneStore
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_local_codec import encode_payload
from raes_runtime.control_plane_store_records import _record_payload


def _context(
    *,
    actor: str = "operator-a",
    kind: OperationKind = OperationKind.PROVISIONING,
    commitment: str | None = None,
    authorization_scope: tuple[str, ...] = ("role:operator",),
    parent_operation_id: str | None = None,
) -> OperationAdmissionContext:
    return OperationAdmissionContext(
        actor_id=actor,
        authorization_scope=authorization_scope,
        target_scope="target:stub",
        run_scope="run:default",
        operation_kind=kind,
        request_commitment=commitment or f"sha256:{'a' * 64}",
        parent_operation_id=parent_operation_id,
    )


def _record(
    operation_id: str,
    *,
    context: OperationAdmissionContext | None = None,
    key: str = "shared-key",
    result_payload: dict[str, object] | None = None,
) -> ControlPlaneOperationRecord:
    operation_context = context or _context()
    receipt = OperationReceipt(
        operation_id=operation_id,
        domain=RuntimeDomain.PROVISIONING,
        submitted_at="2026-09-18T10:00:00Z",
        accepted=True,
        context=operation_context,
    )
    status = OperationStatus(
        operation_id=operation_id,
        domain=receipt.domain,
        state=OperationState.RUNNING,
        submitted_at=receipt.submitted_at,
        updated_at=receipt.submitted_at,
        context=operation_context,
    )
    return ControlPlaneOperationRecord(
        receipt=receipt,
        status=status,
        request_fingerprint=operation_context.request_commitment,
        idempotency_key=key,
        result_payload=result_payload,
    )


@pytest.fixture(params=("memory", "local"))
def admitted_store(request: pytest.FixtureRequest, tmp_path):
    if request.param == "memory":
        yield InMemoryControlPlaneStore()
        return
    store = LocalControlPlaneStore(tmp_path / "control-plane-store")
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:default")
    try:
        yield store
    finally:
        store.close()
        lease.close()


def test_atomic_claim_is_scoped_by_actor_and_operation_kind(admitted_store) -> None:
    barrier = Barrier(2)
    equal_claims = (_record("operation-a"), _record("operation-b"))

    def claim(record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
        barrier.wait()
        return admitted_store.claim_record(record)

    with ThreadPoolExecutor(max_workers=2) as executor:
        winners = list(executor.map(claim, equal_claims))

    assert len({record.receipt.operation_id for record in winners}) == 1

    other_actor = admitted_store.claim_record(_record("operation-other-actor", context=_context(actor="operator-b")))
    other_kind = admitted_store.claim_record(
        _record(
            "operation-other-kind",
            context=_context(kind=OperationKind.ORCHESTRATION),
        )
    )

    assert other_actor.receipt.operation_id == "operation-other-actor"
    assert other_kind.receipt.operation_id == "operation-other-kind"
    assert len(admitted_store.load_records()) == 3


def test_atomic_claim_does_not_call_the_separate_lookup_api() -> None:
    class LookupRejectingStore(InMemoryControlPlaneStore):
        def find_by_idempotency(self, *args, **kwargs):
            raise AssertionError("claim must not perform a separate idempotency lookup")

    store = LookupRejectingStore()
    first = store.claim_record(_record("operation-first"))
    replay = store.claim_record(_record("operation-replay"))

    assert replay.receipt.operation_id == first.receipt.operation_id


def test_runtime_submission_uses_only_the_atomic_claim_operation() -> None:
    class LookupRejectingStore(InMemoryControlPlaneStore):
        def find_by_idempotency(self, *args, **kwargs):
            raise AssertionError("runtime must not perform lookup before claim")

    target = create_stub_target()
    original_apply = target.provisioner.apply
    apply_count = 0

    def counted_apply(*args, **kwargs):
        nonlocal apply_count
        apply_count += 1
        return original_apply(*args, **kwargs)

    target.provisioner.apply = counted_apply
    control_plane = RuntimeControlPlane(target, store=LookupRejectingStore())

    first = control_plane.submit_provisioning(ProvisioningPlan(), idempotency_key="runtime-key")
    replay = control_plane.submit_provisioning(ProvisioningPlan(), idempotency_key="runtime-key")

    assert replay == first
    assert apply_count == 1
    control_plane.close()


def test_retry_returns_incumbent_before_changed_admission_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    plan = ProvisioningPlan()
    first = control_plane.submit_provisioning(plan, idempotency_key="changed-admission")
    rejection = Diagnostic(
        code="runtime.control-plane.test-rejection",
        domain="runtime",
        address="runtime.control-plane.provisioning",
        message="current admission state changed",
    )
    monkeypatch.setattr(
        control_plane_module,
        "control_plane_plan_diagnostics",
        lambda *_args, **_kwargs: [rejection],
    )

    retry = control_plane.submit_provisioning(plan, idempotency_key="changed-admission")

    assert retry == first
    control_plane.close()


def test_workflow_cancellation_retry_returns_incumbent_after_state_turns_terminal() -> None:
    workflow_address = "workflow.atomic-retry"
    workflow = WorkflowExecutionState(
        workflow_status=WorkflowStatus.RUNNING,
        run_id="run:default",
        started_at="2026-09-18T10:00:00Z",
        updated_at="2026-09-18T10:00:00Z",
    )
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        initial_snapshot=RuntimeSnapshot(
            orchestration_results={workflow_address: workflow.to_payload()},
        ),
    )

    first = control_plane.cancel_workflow(
        workflow_address,
        idempotency_key="cancel-terminal-retry",
    )
    retry = control_plane.cancel_workflow(
        workflow_address,
        idempotency_key="cancel-terminal-retry",
    )

    assert retry == first
    assert len(control_plane._store.load_records()) == 1
    control_plane.close()


def test_stale_explicit_base_does_not_persist_a_new_claim() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    stale = replace(control_plane.snapshot, metadata={"revision": "stale"})
    plan = ProvisioningPlan()

    with pytest.raises(
        ValueError,
        match="explicit base snapshot does not match the authoritative runtime snapshot",
    ):
        control_plane.submit_provisioning(plan, base_snapshot=stale, idempotency_key="stale-base")

    assert control_plane._store.load_records() == {}
    control_plane.close()


@pytest.mark.parametrize(
    "changed_context",
    [
        _context(commitment=f"sha256:{'b' * 64}"),
        _context(authorization_scope=("role:operator", "participant-control:subject:controller")),
        _context(parent_operation_id="parent-operation"),
    ],
)
def test_atomic_claim_rejects_changed_immutable_replay_conditions(
    admitted_store,
    changed_context: OperationAdmissionContext,
) -> None:
    admitted_store.claim_record(_record("operation-original"))
    conflicting_record = _record("operation-conflict", context=changed_context)

    with pytest.raises(ValueError, match="idempotency claim conflicts with the original request"):
        admitted_store.claim_record(conflicting_record)

    assert set(admitted_store.load_records()) == {"operation-original"}


def test_operation_commitment_has_a_versioned_operation_specific_domain() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    request = {"opaque": "semantic-input"}

    provisioning = operation_admission_context(
        control_plane,
        kind=OperationKind.PROVISIONING,
        request=request,
    )
    orchestration = operation_admission_context(
        control_plane,
        kind=OperationKind.ORCHESTRATION,
        request=request,
    )

    assert provisioning.request_commitment == canonical_json_digest(
        {
            "domain": "raes.runtime.control-plane.provisioning.request-commitment/v1",
            "request": request,
            "base_snapshot": None,
        }
    )
    assert orchestration.request_commitment != provisioning.request_commitment
    assert "semantic-input" not in provisioning.request_commitment
    control_plane.close()


@pytest.mark.parametrize("key", ["contains whitespace", "control\ncharacter", "x" * 257])
def test_idempotency_key_shape_is_bounded_at_the_core(key: str) -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    plan = ProvisioningPlan()

    with pytest.raises(ValueError, match="Idempotency-Key must be 1-256 visible ASCII characters"):
        control_plane.submit_provisioning(plan, idempotency_key=key)

    assert control_plane.snapshot.entries == {}
    control_plane.close()


def test_operation_status_read_requires_the_original_actor_and_scope() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    owner = ControlPlaneIdentity(
        identity="operator-a",
        roles=frozenset({ControlPlaneRole.OPERATOR}),
        target_name="stub",
    )
    stranger = replace(owner, identity="operator-b")
    receipt = control_plane.submit_provisioning(
        ProvisioningPlan(),
        idempotency_key="owner-key",
        identity=owner,
    )

    assert control_plane.get_operation(receipt.operation_id, identity=owner) is not None
    assert control_plane.get_operation(receipt.operation_id, identity=stranger) is None
    assert control_plane.get_operation("unknown-operation", identity=stranger) is None
    control_plane.close()


def test_observation_execution_rebuilds_a_forged_operation_cache() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    forged_payload = {
        "schema_version": "observation-operation-result/v1",
        "operation_id": "forged-operation",
        "lifecycle": {
            "collected": [],
            "retained": [],
            "exported": [],
            "operational_count": 0,
        },
        "retained": [],
        "realized_form_disclosures": [],
    }
    control_plane._operations["forged-operation"] = _record(
        "forged-operation",
        key="",
        result_payload=forged_payload,
    )

    assert control_plane.observation_execution("forged-operation") is None
    control_plane.close()


def test_v3_store_migration_builds_composite_claims_and_quarantines_opaque_participant_keys(
    tmp_path,
) -> None:
    store_path = tmp_path / "v3-store"
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:default")
    legacy = replace(
        _record(
            "legacy-participant-operation",
            context=_context(kind=OperationKind.PARTICIPANT_CONTROL),
            key=f"participant-control:{'a' * 64}",
        ),
        request_fingerprint="legacy-participant-semantic-hash",
    )
    store.claim_record(legacy)
    store.close()
    lease.close()

    database = store_path / "control-plane.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("DROP INDEX operations_idempotency_claim")
        for column in (
            "legacy_opaque_claim",
            "request_commitment",
            "run_scope",
            "target_scope",
            "operation_kind",
            "actor_id",
        ):
            connection.execute(f"ALTER TABLE operations DROP COLUMN {column}")
        connection.execute(
            "CREATE UNIQUE INDEX operations_idempotency_key ON operations(idempotency_key) WHERE idempotency_key != ''"
        )
        connection.execute("UPDATE metadata SET value='3' WHERE key='schema-version'")

    migrated = LocalControlPlaneStore(store_path)
    migrated_lease = migrated.admit_runtime(target_scope="target:stub", run_scope="run:default")
    try:
        migrated_record = migrated.load_records()[legacy.receipt.operation_id]
        assert migrated_record.request_fingerprint == legacy.receipt.context.request_commitment
        with sqlite3.connect(database) as connection:
            row = connection.execute("SELECT actor_id, operation_kind, legacy_opaque_claim FROM operations").fetchone()
            assert row == ("operator-a", "participant-control", 1)
            assert connection.execute("SELECT value FROM metadata WHERE key='schema-version'").fetchone() == ("5",)
        conflicting_record = _record(
            "post-migration-retry",
            context=_context(kind=OperationKind.PARTICIPANT_CONTROL),
            key="original-client-key-is-not-recoverable",
        )
        with pytest.raises(ValueError, match="idempotency claim conflicts with the original request"):
            migrated.claim_record(conflicting_record)
        assert set(migrated.load_records()) == {legacy.receipt.operation_id}
    finally:
        migrated.close()
        migrated_lease.close()


def test_v3_store_migration_preserves_ordinary_claim_replay(tmp_path) -> None:
    store_path = tmp_path / "ordinary-v3-store"
    plan = ProvisioningPlan()
    old_commitment = legacy_operation_request_commitment(
        kind=OperationKind.PROVISIONING,
        request=plan,
    )
    legacy = _record(
        "ordinary-v3-operation",
        context=_context(
            actor="embedded-process",
            authorization_scope=("process:trusted-embedder",),
            commitment=old_commitment,
        ),
        key="v3-retry",
    )
    store = LocalControlPlaneStore(store_path)
    lease = store.admit_runtime(target_scope="target:stub", run_scope="run:default")
    store.claim_record(legacy)
    store.close()
    lease.close()

    payload = _record_payload(legacy)
    payload.pop("legacy_request_commitment")
    content, digest = encode_payload(payload)
    database = store_path / "control-plane.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE operations SET payload=?, digest=? WHERE operation_id=?",
            (content, digest, legacy.receipt.operation_id),
        )
        connection.execute("DROP INDEX operations_idempotency_claim")
        for column in (
            "legacy_opaque_claim",
            "request_commitment",
            "run_scope",
            "target_scope",
            "operation_kind",
            "actor_id",
        ):
            connection.execute(f"ALTER TABLE operations DROP COLUMN {column}")
        connection.execute(
            "CREATE UNIQUE INDEX operations_idempotency_key ON operations(idempotency_key) WHERE idempotency_key != ''"
        )
        connection.execute("UPDATE metadata SET value='3' WHERE key='schema-version'")

    control_plane = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(store_path),
    )
    retry = control_plane.submit_provisioning(plan, idempotency_key="v3-retry")

    assert retry.operation_id == legacy.receipt.operation_id
    control_plane.close()
