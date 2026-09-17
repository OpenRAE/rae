"""CP-3 startup reconciliation and linked-resolution acceptance tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from raes_backend_protocols.capabilities import RecoveryObservationCapabilities
from raes_backend_protocols.manifest import (
    backend_manifest_from_v2_model_with_envelope,
    backend_manifest_payload,
)
from raes_backend_protocols.recovery_observation import (
    RecoveryEffectClassification,
    RecoveryObservationRequest,
    RecoveryObservationResult,
)
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.contracts import BackendManifestV2Model, schema_bundle
from raes_contracts.diagnostics import Severity
from raes_contracts.planning import ProvisioningPlan, RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
    SnapshotEntry,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_operation_context import operation_admission_context
from raes_runtime.control_plane_recovery import IndeterminateResolutionDisposition
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
    ParticipantControlSubjectBinding,
)
from raes_runtime.control_plane_store import ControlPlaneOperationRecord, InMemoryControlPlaneStore
from raes_runtime.control_plane_store_record_migration import migrate_legacy_operation_payload
from raes_runtime.control_plane_store_records import _record_payload
from raes_runtime.registry import RuntimeTarget


def _context(
    *,
    kind: OperationKind = OperationKind.PROVISIONING,
    run_scope: str = "run:issue-1179",
    subject_scope: str | None = None,
) -> OperationAdmissionContext:
    scopes = ["role:operator"]
    if subject_scope is not None:
        scopes.append(subject_scope)
    return OperationAdmissionContext(
        actor_id="operator-1179",
        authorization_scope=tuple(scopes),
        target_scope="target:stub",
        run_scope=run_scope,
        operation_kind=kind,
        request_commitment=f"sha256:{'1' * 64}",
    )


def _record(
    operation_id: str,
    *,
    state: OperationState = OperationState.RUNNING,
    kind: OperationKind = OperationKind.PROVISIONING,
    run_scope: str = "run:issue-1179",
    subject_scope: str | None = None,
    idempotency_key: str | None = None,
) -> ControlPlaneOperationRecord:
    context = _context(kind=kind, run_scope=run_scope, subject_scope=subject_scope)
    submitted_at = "2026-09-17T00:00:00Z"
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
        request_fingerprint=context.request_commitment,
        idempotency_key=idempotency_key or f"key-{operation_id}",
    )


class _RecoveryObserver:
    def __init__(
        self,
        result: RecoveryObservationResult
        | Callable[[RecoveryObservationRequest], RecoveryObservationResult]
        | BaseException,
    ) -> None:
        self.result = result
        self.requests: list[RecoveryObservationRequest] = []

    def observe_effect(self, request: RecoveryObservationRequest) -> RecoveryObservationResult:
        self.requests.append(request)
        if isinstance(self.result, BaseException):
            raise self.result
        if callable(self.result):
            return self.result(request)
        return self.result


class _CountingProvisioner:
    def __init__(self) -> None:
        self.delegate = StubProvisioner()
        self.validate_count = 0
        self.apply_count = 0

    def validate(self, plan: ProvisioningPlan) -> list[object]:
        self.validate_count += 1
        return self.delegate.validate(plan)

    def apply(self, plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> object:
        self.apply_count += 1
        return self.delegate.apply(plan, snapshot)


def _target(
    observer: _RecoveryObserver | None = None,
    *,
    supported_kinds: frozenset[OperationKind] | None = None,
    provisioner: object | None = None,
) -> RuntimeTarget:
    target = create_stub_target()
    if observer is None and supported_kinds is None:
        return replace(target, provisioner=provisioner or target.provisioner)
    capability = RecoveryObservationCapabilities(
        name="stub-recovery-observer",
        supported_operation_kinds=supported_kinds or frozenset({OperationKind.PROVISIONING}),
    )
    manifest = replace(
        target.manifest,
        capabilities=replace(target.manifest.capabilities, recovery_observation=capability),
    )
    return replace(
        target,
        manifest=manifest,
        provisioner=provisioner or target.provisioner,
        recovery_observer=observer,
    )


def _store_with(record: ControlPlaneOperationRecord) -> InMemoryControlPlaneStore:
    store = InMemoryControlPlaneStore()
    if record.status.state is OperationState.ACCEPTED:
        store.save_record(record)
    else:
        store.claim_record(record)
    return store


def _applied_result(request: RecoveryObservationRequest) -> RecoveryObservationResult:
    return RecoveryObservationResult(
        classification=RecoveryEffectClassification.EFFECT_APPLIED,
        operation_id=request.operation_id,
        request_commitment=request.request_commitment,
        snapshot=request.baseline_snapshot,
    )


def _operator(*, target_name: str = "stub", subjects: tuple[object, ...] = ()) -> ControlPlaneIdentity:
    return ControlPlaneIdentity(
        identity="resolver-1179",
        roles=frozenset({ControlPlaneRole.OPERATOR}),
        target_name=target_name,
        participant_control_subjects=subjects,
    )


def test_accepted_claim_is_closed_as_known_absent_without_observation_or_replay() -> None:
    record = _record("accepted-1179", state=OperationState.ACCEPTED)
    store = _store_with(record)
    provisioner = _CountingProvisioner()

    RuntimeControlPlane(_target(provisioner=provisioner), store=store)

    recovered = store.load_records()[record.receipt.operation_id]
    assert recovered.status.state is OperationState.CANCELLED
    assert [diagnostic.code for diagnostic in recovered.status.diagnostics] == [
        "runtime.control-plane.recovery-effect-absent",
        "runtime.control-plane.operation-cancelled",
    ]
    assert provisioner.validate_count == provisioner.apply_count == 0
    assert store.find_by_idempotency(record.idempotency_key) == recovered
    assert store.read_audit()[-1].reason == "operation-cancelled"


def test_legacy_migrated_accepted_claim_is_indeterminate_without_replay() -> None:
    legacy = _record("legacy-accepted-1179", state=OperationState.ACCEPTED)
    payload = _record_payload(legacy)
    payload["receipt"].pop("context")
    payload["status"].pop("context")
    migrated = migrate_legacy_operation_payload(payload).record
    assert migrated is not None
    assert migrated.status.context.authorization_scope == ("legacy:unattributed",)
    store = _store_with(migrated)
    provisioner = _CountingProvisioner()

    RuntimeControlPlane(_target(provisioner=provisioner), store=store)

    recovered = store.load_records()[migrated.receipt.operation_id]
    assert recovered.status.state is OperationState.INDETERMINATE
    assert [diagnostic.code for diagnostic in recovered.status.diagnostics] == [
        "runtime.control-plane.recovery-effect-unobservable",
        "runtime.control-plane.operation-indeterminate",
    ]
    assert store.find_by_idempotency(migrated.idempotency_key) == recovered
    assert provisioner.validate_count == provisioner.apply_count == 0


def test_running_claim_without_observer_is_indeterminate_and_retry_never_replays() -> None:
    record = _record("unobservable-1179", run_scope="run:default")
    retry_context = operation_admission_context(
        type("ControlPlaneContext", (), {"_target": type("Target", (), {"name": "stub"})()})(),
        kind=OperationKind.PROVISIONING,
        request=ProvisioningPlan(),
    )
    record = replace(
        record,
        receipt=replace(record.receipt, context=retry_context),
        status=replace(record.status, context=retry_context),
        request_fingerprint=retry_context.request_commitment,
    )
    store = _store_with(record)
    provisioner = _CountingProvisioner()
    control_plane = RuntimeControlPlane(_target(provisioner=provisioner), store=store)

    status = control_plane.get_operation(record.receipt.operation_id)
    assert status is not None
    assert status.state is OperationState.INDETERMINATE
    assert [diagnostic.code for diagnostic in status.diagnostics] == [
        "runtime.control-plane.recovery-effect-unobservable",
        "runtime.control-plane.operation-indeterminate",
    ]
    retry = control_plane.submit_provisioning(ProvisioningPlan(), idempotency_key=record.idempotency_key)
    assert retry.operation_id == record.receipt.operation_id
    assert provisioner.validate_count == provisioner.apply_count == 0


def test_observed_absent_running_claim_fails_with_stable_diagnostics() -> None:
    record = _record("absent-1179")
    observer = _RecoveryObserver(
        lambda request: RecoveryObservationResult(
            classification=RecoveryEffectClassification.EFFECT_ABSENT,
            operation_id=request.operation_id,
            request_commitment=request.request_commitment,
        )
    )
    store = _store_with(record)

    RuntimeControlPlane(_target(observer), store=store)

    status = store.load_records()[record.receipt.operation_id].status
    assert status.state is OperationState.FAILED
    assert [diagnostic.code for diagnostic in status.diagnostics] == [
        "runtime.control-plane.recovery-effect-absent",
        "runtime.control-plane.operation-failed",
    ]
    assert len(observer.requests) == 1


def test_observed_applied_claim_validates_and_atomically_publishes_snapshot_status_and_audit() -> None:
    record = _record("applied-1179")
    observer = _RecoveryObserver(_applied_result)
    store = _store_with(record)

    control_plane = RuntimeControlPlane(_target(observer), store=store)

    status = control_plane.get_operation(record.receipt.operation_id)
    assert status is not None
    assert status.state is OperationState.SUCCEEDED
    assert status.diagnostics[0].code == "runtime.control-plane.recovery-effect-applied"
    assert status.diagnostics[0].severity is Severity.INFO
    assert control_plane.snapshot == store.load_snapshot()
    assert control_plane.snapshot == RuntimeSnapshot()
    assert store.read_audit()[-1].reason == "operation-succeeded"


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("provider-secret-1179"),
        TimeoutError("provider-timeout-secret-1179"),
    ],
)
def test_observer_exception_or_timeout_is_redacted_indeterminate(failure: BaseException) -> None:
    record = _record("observer-failure-1179")
    store = _store_with(record)

    RuntimeControlPlane(_target(_RecoveryObserver(failure)), store=store)

    persisted = store.load_records()[record.receipt.operation_id]
    rendered = repr(persisted) + repr(store.read_audit())
    assert persisted.status.state is OperationState.INDETERMINATE
    assert "provider-secret" not in rendered
    assert "provider-timeout-secret" not in rendered


def test_mismatched_observation_binding_is_indeterminate() -> None:
    record = _record("mismatch-1179")
    observer = _RecoveryObserver(
        RecoveryObservationResult(
            classification=RecoveryEffectClassification.EFFECT_ABSENT,
            operation_id="different-operation",
            request_commitment=f"sha256:{'2' * 64}",
        )
    )
    store = _store_with(record)

    RuntimeControlPlane(_target(observer), store=store)

    assert store.load_records()[record.receipt.operation_id].status.state is OperationState.INDETERMINATE


def test_unsupported_operation_kind_does_not_call_observer() -> None:
    record = _record("unsupported-kind-1179")
    observer = _RecoveryObserver(RuntimeError("must-not-run"))
    store = _store_with(record)

    RuntimeControlPlane(
        _target(observer, supported_kinds=frozenset({OperationKind.EVALUATION})),
        store=store,
    )

    assert observer.requests == []
    assert store.load_records()[record.receipt.operation_id].status.state is OperationState.INDETERMINATE


def test_malformed_or_semantically_invalid_applied_result_is_indeterminate() -> None:
    record = _record("invalid-applied-1179")

    def invalid_applied(request: RecoveryObservationRequest) -> RecoveryObservationResult:
        address = "provision.node.outside-authority"
        return RecoveryObservationResult(
            classification=RecoveryEffectClassification.EFFECT_APPLIED,
            operation_id=request.operation_id,
            request_commitment=request.request_commitment,
            snapshot=RuntimeSnapshot(
                entries={
                    address: SnapshotEntry(
                        address=address,
                        domain=RuntimeDomain.PROVISIONING,
                        resource_type="node",
                        payload={},
                    )
                }
            ),
            changed_addresses=(address,),
        )

    store = _store_with(record)
    RuntimeControlPlane(_target(_RecoveryObserver(invalid_applied)), store=store)
    assert store.load_records()[record.receipt.operation_id].status.state is OperationState.INDETERMINATE

    malformed = _record("malformed-result-1179")
    malformed_store = _store_with(malformed)
    observer = _RecoveryObserver(object())  # type: ignore[arg-type]
    RuntimeControlPlane(_target(observer), store=malformed_store)
    assert malformed_store.load_records()[malformed.receipt.operation_id].status.state is OperationState.INDETERMINATE


def test_manifest_round_trip_and_schema_keep_recovery_separate_from_experiment_observation() -> None:
    target = _target(_RecoveryObserver(RuntimeError("not-called")))
    payload = backend_manifest_payload(target.manifest)

    assert "recovery_observation" in payload["capabilities"]
    assert payload["capabilities"]["recovery_observation"]["supported_operation_kinds"] == ["provisioning"]
    assert target.manifest.observation is not target.manifest.recovery_observation
    Draft202012Validator(schema_bundle()["backend-manifest-v2"]).validate(payload)
    assert target.manifest.realization_envelope is not None
    reconstructed = backend_manifest_from_v2_model_with_envelope(
        BackendManifestV2Model.model_validate(payload),
        target.manifest.realization_envelope,
    )
    assert reconstructed.recovery_observation == target.manifest.recovery_observation


def test_runtime_target_requires_exact_recovery_manifest_component_agreement() -> None:
    target = create_stub_target()
    capability = RecoveryObservationCapabilities(
        name="declared-only",
        supported_operation_kinds=frozenset({OperationKind.PROVISIONING}),
    )
    declared = replace(
        target.manifest,
        capabilities=replace(target.manifest.capabilities, recovery_observation=capability),
    )
    undeclared_observer = _RecoveryObserver(RuntimeError("not-called"))

    with pytest.raises(ValueError, match="recovery_observer presence"):
        replace(target, manifest=declared)
    with pytest.raises(ValueError, match="recovery_observer presence"):
        replace(target, recovery_observer=undeclared_observer)


def test_resolution_creates_fresh_linked_operation_and_unblocks_mutation_without_rewriting_parent() -> None:
    parent = _record("parent-1179", run_scope="run:default")
    store = _store_with(parent)
    control_plane = RuntimeControlPlane(_target(), store=store)
    indeterminate = store.load_records()[parent.receipt.operation_id]
    blocked_plan = ProvisioningPlan()

    with pytest.raises(RuntimeError, match="indeterminate operation requires resolution"):
        control_plane.submit_provisioning(blocked_plan, idempotency_key="blocked-effect")
    child_receipt = control_plane.resolve_indeterminate_operation(
        parent.receipt.operation_id,
        disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
        idempotency_key="resolution-child-1179",
        identity=_operator(),
    )

    records = store.load_records()
    assert records[parent.receipt.operation_id] == indeterminate
    child = records[child_receipt.operation_id]
    assert child.status.state is OperationState.SUCCEEDED
    assert child.status.context.operation_kind is OperationKind.INDETERMINATE_RESOLUTION
    assert child.status.context.parent_operation_id == parent.receipt.operation_id
    assert child.status.context.run_scope == parent.status.context.run_scope
    assert child.idempotency_key == "resolution-child-1179"
    assert child.idempotency_key != parent.idempotency_key
    assert sum(event.operation_id == child_receipt.operation_id for event in store.read_audit()) == 1
    assert control_plane.submit_provisioning(ProvisioningPlan(), idempotency_key="unblocked-effect").accepted


def test_quarantine_is_scoped_to_the_indeterminate_target_and_run() -> None:
    parent = _record("other-run-parent-1179", run_scope="run:other")
    store = _store_with(parent)
    control_plane = RuntimeControlPlane(_target(), store=store)

    receipt = control_plane.submit_provisioning(ProvisioningPlan(), idempotency_key="default-run-effect")

    assert receipt.accepted
    assert store.load_records()[parent.receipt.operation_id].status.state is OperationState.INDETERMINATE


def test_resolution_retry_is_idempotent_and_already_resolved_parent_rejects_a_new_child() -> None:
    parent = _record("retry-parent-1179")
    store = _store_with(parent)
    control_plane = RuntimeControlPlane(_target(), store=store)
    kwargs = {
        "disposition": IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
        "idempotency_key": "retry-child-1179",
        "identity": _operator(),
    }

    first = control_plane.resolve_indeterminate_operation(parent.receipt.operation_id, **kwargs)
    retry = control_plane.resolve_indeterminate_operation(parent.receipt.operation_id, **kwargs)
    assert retry.operation_id == first.operation_id
    assert sum(event.operation_id == first.operation_id for event in store.read_audit()) == 1
    operator = _operator()

    with pytest.raises(ValueError, match="already resolved"):
        control_plane.resolve_indeterminate_operation(
            parent.receipt.operation_id,
            disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
            idempotency_key="next",
            identity=operator,
        )
    assert store.find_by_idempotency("next") is None


def test_participant_subject_scope_is_reauthorized_before_resolution_claim() -> None:
    scope = "participant-control:participant.alpha:controller.alpha"
    parent = _record("subject-parent-1179", subject_scope=scope)
    store = _store_with(parent)
    control_plane = RuntimeControlPlane(_target(), store=store)
    operator = _operator()

    with pytest.raises(PermissionError):
        control_plane.resolve_indeterminate_operation(
            parent.receipt.operation_id,
            disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
            idempotency_key="deny",
            identity=operator,
        )
    assert store.find_by_idempotency("deny") is None

    allowed = _operator(
        subjects=(
            ParticipantControlSubjectBinding(
                participant_address="participant.alpha",
                controller_ref="controller.alpha",
            ),
        )
    )
    receipt = control_plane.resolve_indeterminate_operation(
        parent.receipt.operation_id,
        disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
        idempotency_key="allow",
        identity=allowed,
    )
    assert store.load_records()[receipt.operation_id].status.state is OperationState.SUCCEEDED


@pytest.mark.parametrize(
    "identity",
    [
        None,
        ControlPlaneIdentity(
            identity="backend-1179",
            roles=frozenset({ControlPlaneRole.BACKEND}),
            target_name="stub",
        ),
        ControlPlaneIdentity(
            identity="auditor-1179",
            roles=frozenset({ControlPlaneRole.AUDITOR}),
            target_name="stub",
        ),
        _operator(target_name="other-target"),
    ],
)
def test_core_resolution_denial_creates_no_child_claim(identity: ControlPlaneIdentity | None) -> None:
    parent = _record("denied-parent-1179")
    store = _store_with(parent)
    control_plane = RuntimeControlPlane(_target(), store=store)

    with pytest.raises(PermissionError):
        control_plane.resolve_indeterminate_operation(
            parent.receipt.operation_id,
            disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
            idempotency_key="denied-child-1179",
            identity=identity,
        )

    assert set(store.load_records()) == {parent.receipt.operation_id}
    assert store.find_by_idempotency("denied-child-1179") is None


def test_http_resolution_is_operator_only_and_returns_stable_errors() -> None:
    parent = _record("http-parent-1179")
    store = _store_with(parent)
    control_plane = RuntimeControlPlane(_target(), store=store)
    security = ControlPlaneSecurityConfig(
        bearer_tokens={
            "operator-token": _operator(),
            "backend-token": ControlPlaneIdentity(
                identity="backend-1179",
                roles=frozenset({ControlPlaneRole.BACKEND}),
                target_name="stub",
            ),
        }
    )
    client = TestClient(create_control_plane_app(control_plane, security=security))
    path = f"/operations/{parent.receipt.operation_id}/resolution"
    body = {"disposition": "accept-current-snapshot"}

    denied = client.post(
        path,
        json=body,
        headers={"authorization": "Bearer backend-token", "idempotency-key": "http-denied-child"},
    )
    assert denied.status_code == 403
    assert store.find_by_idempotency("http-denied-child") is None

    accepted = client.post(
        path,
        json=body,
        headers={"authorization": "Bearer operator-token", "idempotency-key": "http-child-1179"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["context"]["parent_operation_id"] == parent.receipt.operation_id
