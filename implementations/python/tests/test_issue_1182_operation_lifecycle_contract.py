"""CP-1 operation lifecycle and carrier contract acceptance tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from itertools import product

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import OperationReceiptModel, OperationStatusModel, schema_bundle
from raes_contracts.diagnostics import Diagnostic, DiagnosticModel, portable_diagnostic_payload
from raes_contracts.planning import (
    ChangeAction,
    EvaluationPlan,
    OrchestrationPlan,
    ProvisioningPlan,
    ProvisionOp,
    RuntimeDomain,
)
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
    is_operation_transition_allowed,
    operation_terminal_diagnostic,
    operation_transition_diagnostic,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_operation_context import (
    operation_admission_context,
    operation_idempotency_fingerprint,
)
from raes_runtime.control_plane_security import ControlPlaneIdentity, ControlPlaneRole
from raes_runtime.control_plane_store import ControlPlaneOperationRecord, InMemoryControlPlaneStore
from raes_runtime.control_plane_store_local import LocalControlPlaneStore
from raes_runtime.control_plane_store_records import _record_from_payload, _record_payload

_LEGAL_TRANSITIONS = {
    (OperationState.ACCEPTED, OperationState.RUNNING),
    (OperationState.ACCEPTED, OperationState.CANCELLED),
    (OperationState.RUNNING, OperationState.SUCCEEDED),
    (OperationState.RUNNING, OperationState.FAILED),
    (OperationState.RUNNING, OperationState.CANCELLED),
    (OperationState.RUNNING, OperationState.INDETERMINATE),
}


def _context(**updates: object) -> OperationAdmissionContext:
    values: dict[str, object] = {
        "actor_id": "operator-1",
        "authorization_scope": ("role:operator", "subject:participant.red-team"),
        "target_scope": "target:stub",
        "run_scope": "run:test-1182",
        "operation_kind": OperationKind.PROVISIONING,
        "request_commitment": f"sha256:{'a' * 64}",
        "parent_operation_id": None,
    }
    values.update(updates)
    return OperationAdmissionContext.model_validate(values)


def _record(
    state: OperationState,
    *,
    context: OperationAdmissionContext | None = None,
    updated_at: str = "2026-09-06T10:00:01Z",
) -> ControlPlaneOperationRecord:
    operation_context = context or _context()
    receipt = OperationReceipt(
        operation_id="operation-1182",
        domain=RuntimeDomain.PROVISIONING,
        submitted_at="2026-09-06T10:00:00Z",
        accepted=True,
        context=operation_context,
    )
    status = OperationStatus(
        operation_id=receipt.operation_id,
        domain=receipt.domain,
        state=state,
        submitted_at=receipt.submitted_at,
        updated_at=updated_at,
        context=operation_context,
    )
    return ControlPlaneOperationRecord(
        receipt=receipt,
        status=status,
        idempotency_key="test-key",
    )


def test_operation_state_transition_relation_is_the_closed_fm3_matrix() -> None:
    states = tuple(OperationState)

    assert set(product(states, repeat=2)) - _LEGAL_TRANSITIONS
    for source, target in product(states, repeat=2):
        assert is_operation_transition_allowed(source, target) is ((source, target) in _LEGAL_TRANSITIONS)


@pytest.mark.parametrize("source,target", sorted(set(product(OperationState, repeat=2)) - _LEGAL_TRANSITIONS))
def test_illegal_transition_diagnostics_are_stable_closed_and_value_free(
    source: OperationState,
    target: OperationState,
) -> None:
    diagnostic = operation_transition_diagnostic(source, target)

    assert diagnostic.code == "runtime.control-plane.operation-transition-invalid"
    assert diagnostic.domain == "runtime"
    assert diagnostic.address == "/state"
    assert diagnostic.message == "Operation lifecycle transition is not permitted."
    DiagnosticModel.model_validate(
        {
            "code": diagnostic.code,
            "domain": diagnostic.domain,
            "address": diagnostic.address,
            "message": diagnostic.message,
            "severity": diagnostic.severity.value,
        }
    )


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (OperationState.FAILED, "runtime.control-plane.operation-failed"),
        (OperationState.CANCELLED, "runtime.control-plane.operation-cancelled"),
        (OperationState.INDETERMINATE, "runtime.control-plane.operation-indeterminate"),
    ],
)
def test_non_success_terminal_states_have_distinct_stable_diagnostics(
    state: OperationState,
    code: str,
) -> None:
    diagnostic = operation_terminal_diagnostic(state)

    assert diagnostic.code == code
    assert diagnostic.address == "/state"
    assert len(diagnostic.message) <= 512
    assert "exception" not in diagnostic.message.lower()


def test_admission_context_is_closed_typed_and_deeply_immutable() -> None:
    context = _context()

    extra_context = {**context.model_dump(), "unknown": "value"}
    with pytest.raises(ValidationError):
        OperationAdmissionContext.model_validate(extra_context)
    with pytest.raises(ValidationError):
        _context(request_commitment="not-a-commitment")
    with pytest.raises(ValidationError):
        _context(authorization_scope=("role:operator", "role:operator"))
    with pytest.raises(ValidationError):
        _context(operation_kind="store-private-kind")
    with pytest.raises(ValidationError):
        _context(actor_id=1)
    with pytest.raises(ValidationError):
        context.actor_id = "rewritten"  # type: ignore[misc]

    receipt = _record(OperationState.ACCEPTED).receipt
    with pytest.raises(FrozenInstanceError):
        receipt.context = _context(actor_id="other")  # type: ignore[misc]


def test_transport_carriers_require_the_same_closed_admission_context() -> None:
    context = _context()
    receipt_payload = {
        "schema_version": "runtime-operation/v1",
        "operation_id": "operation-1182",
        "domain": "provisioning",
        "submitted_at": "2026-09-06T10:00:00Z",
        "accepted": True,
        "context": context.model_dump(mode="json"),
        "diagnostics": [],
    }
    status_payload = {
        "schema_version": "runtime-operation/v1",
        "operation_id": "operation-1182",
        "domain": "provisioning",
        "state": "indeterminate",
        "submitted_at": "2026-09-06T10:00:00Z",
        "updated_at": "2026-09-06T10:00:01Z",
        "context": context.model_dump(mode="json"),
        "diagnostics": [portable_diagnostic_payload(operation_terminal_diagnostic(OperationState.INDETERMINATE))],
        "changed_addresses": [],
    }

    receipt = OperationReceiptModel.model_validate(receipt_payload)
    status = OperationStatusModel.model_validate(status_payload)
    assert receipt.context == status.context == context
    assert status.state is OperationState.INDETERMINATE
    for model, payload in ((OperationReceiptModel, receipt_payload), (OperationStatusModel, status_payload)):
        missing_context = {key: value for key, value in payload.items() if key != "context"}
        with pytest.raises(ValidationError):
            model.model_validate(missing_context)
        unknown_field = {**payload, "unknown": "value"}
        with pytest.raises(ValidationError):
            model.model_validate(unknown_field)


@pytest.mark.parametrize(
    "state",
    [OperationState.FAILED, OperationState.CANCELLED, OperationState.INDETERMINATE],
)
def test_transport_rejects_missing_or_malformed_terminal_classification(state: OperationState) -> None:
    status = _record(state).status
    payload = {
        "schema_version": status.schema_version,
        "operation_id": status.operation_id,
        "domain": status.domain.value,
        "state": status.state.value,
        "submitted_at": status.submitted_at,
        "updated_at": status.updated_at,
        "context": status.context.model_dump(mode="json"),
        "diagnostics": [portable_diagnostic_payload(diagnostic) for diagnostic in status.diagnostics],
        "changed_addresses": [],
    }

    with pytest.raises(ValidationError, match="canonical state diagnostic"):
        OperationStatusModel.model_validate({**payload, "diagnostics": []})
    malformed = dict(payload)
    malformed["diagnostics"] = [{**payload["diagnostics"][0], "message": "non-canonical"}]
    with pytest.raises(ValidationError, match="not canonical"):
        OperationStatusModel.model_validate(malformed)
    wrong_state = OperationState.CANCELLED if state is not OperationState.CANCELLED else OperationState.FAILED
    with pytest.raises(ValidationError, match="not canonical"):
        OperationStatusModel.model_validate({**payload, "state": wrong_state.value})
    duplicated = {**payload, "diagnostics": [*payload["diagnostics"], *payload["diagnostics"]]}
    with pytest.raises(ValidationError, match="canonical state diagnostic"):
        OperationStatusModel.model_validate(duplicated)
    assert not Draft202012Validator(schema_bundle()["operation-status-v1"]).is_valid(duplicated)


def test_domain_status_adds_canonical_terminal_classification_once() -> None:
    status = _record(OperationState.INDETERMINATE).status
    malformed = Diagnostic(
        code="runtime.control-plane.operation-indeterminate",
        domain="runtime",
        address="/state",
        message="non-canonical",
    )

    assert status.diagnostics == [operation_terminal_diagnostic(OperationState.INDETERMINATE)]
    with pytest.raises(ValueError, match="not canonical"):
        OperationStatus(
            operation_id=status.operation_id,
            domain=status.domain,
            state=status.state,
            submitted_at=status.submitted_at,
            updated_at=status.updated_at,
            context=status.context,
            diagnostics=[malformed],
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.pop("receipt"),
        lambda payload: payload.__setitem__("unknown", "value"),
        lambda payload: payload["receipt"].__setitem__("accepted", "false"),
        lambda payload: payload["status"].__setitem__("state", "unknown"),
        lambda payload: payload["status"]["context"].__setitem__("request_commitment", "bad"),
        lambda payload: payload["status"]["diagnostics"].append({"code": "open"}),
    ],
)
def test_persisted_operation_carrier_rejects_missing_unknown_or_malformed_state(mutation: object) -> None:
    payload = _record_payload(_record(OperationState.RUNNING))
    mutation(payload)  # type: ignore[operator]

    with pytest.raises(ValidationError):
        _record_from_payload(payload)


def test_persisted_terminal_carrier_rejects_missing_state_diagnostic() -> None:
    payload = _record_payload(_record(OperationState.FAILED))
    payload["status"]["diagnostics"] = []

    with pytest.raises(ValidationError, match="canonical state diagnostic"):
        _record_from_payload(payload)


@pytest.mark.parametrize("store_kind", ["memory"])
def test_store_enforces_context_immutability_and_exact_retry(store_kind: str) -> None:
    del store_kind
    store = InMemoryControlPlaneStore()
    accepted = _record(OperationState.ACCEPTED)
    running = _record(OperationState.RUNNING)
    succeeded = _record(OperationState.SUCCEEDED)

    store.claim_record(accepted)
    store.save_record(running)
    observed_revision = store.load_snapshot_state().revision
    store.commit_terminal_operation(
        store.load_snapshot(),
        succeeded,
        expected_revision=observed_revision,
    )
    store.commit_terminal_operation(
        store.load_snapshot(),
        succeeded,
        expected_revision=observed_revision,
    )

    for field, value in (
        ("actor_id", "other"),
        ("authorization_scope", ("role:auditor",)),
        ("target_scope", "target:other"),
        ("run_scope", "run:other"),
        ("operation_kind", OperationKind.EVALUATION),
        ("request_commitment", f"sha256:{'b' * 64}"),
        ("parent_operation_id", "parent-other"),
    ):
        rewritten_context = _context(**{field: value})
        rewritten = _record(OperationState.SUCCEEDED, context=rewritten_context)
        snapshot = store.load_snapshot()
        revision = store.load_snapshot_state().revision
        with pytest.raises(ValueError, match="immutable"):
            store.commit_terminal_operation(
                snapshot,
                rewritten,
                expected_revision=revision,
            )

    invalid_transition = replace(
        succeeded,
        status=replace(succeeded.status, state=OperationState.RUNNING, diagnostics=[]),
    )
    with pytest.raises(ValueError, match="transition"):
        store.save_record(invalid_transition)


def test_operation_schemas_publish_closed_context_state_and_diagnostics() -> None:
    bundle = schema_bundle()

    for contract_id in ("operation-receipt-v1", "operation-status-v1"):
        schema = bundle[contract_id]
        assert schema["additionalProperties"] is False
        assert "context" in schema["required"]
        diagnostic_ref = schema["properties"]["diagnostics"]["items"]["$ref"].rsplit("/", 1)[-1]
        assert schema["$defs"][diagnostic_ref]["additionalProperties"] is False
    status_schema = bundle["operation-status-v1"]
    assert status_schema["allOf"]
    assert all(
        constraint["then"]["properties"]["diagnostics"]["maxContains"] == 1 for constraint in status_schema["allOf"][:3]
    )
    state_ref = status_schema["properties"]["state"]["$ref"].rsplit("/", 1)[-1]
    assert status_schema["$defs"][state_ref]["enum"] == [state.value for state in OperationState]


def test_denied_admission_creates_no_operation_or_idempotency_claim() -> None:
    store = InMemoryControlPlaneStore()
    control_plane = RuntimeControlPlane(create_stub_target(), store=store)
    invalid = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.node.test",
                resource_type="node",
                payload={},
                ordering_dependencies=("provision.network.missing",),
            )
        ]
    )

    identity = ControlPlaneIdentity(
        identity="operator-test",
        roles=frozenset({ControlPlaneRole.OPERATOR}),
        target_name="stub",
    )
    first = control_plane.submit_provisioning(invalid, idempotency_key="denied-1182", identity=identity)
    retry = control_plane.submit_provisioning(invalid, idempotency_key="denied-1182", identity=identity)

    assert first.accepted is retry.accepted is False
    assert first.operation_id != retry.operation_id
    assert control_plane.get_operation(first.operation_id) is None
    assert store.find_by_idempotency("denied-1182") is None
    assert store.load_records() == {}
    audits = store.read_audit()
    assert [event.operation_id for event in audits] == [first.operation_id, retry.operation_id]
    assert all(
        event.identity == identity.identity
        and event.allowed is False
        and event.reason == "operation-admission-denied"
        and event.details == {"diagnostic_codes": ["runtime.plan-dependency-unresolved"]}
        for event in audits
    )
    control_plane.close()


def test_idempotency_binds_semantic_commitment_not_transport_fingerprint() -> None:
    control_plane = RuntimeControlPlane(create_stub_target())
    first_plan = ProvisioningPlan(operation_id="semantic-one")

    first = control_plane.submit_provisioning(
        first_plan,
        idempotency_key="semantic-1182",
        request_fingerprint="transport-one",
    )
    representation_retry = control_plane.submit_provisioning(
        first_plan,
        idempotency_key="semantic-1182",
        request_fingerprint="transport-two",
    )

    assert representation_retry == first
    changed_plan = ProvisioningPlan(operation_id="semantic-two")
    with pytest.raises(ValueError, match="different request body"):
        control_plane.submit_provisioning(
            changed_plan,
            idempotency_key="semantic-1182",
            request_fingerprint="transport-one",
        )
    different_actor = ControlPlaneIdentity(
        identity="different-actor",
        roles=frozenset({ControlPlaneRole.OPERATOR}),
        target_name="stub",
    )
    with pytest.raises(ValueError, match="different request body"):
        control_plane.submit_provisioning(
            first_plan,
            idempotency_key="semantic-1182",
            identity=different_actor,
        )
    control_plane.close()


@pytest.mark.parametrize(
    ("method_name", "plan"),
    [
        ("submit_provisioning", ProvisioningPlan()),
        ("submit_orchestration", OrchestrationPlan()),
        ("submit_evaluation", EvaluationPlan()),
    ],
)
def test_plan_idempotency_binds_explicit_base_snapshot(method_name: str, plan: object) -> None:
    first_snapshot = RuntimeSnapshot(metadata={"base": "first"})
    control_plane = RuntimeControlPlane(create_stub_target(), initial_snapshot=first_snapshot)
    changed_snapshot = RuntimeSnapshot(metadata={"base": "changed"})
    submit = getattr(control_plane, method_name)

    first = submit(plan, base_snapshot=first_snapshot, idempotency_key="snapshot-key")
    exact_retry = submit(plan, base_snapshot=first_snapshot, idempotency_key="snapshot-key")

    assert exact_retry == first
    with pytest.raises(ValueError, match="different request body"):
        submit(plan, base_snapshot=changed_snapshot, idempotency_key="snapshot-key")
    control_plane.close()


@pytest.mark.parametrize(
    ("classification", "field", "first_value", "second_value"),
    [
        ("secret_fixture", "value", "fixture-alpha", "fixture-beta"),
        ("operator_secret", "reference_id", "credential.alpha", "credential.beta"),
    ],
)
def test_private_idempotency_fingerprint_distinguishes_credential_changes(
    classification: str,
    field: str,
    first_value: str,
    second_value: str,
) -> None:
    control_plane = RuntimeControlPlane(create_stub_target())

    def credential_plan(value: str) -> ProvisioningPlan:
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
                                    "material": {"classification": classification, field: value},
                                }
                            ]
                        }
                    },
                )
            ]
        )

    first = credential_plan(first_value)
    second = credential_plan(second_value)
    first_context = operation_admission_context(
        control_plane,
        kind=OperationKind.PROVISIONING,
        request=first,
    )
    second_context = operation_admission_context(
        control_plane,
        kind=OperationKind.PROVISIONING,
        request=second,
    )

    assert first_context.request_commitment == second_context.request_commitment
    first_exact = operation_idempotency_fingerprint(kind=OperationKind.PROVISIONING, request=first)
    second_exact = operation_idempotency_fingerprint(kind=OperationKind.PROVISIONING, request=second)
    assert first_exact != second_exact

    record = replace(
        _record(OperationState.RUNNING, context=first_context),
        idempotency_key="sensitive-1182",
        request_fingerprint=first_context.request_commitment,
    )
    control_plane._claim_record(record, exact_retry_fingerprint=first_exact)
    persisted = control_plane._store.find_by_idempotency(record.idempotency_key)
    assert persisted is not None
    assert persisted.request_fingerprint == first_context.request_commitment
    assert persisted.request_fingerprint != first_exact
    assert (
        control_plane._idempotent_receipt(
            idempotency_key=record.idempotency_key,
            request_fingerprint=first_context.request_commitment,
            context=first_context,
            exact_retry_fingerprint=first_exact,
        )
        == record.receipt
    )
    with pytest.raises(ValueError, match="sensitive retry proof"):
        control_plane._idempotent_receipt(
            idempotency_key=record.idempotency_key,
            request_fingerprint=second_context.request_commitment,
            context=second_context,
            exact_retry_fingerprint=second_exact,
        )
    control_plane.close()


def test_sensitive_retry_proof_is_not_persisted_and_fails_closed_after_restart(tmp_path) -> None:
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.account.restart",
                resource_type="account-placement",
                payload={
                    "spec": {
                        "credential_bindings": [
                            {
                                "credential_id": "login",
                                "purpose": "primary-authentication",
                                "auth_method": "password",
                                "material": {"classification": "secret_fixture", "value": "fixture-restart-proof"},
                            }
                        ]
                    }
                },
            )
        ]
    )
    store_path = tmp_path / "sensitive-retry"
    first = RuntimeControlPlane(create_stub_target(), store=LocalControlPlaneStore(store_path))
    context = operation_admission_context(first, kind=OperationKind.PROVISIONING, request=plan)
    exact = operation_idempotency_fingerprint(kind=OperationKind.PROVISIONING, request=plan)
    record = replace(
        _record(OperationState.RUNNING, context=context),
        idempotency_key="restart-sensitive-1182",
        request_fingerprint=context.request_commitment,
    )
    first._claim_record(record, exact_retry_fingerprint=exact)
    first.close()

    persisted = LocalControlPlaneStore(store_path)
    with persisted._connection() as connection:
        request_fingerprint, payload = connection.execute(
            "SELECT request_fingerprint, payload FROM operations WHERE operation_id=?",
            (record.receipt.operation_id,),
        ).fetchone()
    assert request_fingerprint == context.request_commitment
    assert exact not in payload
    assert "fixture-restart-proof" not in payload

    restarted = RuntimeControlPlane(create_stub_target(), store=persisted)
    with pytest.raises(ValueError, match="sensitive retry proof"):
        restarted._idempotent_receipt(
            idempotency_key=record.idempotency_key,
            request_fingerprint=context.request_commitment,
            context=context,
            exact_retry_fingerprint=exact,
        )
    restarted.close()
