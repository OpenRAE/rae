"""API-404 crash consistency, recovery, and local runtime ownership tests."""

from __future__ import annotations

import errno
import inspect
import json
import os
import sqlite3
import stat
import sys
from contextlib import closing
from dataclasses import asdict, dataclass, fields, replace
from hashlib import sha256
from multiprocessing import get_all_start_methods, get_context
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic, sleep
from types import SimpleNamespace
from typing import Any

import pytest
from raes import parse_sdl
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan, RuntimeDomain
from raes_contracts.realization_envelope import (
    BackendRealizationEnvelopeModel,
    ObservationStrength,
    RealizationConcern,
    realization_envelope_digest,
    realizer_configuration_digest,
)
from raes_contracts.realization_observation import (
    ObservedOperatingSystemIdentity,
    RealizationObservation,
    bind_operating_system_observations,
)
from raes_contracts.runtime_state import (
    ApplyResult,
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
    SnapshotEntry,
    operation_terminal_diagnostic,
)
from raes_contracts.vocabulary import RealizationVerificationScope
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime import control_plane_store_lease as lease_module
from raes_runtime import control_plane_store_local as local_store_module
from raes_runtime import control_plane_store_paths as store_paths_module
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_execution import (
    OperationExecutionRequest,
    SucceededOperationRequest,
    execute_operation,
    execute_participant_action,
    persist_succeeded_operation,
)
from raes_runtime.control_plane_store import (
    INTERRUPTED_OPERATION_DIAGNOSTIC_CODE,
    AtomicControlPlaneStore,
    AuditEvent,
    ControlPlaneOperationRecord,
    ControlPlaneStore,
    InMemoryControlPlaneStore,
)
from raes_runtime.control_plane_store_compatibility import (
    LegacyControlPlaneStoreWarning,
    adapt_control_plane_store,
)
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_snapshots import (
    _require_complete_runtime_snapshot_fields,
    _snapshot_from_payload,
    _snapshot_payload,
)


class _CountingProvisioner:
    def __init__(
        self,
        delegate: object,
        *,
        realization_envelope: BackendRealizationEnvelopeModel,
        interrupt_before_effect: bool = False,
    ) -> None:
        self._delegate = delegate
        self._realization_envelope = realization_envelope
        self._interrupt_before_effect = interrupt_before_effect
        self.apply_count = 0

    def validate(self, provisioning_plan: ProvisioningPlan) -> list[object]:
        return self._delegate.validate(provisioning_plan)

    def apply(
        self,
        provisioning_plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        self.apply_count += 1
        if self._interrupt_before_effect:
            raise KeyboardInterrupt("injected crash before backend effect")
        result = self._delegate.apply(provisioning_plan, snapshot)
        if not result.success:
            return result
        authority = next(
            (entry for entry in provisioning_plan.realization_authority if entry.requirement_kind == "os-family"),
            None,
        )
        if authority is None:
            return result
        if provisioning_plan.operation_id is None:
            raise AssertionError("fixture OS observation requires a bound operation")
        observation = RealizationObservation(
            address=authority.address,
            field_path="guest.os-release",
            concern=RealizationConcern.OPERATING_SYSTEM,
            source=ObservationStrength.GUEST_OBSERVED,
            value=ObservedOperatingSystemIdentity(
                family="linux",
                distribution="ubuntu",
                version="24.04",
            ),
            operation_id=provisioning_plan.operation_id,
            envelope_digest=self._realization_envelope.digest,
            configuration_digest=self._realization_envelope.configuration.configuration_digest,
            observer_version="issue-1092-fixture/v1",
            sequence=0,
            binding_verified=True,
        )
        disclosures = bind_operating_system_observations(
            plan=provisioning_plan,
            observations=(observation,),
            envelope=self._realization_envelope,
            previous=result.snapshot.realization_observations,
        )
        return replace(
            result,
            snapshot=result.snapshot.with_entries(
                dict(result.snapshot.entries),
                realization_observations=disclosures,
            ),
        )


class _BlockingProvisioner:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self.entered = Event()
        self.release = Event()

    def validate(self, provisioning_plan: ProvisioningPlan) -> list[object]:
        return self._delegate.validate(provisioning_plan)

    def apply(
        self,
        provisioning_plan: ProvisioningPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("blocked provisioner was not released")
        return self._delegate.apply(provisioning_plan, snapshot)


class _LegacyControlPlaneStore:
    """Pre-atomic custom-store shape retained for 3.x compatibility tests."""

    def __init__(self) -> None:
        self.delegate = InMemoryControlPlaneStore()
        self.write_calls: list[str] = []
        self.fail_snapshot = False
        self.fail_terminal_record = False

    def load_snapshot(self) -> RuntimeSnapshot:
        return self.delegate.load_snapshot()

    def save_snapshot(self, snapshot: RuntimeSnapshot) -> None:
        self.write_calls.append("save_snapshot")
        if self.fail_snapshot:
            raise RuntimeError("injected legacy snapshot failure")
        self.delegate.save_snapshot(snapshot)

    def load_records(self) -> dict[str, ControlPlaneOperationRecord]:
        return self.delegate.load_records()

    def save_record(self, record: ControlPlaneOperationRecord) -> None:
        self.write_calls.append("save_record")
        if self.fail_terminal_record and record.status.state not in {OperationState.ACCEPTED, OperationState.RUNNING}:
            raise RuntimeError("injected legacy terminal-record failure")
        self.delegate.save_record(record)

    def find_by_idempotency(self, key: str) -> ControlPlaneOperationRecord | None:
        return self.delegate.find_by_idempotency(key)

    def append_audit(self, event: AuditEvent) -> None:
        self.delegate.append_audit(event)

    def read_audit(self) -> list[AuditEvent]:
        return self.delegate.read_audit()

    def commit_control_transition(
        self,
        *,
        participant_address: str,
        expected_head: str | None,
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> None:
        self.delegate.commit_control_transition(
            participant_address=participant_address,
            expected_head=expected_head,
            snapshot=snapshot,
            record=record,
            audit_event=audit_event,
        )

    def commit_participant_transition(
        self,
        *,
        expected_history_heads: dict[str, str | None],
        snapshot: RuntimeSnapshot,
        record: ControlPlaneOperationRecord,
        audit_event: AuditEvent,
    ) -> None:
        self.delegate.commit_participant_transition(
            expected_history_heads=expected_history_heads,
            snapshot=snapshot,
            record=record,
            audit_event=audit_event,
        )


class _PartiallyAtomicControlPlaneStore(_LegacyControlPlaneStore):
    def commit_terminal_operation(
        self,
        _snapshot: RuntimeSnapshot,
        _record: ControlPlaneOperationRecord,
    ) -> None:
        raise AssertionError("a partial atomic capability must not create hybrid semantics")


def _durability_fixture_envelope(base_target: object) -> BackendRealizationEnvelopeModel:
    base_envelope = base_target.manifest.realization_envelope
    if base_envelope is None:
        raise AssertionError("fixture requires the governed stub realization envelope")
    payload = base_envelope.model_dump(mode="json")
    configuration = payload["configuration"]
    configuration["operating_systems"] = [{"family": "linux", "distribution": "ubuntu", "versions": ["24.04"]}]
    configuration["configuration_digest"] = realizer_configuration_digest(configuration)
    operating_system = next(
        claim for claim in payload["concerns"] if claim["concern"] == RealizationConcern.OPERATING_SYSTEM.value
    )
    operating_system.update(
        disposition="realized",
        observation_strength=ObservationStrength.GUEST_OBSERVED.value,
        mechanism="issue-1092-fixture-guest-os-release",
    )
    payload["digest"] = realization_envelope_digest(payload)
    return BackendRealizationEnvelopeModel.model_validate(payload)


def _target_and_plan(*, interrupt_before_effect: bool = False) -> tuple[object, ProvisioningPlan, _CountingProvisioner]:
    base_target = create_stub_target()
    realization_envelope = _durability_fixture_envelope(base_target)
    declaration = base_target.manifest.realization_support[0]
    manifest = replace(
        base_target.manifest,
        realization_envelope=realization_envelope,
        realization_support=(
            replace(
                declaration,
                observation_capabilities={
                    **declaration.observation_capabilities,
                    "operating-system": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.PRESENCE,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                },
            ),
        ),
    )
    provisioner = _CountingProvisioner(
        StubProvisioner(realization_envelope),
        realization_envelope=realization_envelope,
        interrupt_before_effect=interrupt_before_effect,
    )
    target = replace(base_target, manifest=manifest, provisioner=provisioner)
    scenario = parse_sdl(
        """
name: crash-consistency
nodes:
  vm:
    type: compute
    os: linux
    resources: {ram: 1 gib, cpu: 1}
"""
    )
    provisioning_plan = plan(compile_runtime_model(scenario), target.manifest).provisioning
    return target, provisioning_plan, provisioner


def _authorize_provisioning_plan(
    control_plane: RuntimeControlPlane,
    target: object,
    provisioning_plan: ProvisioningPlan,
) -> None:
    """Forge component authorization where planner validity is explicitly out of scope."""

    scenario = parse_sdl("name: crash-consistency-authorization")
    execution_plan = plan(compile_runtime_model(scenario), target.manifest)
    control_plane.register_planner_produced_plan(replace(execution_plan, provisioning=provisioning_plan))


def test_durability_fixture_declares_guest_observed_os_presence_corroboration() -> None:
    target, _, _ = _target_and_plan()

    capability = target.manifest.realization_support[0].observation_capabilities["operating-system"]
    envelope_claim = next(
        claim
        for claim in target.manifest.realization_envelope.concerns
        if claim.concern is RealizationConcern.OPERATING_SYSTEM
    )
    assert capability == RealizationObservationCapability(
        verification_scope=RealizationVerificationScope.PRESENCE,
        observation_strength=ObservationStrength.GUEST_OBSERVED,
    )
    assert envelope_claim.observation_strength is ObservationStrength.GUEST_OBSERVED


def _running_record(
    operation_id: str, *, state: OperationState = OperationState.RUNNING
) -> ControlPlaneOperationRecord:
    submitted_at = "2026-08-11T12:00:00Z"
    context = OperationAdmissionContext(
        actor_id="embedded-process",
        authorization_scope=("process:trusted-embedder",),
        target_scope="target:stub",
        run_scope="run:test",
        operation_kind=OperationKind.PROVISIONING,
        request_commitment=f"sha256:{'a' * 64}",
    )
    return ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PROVISIONING,
            submitted_at=submitted_at,
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PROVISIONING,
            state=state,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=context,
        ),
        idempotency_key=f"key-{operation_id}",
        request_fingerprint=context.request_commitment,
    )


def _pre_lifecycle_record_payload(
    record: ControlPlaneOperationRecord,
    *,
    accepted: bool = True,
) -> dict[str, Any]:
    payload = local_store_module._record_payload(record)
    payload["receipt"].pop("context")
    payload["receipt"]["accepted"] = accepted
    payload["status"].pop("context")
    if record.status.state in {
        OperationState.FAILED,
        OperationState.CANCELLED,
        OperationState.INDETERMINATE,
    }:
        payload["status"]["diagnostics"] = []
    payload["request_fingerprint"] = "legacy-unclassified-fingerprint"
    return payload


def _terminal_record(record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
    return replace(
        record,
        status=replace(
            record.status,
            state=OperationState.SUCCEEDED,
            updated_at="2026-08-11T12:00:01Z",
        ),
    )


def _audit_event(action: str = "test") -> AuditEvent:
    return AuditEvent(
        timestamp="2026-08-11T12:00:00Z",
        action=action,
        identity="test-identity",
        allowed=True,
        target="runtime.control-plane",
    )


def _atomic_store(kind: str, tmp_path: Path) -> InMemoryControlPlaneStore | LocalControlPlaneStore:
    if kind.startswith("memory"):
        return InMemoryControlPlaneStore()
    return LocalControlPlaneStore(tmp_path / f"control-plane-{kind}")


def _interrupted_record(record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
    terminal_state = (
        OperationState.CANCELLED if record.status.state is OperationState.ACCEPTED else OperationState.INDETERMINATE
    )
    return replace(
        record,
        status=replace(
            record.status,
            state=terminal_state,
            updated_at="2026-08-11T12:00:02Z",
            diagnostics=[
                Diagnostic(
                    code=INTERRUPTED_OPERATION_DIAGNOSTIC_CODE,
                    domain="runtime",
                    address="/state",
                    message="Operation was interrupted before its terminal durable commit.",
                )
            ],
        ),
    )


def _runtime_owner_result(store_path: str, queue: Any) -> None:
    try:
        control_plane = RuntimeControlPlane(
            create_stub_target(),
            store=LocalControlPlaneStore(Path(store_path)),
        )
    except RuntimeError as exc:
        queue.put(str(exc))
        return
    control_plane.close()
    queue.put("acquired")


def _inherited_runtime_result(control_plane: RuntimeControlPlane, queue: Any) -> None:
    try:
        control_plane.get_snapshot()
    except RuntimeError as exc:
        queue.put(str(exc))
        return
    queue.put("used")


def _stress_local_store_writes(
    store_path: str,
    process_index: int,
    write_count: int,
    barrier: Any,
) -> None:
    for write_index in range(write_count):
        barrier.wait(timeout=15)
        LocalControlPlaneStore(Path(store_path)).save_record(_running_record(f"stress-{process_index}-{write_index}"))


def test_runtime_snapshot_durable_codec_is_exhaustive_and_round_trips_closure_records() -> None:
    participant_address = "participant.behavior.alpha"
    snapshot = RuntimeSnapshot(
        participant_episode_closure_records={
            participant_address: [
                {
                    "participant_address": participant_address,
                    "episode_id": "episode-alpha",
                    "source_signal": "environment_terminal",
                }
            ]
        },
        metadata={"generation": 1},
    )

    payload = _snapshot_payload(snapshot)

    assert set(payload) == {"schema_version", *(field.name for field in fields(RuntimeSnapshot))}
    assert _snapshot_from_payload(payload) == snapshot


def test_runtime_snapshot_durable_codec_rejects_missing_or_unexpected_fields() -> None:
    complete = {field.name: None for field in fields(RuntimeSnapshot)}

    missing = dict(complete)
    missing.pop("participant_episode_closure_records")
    with pytest.raises(RuntimeError, match="missing=participant_episode_closure_records"):
        _require_complete_runtime_snapshot_fields(missing)

    with pytest.raises(RuntimeError, match="unexpected=unknown"):
        _require_complete_runtime_snapshot_fields({**complete, "unknown": None})


@pytest.mark.parametrize("store_kind", ["memory", "local"])
def test_terminal_commit_is_idempotent_but_rejects_snapshot_or_record_rewrite(
    tmp_path: Path,
    store_kind: str,
) -> None:
    store = _atomic_store(store_kind, tmp_path)
    terminal = _terminal_record(_running_record("terminal-idempotency"))
    snapshot = RuntimeSnapshot(metadata={"generation": 1})

    store.claim_record(_running_record("terminal-idempotency"))
    store.commit_terminal_operation(snapshot, terminal)
    store.commit_terminal_operation(snapshot, terminal)

    different_snapshot = RuntimeSnapshot(metadata={"generation": 2})
    with pytest.raises(ValueError, match="does not match the durable snapshot"):
        store.commit_terminal_operation(different_snapshot, terminal)
    rewritten = replace(terminal, status=replace(terminal.status, updated_at="2026-08-11T12:00:03Z"))
    with pytest.raises(ValueError, match="cannot be rewritten"):
        store.commit_terminal_operation(snapshot, rewritten)


@pytest.mark.parametrize("store_kind", ["memory", "local"])
def test_terminal_commit_rejects_nonterminal_and_immutable_identity_changes(
    tmp_path: Path,
    store_kind: str,
) -> None:
    store = _atomic_store(store_kind, tmp_path)
    running = _running_record("immutable")
    empty_snapshot = RuntimeSnapshot()

    with pytest.raises(ValueError, match="requires a terminal status"):
        store.commit_terminal_operation(empty_snapshot, running)
    terminal_record = _terminal_record(running)
    terminal_status = terminal_record.status
    for status, message in (
        (replace(terminal_status, operation_id="other"), "identities do not match"),
        (replace(terminal_status, domain=RuntimeDomain.EVALUATION), "domains do not match"),
        (replace(terminal_status, submitted_at="2026-08-11T12:00:04Z"), "submission times do not match"),
    ):
        with pytest.raises(ValueError, match=message):
            replace(terminal_record, status=status)

    store.claim_record(running)
    denied_receipt = replace(running.receipt, accepted=False)
    with pytest.raises(ValueError, match="denied operation receipts cannot be persisted"):
        replace(terminal_record, receipt=denied_receipt)
    changed_fingerprint = replace(terminal_record, request_fingerprint="changed")
    with pytest.raises(ValueError, match="operation identity is immutable"):
        store.commit_terminal_operation(empty_snapshot, changed_fingerprint)


@pytest.mark.parametrize("store_kind", ["memory", "local"])
@pytest.mark.parametrize("source_state", [OperationState.ACCEPTED, OperationState.RUNNING])
def test_interrupted_reconciliation_validates_and_seals_terminal_record(
    tmp_path: Path,
    store_kind: str,
    source_state: OperationState,
) -> None:
    store = _atomic_store(store_kind, tmp_path)
    running = _running_record(f"recovery-invariants-{source_state.value}", state=source_state)
    store.save_record(running)
    recovered = _interrupted_record(running)

    store.reconcile_interrupted_records((recovered,))
    store.reconcile_interrupted_records((recovered,))
    rewritten = replace(recovered, status=replace(recovered.status, updated_at="2026-08-11T12:00:05Z"))
    with pytest.raises(ValueError, match="cannot be rewritten during recovery"):
        store.reconcile_interrupted_records((rewritten,))

    missing = _running_record("missing")
    interrupted_missing = _interrupted_record(missing)
    with pytest.raises(ValueError, match="no longer exists"):
        store.reconcile_interrupted_records((interrupted_missing,))


@pytest.mark.parametrize("store_kind", ["memory", "local"])
@pytest.mark.parametrize("invalid_recovery", ["nonfailed", "missing-diagnostic"])
def test_interrupted_reconciliation_rejects_invalid_replacement(
    tmp_path: Path,
    store_kind: str,
    invalid_recovery: str,
) -> None:
    store = _atomic_store(f"{store_kind}-{invalid_recovery}", tmp_path)
    running = _running_record(f"invalid-{invalid_recovery}")
    store.save_record(running)
    replacement = _interrupted_record(running)
    if invalid_recovery == "nonfailed":
        replacement = replace(
            replacement,
            status=replace(
                replacement.status,
                state=OperationState.FAILED,
                diagnostics=[
                    *[
                        diagnostic
                        for diagnostic in replacement.status.diagnostics
                        if diagnostic.code == INTERRUPTED_OPERATION_DIAGNOSTIC_CODE
                    ],
                    operation_terminal_diagnostic(OperationState.FAILED),
                ],
            ),
        )
        message = "must persist indeterminate"
    else:
        replacement = replace(replacement, status=replace(replacement.status, diagnostics=[]))
        message = "requires its stable diagnostic"

    with pytest.raises(ValueError, match=message):
        store.reconcile_interrupted_records((replacement,))


@pytest.mark.parametrize("store_kind", ["memory", "local"])
def test_claim_returns_existing_idempotency_owner_without_snapshot_change(
    tmp_path: Path,
    store_kind: str,
) -> None:
    store = _atomic_store(f"{store_kind}-collision", tmp_path)
    first = replace(_running_record("first"), idempotency_key="shared")
    second = replace(_running_record("second"), idempotency_key="shared")
    store.save_record(first)
    assert store.claim_record(second) == first

    assert store.load_snapshot() == RuntimeSnapshot()
    assert set(store.load_records()) == {"first"}


def test_in_memory_store_idempotency_claim_and_write_collisions_fail_closed() -> None:
    store = InMemoryControlPlaneStore()
    first = replace(_running_record("first-claim"), idempotency_key="shared-claim")
    competing = replace(_running_record("competing-claim"), idempotency_key="shared-claim")

    assert store.claim_record(first) == first
    assert store.claim_record(competing) == first

    with pytest.raises(ValueError, match="idempotency key already belongs"):
        store.save_record(competing)


def test_in_memory_participant_transition_rolls_back_immutable_claim_rewrite() -> None:
    store = InMemoryControlPlaneStore()
    first = replace(_running_record("first-transition"), idempotency_key="shared-transition")
    competing_running = replace(_running_record("competing-transition"), idempotency_key="competing-claim")
    competing = replace(_terminal_record(competing_running), idempotency_key="shared-transition")
    store.save_record(first)
    store.save_record(competing_running)
    rollback_snapshot = RuntimeSnapshot(metadata={"must": "rollback"})
    event = _audit_event("participant-transition")

    with pytest.raises(ValueError, match="operation identity is immutable"):
        store.commit_participant_transition(
            expected_history_heads={},
            snapshot=rollback_snapshot,
            record=competing,
            audit_event=event,
        )

    assert store.load_snapshot() == RuntimeSnapshot()
    assert store.read_audit() == []
    assert set(store.load_records()) == {
        first.receipt.operation_id,
        competing_running.receipt.operation_id,
    }


def test_in_memory_participant_transition_accepts_record_without_idempotency_key() -> None:
    store = InMemoryControlPlaneStore()
    running = replace(_running_record("without-idempotency"), idempotency_key="")
    record = _terminal_record(running)
    snapshot = RuntimeSnapshot(metadata={"committed": True})
    event = _audit_event("participant-transition-without-idempotency")

    store.claim_record(running)
    store.commit_participant_transition(
        expected_history_heads={},
        snapshot=snapshot,
        record=record,
        audit_event=event,
    )

    assert store.load_snapshot() == snapshot
    assert store.load_records() == {record.receipt.operation_id: record}
    assert store.read_audit() == [event]


@pytest.mark.parametrize("crash_boundary", ["before-backend", "before-terminal-transaction"])
def test_restart_classifies_interrupted_operation_and_retry_does_not_repeat_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_boundary: str,
) -> None:
    target, provisioning_plan, provisioner = _target_and_plan(
        interrupt_before_effect=crash_boundary == "before-backend"
    )
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    control_plane = RuntimeControlPlane(target, store=store)
    _authorize_provisioning_plan(control_plane, target, provisioning_plan)
    if crash_boundary == "before-terminal-transaction":

        def interrupt_commit(_snapshot: RuntimeSnapshot, _record: ControlPlaneOperationRecord) -> None:
            raise KeyboardInterrupt("injected crash before terminal transaction")

        monkeypatch.setattr(store, "commit_terminal_operation", interrupt_commit)

    with pytest.raises(KeyboardInterrupt, match="injected crash"):
        control_plane.submit_provisioning(
            provisioning_plan,
            idempotency_key="retry-safe",
            request_fingerprint="same-request",
        )

    records = store.load_records()
    assert len(records) == 1
    operation_id, interrupted = next(iter(records.items()))
    expected_state = (
        OperationState.INDETERMINATE if crash_boundary == "before-terminal-transaction" else OperationState.RUNNING
    )
    assert interrupted.status.state == expected_state
    assert store.load_snapshot() == RuntimeSnapshot()
    control_plane.close()

    restarted = RuntimeControlPlane(target, store=LocalControlPlaneStore(store_path))
    _authorize_provisioning_plan(restarted, target, provisioning_plan)
    recovered = restarted.get_operation(operation_id)
    assert recovered is not None
    assert recovered.state == OperationState.INDETERMINATE
    assert any(diagnostic.code == INTERRUPTED_OPERATION_DIAGNOSTIC_CODE for diagnostic in recovered.diagnostics)
    assert recovered.diagnostics[-1].code == "runtime.control-plane.operation-indeterminate"

    retry = restarted.submit_provisioning(
        provisioning_plan,
        idempotency_key="retry-safe",
        request_fingerprint="same-request",
    )
    assert retry.operation_id == operation_id
    assert provisioner.apply_count == 1
    restarted.close()


@pytest.mark.parametrize("write_boundary", ["snapshot", "record"])
def test_terminal_transaction_rolls_back_at_each_internal_write_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write_boundary: str,
) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    running = _running_record("transaction-crash")
    store.claim_record(running)
    next_snapshot = RuntimeSnapshot(metadata={"generation": 2})
    method_name = f"_upsert_{write_boundary}"
    real_upsert = getattr(store, method_name)

    def interrupt_after_write(connection: object, value: object) -> None:
        real_upsert(connection, value)
        raise KeyboardInterrupt(f"injected crash after {write_boundary} write")

    monkeypatch.setattr(store, method_name, interrupt_after_write)
    terminal = _terminal_record(running)
    with pytest.raises(KeyboardInterrupt, match=f"after {write_boundary} write"):
        store.commit_terminal_operation(next_snapshot, terminal)

    assert store.load_snapshot() == RuntimeSnapshot()
    assert store.load_records()[running.receipt.operation_id] == running


def test_runtime_resynchronizes_after_error_reported_after_durable_terminal_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, provisioning_plan, provisioner = _target_and_plan()
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    control_plane = RuntimeControlPlane(target, store=store)
    _authorize_provisioning_plan(control_plane, target, provisioning_plan)
    real_commit = store.commit_terminal_operation

    def commit_then_error(snapshot: RuntimeSnapshot, record: ControlPlaneOperationRecord) -> None:
        real_commit(snapshot, record)
        raise RuntimeError("injected error after terminal commit")

    monkeypatch.setattr(store, "commit_terminal_operation", commit_then_error)
    with pytest.raises(RuntimeError, match="after terminal commit"):
        control_plane.submit_provisioning(
            provisioning_plan,
            idempotency_key="committed",
            request_fingerprint="same-request",
        )

    durable_record = next(iter(store.load_records().values()))
    assert durable_record.status.state == OperationState.SUCCEEDED
    assert store.load_snapshot().entries
    assert control_plane.snapshot == store.load_snapshot()
    assert control_plane.get_operation(durable_record.receipt.operation_id) == durable_record.status

    retry = control_plane.submit_provisioning(
        provisioning_plan,
        idempotency_key="committed",
        request_fingerprint="same-request",
    )
    assert retry.operation_id == durable_record.receipt.operation_id
    assert provisioner.apply_count == 1
    control_plane.close()

    restarted = RuntimeControlPlane(target, store=LocalControlPlaneStore(store_path))
    _authorize_provisioning_plan(restarted, target, provisioning_plan)
    assert restarted.get_operation(durable_record.receipt.operation_id) == durable_record.status
    restarted_retry = restarted.submit_provisioning(
        provisioning_plan,
        idempotency_key="committed",
        request_fingerprint="same-request",
    )
    assert restarted_retry.operation_id == durable_record.receipt.operation_id
    assert provisioner.apply_count == 1
    restarted.close()


def test_runtime_seals_reloaded_non_terminal_operations_after_uncertain_terminal_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target, provisioning_plan, provisioner = _target_and_plan()
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(target, store=store)
    _authorize_provisioning_plan(control_plane, target, provisioning_plan)

    def fail_terminal_commit(_snapshot: RuntimeSnapshot, _record: ControlPlaneOperationRecord) -> None:
        raise RuntimeError("injected terminal commit failure")

    monkeypatch.setattr(store, "commit_terminal_operation", fail_terminal_commit)
    with pytest.raises(RuntimeError, match="terminal commit failure"):
        control_plane.submit_provisioning(
            provisioning_plan,
            idempotency_key="uncertain-terminal-commit",
            request_fingerprint="same-request",
        )

    durable_record = next(iter(store.load_records().values()))
    assert durable_record.status.state == OperationState.INDETERMINATE
    assert any(
        diagnostic.code == INTERRUPTED_OPERATION_DIAGNOSTIC_CODE for diagnostic in durable_record.status.diagnostics
    )
    assert control_plane.get_operation(durable_record.receipt.operation_id) == durable_record.status

    retry = control_plane.submit_provisioning(
        provisioning_plan,
        idempotency_key="uncertain-terminal-commit",
        request_fingerprint="same-request",
    )
    assert retry.operation_id == durable_record.receipt.operation_id
    assert provisioner.apply_count == 1
    control_plane.close()


def test_runtime_error_reconciliation_does_not_seal_a_concurrent_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)
    failing = _running_record("failing-commit")
    concurrent = _running_record("concurrent-commit")
    control_plane._claim_record(failing)
    store.save_record(concurrent)

    def fail_terminal_commit(_snapshot: RuntimeSnapshot, _record: ControlPlaneOperationRecord) -> None:
        raise RuntimeError("injected terminal commit failure")

    monkeypatch.setattr(store, "commit_terminal_operation", fail_terminal_commit)
    snapshot = RuntimeSnapshot()
    terminal = _terminal_record(failing)
    with pytest.raises(RuntimeError, match="terminal commit failure"):
        control_plane._commit_terminal_operation(snapshot, terminal)

    records = store.load_records()
    assert records[failing.receipt.operation_id].status.state is OperationState.INDETERMINATE
    assert records[concurrent.receipt.operation_id] == concurrent


def test_runtime_poisoned_when_store_error_cannot_be_reconciled(monkeypatch: pytest.MonkeyPatch) -> None:
    target, provisioning_plan, _ = _target_and_plan()
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(target, store=store)
    _authorize_provisioning_plan(control_plane, target, provisioning_plan)

    def fail_commit(_snapshot: RuntimeSnapshot, _record: ControlPlaneOperationRecord) -> None:
        raise RuntimeError("terminal commit failed")

    def fail_reload() -> RuntimeSnapshot:
        raise OSError("durable reload failed")

    monkeypatch.setattr(store, "commit_terminal_operation", fail_commit)
    monkeypatch.setattr(store, "load_snapshot", fail_reload)

    with pytest.raises(RuntimeError, match="terminal commit failed") as caught:
        control_plane.submit_provisioning(provisioning_plan)
    assert any("runtime is poisoned" in note for note in caught.value.__notes__)
    with pytest.raises(RuntimeError, match="requires restart"):
        control_plane.get_snapshot()
    control_plane.close()


def test_startup_reconciliation_is_atomic_and_restarts_cleanly_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    accepted = _running_record("accepted", state=OperationState.ACCEPTED)
    running = _running_record("running")
    store.save_record(accepted)
    store.save_record(running)
    real_upsert = store._upsert_record
    writes = 0

    def fail_second_recovery_write(connection: object, record: ControlPlaneOperationRecord) -> None:
        nonlocal writes
        writes += 1
        real_upsert(connection, record)
        if writes == 2:
            raise OSError("injected recovery crash")

    monkeypatch.setattr(store, "_upsert_record", fail_second_recovery_write)
    target = create_stub_target()
    with pytest.raises(OSError, match="injected recovery crash"):
        RuntimeControlPlane(target, store=store)

    assert {record.status.state for record in store.load_records().values()} == {
        OperationState.ACCEPTED,
        OperationState.RUNNING,
    }

    restarted = RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(store_path))
    recovered = restarted._operations.values()
    assert {record.status.state for record in recovered} == {
        OperationState.CANCELLED,
        OperationState.INDETERMINATE,
    }
    assert all(
        any(diagnostic.code == INTERRUPTED_OPERATION_DIAGNOSTIC_CODE for diagnostic in record.status.diagnostics)
        for record in recovered
    )
    restarted.close()


def test_local_store_rejects_second_runtime_owner_then_allows_clean_handoff(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    target = create_stub_target()
    first = RuntimeControlPlane(target, store=store)

    with pytest.raises(RuntimeError, match="exactly one worker"):
        RuntimeControlPlane(target, store=store)
    competing_store = LocalControlPlaneStore(store_path)
    with pytest.raises(RuntimeError, match="exactly one worker"):
        RuntimeControlPlane(target, store=competing_store)

    first.close()
    second = RuntimeControlPlane(target, store=LocalControlPlaneStore(store_path))
    second.close()


def test_local_store_rejects_empty_idempotency_lookup_and_tampered_operation_identity(tmp_path: Path) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    record = _running_record("durable-identity")
    store.save_record(record)
    assert store.find_by_idempotency("") is None

    tampered_key = "tampered-durable-key"
    with store._connection() as connection, local_store_module._transaction(connection):
        connection.execute(
            "UPDATE operations SET operation_id=? WHERE operation_id=?",
            (tampered_key, record.receipt.operation_id),
        )

    with pytest.raises(ValueError, match="identity does not match its durable key"):
        store.load_records()
    terminal = _terminal_record(_running_record(tampered_key))
    empty_snapshot = RuntimeSnapshot()
    with pytest.raises(ValueError, match="identity does not match its durable key"):
        store.commit_terminal_operation(empty_snapshot, terminal)


def test_local_store_rejects_unsupported_schema_and_failed_quick_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_path = tmp_path / "unsupported-schema"
    schema_store = LocalControlPlaneStore(schema_path)
    with schema_store._connection() as connection, local_store_module._transaction(connection):
        connection.execute("UPDATE metadata SET value='future' WHERE key='schema-version'")
    with pytest.raises(ValueError, match="unsupported local control-plane database schema"):
        LocalControlPlaneStore(schema_path)

    quick_check_path = tmp_path / "failed-quick-check"
    LocalControlPlaneStore(quick_check_path)
    real_connect = LocalControlPlaneStore._connect

    class _QuickCheckFailureConnection:
        def __init__(self, connection: Any) -> None:
            self._connection = connection

        def execute(self, statement: str, *args: Any) -> Any:
            if statement == "PRAGMA quick_check":
                return SimpleNamespace(fetchone=lambda: ("injected-corruption",))
            return self._connection.execute(statement, *args)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._connection, name)

    def failed_quick_check_connect(
        store: LocalControlPlaneStore,
        **kwargs: Any,
    ) -> tuple[Any, os.stat_result]:
        connection, metadata = real_connect(store, **kwargs)
        return _QuickCheckFailureConnection(connection), metadata

    monkeypatch.setattr(LocalControlPlaneStore, "_connect", failed_quick_check_connect)
    with pytest.raises(ValueError, match="database failed its integrity check"):
        LocalControlPlaneStore(quick_check_path)


def test_local_store_migrates_v1_sqlite_operations_and_disposes_denials(tmp_path: Path) -> None:
    store_path = tmp_path / "v1-operation-records"
    original = LocalControlPlaneStore(store_path)
    accepted = _running_record("legacy-sqlite-accepted", state=OperationState.FAILED)
    denied = _running_record("legacy-sqlite-denied", state=OperationState.FAILED)
    with original._connection() as connection, local_store_module._transaction(connection):
        for record, is_accepted in ((accepted, True), (denied, False)):
            payload, digest = local_store_module._encode_payload(
                _pre_lifecycle_record_payload(record, accepted=is_accepted)
            )
            connection.execute(
                """
                INSERT INTO operations(operation_id, idempotency_key, request_fingerprint, payload, digest)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.receipt.operation_id,
                    record.idempotency_key,
                    "legacy-unclassified-fingerprint",
                    payload,
                    digest,
                ),
            )
        connection.execute("UPDATE metadata SET value='1' WHERE key='schema-version'")

    migrated = LocalControlPlaneStore(store_path)
    records = migrated.load_records()

    assert set(records) == {accepted.receipt.operation_id}
    migrated_record = records[accepted.receipt.operation_id]
    assert migrated_record.receipt.context.actor_id == "legacy-store-migration"
    assert migrated_record.receipt.context == migrated_record.status.context
    assert migrated_record.request_fingerprint == migrated_record.receipt.context.request_commitment
    assert migrated_record.status.diagnostics == [operation_terminal_diagnostic(OperationState.FAILED)]
    assert migrated.find_by_idempotency(denied.idempotency_key) is None
    denial_audit = migrated.read_audit()[-1]
    assert denial_audit.operation_id == denied.receipt.operation_id
    assert denial_audit.allowed is False
    assert denial_audit.reason == "legacy-denied-operation-disposed"
    with migrated._connection() as connection:
        assert connection.execute("SELECT value FROM metadata WHERE key='schema-version'").fetchone() == ("2",)


def test_local_store_rejects_non_wal_before_schema_or_legacy_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store_path.mkdir(mode=0o700)
    legacy_path = store_path / "operations.json"
    legacy_payload = "{}"
    legacy_path.write_text(legacy_payload, encoding="utf-8")
    real_connect = local_store_module.sqlite3.connect

    class _NonWalConnection:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self._connection = connection

        def execute(self, statement: str, *args: Any) -> Any:
            if statement == "PRAGMA journal_mode=WAL":
                return SimpleNamespace(fetchone=lambda: ("delete",))
            return self._connection.execute(statement, *args)

        def executescript(self, _script: str) -> Any:
            pytest.fail("schema work must not run without WAL admission")

        def __getattr__(self, name: str) -> Any:
            return getattr(self._connection, name)

    def connect_without_wal(*args: Any, **kwargs: Any) -> _NonWalConnection:
        return _NonWalConnection(real_connect(*args, **kwargs))

    monkeypatch.setattr(local_store_module.sqlite3, "connect", connect_without_wal)
    monkeypatch.setattr(
        LocalControlPlaneStore,
        "_migrate_legacy_json",
        lambda *_args, **_kwargs: pytest.fail("legacy migration must not run without WAL admission"),
    )

    with pytest.raises(RuntimeError, match="did not enter required SQLite WAL journal mode"):
        LocalControlPlaneStore(store_path)

    assert legacy_path.read_text(encoding="utf-8") == legacy_payload
    assert list(store_path.glob("legacy-json-backup-*")) == []
    with closing(real_connect(store_path / "control-plane.sqlite3")) as connection, connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []


def test_local_store_rejects_non_object_durable_payload(tmp_path: Path) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    store.save_snapshot(RuntimeSnapshot(metadata={"stored": True}))
    content = "[]"
    digest = sha256(content.encode("utf-8")).hexdigest()
    with store._connection() as connection, local_store_module._transaction(connection):
        connection.execute(
            "UPDATE state SET payload=?, digest=? WHERE key='runtime-snapshot'",
            (content, digest),
        )

    with pytest.raises(ValueError, match="payload must be an object"):
        store.load_snapshot()


def test_local_store_migrates_complete_legacy_state_and_keeps_auditable_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store_path.mkdir(mode=0o700)
    file_snapshot = RuntimeSnapshot(metadata={"source": "snapshot-file"})
    committed_snapshot = RuntimeSnapshot(
        participant_control_history={"participant.test": [{}]},
        metadata={"source": "control-transition-state"},
    )
    control_record = _running_record("legacy-control-record")
    operations_record = _running_record("legacy-operations-record")
    first_audit = _audit_event("legacy-control-audit")
    second_audit = _audit_event("legacy-jsonl-audit")
    (store_path / "snapshot.json").write_text(
        json.dumps(_snapshot_payload(file_snapshot)),
        encoding="utf-8",
    )
    (store_path / "control-transition-state.json").write_text(
        json.dumps(
            {
                "snapshot": _snapshot_payload(committed_snapshot),
                "records": {control_record.receipt.operation_id: local_store_module._record_payload(control_record)},
                "audit": [asdict(first_audit)],
            }
        ),
        encoding="utf-8",
    )
    (store_path / "operations.json").write_text(
        json.dumps({operations_record.receipt.operation_id: local_store_module._record_payload(operations_record)}),
        encoding="utf-8",
    )
    (store_path / "audit.jsonl").write_text(
        "\n" + json.dumps(asdict(first_audit)) + "\n" + json.dumps(asdict(second_audit)) + "\n",
        encoding="utf-8",
    )
    fsync_targets: list[str] = []
    real_fsync = store_paths_module.os.fsync

    def observe_fsync(descriptor: int) -> None:
        mode = os.fstat(descriptor).st_mode
        fsync_targets.append("file" if stat.S_ISREG(mode) else "directory")
        real_fsync(descriptor)

    monkeypatch.setattr(store_paths_module.os, "fsync", observe_fsync)

    migrated = LocalControlPlaneStore(store_path)

    assert migrated.load_snapshot().metadata == {"source": "control-transition-state"}
    assert set(migrated.load_records()) == {
        control_record.receipt.operation_id,
        operations_record.receipt.operation_id,
    }
    assert migrated.read_audit() == [first_audit, second_audit]
    backups = list(store_path.glob("legacy-json-backup-*"))
    assert len(backups) == 1
    assert {path.name for path in backups[0].iterdir()} == {
        "snapshot.json",
        "control-transition-state.json",
        "operations.json",
        "audit.jsonl",
    }
    expected_fsync_targets = ["file"] * 4
    if store_paths_module._DIRECTORY_FSYNC_SUPPORTED:
        expected_fsync_targets.extend(["directory"] * 3)
    assert fsync_targets == expected_fsync_targets


def test_local_store_backup_file_fsync_failure_rolls_back_and_restarts_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store_path.mkdir(mode=0o700)
    record = _running_record("legacy-fsync-restart")
    legacy_path = store_path / "operations.json"
    legacy_payload = json.dumps({record.receipt.operation_id: local_store_module._record_payload(record)})
    legacy_path.write_text(legacy_payload, encoding="utf-8")
    real_fsync = store_paths_module.os.fsync
    failed_regular_file = False

    def fail_first_regular_file(descriptor: int) -> None:
        nonlocal failed_regular_file
        if stat.S_ISREG(os.fstat(descriptor).st_mode) and not failed_regular_file:
            failed_regular_file = True
            raise OSError(errno.EIO, "injected backup fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(store_paths_module.os, "fsync", fail_first_regular_file)

    with pytest.raises(RuntimeError, match="could not durably synchronize local control-plane file") as caught:
        LocalControlPlaneStore(store_path)

    assert isinstance(caught.value.__cause__, OSError)
    assert caught.value.__cause__.errno == errno.EIO
    assert legacy_path.read_text(encoding="utf-8") == legacy_payload
    assert len(list(store_path.glob("legacy-json-backup-*"))) == 1
    with closing(sqlite3.connect(store_path / "control-plane.sqlite3")) as connection, connection:
        assert connection.execute("SELECT value FROM metadata WHERE key='legacy-json-migration'").fetchone() is None

    monkeypatch.undo()
    migrated = LocalControlPlaneStore(store_path)
    assert migrated.load_records() == {record.receipt.operation_id: record}
    assert legacy_path.read_text(encoding="utf-8") == legacy_payload
    assert len(list(store_path.glob("legacy-json-backup-*"))) == 2


def test_local_store_rolls_back_unverified_legacy_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store_path.mkdir(mode=0o700)
    record = _running_record("legacy-unverified")
    snapshot = RuntimeSnapshot(metadata={"source": "same-transition-count"})
    (store_path / "snapshot.json").write_text(
        json.dumps(_snapshot_payload(snapshot)),
        encoding="utf-8",
    )
    (store_path / "control-transition-state.json").write_text(
        json.dumps({"snapshot": _snapshot_payload(snapshot)}),
        encoding="utf-8",
    )
    (store_path / "operations.json").write_text(
        json.dumps({record.receipt.operation_id: local_store_module._record_payload(record)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        LocalControlPlaneStore,
        "_upsert_record",
        staticmethod(lambda _connection, _record: None),
    )

    with pytest.raises(ValueError, match="legacy control-plane migration verification failed"):
        LocalControlPlaneStore(store_path)


def test_local_store_migrates_legacy_records_without_snapshot_files(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    store_path.mkdir(mode=0o700)
    record = _running_record("legacy-record-only")
    (store_path / "operations.json").write_text(
        json.dumps({record.receipt.operation_id: _pre_lifecycle_record_payload(record)}),
        encoding="utf-8",
    )

    migrated = LocalControlPlaneStore(store_path)
    migrated_record = migrated.load_records()[record.receipt.operation_id]

    assert migrated.load_snapshot() == RuntimeSnapshot()
    assert migrated_record.status.state is OperationState.RUNNING
    assert migrated_record.receipt.context.actor_id == "legacy-store-migration"
    assert migrated_record.receipt.context == migrated_record.status.context
    assert migrated_record.request_fingerprint == migrated_record.receipt.context.request_commitment


def test_snapshot_serialization_preserves_account_placement_without_credentials() -> None:
    address = "account-placement.test"
    payload = {"account_address": "account.test", "node_address": "node.test"}
    snapshot = RuntimeSnapshot(
        entries={
            address: SnapshotEntry(
                address=address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="account-placement",
                payload=payload,
            )
        }
    )

    assert _snapshot_payload(snapshot)["entries"][address]["payload"] == payload


def test_terminal_commit_retry_compares_canonical_value_free_snapshot(tmp_path: Path) -> None:
    address = "provision.account.test"
    snapshot = RuntimeSnapshot(
        entries={
            address: SnapshotEntry(
                address=address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="account-placement",
                payload={
                    "spec": {
                        "credential_bindings": [
                            {
                                "credential_id": "root",
                                "purpose": "login",
                                "auth_method": "password",
                                "material": {"classification": "secret_fixture", "value": "secret"},
                            }
                        ]
                    }
                },
            )
        }
    )
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    running = replace(_running_record("canonical-terminal-retry"), idempotency_key="canonical-retry")
    terminal = _terminal_record(running)
    store.claim_record(running)

    store.commit_terminal_operation(snapshot, terminal)
    store.commit_terminal_operation(snapshot, terminal)

    assert store.load_records()[running.receipt.operation_id] == terminal
    assert store.load_snapshot() == _snapshot_from_payload(_snapshot_payload(snapshot))


def test_local_store_rejects_configured_multiworker_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    target = create_stub_target()
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    with pytest.raises(RuntimeError, match="WEB_CONCURRENCY=2"):
        RuntimeControlPlane(target, store=store)


def test_local_store_rejects_invalid_worker_count_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UVICORN_WORKERS", "many")
    target = create_stub_target()
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    with pytest.raises(RuntimeError, match="UVICORN_WORKERS must be 1"):
        RuntimeControlPlane(target, store=store)


def test_local_store_accepts_explicit_single_worker_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    owner = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(tmp_path / "control-plane"),
    )
    assert owner.get_snapshot().snapshot == RuntimeSnapshot()
    owner.close()


def test_local_store_migrates_directory_and_database_and_validates_private_sidecars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name == "nt":
        pytest.skip("POSIX mode bits are unavailable")
    store_path = tmp_path / "control-plane"
    store_path.mkdir()
    store_path.chmod(0o777)
    database_path = store_path / "control-plane.sqlite3"
    database_path.touch(mode=0o644)
    connection_observations: list[tuple[int, tuple[str, ...]]] = []
    connect = local_store_module.sqlite3.connect

    def observe_connect(*args: Any, **kwargs: Any) -> Any:
        existing_sidecars = tuple(
            suffix
            for suffix in store_paths_module._SQLITE_SIDECAR_SUFFIXES
            if Path(f"{database_path}{suffix}").exists()
        )
        connection_observations.append((store_path.stat().st_mode & 0o777, existing_sidecars))
        return connect(*args, **kwargs)

    monkeypatch.setattr(local_store_module.sqlite3, "connect", observe_connect)

    store = LocalControlPlaneStore(store_path)

    assert connection_observations[0] == (0o700, ())
    assert store_path.stat().st_mode & 0o777 == 0o700
    assert database_path.stat().st_mode & 0o777 == 0o600
    with store._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('permission-probe', 'ok')")
        connection.commit()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{database_path}{suffix}")
            assert sidecar.exists()
            assert sidecar.stat().st_mode & 0o777 == 0o600


def test_local_store_never_uses_raw_descriptors_for_sqlite_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    database_path = store_path / "control-plane.sqlite3"
    sqlite_paths = {
        database_path,
        *(Path(f"{database_path}{suffix}") for suffix in store_paths_module._SQLITE_SIDECAR_SUFFIXES),
    }
    directory_descriptors: set[int] = set()
    raw_open = store_paths_module.os.open
    raw_fchmod = store_paths_module.os.fchmod
    raw_path_open = Path.open

    def guarded_raw_open(path: Any, *args: Any, **kwargs: Any) -> int:
        assert Path(path) not in sqlite_paths
        descriptor = raw_open(path, *args, **kwargs)
        directory_descriptors.add(descriptor)
        return descriptor

    def guarded_fchmod(descriptor: int, mode: int) -> None:
        assert descriptor in directory_descriptors
        raw_fchmod(descriptor, mode)

    def guarded_path_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        assert path not in sqlite_paths
        return raw_path_open(path, *args, **kwargs)

    monkeypatch.setattr(store_paths_module.os, "open", guarded_raw_open)
    monkeypatch.setattr(store_paths_module.os, "fchmod", guarded_fchmod)
    monkeypatch.setattr(Path, "open", guarded_path_open)

    store = LocalControlPlaneStore(store_path)
    with store._connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('sidecar-probe', 'ok')")
        connection.commit()
        assert Path(f"{database_path}-wal").exists()
        assert Path(f"{database_path}-shm").exists()


def test_local_store_uses_encoded_sqlite_uri_creation_and_existing_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control plane?#"
    connection_uris: list[tuple[str, bool]] = []
    connect = local_store_module.sqlite3.connect

    def observe_connect(database: str, *args: Any, **kwargs: Any) -> Any:
        connection_uris.append((database, kwargs.get("uri") is True))
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(local_store_module.sqlite3, "connect", observe_connect)

    store = LocalControlPlaneStore(store_path)
    store.load_snapshot()

    assert connection_uris[0][0].endswith("control%20plane%3F%23/control-plane.sqlite3?mode=rwc")
    assert connection_uris[-1][0].endswith("control%20plane%3F%23/control-plane.sqlite3?mode=rw")
    assert all(uri_enabled for _, uri_enabled in connection_uris)


def test_local_store_does_not_recreate_existing_database_that_disappears_before_connect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    database_path = store._database_path
    connect = local_store_module.sqlite3.connect

    def remove_then_connect(*args: Any, **kwargs: Any) -> Any:
        database_path.unlink()
        return connect(*args, **kwargs)

    monkeypatch.setattr(local_store_module.sqlite3, "connect", remove_then_connect)

    with pytest.raises(sqlite3.OperationalError):
        store.load_snapshot()
    assert not database_path.exists()


@pytest.mark.parametrize(
    ("changed_call", "message"),
    [
        (2, "database file changed while SQLite opened it"),
        (3, "database file changed while SQLite was connected"),
    ],
)
def test_local_store_rejects_database_identity_replacement_across_sqlite_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_call: int,
    message: str,
) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    secure_database_file = local_store_module._secure_database_file
    calls = 0

    def changed_identity(*args: Any, **kwargs: Any) -> os.stat_result | None:
        nonlocal calls
        calls += 1
        metadata = secure_database_file(*args, **kwargs)
        if calls != changed_call or metadata is None:
            return metadata
        values = list(metadata)
        values[stat.ST_INO] += 1
        return os.stat_result(values)

    monkeypatch.setattr(local_store_module, "_secure_database_file", changed_identity)

    with pytest.raises(RuntimeError, match=message):
        store.load_snapshot()


def test_local_store_rejects_database_replacement_between_connections(tmp_path: Path) -> None:
    original_path = tmp_path / "original"
    replacement_path = tmp_path / "replacement"
    store = LocalControlPlaneStore(original_path)
    store.save_snapshot(RuntimeSnapshot(metadata={"database": "original"}))
    replacement = LocalControlPlaneStore(replacement_path)
    replacement.save_snapshot(RuntimeSnapshot(metadata={"database": "replacement"}))
    os.replace(replacement._database_path, store._database_path)

    with pytest.raises(RuntimeError, match="database file changed while the store was active"):
        store.load_snapshot()


def test_local_store_rejects_hard_linked_database_alias(tmp_path: Path) -> None:
    original_path = tmp_path / "original"
    alias_path = tmp_path / "alias"
    original = LocalControlPlaneStore(original_path)
    alias_path.mkdir(mode=0o700)
    try:
        os.link(original._database_path, alias_path / "control-plane.sqlite3")
    except OSError:
        pytest.skip("hard links are unavailable")

    with pytest.raises(RuntimeError, match="database file must not have hard links"):
        LocalControlPlaneStore(alias_path)


def test_sqlite_sidecar_validation_is_metadata_only_and_tolerates_disappearance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sidecar = tmp_path / "control-plane.sqlite3-shm"
    sidecar.touch(mode=0o600)

    def unexpected_descriptor_operation(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("SQLite sidecar validation must remain metadata-only")

    monkeypatch.setattr(store_paths_module.os, "open", unexpected_descriptor_operation)
    monkeypatch.setattr(store_paths_module.os, "fchmod", unexpected_descriptor_operation, raising=False)
    monkeypatch.setattr(store_paths_module.os, "chmod", unexpected_descriptor_operation)
    monkeypatch.setattr(Path, "chmod", unexpected_descriptor_operation)

    assert store_paths_module._validate_sqlite_sidecar(sidecar) is True
    disappearing = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o600,
        st_file_attributes=0,
        st_uid=getattr(os, "geteuid", lambda: 0)(),
        st_nlink=0,
    )
    monkeypatch.setattr(Path, "lstat", lambda _path: disappearing)
    assert store_paths_module._validate_sqlite_sidecar(sidecar) is False
    monkeypatch.undo()
    sidecar.unlink()
    assert store_paths_module._validate_sqlite_sidecar(sidecar) is False


def test_sqlite_sidecar_validation_rejects_unsafe_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_uid = getattr(os, "geteuid", lambda: 0)()
    sidecar = tmp_path / "control-plane.sqlite3-shm"
    cases = [
        (
            SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0, st_uid=current_uid),
            "symlink or reparse point",
        ),
        (
            SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0, st_uid=current_uid),
            "wrong filesystem type",
        ),
        (
            SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600,
                st_file_attributes=0,
                st_uid=current_uid,
                st_nlink=2,
            ),
            "must not have hard links",
        ),
    ]
    if os.name != "nt":
        cases.append(
            (
                SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_file_attributes=0, st_uid=current_uid),
                "private permissions 0600",
            )
        )
    if hasattr(os, "geteuid"):
        cases.append(
            (
                SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_file_attributes=0, st_uid=current_uid + 1),
                "owned by the current user",
            )
        )

    for metadata, message in cases:
        with monkeypatch.context() as patch:
            patch.setattr(Path, "lstat", lambda _path, value=metadata: value)
            with pytest.raises(RuntimeError, match=message):
                store_paths_module._validate_sqlite_sidecar(sidecar)


def test_local_store_repeated_multiprocess_wal_lifecycle(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    LocalControlPlaneStore(store_path)
    context = get_context("spawn")
    process_count = 4
    write_count = 6
    barrier = context.Barrier(process_count)
    processes = [
        context.Process(
            target=_stress_local_store_writes,
            args=(str(store_path), process_index, write_count, barrier),
        )
        for process_index in range(process_count)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)

    assert [process.exitcode for process in processes] == [0] * process_count
    assert set(LocalControlPlaneStore(store_path).load_records()) == {
        f"stress-{process_index}-{write_index}"
        for process_index in range(process_count)
        for write_index in range(write_count)
    }


def test_local_store_rejects_symlink_directory_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    marker = target / "marker"
    marker.write_text("unchanged", encoding="utf-8")
    store_path = tmp_path / "control-plane"
    try:
        store_path.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(RuntimeError, match="directory must not be a symlink or reparse point"):
        LocalControlPlaneStore(store_path)

    assert marker.read_text(encoding="utf-8") == "unchanged"


def test_local_store_rejects_non_directory_store_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store_path.write_text("not a directory", encoding="utf-8")
    before = os.stat(store_path)

    def unexpected_mutation(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("unsafe path was opened or chmodded")

    monkeypatch.setattr(store_paths_module.os, "open", unexpected_mutation)
    monkeypatch.setattr(store_paths_module.os, "fchmod", unexpected_mutation, raising=False)

    with pytest.raises(RuntimeError, match="directory has the wrong filesystem type"):
        LocalControlPlaneStore(store_path)

    after = os.stat(store_path)
    assert store_path.read_text(encoding="utf-8") == "not a directory"
    assert (after.st_ino, after.st_mode, after.st_mtime_ns) == (before.st_ino, before.st_mode, before.st_mtime_ns)


def test_local_store_rejects_foreign_directory_without_open_or_chmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_effective_uid = getattr(os, "geteuid", None)
    if not callable(get_effective_uid):
        pytest.skip("filesystem ownership is unavailable")
    store_path = tmp_path / "control-plane"
    store_path.mkdir()
    store_path.chmod(0o777)
    before = os.stat(store_path)
    lstat = Path.lstat
    foreign_metadata = SimpleNamespace(
        st_mode=before.st_mode,
        st_file_attributes=0,
        st_uid=get_effective_uid() + 1,
    )

    def fake_lstat(path: Path) -> Any:
        if path == store_path:
            return foreign_metadata
        return lstat(path)

    def unexpected_mutation(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("foreign path was opened or chmodded")

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    monkeypatch.setattr(store_paths_module.os, "open", unexpected_mutation)
    monkeypatch.setattr(store_paths_module.os, "fchmod", unexpected_mutation, raising=False)

    with pytest.raises(RuntimeError, match="directory must be owned by the current user"):
        LocalControlPlaneStore(store_path)

    after = os.stat(store_path)
    assert (after.st_ino, after.st_mode, after.st_mtime_ns) == (before.st_ino, before.st_mode, before.st_mtime_ns)


def test_store_path_windows_mode_branches_do_not_call_fchmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory_path = tmp_path / "control-plane"
    directory_path.mkdir()
    database_path = directory_path / "control-plane.sqlite3"
    database_path.touch()
    fchmod_calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(store_paths_module.os, "name", "nt")
    monkeypatch.setattr(
        store_paths_module.os,
        "fchmod",
        lambda *args: fchmod_calls.append(args),
        raising=False,
    )

    store_paths_module._secure_store_directory(directory_path)
    assert store_paths_module._secure_database_file(database_path, allow_missing=False) is not None
    assert store_paths_module._validate_sqlite_sidecar(database_path)
    assert fchmod_calls == []


def test_store_path_legacy_json_and_transition_count_helpers(tmp_path: Path) -> None:
    legacy_path = tmp_path / "snapshot.json"
    legacy_path.write_text('{"snapshot": true}', encoding="utf-8")
    assert store_paths_module._read_json_object(legacy_path) == {"snapshot": True}

    legacy_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain an object"):
        store_paths_module._read_json_object(legacy_path)

    snapshot = RuntimeSnapshot(
        participant_control_history={"participant-a": [{}, {}]},
        participant_crossing_history={"participant-a": [{}]},
        information_state_history={"participant-a": [{}, {}, {}]},
    )
    assert store_paths_module._participant_transition_count(snapshot) == 6


def test_local_store_directory_fsync_skips_platforms_without_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(store_paths_module, "_DIRECTORY_FSYNC_SUPPORTED", False)
    monkeypatch.setattr(
        store_paths_module.os,
        "open",
        lambda *_args, **_kwargs: pytest.fail("unsupported directory fsync must not open the directory"),
    )

    store_paths_module._fsync_directory(tmp_path)


@pytest.mark.parametrize(
    "unsupported_errno",
    sorted(store_paths_module._UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS),
)
@pytest.mark.parametrize("failure_stage", ["open", "fsync"])
def test_local_store_directory_fsync_tolerates_only_known_unsupported_errnos(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsupported_errno: int,
    failure_stage: str,
) -> None:
    opened_descriptors: list[int] = []
    real_open = store_paths_module.os.open

    def unsupported_open(*_args: Any, **_kwargs: Any) -> int:
        raise OSError(unsupported_errno, "unsupported directory open")

    def observe_open(*args: Any, **kwargs: Any) -> int:
        descriptor = real_open(*args, **kwargs)
        opened_descriptors.append(descriptor)
        return descriptor

    def unsupported_fsync(_descriptor: int) -> None:
        raise OSError(unsupported_errno, "unsupported directory fsync")

    monkeypatch.setattr(store_paths_module, "_DIRECTORY_FSYNC_SUPPORTED", True)
    monkeypatch.setattr(
        store_paths_module.os,
        "open",
        unsupported_open if failure_stage == "open" else observe_open,
    )
    if failure_stage == "fsync":
        monkeypatch.setattr(store_paths_module.os, "fsync", unsupported_fsync)

    store_paths_module._fsync_directory(tmp_path)

    if opened_descriptors:
        with pytest.raises(OSError) as caught:
            os.fstat(opened_descriptors[0])
        assert caught.value.errno == errno.EBADF


@pytest.mark.parametrize("failure_stage", ["open", "fsync"])
def test_local_store_directory_fsync_propagates_eio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    opened_descriptors: list[int] = []
    real_open = store_paths_module.os.open

    def fail_open(*_args: Any, **_kwargs: Any) -> int:
        raise OSError(errno.EIO, "injected directory open failure")

    def observe_open(*args: Any, **kwargs: Any) -> int:
        descriptor = real_open(*args, **kwargs)
        opened_descriptors.append(descriptor)
        return descriptor

    def fail_fsync(_descriptor: int) -> None:
        raise OSError(errno.EIO, "injected directory fsync failure")

    monkeypatch.setattr(store_paths_module, "_DIRECTORY_FSYNC_SUPPORTED", True)
    monkeypatch.setattr(
        store_paths_module.os,
        "open",
        fail_open if failure_stage == "open" else observe_open,
    )
    if failure_stage == "fsync":
        monkeypatch.setattr(store_paths_module.os, "fsync", fail_fsync)

    with pytest.raises(RuntimeError, match="could not durably synchronize local control-plane directory") as caught:
        store_paths_module._fsync_directory(tmp_path)

    assert isinstance(caught.value.__cause__, OSError)
    assert caught.value.__cause__.errno == errno.EIO
    if opened_descriptors:
        with pytest.raises(OSError) as closed:
            os.fstat(opened_descriptors[0])
        assert closed.value.errno == errno.EBADF


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_local_store_rejects_symlink_database_paths_without_touching_target(
    tmp_path: Path,
    suffix: str,
) -> None:
    store_path = tmp_path / "control-plane"
    store_path.mkdir(mode=0o700)
    database_path = store_path / "control-plane.sqlite3"
    if suffix:
        database_path.touch(mode=0o600)
    victim = tmp_path / f"victim{suffix or '-database'}"
    victim.write_text("unchanged", encoding="utf-8")
    unsafe_path = Path(f"{database_path}{suffix}")
    try:
        unsafe_path.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    path_kind = "database file" if not suffix else "SQLite sidecar"
    with pytest.raises(RuntimeError, match=rf"{path_kind} must not be a symlink or reparse point"):
        LocalControlPlaneStore(store_path)

    assert victim.read_text(encoding="utf-8") == "unchanged"


def test_local_store_path_metadata_rejects_reparse_wrong_type_and_foreign_owner(tmp_path: Path) -> None:
    current_uid = getattr(os, "geteuid", lambda: 0)()
    path = tmp_path / "control-plane"
    cases = [
        (
            SimpleNamespace(
                st_mode=stat.S_IFDIR | 0o700,
                st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
                st_uid=current_uid,
            ),
            "directory",
            "symlink or reparse point",
        ),
        (
            SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_file_attributes=0, st_uid=current_uid),
            "directory",
            "wrong filesystem type",
        ),
    ]
    if hasattr(os, "geteuid"):
        cases.append(
            (
                SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_file_attributes=0, st_uid=current_uid + 1),
                "database file",
                "owned by the current user",
            )
        )
    for metadata, kind, message in cases:
        with pytest.raises(RuntimeError, match=message):
            store_paths_module._require_safe_store_path_metadata(
                metadata,  # type: ignore[arg-type]
                path,
                kind=kind,
            )


def test_local_store_rejects_directory_and_database_identity_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory_path = tmp_path / "directory-race"
    directory_path.mkdir(mode=0o700)
    with monkeypatch.context() as patch:
        patch.setattr(store_paths_module.os.path, "samestat", lambda _left, _right: False)
        with pytest.raises(RuntimeError, match="directory changed while it was opened"):
            LocalControlPlaneStore(directory_path)

    database_path = tmp_path / "database-race"
    database_path.mkdir(mode=0o700)
    (database_path / "control-plane.sqlite3").touch(mode=0o600)
    comparisons = 0

    def change_database_identity(_left: object, _right: object) -> bool:
        nonlocal comparisons
        comparisons += 1
        return comparisons == 1

    with monkeypatch.context() as patch:
        patch.setattr(store_paths_module.os.path, "samestat", change_database_identity)
        with pytest.raises(RuntimeError, match="database file changed while it was secured"):
            LocalControlPlaneStore(database_path)


def test_secure_database_file_handles_missing_path(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "control-plane.sqlite3"
    assert store_paths_module._secure_database_file(database_path, allow_missing=True) is None
    with pytest.raises(RuntimeError, match="database file is missing"):
        store_paths_module._secure_database_file(database_path, allow_missing=False)


@pytest.mark.skipif(os.name == "nt", reason="POSIX path-mode tightening is unavailable")
@pytest.mark.parametrize("failure", [PermissionError("denied"), NotImplementedError("unsupported")])
def test_secure_database_file_maps_path_chmod_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    database_path = tmp_path / "control-plane.sqlite3"
    database_path.touch(mode=0o644)
    monkeypatch.setattr(
        store_paths_module.os,
        "chmod",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(RuntimeError, match="could not secure local control-plane database file"):
        store_paths_module._secure_database_file(database_path, allow_missing=False)


@pytest.mark.skipif(os.name == "nt", reason="POSIX path-mode tightening is unavailable")
def test_secure_database_file_rejects_ineffective_path_chmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "control-plane.sqlite3"
    database_path.touch(mode=0o644)
    monkeypatch.setattr(store_paths_module.os, "chmod", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="must use private permissions 0600"):
        store_paths_module._secure_database_file(database_path, allow_missing=False)


def test_secure_database_file_fails_when_main_database_disappears_during_identity_recheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "control-plane.sqlite3"
    database_path.touch(mode=0o600)
    real_lstat = Path.lstat
    calls = 0

    def disappear_during_identity_recheck(path: Path) -> os.stat_result:
        nonlocal calls
        calls += 1
        if calls == 2:
            path.unlink()
            raise FileNotFoundError(path)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", disappear_during_identity_recheck)
    with pytest.raises(RuntimeError, match="database file disappeared while it was secured"):
        store_paths_module._secure_database_file(database_path, allow_missing=False)


def test_local_store_fails_closed_when_database_disappears(tmp_path: Path) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    store._database_path.unlink()

    with pytest.raises(RuntimeError, match="database file is missing"):
        store.load_snapshot()


def test_runtime_context_manager_closes_control_plane() -> None:
    with RuntimeControlPlane(create_stub_target()) as control_plane:
        assert control_plane.get_snapshot().snapshot == RuntimeSnapshot()

    with pytest.raises(RuntimeError, match="control plane is closed"):
        control_plane.get_snapshot()
    control_plane.close()


def test_close_waits_for_backend_and_keeps_lease_until_terminal_commit(tmp_path: Path) -> None:
    target, provisioning_plan, _ = _target_and_plan()
    provisioner = _BlockingProvisioner(target.provisioner)
    target = replace(target, provisioner=provisioner)
    store_path = tmp_path / "control-plane"
    control_plane = RuntimeControlPlane(target, store=LocalControlPlaneStore(store_path))
    _authorize_provisioning_plan(control_plane, target, provisioning_plan)
    submission_errors: list[BaseException] = []
    close_errors: list[BaseException] = []
    close_completed = [Event(), Event()]

    def submit() -> None:
        try:
            control_plane.submit_provisioning(
                provisioning_plan,
                idempotency_key="blocked-close",
                request_fingerprint="blocked-close-request",
            )
        except BaseException as exc:
            submission_errors.append(exc)

    def close(index: int) -> None:
        try:
            control_plane.close()
        except BaseException as exc:
            close_errors.append(exc)
        finally:
            close_completed[index].set()

    submission = Thread(target=submit)
    closers = [Thread(target=close, args=(index,)) for index in range(2)]
    submission.start()
    try:
        assert provisioner.entered.wait(timeout=2)
        for closer in closers:
            closer.start()
        assert not any(completed.wait(timeout=0.1) for completed in close_completed)
        competing_store = LocalControlPlaneStore(store_path)
        with pytest.raises(RuntimeError, match="exactly one worker"):
            RuntimeControlPlane(target, store=competing_store)
    finally:
        provisioner.release.set()
        submission.join(timeout=5)
        for closer in closers:
            closer.join(timeout=5)

    assert not submission.is_alive()
    assert all(not closer.is_alive() for closer in closers)
    assert submission_errors == []
    assert close_errors == []
    assert all(completed.is_set() for completed in close_completed)
    record = next(iter(LocalControlPlaneStore(store_path).load_records().values()))
    assert record.status.state == OperationState.SUCCEEDED

    restarted = RuntimeControlPlane(target, store=LocalControlPlaneStore(store_path))
    restarted.close()


def test_close_allows_nested_work_from_an_already_admitted_call() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    outer_admitted = Event()
    enter_nested = Event()
    nested_completed = Event()

    def admitted_call() -> None:
        with control_plane._runtime_call():
            outer_admitted.set()
            assert enter_nested.wait(timeout=2)
            with control_plane._runtime_call():
                nested_completed.set()

    worker = Thread(target=admitted_call)
    worker.start()
    assert outer_admitted.wait(timeout=2)
    closer = Thread(target=control_plane.close)
    closer.start()
    deadline = monotonic() + 2
    while not control_plane._closing and monotonic() < deadline:
        sleep(0.001)
    assert control_plane._closing

    enter_nested.set()
    worker.join(timeout=2)
    closer.join(timeout=2)

    assert nested_completed.is_set()
    assert not worker.is_alive()
    assert not closer.is_alive()
    assert control_plane._closed


@pytest.mark.parametrize("transition_kind", ["control", "participant"])
def test_runtime_resynchronizes_after_transition_commit_reports_postcommit_error(
    monkeypatch: pytest.MonkeyPatch,
    transition_kind: str,
) -> None:
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)
    snapshot = RuntimeSnapshot(metadata={"committed": transition_kind})
    record = _terminal_record(_running_record(f"{transition_kind}-postcommit"))
    control_plane._claim_record(_running_record(f"{transition_kind}-postcommit"))
    event = _audit_event(f"{transition_kind}-postcommit")
    method_name = f"commit_{transition_kind}_transition"
    real_commit = getattr(store, method_name)

    def commit_then_error(**kwargs: object) -> None:
        real_commit(**kwargs)
        raise RuntimeError("postcommit transition error")

    monkeypatch.setattr(store, method_name, commit_then_error)

    def commit_transition() -> None:
        if transition_kind == "control":
            control_plane._commit_control_transition(
                participant_address="participant.test",
                expected_head=None,
                snapshot=snapshot,
                record=record,
                audit_event=event,
            )
        else:
            control_plane._commit_participant_transition(
                expected_history_heads={},
                snapshot=snapshot,
                record=record,
                audit_event=event,
            )

    with pytest.raises(RuntimeError, match="postcommit transition error"):
        commit_transition()

    assert control_plane.snapshot == snapshot
    assert control_plane.get_operation(record.receipt.operation_id) == record.status
    control_plane.close()


def test_every_public_runtime_method_and_property_has_lifecycle_admission() -> None:
    for name, method in inspect.getmembers(RuntimeControlPlane, predicate=inspect.isfunction):
        if name.startswith("_") or name == "close":
            continue
        assert getattr(method, "__runtime_owned__", False), name
    for name, value in inspect.getmembers(RuntimeControlPlane, lambda candidate: isinstance(candidate, property)):
        if name.startswith("_"):
            continue
        assert value.fget is not None
        assert getattr(value.fget, "__runtime_owned__", False), name
    assert getattr(RuntimeControlPlane.__enter__, "__runtime_owned__", False)


def test_public_participant_reads_fail_after_runtime_close() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    control_plane.close()

    with pytest.raises(RuntimeError, match="control plane is closed"):
        control_plane._assert_runtime_owner()

    calls = (
        lambda: control_plane.participant_execution_state("participant-execution.missing"),
        lambda: control_plane.get_participant_status_view("participant.behavior.missing"),
        lambda: control_plane.get_participant_history_view("participant.behavior.missing", "episode-missing"),
        lambda: control_plane.get_participant_context_view(
            "participant.behavior.missing",
            view_ref="participant-view.missing",
        ),
    )
    for call in calls:
        with pytest.raises(RuntimeError, match="control plane is closed"):
            call()


def test_close_from_an_active_runtime_call_fails_without_releasing_lease() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    try:
        with control_plane._runtime_call():
            with control_plane._runtime_call():
                pass
            with pytest.raises(RuntimeError, match="from one of its active calls"):
                control_plane.close()
        assert control_plane.get_snapshot().snapshot == RuntimeSnapshot()
    finally:
        control_plane.close()


def test_interrupted_close_reopens_lifecycle_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    condition = control_plane._lifecycle_condition

    with monkeypatch.context() as patch:

        def interrupt_wait(_predicate: object) -> None:
            raise KeyboardInterrupt("injected close interruption")

        patch.setattr(condition, "wait_for", interrupt_wait)
        with pytest.raises(KeyboardInterrupt, match="close interruption"):
            control_plane.close()

    assert control_plane._closing is False
    assert control_plane.get_snapshot().snapshot == RuntimeSnapshot()
    control_plane.close()


def test_partially_initialized_runtime_can_release_lease_without_lifecycle_condition() -> None:
    closed = False

    class _Lease:
        def close(self) -> None:
            nonlocal closed
            closed = True

    control_plane = object.__new__(RuntimeControlPlane)
    control_plane._runtime_lease = _Lease()

    control_plane.close()

    assert closed is True
    assert control_plane._runtime_lease is None


def test_runtime_owner_acquisition_releases_descriptor_after_base_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)

    with monkeypatch.context() as patch:

        def interrupt_lock(_descriptor: int) -> None:
            raise KeyboardInterrupt("injected lock acquisition crash")

        patch.setattr(lease_module, "_lock_runtime_owner", interrupt_lock)
        target = create_stub_target()
        with pytest.raises(KeyboardInterrupt, match="lock acquisition crash"):
            RuntimeControlPlane(target, store=store)

    owner = RuntimeControlPlane(create_stub_target(), store=store)
    owner.close()


@pytest.mark.skipif(os.name == "nt", reason="directory flock guard is POSIX-specific")
def test_runtime_owner_directory_guard_maps_secure_open_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "runtime-owner.lock"

    def deny_directory_open(*_args: Any, **_kwargs: Any) -> int:
        raise PermissionError("injected directory-open denial")

    monkeypatch.setattr(lease_module.os, "open", deny_directory_open)

    with pytest.raises(RuntimeError, match="could not securely open runtime-owner store directory"):
        lease_module._acquire_store_directory_guard(lock_path)


@pytest.mark.skipif(os.name == "nt", reason="directory flock guard is POSIX-specific")
def test_runtime_owner_directory_guard_rejects_non_directory_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "runtime-owner.lock"
    opened_descriptors: list[int] = []
    real_open = lease_module.os.open
    real_fstat = lease_module.os.fstat

    def observe_open(*args: Any, **kwargs: Any) -> int:
        descriptor = real_open(*args, **kwargs)
        opened_descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(lease_module.os, "open", observe_open)
    monkeypatch.setattr(
        lease_module.os,
        "fstat",
        lambda _descriptor: SimpleNamespace(st_mode=stat.S_IFREG | 0o600),
    )

    with pytest.raises(RuntimeError, match="store path must be a directory"):
        lease_module._acquire_store_directory_guard(lock_path)

    assert len(opened_descriptors) == 1
    with pytest.raises(OSError) as closed:
        real_fstat(opened_descriptors[0])
    assert closed.value.errno == errno.EBADF


@pytest.mark.skipif(os.name == "nt", reason="directory flock guard is POSIX-specific")
def test_runtime_owner_file_lock_failure_releases_directory_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "runtime-owner.lock"
    real_lock = lease_module._lock_runtime_owner
    lock_calls = 0

    def fail_file_lock(descriptor: int) -> None:
        nonlocal lock_calls
        lock_calls += 1
        if lock_calls == 2:
            raise BlockingIOError("injected file-lock contention")
        real_lock(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(lease_module, "_lock_runtime_owner", fail_file_lock)
        with pytest.raises(RuntimeError, match="exactly one worker"):
            lease_module.RuntimeOwnerLease.acquire(lock_path)

    lease = lease_module.RuntimeOwnerLease.acquire(lock_path)
    lease.close()


def test_closed_runtime_owner_lease_fails_closed_and_close_is_idempotent(tmp_path: Path) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    lease = store.acquire_runtime_lease()
    lease.close()
    lease.close()

    with pytest.raises(RuntimeError, match="lease is closed"):
        lease.assert_owner()


def test_windows_runtime_owner_lock_protocol_is_directly_testable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locking_calls: list[tuple[int, int, int]] = []
    fake_msvcrt = SimpleNamespace(
        LK_NBLCK=1,
        LK_UNLCK=2,
        locking=lambda descriptor, operation, size: locking_calls.append((descriptor, operation, size)),
    )
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(lease_module, "_is_windows", lambda: True)

    lease = lease_module.RuntimeOwnerLease.acquire(tmp_path / "runtime-owner.lock")
    descriptor = lease._descriptor
    lease.assert_owner()
    lease_module._lock_runtime_owner(descriptor)
    lease.close()

    assert [operation for _descriptor, operation, _size in locking_calls] == [1, 1, 2]
    assert all(size == 1 for _descriptor, _operation, size in locking_calls)


def test_runtime_owner_lease_rejects_and_closes_in_a_different_process_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "runtime-owner.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    descriptor_only_lease = lease_module.RuntimeOwnerLease(descriptor)
    descriptor_only_lease.assert_owner()
    descriptor_only_lease.close()

    lease = lease_module.RuntimeOwnerLease.acquire(lock_path)
    with monkeypatch.context() as patch:
        patch.setattr(lease_module.os, "getpid", lambda: lease._owner_pid + 1)
        with pytest.raises(RuntimeError, match="cannot be used after fork"):
            lease.assert_owner()
        lease.close()
    assert lease.closed is True

    reacquired = lease_module.RuntimeOwnerLease.acquire(lock_path)
    reacquired.close()


def test_local_store_runtime_lease_blocks_another_process(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    owner = RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(store_path))
    context = get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=_runtime_owner_result, args=(str(store_path), queue))
    process.start()
    process.join(timeout=15)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
    try:
        assert process.exitcode == 0
        assert "exactly one worker" in queue.get(timeout=2)
    finally:
        owner.close()


def test_runtime_owner_directory_guard_survives_lock_path_replacement(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("directory flock guard is POSIX-specific")
    store_path = tmp_path / "control-plane"
    target = create_stub_target()
    owner = RuntimeControlPlane(target, store=LocalControlPlaneStore(store_path))
    lock_path = store_path / "runtime-owner.lock"
    lock_path.unlink()
    competing_store = LocalControlPlaneStore(store_path)

    with pytest.raises(RuntimeError, match="exactly one worker"):
        RuntimeControlPlane(target, store=competing_store)
    with pytest.raises(RuntimeError, match="lock path changed while the lease was active"):
        owner.get_snapshot()

    owner.close()
    restarted = RuntimeControlPlane(target, store=LocalControlPlaneStore(store_path))
    restarted.close()


@pytest.mark.skipif("fork" not in get_all_start_methods(), reason="fork is unavailable")
def test_inherited_runtime_owner_fails_closed_after_fork(tmp_path: Path) -> None:
    owner = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(tmp_path / "control-plane"),
    )
    context = get_context("fork")
    queue = context.Queue()
    process = context.Process(target=_inherited_runtime_result, args=(owner, queue))
    process.start()
    process.join(timeout=10)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
    try:
        assert process.exitcode == 0
        assert "cannot be used after fork" in queue.get(timeout=2)
        assert owner.get_snapshot().snapshot == RuntimeSnapshot()
    finally:
        owner.close()


@pytest.mark.parametrize("store_type", [_LegacyControlPlaneStore, _PartiallyAtomicControlPlaneStore])
def test_runtime_preserves_ordered_legacy_store_commits_with_deprecation(
    store_type: type[_LegacyControlPlaneStore],
) -> None:
    target, provisioning_plan, _ = _target_and_plan()
    store = store_type()

    with pytest.warns(LegacyControlPlaneStoreWarning, match="before version 4"):
        control_plane = RuntimeControlPlane(target, store=store)  # type: ignore[arg-type]
    _authorize_provisioning_plan(control_plane, target, provisioning_plan)
    receipt = control_plane.submit_provisioning(
        provisioning_plan,
        idempotency_key="legacy-compatible",
        request_fingerprint="legacy-compatible-request",
    )

    assert store.write_calls == ["save_record", "save_snapshot", "save_record"]
    assert store.delegate.load_snapshot() == control_plane.snapshot
    assert store.delegate.load_records()[receipt.operation_id].status.state == OperationState.SUCCEEDED

    replay = control_plane.submit_provisioning(
        provisioning_plan,
        idempotency_key="legacy-compatible",
        request_fingerprint="legacy-compatible-request",
    )
    assert replay == receipt
    assert store.write_calls == ["save_record", "save_snapshot", "save_record"]
    representation_retry = control_plane.submit_provisioning(
        provisioning_plan,
        idempotency_key="legacy-compatible",
        request_fingerprint="different-transport-representation",
    )
    assert representation_retry == receipt
    assert store.write_calls == ["save_record", "save_snapshot", "save_record"]
    control_plane.close()


def test_public_store_protocol_keeps_atomic_capabilities_optional() -> None:
    assert not callable(getattr(ControlPlaneStore, "claim_record", None))
    assert callable(getattr(AtomicControlPlaneStore, "claim_record", None))


def test_legacy_store_claim_fallback_returns_existing_idempotency_record() -> None:
    store = _LegacyControlPlaneStore()
    existing = replace(
        _running_record("legacy-existing-claim"),
        idempotency_key="legacy-shared-claim",
    )
    competing = replace(
        _running_record("legacy-competing-claim"),
        idempotency_key="legacy-shared-claim",
    )
    store.delegate.save_record(existing)

    with pytest.warns(LegacyControlPlaneStoreWarning, match="implement all atomic methods"):
        adapter = adapt_control_plane_store(store)

    assert adapter.claim_record(competing) == existing
    assert store.write_calls == []


def test_runtime_legacy_store_recovers_interrupted_records_one_at_a_time() -> None:
    store = _LegacyControlPlaneStore()
    target = create_stub_target()
    first = _running_record("legacy-recovery-first")
    second = _running_record("legacy-recovery-second")
    store.delegate.save_record(first)
    store.delegate.save_record(second)

    with pytest.warns(LegacyControlPlaneStoreWarning, match="non-crash-atomic 3.x"):
        control_plane = RuntimeControlPlane(target, store=store)  # type: ignore[arg-type]

    assert store.write_calls == ["save_record", "save_record"]
    for operation_id in (first.receipt.operation_id, second.receipt.operation_id):
        recovered = control_plane.get_operation(operation_id)
        assert recovered is not None
        assert recovered.state == OperationState.INDETERMINATE
        assert any(diagnostic.code == INTERRUPTED_OPERATION_DIAGNOSTIC_CODE for diagnostic in recovered.diagnostics)
    control_plane.close()


def test_runtime_legacy_store_preserves_snapshot_first_failure_window() -> None:
    target, provisioning_plan, _ = _target_and_plan()
    store = _LegacyControlPlaneStore()
    with pytest.warns(LegacyControlPlaneStoreWarning):
        control_plane = RuntimeControlPlane(target, store=store)  # type: ignore[arg-type]
    _authorize_provisioning_plan(control_plane, target, provisioning_plan)
    store.fail_terminal_record = True

    with pytest.raises(RuntimeError, match="legacy terminal-record failure"):
        control_plane.submit_provisioning(provisioning_plan)

    assert store.write_calls == ["save_record", "save_snapshot", "save_record", "save_record"]
    assert store.delegate.load_snapshot().entries
    assert next(iter(store.delegate.load_records().values())).status.state == OperationState.RUNNING
    with pytest.raises(RuntimeError, match="requires restart"):
        control_plane.get_snapshot()
    control_plane.close()


def test_runtime_legacy_store_resynchronizes_after_snapshot_write_failure() -> None:
    target, provisioning_plan, _ = _target_and_plan()
    store = _LegacyControlPlaneStore()
    with pytest.warns(LegacyControlPlaneStoreWarning):
        control_plane = RuntimeControlPlane(target, store=store)  # type: ignore[arg-type]
    _authorize_provisioning_plan(control_plane, target, provisioning_plan)
    store.fail_snapshot = True

    with pytest.raises(RuntimeError, match="legacy snapshot failure"):
        control_plane.submit_provisioning(provisioning_plan)

    assert store.write_calls == ["save_record", "save_snapshot", "save_record"]
    assert control_plane.snapshot == RuntimeSnapshot()
    assert store.delegate.load_snapshot() == control_plane.snapshot
    assert next(iter(store.delegate.load_records().values())).status.state == OperationState.INDETERMINATE
    control_plane.close()


def test_runtime_rejects_store_without_the_legacy_contract() -> None:
    target = create_stub_target()
    missing_store = object()
    with pytest.raises(TypeError, match="missing required capabilities"):
        RuntimeControlPlane(target, store=missing_store)  # type: ignore[arg-type]


def test_runtime_requires_policy_resolver_for_persisted_crossing_history() -> None:
    store = InMemoryControlPlaneStore(RuntimeSnapshot(participant_crossing_history={"participant.demo": [{}]}))
    target = create_stub_target()

    with pytest.raises(ValueError, match="persisted participant crossing history requires a policy resolver"):
        RuntimeControlPlane(target, store=store)


def test_execution_helpers_return_the_durable_winner_when_an_idempotency_claim_loses() -> None:
    @dataclass(frozen=True)
    class _ParticipantRequest:
        participant_address: str

    class _LosingClaimControlPlane:
        def __init__(self) -> None:
            self._snapshot = RuntimeSnapshot()
            self._operation_lock = RLock()
            self._target = create_stub_target()

        @staticmethod
        def _idempotent_receipt(**_kwargs: object) -> None:
            return None

        @staticmethod
        def _claim_record(record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
            winning_receipt = replace(record.receipt, operation_id="durable-winner")
            winning_status = replace(record.status, operation_id="durable-winner")
            return replace(record, receipt=winning_receipt, status=winning_status)

        @staticmethod
        def _commit_terminal_operation(*_args: object) -> None:
            raise AssertionError("a losing claimant must not call the backend or commit")

    control_plane = _LosingClaimControlPlane()

    def unexpected_backend(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("a losing claimant must not call the backend")

    participant_receipt = execute_participant_action(
        control_plane,
        method=unexpected_backend,
        request=_ParticipantRequest(participant_address="participant.demo"),
        address="participant.demo",
        idempotency_key="participant-key",
        request_fingerprint="participant-fingerprint",
    )
    persisted_receipt = persist_succeeded_operation(
        control_plane,
        SucceededOperationRequest(
            operation_id="local-persist",
            domain=RuntimeDomain.EVALUATION,
            submitted_at="2026-08-12T00:00:00Z",
            idempotency_key="persist-key",
            context=OperationAdmissionContext(
                actor_id="embedded-process",
                authorization_scope=("process:trusted-embedder",),
                target_scope="target:stub",
                run_scope="run:test",
                operation_kind=OperationKind.EVALUATION,
                request_commitment=f"sha256:{'b' * 64}",
            ),
        ),
    )
    operation_receipt = execute_operation(
        control_plane,
        OperationExecutionRequest(
            domain=RuntimeDomain.EVALUATION,
            method=unexpected_backend,
            plan=object(),
            address="evaluation.demo",
            diagnostics=[],
            base_snapshot=None,
            idempotency_key="operation-key",
            request_fingerprint="operation-fingerprint",
            context=OperationAdmissionContext(
                actor_id="embedded-process",
                authorization_scope=("process:trusted-embedder",),
                target_scope="target:stub",
                run_scope="run:test",
                operation_kind=OperationKind.EVALUATION,
                request_commitment=f"sha256:{'c' * 64}",
            ),
        ),
    )

    assert participant_receipt.operation_id == "durable-winner"
    assert persisted_receipt.operation_id == "durable-winner"
    assert operation_receipt.operation_id == "durable-winner"


def test_persist_succeeded_operation_returns_newly_claimed_receipt() -> None:
    class _WinningClaimControlPlane:
        def __init__(self) -> None:
            self._snapshot = RuntimeSnapshot()

        @staticmethod
        def _claim_record(record: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
            return record

        @staticmethod
        def _commit_terminal_operation(*_args: object) -> None:
            return None

    receipt = persist_succeeded_operation(
        _WinningClaimControlPlane(),
        SucceededOperationRequest(
            operation_id="newly-claimed",
            domain=RuntimeDomain.EVALUATION,
            submitted_at="2026-08-12T00:00:00Z",
            idempotency_key="new-key",
            context=OperationAdmissionContext(
                actor_id="embedded-process",
                authorization_scope=("process:trusted-embedder",),
                target_scope="target:stub",
                run_scope="run:test",
                operation_kind=OperationKind.EVALUATION,
                request_commitment=f"sha256:{'d' * 64}",
            ),
        ),
    )

    assert receipt.operation_id == "newly-claimed"


def test_runtime_rejects_losing_claim_with_different_request_fingerprint() -> None:
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)
    existing = replace(_running_record("fingerprint-winner"), idempotency_key="shared-fingerprint")
    store.claim_record(existing)
    competing = replace(
        _running_record("fingerprint-loser"),
        idempotency_key="shared-fingerprint",
        request_fingerprint="different-fingerprint",
    )

    with pytest.raises(ValueError, match="reused with a different request body"):
        control_plane._claim_record(competing)
    control_plane.close()


def test_runtime_owner_lock_has_private_permissions(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX mode bits are unavailable")
    store_path = tmp_path / "control-plane"
    owner = RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(store_path))
    try:
        assert (store_path / "runtime-owner.lock").stat().st_mode & 0o777 == 0o600
    finally:
        owner.close()


def test_runtime_owner_lock_rejects_symlink_without_opening_or_changing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("must remain unchanged", encoding="utf-8")
    lock_path = store_path / "runtime-owner.lock"
    try:
        lock_path.symlink_to(victim)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    real_open = lease_module.os.open
    opened_lock = False

    def track_open(path: object, *args: object, **kwargs: object) -> int:
        nonlocal opened_lock
        if os.fspath(path) == os.fspath(lock_path):
            opened_lock = True
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(lease_module.os, "open", track_open)
    target = create_stub_target()
    with pytest.raises(RuntimeError, match="must not be a symlink or reparse point"):
        RuntimeControlPlane(target, store=store)

    assert opened_lock is False
    assert victim.read_text(encoding="utf-8") == "must remain unchanged"


def test_runtime_owner_lock_rejects_hard_link_alias(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    lock_path = store_path / "runtime-owner.lock"
    lock_path.touch(mode=0o600)
    try:
        os.link(lock_path, tmp_path / "runtime-owner-alias.lock")
    except OSError:
        pytest.skip("hard links are unavailable")
    target = create_stub_target()

    with pytest.raises(RuntimeError, match="lock path must not have hard links"):
        RuntimeControlPlane(target, store=store)


def test_runtime_owner_lock_rejects_post_open_identity_change_before_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    lock_path = store_path / "runtime-owner.lock"
    lock_path.write_text("sentinel", encoding="ascii")
    lock_path.chmod(0o600)
    monkeypatch.setattr(lease_module.os.path, "samestat", lambda _left, _right: False)
    target = create_stub_target()

    with pytest.raises(RuntimeError, match="changed while it was opened"):
        RuntimeControlPlane(target, store=store)

    assert lock_path.read_text(encoding="ascii") == "sentinel"


def test_runtime_owner_metadata_rejects_windows_reparse_attribute(tmp_path: Path) -> None:
    metadata = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o600,
        st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
        st_uid=getattr(os, "geteuid", lambda: 0)(),
    )

    with pytest.raises(RuntimeError, match="symlink or reparse point"):
        lease_module._require_safe_runtime_owner_metadata(
            metadata,  # type: ignore[arg-type]
            tmp_path / "runtime-owner.lock",
        )


def test_runtime_owner_metadata_rejects_nonregular_file(tmp_path: Path) -> None:
    metadata = SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o700,
        st_file_attributes=0,
        st_uid=getattr(os, "geteuid", lambda: 0)(),
    )

    with pytest.raises(RuntimeError, match="must be a regular file"):
        lease_module._require_safe_runtime_owner_metadata(
            metadata,  # type: ignore[arg-type]
            tmp_path / "runtime-owner.lock",
        )


@pytest.mark.skipif(not hasattr(os, "geteuid"), reason="effective UID is unavailable")
def test_runtime_owner_metadata_rejects_foreign_owner(tmp_path: Path) -> None:
    metadata = SimpleNamespace(
        st_mode=stat.S_IFREG | 0o600,
        st_file_attributes=0,
        st_uid=os.geteuid() + 1,
    )

    with pytest.raises(RuntimeError, match="owned by the current user"):
        lease_module._require_safe_runtime_owner_metadata(
            metadata,  # type: ignore[arg-type]
            tmp_path / "runtime-owner.lock",
        )


def test_runtime_owner_secure_open_failure_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_path = tmp_path / "control-plane"
    store = LocalControlPlaneStore(store_path)
    lock_path = store_path / "runtime-owner.lock"
    real_open = lease_module.os.open

    def deny_lock_open(path: object, *args: object, **kwargs: object) -> int:
        if os.fspath(path) == os.fspath(lock_path):
            raise PermissionError("injected secure-open denial")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(lease_module.os, "open", deny_lock_open)
    target = create_stub_target()
    with pytest.raises(RuntimeError, match="could not securely open runtime-owner lock path"):
        RuntimeControlPlane(target, store=store)
