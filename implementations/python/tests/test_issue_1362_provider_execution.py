"""The installed public protocol passes the real runtime's native settlement gates."""

from dataclasses import replace
from threading import Event, Lock, Thread

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    BackendOperationCapabilitiesModel,
    BackendOperationResponseModel,
    backend_operation_control_digest,
    backend_operation_request_digest,
    canonical_backend_operation_capabilities_digest,
)
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.runtime_state import ApplyResult, OperationState, RuntimeSnapshot
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store_snapshots import _snapshot_payload
from test_issue_1362_runtime_supervision import supervisor


class Provider:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.release.set()
        self._lock = Lock()
        self.sequence = 0
        self.starts = 0
        self.cancels = 0
        self.refuse = False
        self.foreign = False
        self.bad_digest = False

    def operation_capabilities(self):
        return BackendOperationCapabilitiesModel(
            backend_id="stub",
            revision="sha256:" + "c" * 64,
            supported_operation_kinds=("provisioning",),
            guarantees=("cancellation", "cessation-evidence", "effect-observation"),
        )

    def report(self, request, message):
        with self._lock:
            self.sequence += 1
            return BackendOperationResponseModel(
                binding=request.binding.model_copy(update={"owner_generation": 99})
                if self.foreign
                else request.binding,
                request_digest=backend_operation_request_digest(request),
                sequence=self.sequence,
                message=message,
            )

    def check_operation(self, request):
        return self.report(
            request,
            {
                "kind": "admission",
                "disposition": "refused" if self.refuse else "willing",
                "reason": "context-refused" if self.refuse else None,
                "capability_digest": canonical_backend_operation_capabilities_digest(self.operation_capabilities()),
            },
        )

    def start_operation(self, request):
        self.request = request
        self.starts += 1
        self.started.set()
        assert self.release.wait(3)
        return self.report(request, {"kind": "acknowledgement", "disposition": "accepted"})

    def observe_operation(self, control):
        # The fixture owns a scoped absence/cessation witness for its no-op.
        snapshot = RuntimeSnapshot()
        digest = canonical_json_digest(_snapshot_payload(snapshot))
        request = self.request
        return self.report(
            request,
            {
                "kind": "outcome",
                "proposed_state": "succeeded",
                "effects": {
                    "effect": "absent",
                    "cessation_established": True,
                    "evidence_refs": [
                        {
                            "contract_id": "runtime-snapshot-v1",
                            "artifact_id": "fixture-cessation",
                            "digest": digest,
                        }
                    ],
                },
                "satisfaction": "satisfied",
                "release_gates_satisfied": True,
                "cancellation_established": False,
                "result": {
                    "contract_id": "runtime-snapshot-v1",
                    "artifact_id": "fixture-result",
                    "digest": "sha256:" + "a" * 64 if self.bad_digest else digest,
                },
            },
        )

    def cancel_operation(self, control):
        self.cancels += 1
        return self.report(
            self.request,
            {
                "kind": "control",
                "control_id": control.control_id,
                "control_digest": backend_operation_control_digest(control),
                "disposition": "accepted",
            },
        )

    def reconcile_operation(self, control):
        return self.report(
            self.request,
            {
                "kind": "reconciliation",
                "control_id": control.control_id,
                "control_digest": backend_operation_control_digest(control),
                "effects": {"effect": "unknown", "cessation_established": False},
            },
        )


class Evidence:
    def validate_effects(self, request, response):
        return response.binding == request.binding and response.message.effects.effect == "absent"

    def resolve_result(self, request, response, predecessor):
        return ApplyResult(True, predecessor)


def test_a_consumed_grant_requires_evidence_even_when_start_reports_refusal():
    provider = Provider()

    def refuse(request):
        return provider.report(request, {"kind": "acknowledgement", "disposition": "refused", "reason": "unavailable"})

    provider.start_operation = refuse
    plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence())
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        record = plane._store.load_records()[receipt.operation_id]
        assert record.status.state is OperationState.INDETERMINATE
        assert record.invocation.consumed and record.invocation.reserved
        assert not plane.submit_provisioning(ProvisioningPlan()).accepted
    finally:
        plane.close()


def target(provider):
    original = create_stub_target()
    manifest = replace(
        original.manifest,
        supported_contract_versions=tuple(
            dict.fromkeys(
                [
                    *original.manifest.supported_contract_versions,
                    *BACKEND_OPERATION_CONTRACT_IDS,
                ]
            )
        ),
    )
    return replace(original, manifest=manifest, operation_provider=provider)


def test_provider_outcome_is_validated_and_atomic_receipt_replay_never_starts_twice():
    provider = Provider()
    plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence())
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan(), idempotency_key="provider-1362")
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        assert provider.starts == 1
        assert plane.submit_provisioning(ProvisioningPlan(), idempotency_key="provider-1362") == receipt
        assert provider.starts == 1
        record = plane._store.load_records()[receipt.operation_id]
        assert record.invocation.consumed and not record.invocation.reserved
        assert record.invocation.responses[-1].message.kind == "outcome"
    finally:
        plane.close()


@pytest.mark.parametrize("fault", ["foreign", "bad_digest"])
def test_foreign_binding_or_unresolved_result_cannot_establish_success(fault):
    provider = Provider()
    plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence())
    setattr(provider, fault, True)
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan())
        if fault == "foreign":
            assert not receipt.accepted
            assert plane.get_operation(receipt.operation_id) is None
        else:
            assert plane.get_operation(receipt.operation_id).state is OperationState.INDETERMINATE
        assert provider.starts == (0 if fault == "foreign" else 1)
    finally:
        plane.close()


def test_cancel_uses_independent_capacity_is_idempotent_and_acceptance_is_not_cessation():
    from raes_runtime.operation_supervision_configuration import OperationSupervisionConfiguration

    provider = Provider()
    provider.release.clear()
    plane = RuntimeControlPlane(
        target(provider),
        operation_evidence=Evidence(),
        supervision=OperationSupervisionConfiguration(execution_ms=1500),
    )
    receipts, failures = [], []

    def submit():
        try:
            receipts.append(plane.submit_provisioning(ProvisioningPlan()))
        except BaseException as exc:
            failures.append(exc)

    worker = Thread(target=submit)
    worker.start()
    try:
        assert provider.started.wait(1)
        parent_id = next(iter(plane._store.load_records()))
        identity = supervisor()
        control = plane.cancel_operation(parent_id, control_id="provider-cancel", identity=identity)
        assert provider.cancels == 1
        assert plane.cancel_operation(parent_id, control_id="provider-cancel", identity=identity) == control
        assert provider.cancels == 1
        response = plane.get_control_response(parent_id, control.control_id, identity=identity)
        assert response.message.disposition == "accepted"
        assert plane.get_operation(parent_id).state is OperationState.RUNNING
        provider.release.set()
        worker.join(1)
        assert not failures
        assert plane.get_operation(parent_id).state is OperationState.SUCCEEDED
    finally:
        provider.release.set()
        worker.join(2)
        plane.close()


def test_contextual_refusal_before_claim_is_audit_only_and_refusal_after_claim_withdraws_acceptance():
    class RefuseAfterClaim(Provider):
        def __init__(self):
            super().__init__()
            self.checks = 0

        def check_operation(self, request):
            self.checks += 1
            self.refuse = self.checks == 2
            return super().check_operation(request)

    for provider, expected in [(Provider(), None), (RefuseAfterClaim(), OperationState.CANCELLED)]:
        provider.refuse = expected is None
        plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence())
        try:
            receipt = plane.submit_provisioning(ProvisioningPlan())
            assert provider.starts == 0
            assert receipt.accepted is (expected is not None)
            if expected is None:
                assert plane._store.load_records() == {}
                assert plane.audit_log()[-1].allowed is False
            else:
                assert plane.get_operation(receipt.operation_id).state is expected
                assert not plane._store.load_records()[receipt.operation_id].invocation.consumed
        finally:
            plane.close()


def test_replay_resolves_the_atomic_claim_before_a_now_unavailable_provider():
    provider = Provider()
    plane = RuntimeControlPlane(target(provider), operation_evidence=Evidence())
    try:
        receipt = plane.submit_provisioning(ProvisioningPlan(), idempotency_key="terminal-replay")
        assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
        provider.operation_capabilities = lambda: pytest.fail("replay consulted an unavailable provider")
        assert plane.submit_provisioning(ProvisioningPlan(), idempotency_key="terminal-replay") == receipt
        assert provider.starts == 1
    finally:
        plane.close()
