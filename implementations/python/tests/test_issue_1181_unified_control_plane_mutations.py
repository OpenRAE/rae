"""CP-2 acceptance tests for unified runtime-control-plane mutations."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from types import SimpleNamespace

import pytest
from participant_crossing_fixtures import (
    PARTICIPANT,
    admission_request,
    behavior,
    evidence,
    identity,
)
from pydantic import ValidationError
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.contracts.participant_execution import ParticipantExecutionControlRequestModel
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan, RuntimeDomain
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
from raes_runtime.control_plane_api import _offload as control_plane_offload
from raes_runtime.control_plane_api._offload import _ControlPlaneCallExecutor
from raes_runtime.control_plane_mutation import (
    MutationReservationRequired,
    RuntimeMutationAuthority,
    mutation_entry,
    mutation_probe,
)
from raes_runtime.control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    InMemoryControlPlaneStore,
    TerminalCommitMode,
)
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_records import _audit_event_from_payload
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_crossing_egress import ParticipantViewSerialization, serialize_participant_view


def _context() -> OperationAdmissionContext:
    return OperationAdmissionContext(
        actor_id="operator-1181",
        authorization_scope=("role:operator",),
        target_scope="target:stub",
        run_scope="run:issue-1181",
        operation_kind=OperationKind.PROVISIONING,
        request_commitment=f"sha256:{'a' * 64}",
    )


def _running_record(operation_id: str = "operation-1181") -> ControlPlaneOperationRecord:
    context = _context()
    submitted_at = "2026-09-11T04:30:00Z"
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
            state=OperationState.RUNNING,
            submitted_at=submitted_at,
            updated_at=submitted_at,
            context=context,
        ),
        request_fingerprint=context.request_commitment,
        idempotency_key=f"key-{operation_id}",
    )


def _terminal_record(running: ControlPlaneOperationRecord) -> ControlPlaneOperationRecord:
    return replace(
        running,
        status=replace(
            running.status,
            state=OperationState.SUCCEEDED,
            updated_at="2026-09-11T04:30:01Z",
        ),
    )


def _terminal_audit(record: ControlPlaneOperationRecord) -> AuditEvent:
    return AuditEvent(
        timestamp=record.status.updated_at,
        action="provisioning_terminal",
        identity=record.status.context.actor_id,
        allowed=True,
        target=record.status.context.target_scope,
        operation_id=record.receipt.operation_id,
        reason="operation-succeeded",
        details={"state": "succeeded"},
    )


def _lock_is_available_from_another_thread(lock: object) -> bool:
    available: list[bool] = []

    def probe() -> None:
        acquired = lock.acquire(timeout=0.25)  # type: ignore[attr-defined]
        available.append(acquired)
        if acquired:
            lock.release()  # type: ignore[attr-defined]

    thread = Thread(target=probe)
    thread.start()
    thread.join(timeout=1)
    return available == [True]


class _ClaimObservingProvisioner:
    def __init__(self) -> None:
        self.delegate = StubProvisioner()
        self.control_plane: RuntimeControlPlane | None = None
        self.store: InMemoryControlPlaneStore | None = None
        self.phases: list[str] = []

    def _observe_claim(self, phase: str) -> None:
        assert self.control_plane is not None
        assert self.store is not None
        records = self.store.load_records()
        assert len(records) == 1
        assert next(iter(records.values())).status.state is OperationState.RUNNING
        assert _lock_is_available_from_another_thread(self.control_plane._operation_lock)
        with pytest.raises(RuntimeError, match="backend callback cannot start a control-plane mutation"):
            self.control_plane.reconcile_workflow_timeouts(now="2026-09-11T04:30:00Z")
        self.phases.append(phase)

    def validate(self, plan: ProvisioningPlan) -> list[object]:
        self._observe_claim("validate")
        return self.delegate.validate(plan)

    def apply(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> object:
        self._observe_claim("apply")
        return self.delegate.apply(plan, snapshot)


def test_running_claim_precedes_backend_validation_and_apply_without_application_mutex() -> None:
    provisioner = _ClaimObservingProvisioner()
    target = replace(create_stub_target(), provisioner=provisioner)
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(target, store=store)
    provisioner.control_plane = control_plane
    provisioner.store = store

    receipt = control_plane.submit_provisioning(ProvisioningPlan())

    assert provisioner.phases == ["validate", "apply"]
    record = store.load_records()[receipt.operation_id]
    assert record.status.state is OperationState.SUCCEEDED
    assert store.read_audit() == [
        AuditEvent(
            timestamp=record.status.updated_at,
            action="provisioning_terminal",
            identity=record.status.context.actor_id,
            allowed=True,
            target=record.status.context.target_scope,
            operation_id=record.receipt.operation_id,
            reason="operation-succeeded",
            details={"state": "succeeded"},
        )
    ]


class _RejectingValidationProvisioner:
    def __init__(self, store: InMemoryControlPlaneStore) -> None:
        self.store = store
        self.apply_count = 0

    def validate(self, _plan: ProvisioningPlan) -> list[Diagnostic]:
        assert next(iter(self.store.load_records().values())).status.state is OperationState.RUNNING
        return [
            Diagnostic(
                code="runtime.test-validation-failed",
                domain="runtime",
                address="/plan",
                message="The test plan is invalid.",
            )
        ]

    def apply(self, _plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> object:
        self.apply_count += 1
        return StubProvisioner().apply(_plan, snapshot)


def test_backend_validation_error_terminalizes_claim_without_invoking_apply() -> None:
    store = InMemoryControlPlaneStore()
    provisioner = _RejectingValidationProvisioner(store)
    control_plane = RuntimeControlPlane(replace(create_stub_target(), provisioner=provisioner), store=store)

    receipt = control_plane.submit_provisioning(ProvisioningPlan())

    record = store.load_records()[receipt.operation_id]
    assert record.status.state is OperationState.FAILED
    assert [diagnostic.code for diagnostic in record.status.diagnostics] == [
        "runtime.test-validation-failed",
        "runtime.control-plane.operation-failed",
    ]
    assert provisioner.apply_count == 0
    assert store.load_snapshot_state().revision == 0
    assert len(store.read_audit()) == 1


class _BlockingProvisioner:
    def __init__(self) -> None:
        self.delegate = StubProvisioner()
        self.entered = Event()
        self.release = Event()

    def validate(self, plan: ProvisioningPlan) -> list[object]:
        return self.delegate.validate(plan)

    def apply(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> object:
        self.entered.set()
        assert self.release.wait(timeout=5)
        return self.delegate.apply(plan, snapshot)


def test_one_mutation_authority_serializes_families_while_reads_remain_responsive() -> None:
    provisioner = _BlockingProvisioner()
    control_plane = RuntimeControlPlane(replace(create_stub_target(), provisioner=provisioner))
    completed = Event()
    failures: list[BaseException] = []

    def provision() -> None:
        try:
            control_plane.submit_provisioning(ProvisioningPlan())
        except BaseException as exc:  # pragma: no cover - assertion reports the exception
            failures.append(exc)

    def reconcile() -> None:
        try:
            control_plane.reconcile_workflow_timeouts(now="2026-09-11T04:30:00Z")
            completed.set()
        except BaseException as exc:  # pragma: no cover - assertion reports the exception
            failures.append(exc)

    first = Thread(target=provision)
    second = Thread(target=reconcile)
    first.start()
    assert provisioner.entered.wait(timeout=2)
    second.start()
    assert not completed.wait(timeout=0.15)

    started = monotonic()
    assert control_plane.get_snapshot().snapshot == RuntimeSnapshot()
    assert monotonic() - started < 0.5

    provisioner.release.set()
    first.join(timeout=5)
    second.join(timeout=5)
    assert not first.is_alive()
    assert not second.is_alive()
    assert completed.is_set()
    assert failures == []


def test_admission_denial_does_not_wait_for_an_active_backend_mutation() -> None:
    provisioner = _BlockingProvisioner()
    original = create_stub_target()
    manifest = replace(
        original.manifest,
        capabilities=replace(original.manifest.capabilities, orchestrator=None),
    )
    target = replace(original, manifest=manifest, provisioner=provisioner, orchestrator=None)
    control_plane = RuntimeControlPlane(target)
    failure: list[BaseException] = []

    def provision() -> None:
        try:
            control_plane.submit_provisioning(ProvisioningPlan())
        except BaseException as exc:  # pragma: no cover - assertion reports the exception
            failure.append(exc)

    thread = Thread(target=provision)
    thread.start()
    assert provisioner.entered.wait(timeout=2)
    try:
        started = monotonic()
        denied = control_plane.submit_orchestration(OrchestrationPlan())
        assert monotonic() - started < 0.5
        assert not denied.accepted
    finally:
        provisioner.release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert failure == []


def test_mutating_projection_releases_cache_lock_during_extension_work() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    observed: list[bool] = []

    projected, revision = control_plane._project_snapshot_read(
        lambda: observed.append(_lock_is_available_from_another_thread(control_plane._operation_lock)),
        mutation_kind=OperationKind.PARTICIPANT_CROSSING,
    )

    assert projected is None
    assert revision == 0
    assert observed == [True]


def test_http_mutation_waits_for_core_authority_without_occupying_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = RuntimeMutationAuthority()
    holder_entered = Event()
    release_holder = Event()

    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def mutate(label: str) -> str:
        with authority.mutation(OperationKind.PARTICIPANT_ACTION):
            if label == "holder":
                holder_entered.set()
                assert release_holder.wait(timeout=5)
            return label

    worker = asyncio.Semaphore(1)

    async def run_in_one_worker(call: object, *args: object, **kwargs: object) -> object:
        async with worker:
            return await asyncio.to_thread(call, *args, **kwargs)  # type: ignore[operator]

    monkeypatch.setattr(control_plane_offload, "run_in_threadpool", run_in_one_worker)
    executor = _ControlPlaneCallExecutor(max_pending_mutations=2)
    holder = Thread(target=mutate, args=("holder",))
    holder.start()
    assert holder_entered.wait(timeout=2)

    async def exercise() -> None:
        queued = asyncio.create_task(executor.mutate(mutate, "queued"))
        try:
            await asyncio.sleep(0.05)
            assert not queued.done()
            assert await asyncio.wait_for(executor.run(lambda: "responsive"), timeout=0.5) == "responsive"
        finally:
            release_holder.set()
        assert await asyncio.wait_for(queued, timeout=2) == "queued"

    asyncio.run(exercise())
    holder.join(timeout=5)
    assert not holder.is_alive()


def test_cancelled_http_mutation_retains_reservation_until_worker_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = RuntimeMutationAuthority()
    cancelled_entered = Event()
    release_cancelled = Event()
    follower_entered = Event()

    @mutation_entry(OperationKind.PARTICIPANT_ACTION)
    def mutate(label: str) -> str:
        with authority.mutation(OperationKind.PARTICIPANT_ACTION):
            if label == "cancelled":
                cancelled_entered.set()
                assert release_cancelled.wait(timeout=5)
            else:
                follower_entered.set()
            return label

    async def run_in_thread(call: object, *args: object, **kwargs: object) -> object:
        return await asyncio.to_thread(call, *args, **kwargs)  # type: ignore[operator]

    monkeypatch.setattr(control_plane_offload, "run_in_threadpool", run_in_thread)
    executor = _ControlPlaneCallExecutor(max_pending_mutations=2)

    async def exercise() -> None:
        cancelled = asyncio.create_task(executor.mutate(mutate, "cancelled"))
        assert await asyncio.to_thread(cancelled_entered.wait, 2)
        cancelled.cancel()
        follower = asyncio.create_task(executor.mutate(mutate, "follower"))
        await asyncio.sleep(0.05)
        assert not follower_entered.is_set()
        release_cancelled.set()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        assert await asyncio.wait_for(follower, timeout=2) == "follower"

    asyncio.run(exercise())


@pytest.fixture(params=("memory", "local"))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> InMemoryControlPlaneStore | LocalControlPlaneStore:
    if request.param == "memory":
        return InMemoryControlPlaneStore()
    return LocalControlPlaneStore(tmp_path / "control-plane")


@pytest.mark.parametrize(
    ("mode", "expected_revision"),
    ((TerminalCommitMode.SNAPSHOT_BEARING, 1), (TerminalCommitMode.OPERATION_ONLY, 0)),
)
def test_terminal_commit_atomically_publishes_exact_audit_and_explicit_revision_mode(
    store: InMemoryControlPlaneStore | LocalControlPlaneStore,
    mode: TerminalCommitMode,
    expected_revision: int,
) -> None:
    running = _running_record(f"operation-{mode.value}")
    terminal = _terminal_record(running)
    audit = _terminal_audit(terminal)
    store.claim_record(running)

    committed = store.commit_terminal_operation(
        RuntimeSnapshot(metadata={"candidate": mode.value})
        if mode is TerminalCommitMode.SNAPSHOT_BEARING
        else RuntimeSnapshot(),
        terminal,
        audit_event=audit,
        mode=mode,
        expected_revision=0,
    )
    retried = store.commit_terminal_operation(
        committed.snapshot,
        terminal,
        audit_event=audit,
        mode=mode,
        expected_revision=0,
    )

    assert committed.revision == expected_revision
    assert retried == committed
    assert store.load_records()[running.receipt.operation_id] == terminal
    assert store.read_audit() == [audit]


def test_terminal_retry_rejects_a_different_commit_mode(
    store: InMemoryControlPlaneStore | LocalControlPlaneStore,
) -> None:
    running = _running_record("operation-mode-retry")
    terminal = _terminal_record(running)
    audit = _terminal_audit(terminal)
    store.claim_record(running)
    committed = store.commit_terminal_operation(
        RuntimeSnapshot(metadata={"cut": "advanced"}),
        terminal,
        audit_event=audit,
        mode=TerminalCommitMode.SNAPSHOT_BEARING,
        expected_revision=0,
    )

    with pytest.raises(ValueError, match="commit mode"):
        store.commit_terminal_operation(
            committed.snapshot,
            terminal,
            audit_event=audit,
            mode=TerminalCommitMode.OPERATION_ONLY,
            expected_revision=0,
        )


def test_participant_terminal_commit_rejects_audit_actor_or_operation_mismatch(
    store: InMemoryControlPlaneStore | LocalControlPlaneStore,
) -> None:
    running = _running_record("participant-audit-binding")
    terminal = _terminal_record(running)
    store.claim_record(running)
    mismatched = replace(
        _terminal_audit(terminal),
        identity="different-actor",
        operation_id="different-operation",
    )
    candidate = RuntimeSnapshot(metadata={"candidate": "rejected"})

    with pytest.raises(ValueError, match="actor-bound"):
        store.commit_participant_transition(
            expected_history_heads={},
            expected_revision=0,
            snapshot=candidate,
            record=terminal,
            audit_event=mismatched,
        )

    assert store.load_snapshot_state().revision == 0
    assert store.load_records()[running.receipt.operation_id] == running
    assert store.read_audit() == []


@pytest.mark.parametrize("transition", ("participant", "control"))
def test_participant_terminal_commit_exact_retry_is_a_noop(
    store: InMemoryControlPlaneStore | LocalControlPlaneStore,
    transition: str,
) -> None:
    running = _running_record(f"{transition}-exact-retry")
    terminal = _terminal_record(running)
    audit = _terminal_audit(terminal)
    snapshot = RuntimeSnapshot(metadata={"cut": transition})
    store.claim_record(running)
    options: dict[str, object] = (
        {"expected_history_heads": {}}
        if transition == "participant"
        else {"participant_address": "participant.alpha", "expected_head": None}
    )
    commit = getattr(store, f"commit_{transition}_transition")

    committed = commit(
        **options,
        expected_revision=0,
        snapshot=snapshot,
        record=terminal,
        audit_event=audit,
    )
    retried = commit(
        **options,
        expected_revision=0,
        snapshot=snapshot,
        record=terminal,
        audit_event=audit,
    )

    assert retried == committed
    assert committed.revision == 1
    assert store.read_audit() == [audit]


@pytest.mark.parametrize(
    "mutation",
    (
        lambda payload: payload.pop("identity"),
        lambda payload: payload.__setitem__("unknown", "value"),
        lambda payload: payload.__setitem__("allowed", "false"),
        lambda payload: payload.__setitem__("timestamp", 1),
        lambda payload: payload.__setitem__("details", []),
    ),
)
def test_persisted_audit_codec_rejects_missing_unknown_and_coerced_fields(mutation: object) -> None:
    payload = {
        "timestamp": "2026-09-11T04:30:01Z",
        "action": "provisioning_terminal",
        "identity": "operator-1181",
        "allowed": True,
        "target": "target:stub",
        "operation_id": "operation-1181",
        "reason": "operation-succeeded",
        "details": {"state": "succeeded"},
    }
    mutation(payload)  # type: ignore[operator]

    with pytest.raises(ValidationError):
        _audit_event_from_payload(payload)


def test_runtime_rejects_store_without_complete_atomic_mutation_capability() -> None:
    class LegacyStore:
        def __init__(self) -> None:
            self.delegate = InMemoryControlPlaneStore()

        def __getattr__(self, name: str) -> object:
            if name in {"claim_record", "commit_terminal_operation"}:
                raise AttributeError(name)
            return getattr(self.delegate, name)

    target = create_stub_target()
    legacy_store = LegacyStore()
    with pytest.raises(TypeError, match="atomic mutation capabilities"):
        RuntimeControlPlane(target, store=legacy_store)  # type: ignore[arg-type]


def test_restart_preserves_running_claim_for_governed_recovery() -> None:
    store = InMemoryControlPlaneStore()
    running = _running_record("interrupted-operation")
    store.claim_record(running)

    control_plane = RuntimeControlPlane(create_stub_target(), store=store)

    assert store.load_records()[running.receipt.operation_id] == running
    assert control_plane.get_operation(running.receipt.operation_id) == running.status
    assert store.read_audit() == []
    assert not hasattr(store, "reconcile_interrupted_records")


def test_mutating_control_plane_entries_declare_their_operation_kind() -> None:
    expected = {
        "admit_participant_action",
        "admit_participant_decision_surface_selection",
        "admit_participant_decision_surface_selection_v2",
        "cancel_workflow",
        "control_participant_execution",
        "initialize_participant_episode",
        "reconcile_workflow_timeouts",
        "record_participant_control",
        "reset_participant_episode",
        "restart_participant_episode",
        "submit_evaluation",
        "submit_orchestration",
        "submit_provisioning",
        "terminate_participant_episode",
    }

    for name in expected:
        method = inspect.getattr_static(RuntimeControlPlane, name)
        assert getattr(method, "__mutation_authorized__", None) is not None, name
    assert getattr(serialize_participant_view, "__mutation_authorized__", None) is OperationKind.PARTICIPANT_CROSSING


def _assert_requests_mutation_reservation(
    control_plane: RuntimeControlPlane,
    call: Callable[[], object],
    expected_kind: OperationKind,
) -> None:
    with mutation_probe(), pytest.raises(MutationReservationRequired) as raised:
        call()

    assert raised.value.authority is control_plane._mutation_authority
    assert raised.value.kind is expected_kind


@pytest.mark.parametrize(
    ("method_name", "args", "expected_kind"),
    (
        ("submit_provisioning", (ProvisioningPlan(),), OperationKind.PROVISIONING),
        ("submit_orchestration", (OrchestrationPlan(),), OperationKind.ORCHESTRATION),
        ("submit_evaluation", (EvaluationPlan(),), OperationKind.EVALUATION),
        (
            "reconcile_workflow_timeouts",
            (),
            OperationKind.WORKFLOW_TIMEOUT_RECONCILIATION,
        ),
        ("initialize_participant_episode", ("participant.alice",), OperationKind.PARTICIPANT_ACTION),
        ("reset_participant_episode", ("participant.alice",), OperationKind.PARTICIPANT_ACTION),
        ("restart_participant_episode", ("participant.alice",), OperationKind.PARTICIPANT_ACTION),
        ("terminate_participant_episode", ("participant.alice",), OperationKind.PARTICIPANT_ACTION),
    ),
)
def test_accepted_generic_and_episode_entries_reach_the_shared_authority(
    method_name: str,
    args: tuple[object, ...],
    expected_kind: OperationKind,
) -> None:
    control_plane = RuntimeControlPlane(create_stub_target())

    _assert_requests_mutation_reservation(
        control_plane,
        lambda: getattr(control_plane, method_name)(*args),
        expected_kind,
    )


def test_accepted_workflow_cancellation_reaches_the_shared_authority() -> None:
    workflow_address = "orchestration.workflow.response"
    workflow = WorkflowExecutionState(
        workflow_status=WorkflowStatus.RUNNING,
        run_id="run-1181",
        started_at="2026-09-11T04:30:00Z",
        updated_at="2026-09-11T04:30:00Z",
    )
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        initial_snapshot=RuntimeSnapshot(orchestration_results={workflow_address: workflow.to_payload()}),
    )

    _assert_requests_mutation_reservation(
        control_plane,
        lambda: control_plane.cancel_workflow(workflow_address),
        OperationKind.WORKFLOW_CANCELLATION,
    )


def test_accepted_participant_action_and_control_entries_reach_the_shared_authority() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())

    _assert_requests_mutation_reservation(
        control_plane,
        lambda: control_plane.admit_participant_action(behavior(), admission_request()),
        OperationKind.PARTICIPANT_ACTION,
    )
    _assert_requests_mutation_reservation(
        control_plane,
        lambda: control_plane.record_participant_control(
            PARTICIPANT,
            object(),  # type: ignore[arg-type]
            identity=identity(),
        ),
        OperationKind.PARTICIPANT_CONTROL,
    )


def test_accepted_decision_surface_entries_reach_the_shared_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    request = admission_request()
    monkeypatch.setattr(
        "raes_runtime.participant_control.bind_participant_decision_surface_selection",
        lambda **_kwargs: request,
    )
    monkeypatch.setattr(
        "raes_runtime.participant_decision_surface_control_v2.validate_participant_decision_surface_v2_anchor",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "raes_runtime.participant_decision_surface_control_v2.bind_participant_decision_surface_selection_v2",
        lambda **_kwargs: request,
    )
    v1_resolvers = SimpleNamespace(argument_shape=None, apparatus=None)
    v2_resolvers = SimpleNamespace(argument_shape=None, apparatus=None, delivery=None)

    _assert_requests_mutation_reservation(
        control_plane,
        lambda: control_plane.admit_participant_decision_surface_selection(
            behavior(),
            surface=object(),  # type: ignore[arg-type]
            selection=object(),  # type: ignore[arg-type]
            admission_request=request,
            resolvers=v1_resolvers,  # type: ignore[arg-type]
        ),
        OperationKind.PARTICIPANT_ACTION,
    )
    _assert_requests_mutation_reservation(
        control_plane,
        lambda: control_plane.admit_participant_decision_surface_selection_v2(
            behavior(),
            surface=object(),  # type: ignore[arg-type]
            selection=object(),  # type: ignore[arg-type]
            admission_request=request,
            resolvers=v2_resolvers,  # type: ignore[arg-type]
        ),
        OperationKind.PARTICIPANT_ACTION,
    )


def test_accepted_participant_execution_entry_reaches_the_shared_authority() -> None:
    class ExecutionControlRuntime:
        def __init__(self, delegate: object) -> None:
            self._delegate = delegate

        def __getattr__(self, name: str) -> object:
            return getattr(self._delegate, name)

        def control_execution(self, *_args: object) -> object:
            raise AssertionError("the admission probe must stop before backend execution")

    target = create_stub_target()
    control_plane = RuntimeControlPlane(
        replace(target, participant_runtime=ExecutionControlRuntime(target.participant_runtime)),  # type: ignore[arg-type]
    )
    request = ParticipantExecutionControlRequestModel(
        execution_scope_ref="participant.execution.issue-1181",
        action="start",
        expected_generation=0,
    )

    _assert_requests_mutation_reservation(
        control_plane,
        lambda: control_plane.control_participant_execution(request),
        OperationKind.PARTICIPANT_ACTION,
    )


def test_accepted_participant_projection_reaches_the_shared_authority() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    serialization = ParticipantViewSerialization(
        participant_address=PARTICIPANT,
        episode_id="episode-1181",
        subject_kind="participant_status",  # type: ignore[arg-type]
        interaction_kind="retrieval",  # type: ignore[arg-type]
        projection_ref="projection:issue-1181",
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="projection-1181",
    )

    _assert_requests_mutation_reservation(
        control_plane,
        lambda: serialize_participant_view(control_plane, object(), serialization),  # type: ignore[arg-type]
        OperationKind.PARTICIPANT_CROSSING,
    )


def test_runtime_manager_remains_outside_control_plane_store_authority() -> None:
    manager = RuntimeManager(create_stub_target())

    assert not hasattr(manager, "_store")
    assert not hasattr(manager, "_store_commits")
    assert not hasattr(manager, "_mutation_authority")
