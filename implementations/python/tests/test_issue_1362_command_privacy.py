"""Durable command commitments do not retain credential-dependent public proofs."""

from types import SimpleNamespace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.operation_lifecycle import OperationKind
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_operation_context import operation_admission_context
from raes_runtime.control_plane_supervised_execution import invocation_request


def credential_plan(value):
    return ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.account.test",
                resource_type="account-placement",
                payload={
                    "spec": {
                        "credential_bindings": [
                            {
                                "credential_id": "login",
                                "purpose": "primary-authentication",
                                "auth_method": "password",
                                "material": {"classification": "secret_fixture", "value": value},
                            }
                        ]
                    }
                },
            )
        ]
    )


def native_request(plane, plan):
    return SimpleNamespace(
        plan=plan,
        domain=RuntimeDomain.PROVISIONING,
        context=operation_admission_context(plane, kind=OperationKind.PROVISIONING, request=plan),
    )


def test_command_commitment_is_private_to_its_owner_and_exact_plan():
    plan = credential_plan("credential-fixture-alpha-1362")
    plane = RuntimeControlPlane(create_stub_target())
    try:
        first = invocation_request(plane, native_request(plane, plan), "private-command", "2026-10-13T00:00:00Z")
        assert first.command.digest != runtime_plan_digest(plan)
        changed = credential_plan("credential-fixture-beta-1362")
        assert (
            invocation_request(
                plane, native_request(plane, changed), "private-command", "2026-10-13T00:00:00Z"
            ).command.digest
            != first.command.digest
        )
        assert first.binding.context.request_commitment == native_request(plane, changed).context.request_commitment
    finally:
        plane.close()
    reopened = RuntimeControlPlane(create_stub_target())
    try:
        assert (
            invocation_request(
                reopened, native_request(reopened, plan), "private-command", "2026-10-13T00:00:00Z"
            ).command.digest
            != first.command.digest
        )
    finally:
        reopened.close()


@pytest.mark.parametrize("native", [False, True])
def test_serialized_invocation_retains_neither_credential_material_nor_its_unkeyed_plan_digest(native):
    import json

    from raes_contracts.runtime_state import OperationReceipt, OperationState, OperationStatus
    from raes_runtime.control_plane_store import ControlPlaneOperationRecord
    from raes_runtime.control_plane_store_records import _record_payload
    from raes_runtime.operation_invocation_ledger import InvocationLedger

    plane = RuntimeControlPlane(create_stub_target())
    try:
        plan = credential_plan("credential-fixture-private-1362")
        admitted = native_request(plane, plan)
        request = invocation_request(plane, admitted, "retained-private", "2026-10-13T00:00:00Z")
        receipt = OperationReceipt(
            operation_id="retained-private",
            domain=admitted.domain,
            submitted_at=request.budget.started_at,
            accepted=True,
            context=admitted.context,
        )
        status = OperationStatus(
            operation_id=receipt.operation_id,
            domain=admitted.domain,
            submitted_at=receipt.submitted_at,
            updated_at=receipt.submitted_at,
            state=OperationState.ACCEPTED,
            context=admitted.context,
        )
        record = ControlPlaneOperationRecord(
            receipt=receipt,
            status=status,
            request_fingerprint=admitted.context.request_commitment,
            idempotency_key="",
            invocation=InvocationLedger(request=request, native=native),
        )
        retained = json.dumps(_record_payload(record))
        assert "credential-fixture-private-1362" not in retained
        assert runtime_plan_digest(plan) not in retained
        assert request.command.digest in retained
        assert plane._command_commitment_key.hex() not in retained
    finally:
        plane.close()


def test_protected_policy_admission_recomputes_the_exact_native_commitment():
    from raes_contracts.contracts import require_backend_execution_policy_admission
    from raes_runtime.operation_command_commitment import native_command_commitment
    from test_issue_1362_provider_execution import Provider

    plane = RuntimeControlPlane(create_stub_target())
    provider = Provider()
    try:
        plan = credential_plan("credential-fixture-alpha-1362")
        request = invocation_request(plane, native_request(plane, plan), "private-admission", "2026-10-13T00:00:00Z")
        admission = provider.check_operation(request)
        require_backend_execution_policy_admission(
            request,
            provider.operation_capabilities(),
            admission,
            plan,
            resolved_native_plan_commitment=native_command_commitment(plane, plan),
        )
        changed = credential_plan("credential-fixture-beta-1362")
        with pytest.raises(ValueError, match="native plan commitment mismatch"):
            require_backend_execution_policy_admission(
                request,
                provider.operation_capabilities(),
                admission,
                changed,
                resolved_native_plan_commitment=native_command_commitment(plane, changed),
            )
    finally:
        plane.close()
