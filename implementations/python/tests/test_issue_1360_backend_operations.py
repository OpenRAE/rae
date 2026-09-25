"""Portable operation evidence, contextual admission and supervision boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as SchemaValidationError
from pydantic import ValidationError
from raes_contracts import contracts

from tools.policy.requirement_governance import evaluate_requirement_governance

ROOT = Path(__file__).resolve().parents[3]


def request_payload():
    return {
        "schema_version": "backend-operation-request/v1",
        "binding": {
            "operation_id": "operation-1",
            "invocation_id": "invocation-1",
            "attempt_id": "attempt-1",
            "worker_id": "worker-1",
            "deployment_id": "deployment-1",
            "owner_generation": 1,
            "execution_generation": 1,
            "backend_id": "backend-1",
            "baseline_revision": "revision-1",
            "context": {
                "actor_id": "author-1",
                "authorization_scope": ["role:operator"],
                "target_scope": "target-1",
                "run_scope": "run-1",
                "operation_kind": "provisioning",
                "request_commitment": "sha256:" + "a" * 64,
            },
            "effect_scope": {"kind": "target-run"},
        },
        "command": artifact("provisioning-plan-v1"),
        "requirement_refs": [artifact("artifact-requirement-v1")],
        "required_guarantees": ["cessation-evidence"],
        "budget": budget(),
    }


def artifact(contract_id="runtime-snapshot-v1"):
    return {"contract_id": contract_id, "artifact_id": "artifact-1", "digest": "sha256:" + "b" * 64}


def budget():
    return {"origin_id": "budget-1", "started_at": "2026-09-24T00:00:00Z", "limit_ms": 1000, "remaining_ms": 900}


def request():
    return contracts.BackendOperationRequestModel.model_validate(request_payload())


def capabilities():
    return contracts.BackendOperationCapabilitiesModel(
        backend_id="backend-1",
        revision="sha256:" + "c" * 64,
        supported_operation_kinds=["provisioning"],
        guarantees=["cessation-evidence", "cancellation", "effect-observation", "partial-effects"],
    )


def response(message, sequence=1, operation=None):
    operation = operation or request()
    return contracts.BackendOperationResponseModel(
        binding=operation.binding,
        request_digest=contracts.backend_operation_request_digest(operation),
        sequence=sequence,
        message=message,
    )


def admission(disposition="willing"):
    return response(
        {
            "kind": "admission",
            "disposition": disposition,
            "capability_digest": contracts.canonical_backend_operation_capabilities_digest(capabilities()),
            "reason": None if disposition == "willing" else "context-refused",
        }
    )


def evidence(effect="complete", cessation=True):
    result = {
        "effect": effect,
        "cessation_established": cessation,
        "evidence_refs": [artifact("backend-materialization-attestation-v1")],
        "residual_scope": [],
        "residual_state": None,
    }
    if effect in {"complete", "partial"}:
        result.update(residual_scope=["node.vm1"], residual_state=artifact())
    return result


def outcome(state="succeeded", **updates):
    message = {
        "kind": "outcome",
        "proposed_state": state,
        "effects": evidence(),
        "satisfaction": "satisfied",
        "release_gates_satisfied": True,
        "cancellation_established": False,
        "result": artifact("runtime-snapshot-v1"),
    }
    message.update(updates)
    return message


def control(action="cancel"):
    op = request()
    return contracts.BackendOperationControlModel(
        binding=op.binding,
        request_digest=contracts.backend_operation_request_digest(op),
        control_id="control-1",
        actor_id="supervisor-1",
        authorization_scope=["role:operator"],
        action=action,
        budget=budget(),
    )


def test_api_402_is_admitted_by_real_requirement_policy():
    class Client:
        def get_requirement(self, project, uid):
            return {"id": uid, "uid": uid, "status": "ACTIVE"}

        def get_traceability(self, requirement_id):
            return []

    assert (
        evaluate_requirement_governance(ROOT, ["contracts/README.md"], client=Client(), requirement_uid="API-402") == []
    )


def test_contextual_willingness_and_capability_are_both_required():
    contracts.require_backend_operation_admission(request(), capabilities(), admission())
    operation_1 = request()
    capability_report_2 = capabilities()
    admission_report_3 = admission("refused")
    with pytest.raises(ValueError, match="refused"):
        contracts.require_backend_operation_admission(operation_1, capability_report_2, admission_report_3)
    unsupported = capabilities().model_dump()
    unsupported["guarantees"] = []
    unsupported = contracts.BackendOperationCapabilitiesModel.model_validate(unsupported)
    operation_4 = request()
    admission_report_5 = admission()
    with pytest.raises(ValueError):
        contracts.require_backend_operation_admission(operation_4, unsupported, admission_report_5)


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_id", "other"),
        ("invocation_id", "other"),
        ("attempt_id", "other"),
        ("worker_id", "other"),
        ("deployment_id", "other"),
        ("owner_generation", 2),
        ("execution_generation", 2),
        ("backend_id", "other"),
        ("baseline_revision", "other"),
    ],
)
def test_individually_valid_foreign_response_is_rejected(field, value):
    raw = response({"kind": "acknowledgement", "disposition": "accepted", "reason": None}).model_dump()
    raw["binding"][field] = value
    foreign = contracts.BackendOperationResponseModel.model_validate(raw)
    operation_6 = request()
    with pytest.raises(ValueError, match="binding"):
        contracts.validate_backend_operation_response(operation_6, foreign)


@pytest.mark.parametrize("field", ["actor_id", "target_scope", "run_scope", "request_commitment"])
def test_original_admission_context_cannot_be_rebound(field):
    raw = admission().model_dump()
    raw["binding"]["context"][field] = "sha256:" + "d" * 64 if field == "request_commitment" else "other"
    foreign = contracts.BackendOperationResponseModel.model_validate(raw)
    operation_7 = request()
    with pytest.raises(ValueError, match="binding"):
        contracts.validate_backend_operation_response(operation_7, foreign)


def test_request_commitment_includes_guarantees_budget_and_artifact():
    original = request()
    for field, value in [
        ("required_guarantees", []),
        ("budget", {**budget(), "remaining_ms": 800}),
        ("command", artifact("orchestration-plan-v1")),
    ]:
        raw = request_payload()
        raw[field] = value
        changed = contracts.BackendOperationRequestModel.model_validate(raw)
        assert contracts.backend_operation_request_digest(changed) != contracts.backend_operation_request_digest(
            original
        )
        admission_report_15 = admission()
        with pytest.raises(ValueError, match="commitment"):
            contracts.validate_backend_operation_response(changed, admission_report_15)


@pytest.mark.parametrize("effect,ceased", [("unknown", False), ("unknown", True), ("absent", False)])
@pytest.mark.parametrize("state", ["succeeded", "failed", "cancelled"])
def test_unknown_effects_or_unproved_cessation_cannot_claim_known_terminal_outcome(effect, ceased, state):
    outcome_payload_8 = outcome(state, effects=evidence(effect, ceased), cancellation_established=state == "cancelled")
    with pytest.raises(ValidationError):
        response(outcome_payload_8)


def test_known_partial_cancellation_preserves_residual_state():
    result = response(
        outcome(
            "cancelled",
            effects=evidence("partial"),
            satisfaction="unsatisfied",
            release_gates_satisfied=False,
            cancellation_established=True,
        )
    )
    assert result.message.effects.residual_state.contract_id == "runtime-snapshot-v1"
    raw = result.model_dump()
    raw["message"]["effects"]["residual_state"] = None
    with pytest.raises(ValidationError):
        contracts.BackendOperationResponseModel.model_validate(raw)


def test_cancel_acceptance_can_be_followed_by_success_without_claiming_cancellation():
    ctl = control()
    acknowledgement = response({"kind": "acknowledgement", "disposition": "accepted", "reason": None})
    accepted = response(
        {
            "kind": "control",
            "control_id": ctl.control_id,
            "control_digest": contracts.backend_operation_control_digest(ctl),
            "disposition": "accepted",
        },
        2,
    )
    completed = response(outcome(), 3)
    contracts.validate_backend_operation_history(request(), [acknowledgement, accepted, completed], controls=[ctl])
    assert completed.message.proposed_state.value == "succeeded"


def test_duplicate_records_are_idempotent_but_changed_sequence_content_is_rejected():
    ack = response({"kind": "acknowledgement", "disposition": "accepted", "reason": None})
    contracts.validate_backend_operation_history(request(), [ack, ack])
    conflict = response({"kind": "acknowledgement", "disposition": "refused", "reason": "context-refused"})
    operation_9 = request()
    with pytest.raises(ValueError, match="sequence"):
        contracts.validate_backend_operation_history(operation_9, [ack, conflict])


def test_uncertain_completion_and_reconciliation_do_not_rewrite_parent_outcome():
    uncertain = response(
        outcome(
            "indeterminate",
            effects=evidence("unknown", False),
            satisfaction="unknown",
            release_gates_satisfied=False,
            result=None,
        ),
        2,
    )
    ack = response({"kind": "acknowledgement", "disposition": "accepted", "reason": None})
    ctl = control("reconcile")
    observed = response(
        {
            "kind": "reconciliation",
            "control_id": ctl.control_id,
            "control_digest": contracts.backend_operation_control_digest(ctl),
            "effects": evidence(),
        },
        3,
    )
    contracts.validate_backend_operation_history(request(), [ack, uncertain, observed], controls=[ctl])
    operation_10 = request()
    reports_11 = [ack, uncertain, response(outcome(), 3)]
    with pytest.raises(ValueError, match="terminal"):
        contracts.validate_backend_operation_history(operation_10, reports_11)


@pytest.mark.parametrize(
    "field,value",
    [("limit_ms", True), ("limit_ms", "1000"), ("limit_ms", 0), ("remaining_ms", 1001), ("remaining_ms", float("inf"))],
)
def test_budgets_reject_coercion_expiry_and_renewal(field, value):
    raw = request_payload()
    raw["budget"][field] = value
    with pytest.raises(ValidationError):
        contracts.BackendOperationRequestModel.model_validate(raw)


def test_closed_versioned_carriers_reject_unknown_fields_and_versions():
    for mutation in [{"schema_version": "backend-operation-request/v2"}, {"metadata": {"retry": True}}]:
        payload_16 = {**request_payload(), **mutation}
        with pytest.raises(ValidationError):
            contracts.BackendOperationRequestModel.model_validate(payload_16)


def test_supervisor_identity_and_control_commitment_are_independent():
    ctl = control()
    assert ctl.actor_id != ctl.binding.context.actor_id
    raw = ctl.model_dump()
    raw["actor_id"] = "different-supervisor"
    other = contracts.BackendOperationControlModel.model_validate(raw)
    report = response(
        {
            "kind": "control",
            "control_id": ctl.control_id,
            "control_digest": contracts.backend_operation_control_digest(ctl),
            "disposition": "accepted",
        }
    )
    operation_12 = request()
    with pytest.raises(ValueError, match="control"):
        contracts.validate_backend_operation_response(operation_12, report, control=other)


def test_published_family_and_profile_are_consumable_without_runtime():
    from raes_backend_protocols.operation_supervision import BackendOperationProvider, require_operation_provider
    from raes_contracts.backend_profiles import load_backend_profile

    family = {
        "backend-operation-request-v1": request(),
        "backend-operation-capabilities-v1": capabilities(),
        "backend-operation-control-v1": control(),
        "backend-operation-response-v1": admission(),
    }
    profile = load_backend_profile("operation-supervision")
    assert set(family) <= set(profile.required_contracts)
    bundle = contracts.schema_bundle()
    for name, value in family.items():
        schema = json.loads((ROOT / f"contracts/schemas/control-plane/{name}.json").read_text())
        assert schema == bundle[name]
        Draft202012Validator(schema).validate(value.model_dump(mode="json"))
        validator_17 = Draft202012Validator(schema)
        payload_18 = {**value.model_dump(mode="json"), "metadata": {}}
        with pytest.raises(SchemaValidationError):
            validator_17.validate(payload_18)
        assert schema["x-raes-semantic-profile"]["required"] is True
    provider_13 = object()
    with pytest.raises(ValueError, match="installed"):
        require_operation_provider(provider_13, profile.required_contracts)
    assert BackendOperationProvider is not None


@pytest.mark.parametrize(
    "changes",
    [
        {"effects": evidence("partial")},
        {"result": None},
        {"release_gates_satisfied": False},
        {"satisfaction": "unknown"},
        {"cancellation_established": True},
    ],
)
def test_success_requires_full_validated_claim_not_just_observed_effects(changes):
    outcome_payload_14 = outcome(**changes)
    with pytest.raises(ValidationError):
        response(outcome_payload_14)


def test_example_corpus_exercises_every_message_and_required_scenario():
    from raes_contracts.corpus import FIXTURES, corpus_family_root

    root = corpus_family_root(FIXTURES) / "control-plane"
    request_root = root / "backend-operation-request-v1/valid"
    response_root = root / "backend-operation-response-v1/valid"
    kinds = set()
    for scenario in ["accepted", "refused", "cancel-race", "partial-cancel", "duplicate", "uncertain"]:
        op = contracts.BackendOperationRequestModel.model_validate_json((request_root / f"{scenario}.json").read_text())
        reports = [
            contracts.BackendOperationResponseModel.model_validate_json(p.read_text())
            for p in sorted(response_root.glob(f"{scenario}-*.json"))
        ]
        controls = [
            contracts.BackendOperationControlModel.model_validate_json(p.read_text())
            for p in sorted((root / "backend-operation-control-v1/valid").glob(f"{scenario}-*.json"))
        ]
        assert reports
        for report in reports:
            kinds.add(report.message.kind)
            Draft202012Validator(contracts.schema_bundle()["backend-operation-response-v1"]).validate(
                report.model_dump(mode="json")
            )
        contracts.validate_backend_operation_history(op, reports, controls=controls)
    assert kinds == {"admission", "acknowledgement", "progress", "control", "outcome", "reconciliation"}


def test_existing_stub_does_not_advertise_operation_supervision():
    from raes_backend_stubs.manifest import create_stub_manifest
    from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS

    assert set(BACKEND_OPERATION_CONTRACT_IDS).isdisjoint(create_stub_manifest().supported_contract_versions)
