"""Private identities exercise portable language contracts, not product recipes."""

from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import instantiate_scenario, parse_sdl
from raes.nodes import Node
from raes.runtime_app_authorization import (
    RuntimeAppAuthorization,
    RuntimeAppAuthorizationGrant,
    RuntimeAppAuthorizationGrantEffect,
)
from raes.runtime_configuration import RuntimeConfiguration
from raes.runtime_database import RuntimeDatabaseService
from raes.runtime_database_vocab import DatabaseEngine
from raes.runtime_filesystem import RuntimeSensitivityClassification
from raes.runtime_values import parse_runtime_enum_or_var
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization_concerns import project_realization_concern


@pytest.mark.parametrize("token", ["x-lab:engine-a", "x-other:engine-a", "x-lab:engine-b"])
def test_private_database_identity_survives_model_and_json_roundtrips(token):
    service = RuntimeDatabaseService(database_service_id="database", engine=token)
    assert service.engine == token
    payload = service.model_dump(mode="json")
    assert payload["engine"] == token
    assert RuntimeDatabaseService.model_validate_json(service.model_dump_json()).engine == token
    assert Draft202012Validator(RuntimeDatabaseService.model_json_schema()).is_valid(payload)


@pytest.mark.parametrize("token", ["private-engine", "x-Lab:engine", "x-lab:engine\n", "x-lab:engine_1"])
def test_malformed_identity_is_rejected_by_parser_and_schema(token):
    payload = {"database_service_id": "database", "engine": token}
    with pytest.raises(ValidationError):
        RuntimeDatabaseService.model_validate(payload)
    assert not Draft202012Validator(RuntimeDatabaseService.model_json_schema()).is_valid(payload)


def test_builtin_aliases_still_return_enum_members():
    assert parse_runtime_enum_or_var("PostgreSQL", DatabaseEngine, field_name="engine") is DatabaseEngine.POSTGRESQL


@pytest.mark.parametrize("enum_type", [RuntimeAppAuthorizationGrantEffect, RuntimeSensitivityClassification])
def test_private_names_cannot_add_grant_effects_or_bypass_redaction(enum_type):
    with pytest.raises(ValueError):
        parse_runtime_enum_or_var("x-lab:allow", enum_type, field_name="policy")


def test_grant_schema_does_not_admit_a_new_effect():
    payload = {"grant_id": "grant", "effect": "x-lab:allow"}
    with pytest.raises(ValidationError):
        RuntimeAppAuthorizationGrant.model_validate(payload)
    assert not Draft202012Validator(RuntimeAppAuthorizationGrant.model_json_schema()).is_valid(payload)


def test_private_resource_vocabulary_keeps_grant_agreement():
    with pytest.raises(ValidationError):
        RuntimeAppAuthorization(app_authorization_id="authorization", resource_vocabulary="x-lab:resource")
    authorization = RuntimeAppAuthorization(
        app_authorization_id="authorization",
        resource_vocabulary="x-lab:resource",
        permission_grants=[{"grant_id": "grant", "resource_kind": "x-lab:resource", "effect": "deny"}],
    )
    assert authorization.permission_grants[0].effect is RuntimeAppAuthorizationGrantEffect.DENY


def test_governed_os_family_matches_the_capability_identity_contract():
    node = Node(type="compute", os="x-lab:os")
    assert node.model_dump(mode="json")["os"] == "x-lab:os"
    assert Node.model_validate_json(node.model_dump_json()).os == "x-lab:os"


def _database_constraint(engine):
    source = f"""
name: private-identity
realization: {{default: open}}
nodes:
  host:
    type: compute
    runtime:
      database_services:
        - {{database_service_id: database, engine: '{engine}'}}
"""
    model = compile_runtime_model(instantiate_scenario(parse_sdl(source)))
    requirement = next(r for r in model.realization_requirements if r.requirement_kind == "runtime-database-services")
    assert not requirement.structure_error
    assert requirement.constraint_document is not None
    return requirement.constraint_document


def test_private_identity_is_binding_inside_an_inherited_open_scope():
    document = _database_constraint("x-lab:engine-a")
    runtime = RuntimeConfiguration.model_validate(
        {"database_services": [{"database_service_id": "database", "engine": "x-lab:engine-a"}]}
    )
    projected = project_realization_concern("runtime-database-services", runtime.database_services, recursive=True)
    assert evaluate_realization_constraint(document, projected).conformant
    for field, replacement in (("engine", "x-lab:engine-b"), ("database_service_id", "replacement")):
        changed = deepcopy(projected)
        changed[0][field] = replacement
        assert not evaluate_realization_constraint(document, changed).conformant


@pytest.mark.parametrize("sentinel", ["unknown", "other"])
def test_unknown_identity_does_not_authorize_a_core_product_completion(sentinel):
    document = _database_constraint(sentinel)
    engine = document.root.members[0].constraint.fields["engine"]
    assert engine.kind == "knowledge"
    candidate = RuntimeDatabaseService(database_service_id="database", engine="postgresql", protocol="postgresql")
    projected = project_realization_concern("runtime-database-services", [candidate], recursive=True)
    result = evaluate_realization_constraint(document, projected)
    assert not result.conformant
    assert result.status.value == "unresolved"


def test_known_engine_rejects_private_protocol_without_leaking_identity():
    # A spelling accepted as identity must not bypass the engine's owned constraint.
    with pytest.raises(ValidationError) as exc:
        RuntimeDatabaseService(database_service_id="database", engine="postgresql", protocol="x-lab:private")
    assert "requires protocol" in exc.value.errors(include_input=False)[0]["msg"]
    assert "x-lab:private" not in exc.value.errors(include_input=False)[0]["msg"]
