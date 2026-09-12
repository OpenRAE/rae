"""Issue #673 / DSL-439: typed account fixture-credential semantics."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import SDLValidationError, parse_sdl, parse_sdl_file
from raes.accounts import Account
from raes.scenario import Scenario
from raes.validator import SemanticValidator
from raes_backend_stubs.stubs import create_stub_manifest, create_stub_target
from raes_cli.processor import _execution_plan_payload
from raes_contracts.contracts import schema_bundle
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisioningPlan, ProvisionOp, RuntimeDomain
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, RuntimeSnapshotEnvelope, SnapshotEntry
from raes_processor.compiler import compile_runtime_model, compile_scenario_runtime_model
from raes_processor.planner import plan
from raes_runtime.backend_calls import _call_backend_apply, _call_backend_diagnostics
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_api_models import _snapshot_model
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
)
from raes_runtime.control_plane_store import _snapshot_payload
from raes_runtime.control_plane_submission import _submitted_plan_diagnostics
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_SENTINEL = "deliberately-weak-fixture"  # noqa: S105
OPERATOR_REFERENCE = "operator-secret.web-bootstrap"  # noqa: S105


def _account_payload() -> dict[str, object]:
    return {
        "username": "admin",
        "node": "web",
        "password_strength": "weak",
        "auth_method": "PASSWORD",
        "credential_bindings": [
            {
                "credential_id": "primary-login",
                "purpose": "primary-authentication",
                "auth_method": "password",
                "material": {
                    "classification": "secret_fixture",
                    "value": FIXTURE_SENTINEL,
                },
            },
            {
                "credential_id": "operator-bootstrap",
                "purpose": "administrative_authentication",
                "auth_method": "certificate",
                "material": {
                    "classification": "operator_secret",
                    "reference_id": OPERATOR_REFERENCE,
                },
            },
        ],
    }


def _scenario_with_account(account: dict[str, object]) -> Scenario:
    return Scenario.model_validate(
        {
            "name": "credential-bindings",
            "nodes": {
                "web": {
                    "type": "compute",
                    "os": "linux",
                    "resources": {"ram": "1 gib", "cpu": 1},
                }
            },
            "accounts": {"admin": account},
        }
    )


def _semantic_errors(scenario: Scenario) -> list[str]:
    try:
        SemanticValidator(scenario).validate()
    except SDLValidationError as exc:
        return list(exc.errors)
    return []


def _credential_plan(account: dict[str, object] | None = None) -> ProvisioningPlan:
    return ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.account.admin",
                resource_type="account-placement",
                payload={
                    "name": "admin",
                    "account_name": "admin",
                    "node_name": "web",
                    "target_address": "provision.node.web",
                    "spec": account or _account_payload(),
                },
            )
        ]
    )


def test_account_distinguishes_posture_fixture_and_operator_reference() -> None:
    account = Account.model_validate(_account_payload())

    assert account.password_strength.value == "weak"
    assert account.auth_method.value == "password"
    assert account.credential_bindings[0].material.classification == "secret_fixture"
    assert account.credential_bindings[0].material.value == FIXTURE_SENTINEL
    assert account.credential_bindings[1].material.classification == "operator_secret"
    assert account.credential_bindings[1].material.reference_id == OPERATOR_REFERENCE


@pytest.mark.parametrize(
    "material",
    [
        {"value": FIXTURE_SENTINEL},
        {"classification": "secret_fixture", "reference_id": OPERATOR_REFERENCE},
        {
            "classification": "operator_secret",
            "reference_id": OPERATOR_REFERENCE,
            "value": FIXTURE_SENTINEL,
        },
        {"classification": "operator_secret", "value": FIXTURE_SENTINEL},
        {"classification": "unknown", "value": FIXTURE_SENTINEL},
    ],
)
def test_account_rejects_unclassified_or_mixed_material(material: dict[str, str]) -> None:
    payload = _account_payload()
    payload["credential_bindings"] = [
        {
            "credential_id": "primary-login",
            "purpose": "primary_authentication",
            "auth_method": "password",
            "material": material,
        }
    ]

    with pytest.raises(ValidationError):
        Account.model_validate(payload)


def test_nested_binding_rejects_cross_account_target() -> None:
    payload = _account_payload()
    payload["credential_bindings"][0]["account_ref"] = "other-account"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Account.model_validate(payload)


def test_operator_reference_rejects_locator_and_environment_conventions() -> None:
    for reference in ("${HOME}", "/run/secrets/admin", "env.ADMIN_PASSWORD", "https://vault.test/secret"):
        payload = _account_payload()
        payload["credential_bindings"][1]["material"]["reference_id"] = reference
        with pytest.raises(ValidationError):
            Account.model_validate(payload)


def test_semantic_validation_rejects_duplicate_purpose_method_without_material_disclosure() -> None:
    payload = _account_payload()
    payload["credential_bindings"].append(
        {
            "credential_id": "duplicate-login",
            "purpose": "primary_authentication",
            "auth_method": "password",
            "material": {"classification": "secret_fixture", "value": "second-fixture"},
        }
    )

    errors = _semantic_errors(_scenario_with_account(payload))

    assert any("duplicate credential purpose and authentication method" in error for error in errors)
    assert all(FIXTURE_SENTINEL not in error and "second-fixture" not in error for error in errors)


@pytest.mark.parametrize(
    "bindings",
    [
        [
            {
                "credential_id": "admin-login",
                "purpose": "administrative_authentication",
                "auth_method": "password",
                "material": {"classification": "secret_fixture", "value": FIXTURE_SENTINEL},
            }
        ],
        [
            {
                "credential_id": "primary-login",
                "purpose": "primary_authentication",
                "auth_method": "certificate",
                "material": {"classification": "operator_secret", "reference_id": OPERATOR_REFERENCE},
            }
        ],
    ],
)
def test_semantic_validation_requires_one_primary_binding_matching_account_posture(
    bindings: list[dict[str, object]],
) -> None:
    payload = _account_payload()
    payload["credential_bindings"] = bindings

    errors = _semantic_errors(_scenario_with_account(payload))

    assert any("primary credential binding" in error for error in errors)
    assert all(FIXTURE_SENTINEL not in error and OPERATOR_REFERENCE not in error for error in errors)


def test_instantiation_revalidates_bound_purpose_method_and_material() -> None:
    scenario = parse_sdl(
        textwrap.dedent(
            """
            name: bound-credentials
            variables:
              purpose: {type: string, default: primary_authentication}
              method: {type: string, default: password}
              fixture: {type: string, default: deliberately-weak-fixture}
              secret_ref: {type: string, default: operator-secret.web-bootstrap}
            nodes:
              web:
                type: compute
                os: linux
                resources: {ram: 1 gib, cpu: 1}
            accounts:
              admin:
                username: admin
                node: web
                auth_method: ${method}
                credential_bindings:
                  - credential_id: primary-login
                    purpose: ${purpose}
                    auth_method: ${method}
                    material: {classification: secret_fixture, value: "${fixture}"}
                  - credential_id: operator-bootstrap
                    purpose: administrative_authentication
                    auth_method: certificate
                    material: {classification: operator_secret, reference_id: "${secret_ref}"}
            """
        )
    )

    model = compile_scenario_runtime_model(scenario)
    account = model.account_placements["provision.account.admin"]

    assert account.spec["credential_bindings"][0]["material"]["value"] == FIXTURE_SENTINEL
    assert account.spec["credential_bindings"][1]["material"]["reference_id"] == OPERATOR_REFERENCE
    assert model.realization_instance.instantiation_provenance.bindings


def test_composition_keeps_bindings_nested_under_the_qualified_account(tmp_path: Path) -> None:
    module = tmp_path / "accounts.yaml"
    module.write_text(
        textwrap.dedent(
            f"""
            name: credential-module
            module:
              id: example/accounts
              version: 1.0.0
              exports:
                nodes: [web]
                accounts: [admin]
            nodes:
              web: {{type: compute, os: linux, resources: {{ram: 1 gib, cpu: 1}}}}
            accounts:
              admin:
                username: admin
                node: web
                auth_method: password
                credential_bindings:
                  - credential_id: primary-login
                    purpose: primary_authentication
                    auth_method: password
                    material: {{classification: secret_fixture, value: {FIXTURE_SENTINEL}}}
                  - credential_id: operator-bootstrap
                    purpose: administrative_authentication
                    auth_method: certificate
                    material: {{classification: operator_secret, reference_id: {OPERATOR_REFERENCE}}}
            """
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: composed
            imports:
              - path: accounts.yaml
                namespace: shared
            """
        ),
        encoding="utf-8",
    )

    account = parse_sdl_file(root).accounts["shared.admin"]

    assert account.node == "shared.web"
    assert account.credential_bindings[0].material.value == FIXTURE_SENTINEL
    assert account.credential_bindings[1].material.reference_id == OPERATOR_REFERENCE


def test_provisioner_feature_gate_rejects_unadvertised_credential_bindings() -> None:
    scenario = _scenario_with_account(_account_payload())
    model = compile_runtime_model(scenario)
    execution_plan = plan(model, create_stub_manifest())

    assert any(
        diagnostic.code == "provisioner.unsupported-account-feature" and "credential_bindings" in diagnostic.message
        for diagnostic in execution_plan.diagnostics
    )


def test_direct_plan_submission_reconstructs_account_and_fails_closed() -> None:
    plan_value = _credential_plan()
    diagnostics = _submitted_plan_diagnostics(
        plan_value,
        RuntimeDomain.PROVISIONING,
        RuntimeSnapshot(),
        create_stub_manifest(),
    )

    assert diagnostics
    assert diagnostics[0].code == "provisioner.unsupported-account-feature"
    assert "credential_bindings" in diagnostics[0].message


def test_generic_plan_output_is_value_free() -> None:
    execution_plan = plan(
        compile_runtime_model(_scenario_with_account(_account_payload())),
        create_stub_manifest(),
    )

    rendered = json.dumps(_execution_plan_payload(execution_plan), sort_keys=True)

    assert FIXTURE_SENTINEL not in rendered
    assert OPERATOR_REFERENCE not in rendered
    assert "secret_fixture" in rendered
    assert "operator_secret" in rendered


def test_generic_plan_projection_preserves_typed_identity_on_token_collision() -> None:
    payload = _account_payload()
    payload["credential_bindings"][0]["material"]["value"] = "admin"
    execution_plan = plan(
        compile_runtime_model(_scenario_with_account(payload)),
        create_stub_manifest(),
    )

    rendered = _execution_plan_payload(execution_plan)
    account_operation = next(
        operation
        for operation in rendered["provisioning"]["operations"]
        if operation["resource_type"] == "account-placement"
    )

    assert account_operation["address"] == "provision.account.admin"
    assert account_operation["payload"]["account_name"] == "admin"
    assert account_operation["payload"]["spec"]["credential_bindings"][0]["material"] == {
        "classification": "secret_fixture",
        "value_present": True,
    }


def test_backend_result_sanitizes_snapshot_diagnostics_and_details() -> None:
    plan_value = _credential_plan()
    address = "provision.account.admin"

    def apply(_plan: ProvisioningPlan, _snapshot: RuntimeSnapshot) -> ApplyResult:
        snapshot = RuntimeSnapshot(
            entries={
                address: SnapshotEntry(
                    address=address,
                    domain=RuntimeDomain.PROVISIONING,
                    resource_type="account-placement",
                    payload=plan_value.operations[0].payload,
                    status="applied",
                )
            }
        )
        return ApplyResult(
            success=True,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="backend.account-applied",
                    domain="runtime",
                    address=address,
                    message=f"applied {FIXTURE_SENTINEL} via {OPERATOR_REFERENCE}",
                )
            ],
            changed_addresses=[address],
        )

    result = _call_backend_apply(
        apply,
        plan_value,
        RuntimeSnapshot(),
        address="runtime.test.apply",
        snapshot=RuntimeSnapshot(),
    )
    rendered = json.dumps(
        {
            "snapshot": result.snapshot.entries[address].payload,
            "diagnostics": [diagnostic.message for diagnostic in result.diagnostics],
            "details": result.details,
        },
        sort_keys=True,
    )

    assert result.success
    assert FIXTURE_SENTINEL not in rendered
    assert OPERATOR_REFERENCE not in rendered
    assert result.diagnostics[0].message == "Backend reported an account credential diagnostic."


def test_backend_validation_diagnostic_does_not_echo_credential_material() -> None:
    plan_value = _credential_plan()

    def validate(_plan: ProvisioningPlan) -> list[Diagnostic]:
        return [
            Diagnostic(
                code="backend.account-invalid",
                domain="runtime",
                address="provision.account.admin",
                message=f"rejected {FIXTURE_SENTINEL} via {OPERATOR_REFERENCE} after resolving unknown-secret",
            )
        ]

    diagnostics = _call_backend_diagnostics(
        validate,
        plan_value,
        address="runtime.test.validate",
    )

    assert FIXTURE_SENTINEL not in diagnostics[0].message
    assert OPERATOR_REFERENCE not in diagnostics[0].message
    assert "unknown-secret" not in diagnostics[0].message


def test_backend_result_fails_closed_on_credential_material_mapping_key() -> None:
    plan_value = _credential_plan()

    def apply(_plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=snapshot,
            details={FIXTURE_SENTINEL: "present"},
        )

    result = _call_backend_apply(
        apply,
        plan_value,
        RuntimeSnapshot(),
        address="runtime.test.apply",
        snapshot=RuntimeSnapshot(),
    )

    assert not result.success
    assert FIXTURE_SENTINEL not in json.dumps([diagnostic.message for diagnostic in result.diagnostics])


def test_backend_result_rejects_resolved_secret_in_unapproved_carriers() -> None:
    plan_value = _credential_plan()

    def apply_with_details(_plan: ProvisioningPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(success=True, snapshot=snapshot, details={"resolved": "unknown-secret"})

    details_result = _call_backend_apply(
        apply_with_details,
        plan_value,
        RuntimeSnapshot(),
        address="runtime.test.apply",
        snapshot=RuntimeSnapshot(),
    )

    assert not details_result.success
    assert "unknown-secret" not in json.dumps([item.message for item in details_result.diagnostics])

    def apply_with_metadata(_plan: ProvisioningPlan, _snapshot: RuntimeSnapshot) -> ApplyResult:
        address = plan_value.operations[0].address
        return ApplyResult(
            success=True,
            snapshot=RuntimeSnapshot(
                entries={
                    address: SnapshotEntry(
                        address=address,
                        domain=RuntimeDomain.PROVISIONING,
                        resource_type="account-placement",
                        payload=plan_value.operations[0].payload,
                        status="applied",
                    )
                },
                metadata={"resolved": "unknown-secret"},
            ),
            changed_addresses=[address],
        )

    metadata_result = _call_backend_apply(
        apply_with_metadata,
        plan_value,
        RuntimeSnapshot(),
        address="runtime.test.apply",
        snapshot=RuntimeSnapshot(),
    )

    assert not metadata_result.success
    assert "unknown-secret" not in json.dumps([item.message for item in metadata_result.diagnostics])


def test_generic_snapshot_persistence_and_api_projection_are_value_free() -> None:
    address = "provision.account.admin"
    snapshot = RuntimeSnapshot(
        entries={
            address: SnapshotEntry(
                address=address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type="account-placement",
                payload=_credential_plan().operations[0].payload,
            )
        },
        metadata={"unrelated": {"classification": "secret_fixture", "value": "ordinary-data"}},
    )

    persisted = json.dumps(_snapshot_payload(snapshot), sort_keys=True)
    published = _snapshot_model(RuntimeSnapshotEnvelope(snapshot=snapshot)).model_dump_json()

    assert FIXTURE_SENTINEL not in persisted
    assert OPERATOR_REFERENCE not in persisted
    assert FIXTURE_SENTINEL not in published
    assert OPERATOR_REFERENCE not in published
    assert json.loads(persisted)["metadata"]["unrelated"]["value"] == "ordinary-data"
    assert json.loads(published)["metadata"]["unrelated"]["value"] == "ordinary-data"


def test_collision_remains_valid_across_backend_store_and_snapshot_api() -> None:
    account = _account_payload()
    account["credential_bindings"][0]["material"]["value"] = "admin"
    plan_value = _credential_plan(account)
    address = "provision.account.admin"

    def apply(_plan: ProvisioningPlan, _snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=RuntimeSnapshot(
                entries={
                    address: SnapshotEntry(
                        address=address,
                        domain=RuntimeDomain.PROVISIONING,
                        resource_type="account-placement",
                        payload=plan_value.operations[0].payload,
                        status="applied",
                    )
                }
            ),
            changed_addresses=[address],
        )

    result = _call_backend_apply(
        apply,
        plan_value,
        RuntimeSnapshot(),
        address="runtime.test.apply",
        snapshot=RuntimeSnapshot(),
    )
    persisted = _snapshot_payload(result.snapshot)
    published = _snapshot_model(RuntimeSnapshotEnvelope(snapshot=result.snapshot)).model_dump(mode="json")

    assert result.success
    assert persisted["entries"][address]["payload"]["account_name"] == "admin"
    assert published["entries"][address]["payload"]["account_name"] == "admin"
    assert persisted["entries"][address]["payload"]["spec"]["credential_bindings"][0]["material"] == {
        "classification": "secret_fixture",
        "value_present": True,
    }


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("auth_method",), "${method}"),
        (("credential_bindings", 0, "purpose"), "${purpose}"),
        (("credential_bindings", 0, "material", "value"), "${fixture}"),
        (("credential_bindings", 1, "material", "reference_id"), "${secret_ref}"),
    ],
)
def test_satisfiability_witness_schema_rejects_unresolved_credential_fields(
    field_path: tuple[str | int, ...],
    value: str,
) -> None:
    evidence_schema = schema_bundle()["scenario-satisfiability-evidence-v1"]
    account_schema = {
        "$schema": evidence_schema["$schema"],
        "$defs": evidence_schema["$defs"],
        "$ref": "#/$defs/Account",
    }
    account = _account_payload()
    # This test exercises the raw generated schema rather than Account's
    # case-normalizing Pydantic model, so start from the schema's canonical
    # lowercase representation before isolating each unresolved field.
    account["auth_method"] = "password"
    assert Draft202012Validator(account_schema).is_valid(account)

    target: object = account
    for segment in field_path[:-1]:
        target = target[segment]
    target[field_path[-1]] = value

    assert not Draft202012Validator(account_schema).is_valid(account)


def test_http_422_response_does_not_echo_rejected_credential_input() -> None:
    target = create_stub_target()
    security = ControlPlaneSecurityConfig(
        trust_proxy_identity_headers=False,
        bearer_tokens={
            "operator-token": ControlPlaneIdentity(
                identity="operator",
                roles=frozenset({ControlPlaneRole.OPERATOR}),
                target_name=target.name,
            )
        },
    )
    app = create_control_plane_app(RuntimeControlPlane(target), security=security)

    with TestClient(app) as client:
        response = client.post(
            "/operations/provisioning",
            headers={"authorization": "Bearer operator-token"},
            json={"operations": [], "credential_input": FIXTURE_SENTINEL},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "request validation failed"}
    assert FIXTURE_SENTINEL not in response.text


def test_generated_contract_and_authority_surfaces_publish_credential_bindings() -> None:
    account_schema = schema_bundle()["sdl-authoring-input-v1"]["$defs"]["Account"]
    vocabularies = json.loads(
        (REPO_ROOT / "contracts/concept-authority/controlled-vocabularies-v1.json").read_text(encoding="utf-8")
    )["vocabularies"]
    reference_model = json.loads(
        (REPO_ROOT / "contracts/concept-authority/reference-models-v1.json").read_text(encoding="utf-8")
    )["models"]["scenario-account"]

    assert "credential_bindings" in account_schema["properties"]
    assert set(vocabularies) >= {"account-authentication-methods", "account-credential-purposes"}
    assert "credential_bindings" in vocabularies["provisioner-account-features"]["terms"]
    assert "credential_bindings" in reference_model["key_fields"]
