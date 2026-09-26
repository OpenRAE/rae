"""Adversarial portable supervision inputs and installed-provider admission."""

import pytest
from pydantic import ValidationError
from raes_backend_protocols.operation_supervision import require_operation_provider
from raes_contracts import contracts
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS
from test_issue_1360_backend_operations import (
    admission,
    artifact,
    capabilities,
    control,
    evidence,
    outcome,
    request,
    request_payload,
    response,
)


def test_refused_admission_cannot_be_followed_by_dispatch():
    refused = admission("refused")
    ack = response({"kind": "acknowledgement", "disposition": "accepted"}, 2)
    operation_1 = request()
    with pytest.raises(ValueError, match="terminal"):
        contracts.validate_backend_operation_history(operation_1, [refused, ack])


@pytest.mark.parametrize("disposition", ["willing", "refused"])
def test_admission_cannot_reclassify_an_accepted_invocation(disposition):
    ack = response({"kind": "acknowledgement", "disposition": "accepted"})
    late_admission = response(admission(disposition).message, 2)
    operation_2 = request()
    with pytest.raises(ValueError, match="admission must precede"):
        contracts.validate_backend_operation_history(operation_2, [ack, late_admission])


@pytest.mark.parametrize(
    "timestamp", ["2026-02-30T00:00:00Z", "2026-09-24T00:00:00", "2026-09-24T00:00:00." + "1" * 80 + "Z"]
)
def test_budget_origin_is_a_bounded_real_calendar_instant(timestamp):
    raw = request_payload()
    raw["budget"]["started_at"] = timestamp
    with pytest.raises(ValidationError):
        contracts.BackendOperationRequestModel.model_validate(raw)


@pytest.mark.parametrize(
    "changes",
    [
        {"effect": "partial", "residual_scope": [], "residual_state": None},
        {"effect": "absent"},
        {"evidence_refs": []},
        {"residual_state": artifact("workflow-result-envelope-v1")},
        {"cessation_established": "false"},
        {"residual_scope": ["node.vm1", "node.vm1"]},
    ],
)
def test_effect_claims_reject_missing_contradictory_or_coerced_evidence(changes):
    payload_3 = {**evidence(), **changes}
    with pytest.raises(ValidationError):
        contracts.BackendOperationEffectsModel.model_validate(payload_3)


@pytest.mark.parametrize(
    "scope",
    [
        {"kind": "resources", "addresses": ["node.vm1"]},
        {"kind": "resources", "independence": artifact()},
        {"kind": "target-run", "addresses": ["node.vm1"]},
    ],
)
def test_narrow_scope_requires_an_admitted_independence_witness(scope):
    raw = request_payload()
    raw["binding"]["effect_scope"] = scope
    with pytest.raises(ValidationError):
        contracts.BackendOperationRequestModel.model_validate(raw)


def test_residual_scope_cannot_escape_admitted_resource_boundary():
    raw = request_payload()
    raw["binding"]["effect_scope"] = {
        "kind": "resources",
        "addresses": ["node.vm2"],
        "independence": artifact(),
    }
    op = contracts.BackendOperationRequestModel.model_validate(raw)
    result = response(outcome(), operation=op)
    with pytest.raises(ValueError, match="scope"):
        contracts.validate_backend_operation_response(op, result)


@pytest.mark.parametrize(
    "field,value",
    [("backend_id", "other"), ("supported_operation_kinds", ["evaluation"]), ("revision", "sha256:" + "d" * 64)],
)
def test_wrong_capability_identity_kind_and_revision_prevent_admission(field, value):
    raw = capabilities().model_dump()
    raw[field] = value
    foreign = contracts.BackendOperationCapabilitiesModel.model_validate(raw)
    operation_4 = request()
    admission_report_5 = admission()
    with pytest.raises(ValueError):
        contracts.require_backend_operation_admission(operation_4, foreign, admission_report_5)


def test_non_admission_message_cannot_supply_willingness():
    operation_6 = request()
    capability_report_7 = capabilities()
    response_report_8 = response(outcome())
    with pytest.raises(ValueError, match="admission"):
        contracts.require_backend_operation_admission(operation_6, capability_report_7, response_report_8)


@pytest.mark.parametrize(
    "kind,disposition,reason",
    [
        ("admission", "willing", "context-refused"),
        ("admission", "refused", None),
        ("acknowledgement", "accepted", "context-refused"),
        ("acknowledgement", "refused", None),
    ],
)
def test_refusal_reasons_are_required_only_on_refusal(kind, disposition, reason):
    raw = {"kind": kind, "disposition": disposition, "reason": reason}
    if kind == "admission":
        raw["capability_digest"] = "sha256:" + "c" * 64
    with pytest.raises(ValidationError):
        response(raw)


def test_failure_requires_known_non_satisfaction():
    outcome_payload_9 = outcome("failed")
    with pytest.raises(ValidationError, match="non-satisfaction"):
        response(outcome_payload_9)
    failed = response(outcome("failed", satisfaction="unsatisfied", release_gates_satisfied=False))
    contracts.validate_backend_operation_response(request(), failed)


def test_control_requires_original_binding_commitment_and_matching_action():
    ctl = control()
    report = response(
        {
            "kind": "reconciliation",
            "control_id": ctl.control_id,
            "control_digest": contracts.backend_operation_control_digest(ctl),
            "effects": evidence(),
        }
    )
    operation_10 = request()
    with pytest.raises(ValueError, match="action"):
        contracts.validate_backend_operation_response(operation_10, report, control=ctl)
    operation_11 = request()
    with pytest.raises(ValueError, match="control"):
        contracts.validate_backend_operation_response(operation_11, report)
    raw = ctl.model_dump()
    raw["request_digest"] = "sha256:" + "f" * 64
    other = contracts.BackendOperationControlModel.model_validate(raw)
    operation_12 = request()
    with pytest.raises(ValueError, match="commitment"):
        contracts.validate_backend_operation_response(operation_12, report, control=other)


def test_transcript_rejects_changed_control_and_unordered_or_unacknowledged_records():
    ctl = control()
    raw = ctl.model_dump()
    raw["budget"]["remaining_ms"] = 800
    changed = contracts.BackendOperationControlModel.model_validate(raw)
    operation_13 = request()
    with pytest.raises(ValueError, match="control"):
        contracts.validate_backend_operation_history(operation_13, [], controls=[ctl, changed])
    operation_14 = request()
    reports_15 = [response(outcome())]
    with pytest.raises(ValueError, match="acknowledgement"):
        contracts.validate_backend_operation_history(operation_14, reports_15)
    ack = response({"kind": "acknowledgement", "disposition": "accepted"}, 2)
    operation_16 = request()
    reports_17 = [ack, admission()]
    with pytest.raises(ValueError, match="unordered"):
        contracts.validate_backend_operation_history(operation_16, reports_17)
    operation_18 = request()
    reports_19 = [ack, response(ack.message, 3)]
    with pytest.raises(ValueError, match="twice"):
        contracts.validate_backend_operation_history(operation_18, reports_19)


@pytest.mark.parametrize("field", ["responses", "controls"])
def test_transcript_size_is_bounded_before_traversal(field):
    operation_20 = request()
    reports_21 = [admission()] * (1025 if field == "responses" else 0)
    reports_22 = [control()] * (257 if field == "controls" else 0)
    with pytest.raises(ValueError, match="bound"):
        contracts.validate_backend_operation_history(
            operation_20,
            reports_21,
            controls=reports_22,
        )


def test_protocol_installation_checks_do_not_invoke_provider():
    class Provider:
        def operation_capabilities(self):
            raise AssertionError("shape checking must not invoke the provider")

        def check_operation(self, request):
            raise AssertionError("shape checking must not invoke the provider")

        start_operation = check_operation
        observe_operation = check_operation
        cancel_operation = check_operation
        reconcile_operation = check_operation

    provider = Provider()
    assert require_operation_provider(provider, BACKEND_OPERATION_CONTRACT_IDS) is provider
    with pytest.raises(ValueError, match="declared"):
        require_operation_provider(provider, ["backend-manifest-v2"])
    provider.cancel_operation = lambda: None
    with pytest.raises(ValueError, match="call shape"):
        require_operation_provider(provider, BACKEND_OPERATION_CONTRACT_IDS)


def test_request_is_frozen_and_duplicate_requirements_are_rejected():
    op = request()
    with pytest.raises(ValidationError):
        op.binding.worker_id = "replacement"
    raw = request_payload()
    raw["required_guarantees"] *= 2
    with pytest.raises(ValidationError, match="unique"):
        contracts.BackendOperationRequestModel.model_validate(raw)
