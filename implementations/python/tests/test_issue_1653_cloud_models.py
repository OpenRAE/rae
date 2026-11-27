"""Cloud state extends existing identity and application owners."""

import json
from pathlib import Path

import pytest
from cloud_resource_fixtures import DISABLED, PRINCIPAL, SCOPE_A, SCOPE_B, VERSION, authority, cloud_scenario, secret
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as SchemaValidationError
from pydantic import ValidationError
from raes.runtime_identity_resources import (
    RuntimeIdentityAccessObservation,
    RuntimeIdentityPermissionBinding,
    RuntimeIdentityResourceAccess,
)
from raes.runtime_secret_service import RuntimeSecretConsumer, RuntimeSecretVersion
from raes.scenario import Scenario
from raes.validator import SemanticValidator


def test_cross_project_state_does_not_require_host_details_or_credentials():
    scenario = Scenario.model_validate(cloud_scenario())
    SemanticValidator(scenario).validate()
    identity = scenario.nodes["iam"].runtime.identity_authorities[0]
    assert identity.subjects[0].resource_scope_ref == SCOPE_A
    assert identity.identity_uses[0].principal_ref == PRINCIPAL
    assert scenario.nodes["worker"].os is None
    assert not scenario.accounts
    assert scenario.nodes["secrets"].runtime.platform_applications[0].secrets[0].resource_scope_ref == SCOPE_B


def test_disabled_exact_selection_is_describable_without_fallback():
    raw = cloud_scenario()
    secret(raw)["consumers"][0]["version_ref"] = DISABLED
    scenario = Scenario.model_validate(raw)
    SemanticValidator(scenario).validate()
    selection = scenario.nodes["secrets"].runtime.platform_applications[0].secrets[0].consumers[0]
    assert selection.version_ref == DISABLED
    assert selection.resolved_version_ref == ""


def test_conditions_remain_inert_and_do_not_create_an_access_result():
    raw = cloud_scenario()
    identity = authority(raw)
    identity["access_observations"] = []
    expression = 'resource.name.startsWith("Project-B/") && do_not_execute()'
    identity["policies"][0]["resource_access"]["bindings"][0]["condition"] = {
        "language": "cel",
        "expression": expression,
    }
    scenario = Scenario.model_validate(raw)
    SemanticValidator(scenario).validate()
    policy = scenario.nodes["iam"].runtime.identity_authorities[0].policies[0]
    assert policy.resource_access.bindings[0].condition.expression == expression
    assert scenario.nodes["iam"].runtime.identity_authorities[0].access_observations == []


@pytest.mark.parametrize("outcome", ["unknown", "unsupported"])
def test_non_decided_access_needs_no_fabricated_evidence(outcome):
    raw = cloud_scenario()
    observation = authority(raw)["access_observations"][0]
    observation.update(outcome=outcome, evidence_refs=[])
    scenario = Scenario.model_validate(raw)
    SemanticValidator(scenario).validate()
    assert scenario.nodes["iam"].runtime.identity_authorities[0].access_observations[0].outcome == outcome


@pytest.mark.parametrize("outcome", ["allowed", "denied"])
def test_decided_access_requires_its_own_evidence(outcome):
    raw = cloud_scenario()
    authority(raw)["access_observations"][0].update(outcome=outcome, evidence_refs=[])
    with pytest.raises(ValidationError, match="evidence"):
        Scenario.model_validate(raw)


def test_raw_payload_cannot_be_put_in_a_version():
    raw = cloud_scenario()
    secret(raw)["versions"][0]["value"] = "synthetic-protected-sentinel"
    with pytest.raises(ValidationError, match="Extra inputs"):
        Scenario.model_validate(raw)


def test_destroyed_version_has_no_live_payload_source():
    raw = cloud_scenario()
    secret(raw)["versions"][2]["payload_content_ref"] = "content.fixture"
    with pytest.raises(ValidationError, match="destroyed"):
        Scenario.model_validate(raw)


def test_exact_selection_cannot_report_another_version():
    raw = cloud_scenario()
    secret(raw)["consumers"][0].update(
        resolved_version_ref=DISABLED, resolution_basis="observed", resolution_evidence_refs=["urn:example:selection"]
    )
    with pytest.raises(ValidationError, match="exact"):
        Scenario.model_validate(raw)


def test_alias_selection_preserves_intent_and_observed_resolution():
    raw = cloud_scenario()
    selection = secret(raw)["consumers"][0]
    selection.pop("version_ref")
    selection.update(
        selector={"kind": "alias", "value": "latest"},
        resolved_version_ref=VERSION,
        resolution_basis="observed",
        resolution_evidence_refs=["urn:example:selection"],
    )
    scenario = Scenario.model_validate(raw)
    SemanticValidator(scenario).validate()
    result = scenario.nodes["secrets"].runtime.platform_applications[0].secrets[0].consumers[0]
    assert result.selector.value == "latest"
    assert result.resolved_version_ref == VERSION


def test_observed_resolution_requires_evidence():
    raw = cloud_scenario()
    secret(raw)["consumers"][0].update(resolved_version_ref=VERSION, resolution_basis="observed")
    with pytest.raises(ValidationError, match="evidence"):
        Scenario.model_validate(raw)


@pytest.mark.parametrize(
    "model,payload",
    [
        (
            RuntimeIdentityAccessObservation,
            {
                "observation_id": "a",
                "principal_ref": PRINCIPAL,
                "resource_ref": VERSION,
                "action": "read",
                "outcome": "allowed",
            },
        ),
        (RuntimeSecretVersion, {"version_id": "v1", "state": "destroyed", "payload_content_ref": "content.fixture"}),
        (RuntimeSecretConsumer, {"selection_id": "a", "consumer_ref": "nodes.worker"}),
        (
            RuntimeSecretConsumer,
            {
                "selection_id": "a",
                "consumer_ref": "nodes.worker",
                "version_ref": VERSION,
                "selector": {"kind": "alias", "value": "latest"},
            },
        ),
        (
            RuntimeSecretConsumer,
            {
                "selection_id": "a",
                "consumer_ref": "nodes.worker",
                "version_ref": VERSION,
                "resolved_version_ref": VERSION,
                "resolution_basis": "observed",
            },
        ),
    ],
)
def test_structural_schemas_enforce_local_security_and_selection_rules(model, payload):
    validator = Draft202012Validator(model.model_json_schema())
    with pytest.raises(SchemaValidationError):
        validator.validate(payload)


@pytest.mark.parametrize("role_ref,actions", [("", []), ("", None)])
def test_policy_binding_schema_requires_actions_or_a_role(role_ref, actions):
    payload = {
        "binding_id": "read",
        "principal_refs": [PRINCIPAL],
        "resource_refs": [VERSION],
        "effect": "allow",
        "role_ref": role_ref,
    }
    if actions is not None:
        payload["actions"] = actions
    with pytest.raises(ValidationError):
        RuntimeIdentityPermissionBinding.model_validate(payload)
    validator = Draft202012Validator(RuntimeIdentityPermissionBinding.model_json_schema())
    with pytest.raises(SchemaValidationError):
        validator.validate(payload)


def test_inherited_policy_schema_rejects_copied_bindings():
    payload = {
        "attachment_ref": SCOPE_B,
        "inherited_from_ref": "nodes.iam.runtime.identity_authorities.cloud.policies.reader",
        "bindings": [
            {
                "binding_id": "read",
                "principal_refs": [PRINCIPAL],
                "resource_refs": [VERSION],
                "actions": ["read"],
                "effect": "allow",
            }
        ],
    }
    with pytest.raises(ValidationError):
        RuntimeIdentityResourceAccess.model_validate(payload)
    validator = Draft202012Validator(RuntimeIdentityResourceAccess.model_json_schema())
    with pytest.raises(SchemaValidationError):
        validator.validate(payload)


@pytest.mark.parametrize(
    "schema_path",
    [
        "sdl/sdl-authoring-input-v1.json",
        "sdl/instantiated-scenario-v1.json",
        "sdl/instantiated-scenario-snapshot-v1.json",
        "sdl/materialized-scenario-v1.json",
        "satisfiability/scenario-satisfiability-evidence-v1.json",
    ],
)
@pytest.mark.parametrize("rule", ["actions-or-role", "inherited-view"])
def test_published_policy_schemas_reject_invalid_field_combinations(schema_path, rule):
    raw = cloud_scenario()
    access = authority(raw)["policies"][0]["resource_access"]
    if rule == "actions-or-role":
        payload = access["bindings"][0]
        payload.pop("actions")
        definition = "RuntimeIdentityPermissionBinding"
    else:
        access["inherited_from_ref"] = "nodes.iam.runtime.identity_authorities.cloud.policies.source"
        payload = access
        definition = "RuntimeIdentityResourceAccess"
    root = Path(__file__).resolve().parents[3] / "contracts/schemas"
    definitions = json.loads((root / schema_path).read_text())["$defs"]
    validator = Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": definitions})
    with pytest.raises(SchemaValidationError):
        validator.validate(payload)
