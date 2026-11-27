"""Provider replication intent remains distinct from unspecified placement."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from cloud_resource_fixtures import authority, cloud_scenario, secret
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaError
from pydantic import ValidationError
from raes import SDLInstantiationError, SDLValidationError, instantiate_scenario, parse_sdl
from raes.runtime_configuration import RuntimeSecretReplication, RuntimeServiceSecret

ROOT = Path(__file__).resolve().parents[3]
KEY = "projects/example/locations/{location}/keyRings/example/cryptoKeys/example"
AUTOMATIC = {"provider": "gcp-secret-manager", "mode": "automatic"}
MANAGED = {
    "provider": "gcp-secret-manager",
    "mode": "user-managed",
    "replicas": [
        {"location": "us-east1", "kms_key_name": KEY.format(location="us-east1")},
        {"location": "europe-west1"},
    ],
}


def replication_scenario(policy=MANAGED):
    raw = cloud_scenario()
    secret(raw)["replication"] = deepcopy(policy)
    return raw


@pytest.mark.parametrize(
    "policy", [None, AUTOMATIC, MANAGED, {**AUTOMATIC, "kms_key_name": KEY.format(location="global")}]
)
def test_policy_is_explicit_and_round_trips(policy):
    value = RuntimeServiceSecret(secret_id="example", replication=policy)
    assert RuntimeServiceSecret.model_validate_json(value.model_dump_json()) == value
    assert (value.replication is None) == (policy is None)
    if policy:
        assert value.replication.mode == policy["mode"]


def test_absent_and_empty_legacy_locations_do_not_mean_automatic():
    assert RuntimeServiceSecret(secret_id="a").replication is None
    assert RuntimeServiceSecret(secret_id="a", replica_locations=[]).replication is None
    assert RuntimeServiceSecret(secret_id="a", location="us-east1").replication is None


INVALID_POLICIES = [
    {},
    {"mode": "automatic"},
    {"provider": "aws", "mode": "automatic"},
    {"provider": "gcp-secret-manager", "mode": "userManaged"},
    {"provider": "gcp-secret-manager", "mode": "user-managed"},
    {**MANAGED, "replicas": []},
    {**AUTOMATIC, "replicas": [{"location": "us-east1"}]},
    {**MANAGED, "kms_key_name": KEY.format(location="global")},
    {**AUTOMATIC, "kms_key_name": KEY.format(location="us-east1")},
    {**AUTOMATIC, "kms_key_name": "invalid"},
    {**AUTOMATIC, "kms_key_name": ""},
    {**AUTOMATIC, "credentials": "synthetic-sentinel"},
    {**MANAGED, "replicas": [{"location": " "}]},
    {**MANAGED, "replicas": [{"location": "us-east1", "kms_key_name": KEY.format(location="global")}]},
    {**MANAGED, "replicas": [{"location": "us-east1"}] * 2},
    {**MANAGED, "replicas": [{"location": "us-east1", "value": "synthetic-sentinel"}]},
]


@pytest.mark.parametrize("policy", INVALID_POLICIES)
def test_malformed_or_contradictory_policy_is_rejected(policy):
    with pytest.raises(ValidationError):
        RuntimeSecretReplication.model_validate(policy)


@pytest.mark.parametrize(
    "legacy", [{"location": "us-east1"}, {"replica_locations": ["us-east1"]}, {"encryption_key_ref": "nodes.worker"}]
)
def test_legacy_fields_cannot_compete_with_a_typed_policy(legacy):
    with pytest.raises(ValidationError, match="legacy"):
        RuntimeServiceSecret(secret_id="a", replication=AUTOMATIC, **legacy)


def test_resource_scope_provider_must_agree_with_policy():
    raw = replication_scenario()
    authority(raw)["resource_scopes"][1]["provider"] = "aws"
    encoded = json.dumps(raw)
    with pytest.raises(SDLValidationError, match="gcp scope"):
        parse_sdl(encoded)


@pytest.mark.parametrize(
    "variable,value",
    [("region", "europe-west1"), ("mode", "automatic"), ("key", KEY.format(location="global")), ("provider", "aws")],
)
def test_substitution_revalidates_policy(variable, value):
    raw = replication_scenario()
    raw["variables"] = {
        "region": {"type": "string", "default": "us-east1"},
        "mode": {"type": "string", "default": "user-managed"},
        "key": {"type": "string", "default": KEY.format(location="us-east1")},
        "provider": {"type": "string", "default": "gcp"},
    }
    policy = secret(raw)["replication"]
    policy["mode"] = "${mode}"
    policy["replicas"][0] = {"location": "${region}", "kms_key_name": "${key}"}
    authority(raw)["resource_scopes"][1]["provider"] = "${provider}"
    parsed = parse_sdl(json.dumps(raw))
    instantiate_scenario(parsed)
    with pytest.raises(SDLInstantiationError):
        instantiate_scenario(parsed, {variable: value})


def test_substitution_rechecks_location_uniqueness():
    raw = replication_scenario()
    raw["variables"] = {"region": {"type": "string", "default": "europe-west1"}}
    secret(raw)["replication"]["replicas"][1]["location"] = "${region}"
    parsed = parse_sdl(json.dumps(raw))
    instantiate_scenario(parsed)
    with pytest.raises(SDLInstantiationError):
        instantiate_scenario(parsed, {"region": "us-east1"})


SCHEMAS = [
    "sdl/sdl-authoring-input-v1.json",
    "sdl/instantiated-scenario-v1.json",
    "sdl/instantiated-scenario-snapshot-v1.json",
    "sdl/materialized-scenario-v1.json",
    "satisfiability/scenario-satisfiability-evidence-v1.json",
]


@pytest.mark.parametrize("schema_name", SCHEMAS)
def test_published_schemas_preserve_policy_and_reject_bad_shapes(schema_name):
    schema = json.loads((ROOT / "contracts/schemas" / schema_name).read_text())
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/RuntimeServiceSecret"})
    for policy in (None, AUTOMATIC, MANAGED):
        validator.validate({"secret_id": "example", "replication": policy})
    # Cross-field location equality and uniqueness are callable semantic invariants.
    semantic_only = (8, 13, 14)
    for index, policy in enumerate(INVALID_POLICIES):
        if index in semantic_only:
            continue
        with pytest.raises(SchemaError):
            validator.validate({"secret_id": "example", "replication": policy})
    with pytest.raises(SchemaError):
        validator.validate({"secret_id": "example", "replication": AUTOMATIC, "location": "us-east1"})


def test_portable_location_invariant_is_callable():
    from importlib import import_module

    invariant = RuntimeSecretReplication.model_json_schema()["x-raes-invariants"][0]
    validator = import_module("raes.scenario")
    for token in invariant["validator"].removeprefix("raes.scenario.").split("."):
        validator = getattr(validator, token)
    raw = replication_scenario()
    validator(raw)
    secret(raw)["replication"]["replicas"][1]["location"] = "us-east1"
    with pytest.raises(ValidationError):
        validator(raw)
