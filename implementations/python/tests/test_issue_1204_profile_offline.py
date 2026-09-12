"""Profile schemas cannot turn inert identifiers into resource retrieval."""

import io
import json
import urllib.request

import pytest
from raes_contracts.domain_profiles import (
    DomainProfileAdmissionOutcome,
    DomainProfileAdmissionPolicyModel,
    DomainProfileOperation,
    admit_domain_profile_bindings,
)
from test_issue_1202_domain_profiles import _binding, _context, _definition_with_schema_document, _support


def _schema(child):
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:example:schema:repository",
        "$defs": {"name": {"type": "string"}},
        "type": "object",
        "properties": {"name": child},
    }


def _record_retrieval(monkeypatch):
    calls = []

    def retrieve(request, *_args, **_kwargs):
        calls.append(request.full_url)
        return io.BytesIO(json.dumps({"$defs": {"name": {"type": "string"}}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", retrieve)
    return calls


def _admit(document):
    definition = _definition_with_schema_document(document)
    support = _support(definition, *DomainProfileOperation)
    return admit_domain_profile_bindings(
        (_binding(definition, value={"name": "blue"}),),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(),
    )


@pytest.mark.parametrize("nested_id", ["http://127.0.0.1/profile", "file:///profile-must-not-be-read.json"])
def test_nested_schema_id_is_refused_without_retrieval(monkeypatch, nested_id):
    calls = _record_retrieval(monkeypatch)
    report = _admit(_schema({"$id": nested_id, "$ref": "#/$defs/name"}))
    assert calls == []
    assert not report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.SCHEMA_INVALID


def test_plan_profile_host_refuses_rebased_schema_before_backend_preparation(monkeypatch):
    import test_issue_1204_profile_carrier as host

    calls = _record_retrieval(monkeypatch)
    definition = _definition_with_schema_document(_schema({"$id": "http://127.0.0.1/profile", "$ref": "#/$defs/name"}))
    monkeypatch.setattr(host, "_definition", lambda **_kwargs: definition)
    backend = host._profile_backend()
    previous, result = host._apply_profile_request(backend)
    assert calls == []
    assert not result.success
    assert result.snapshot == previous
    assert (backend.prepares, backend.applies) == (0, 0)


def test_local_profile_reference_still_validates_without_retrieval(monkeypatch):
    calls = _record_retrieval(monkeypatch)
    assert _admit(_schema({"$ref": "#/$defs/name"})).admitted
    assert calls == []


@pytest.mark.parametrize("resource", ["http://127.0.0.1/profile", "file:///profile-must-not-be-read.json"])
def test_profile_validator_disables_retrieval_even_if_preflight_misses_a_reference(monkeypatch, resource):
    from raes_contracts import _domain_profile_validation as validation

    calls = _record_retrieval(monkeypatch)
    monkeypatch.setattr(validation, "_inspect_schema", lambda *_args, **_kwargs: None)
    report = _admit(_schema({"$ref": resource + "#/$defs/name"}))
    assert calls == []
    assert not report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.SCHEMA_INVALID


@pytest.mark.parametrize(
    "identity", [{"$id": "urn:example:nested"}, {"$schema": "http://json-schema.org/draft-07/schema#"}]
)
@pytest.mark.parametrize(
    "keyword",
    [
        "$defs",
        "dependentSchemas",
        "properties",
        "additionalProperties",
        "contains",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "allOf",
        "anyOf",
        "oneOf",
        "prefixItems",
    ],
)
def test_nested_resource_and_dialect_are_refused_at_every_schema_position(monkeypatch, identity, keyword):
    calls = _record_retrieval(monkeypatch)
    document = _schema({"type": "string"})
    if keyword in {"$defs", "dependentSchemas", "properties"}:
        document[keyword] = {"unused": identity}
    elif keyword in {"allOf", "anyOf", "oneOf", "prefixItems"}:
        document[keyword] = [identity]
    else:
        document[keyword] = identity
    report = _admit(document)
    assert not report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.SCHEMA_INVALID
    assert calls == []


@pytest.mark.parametrize(
    "key,reference",
    [
        ("with/slash", "#/$defs/with~1slash"),
        ("with~tilde", "#/$defs/with~0tilde"),
        ("with space", "#/$defs/with%20space"),
        ("with/slash", "#/$defs/with%7E1slash"),
    ],
)
@pytest.mark.parametrize("expected_type,accepted", [("string", True), ("integer", False)])
def test_preflight_and_runtime_use_the_same_local_pointer_semantics(
    monkeypatch, key, reference, expected_type, accepted
):
    calls = _record_retrieval(monkeypatch)
    document = _schema({"$ref": reference})
    document["$defs"] = {key: {"type": expected_type}}
    report = _admit(document)
    assert report.admitted is accepted
    if not accepted:
        assert report.results[0].outcome is DomainProfileAdmissionOutcome.VALUE_INVALID
    assert calls == []


@pytest.mark.parametrize("reference,accepted", [("#/examples/0", True), ("#/examples/1", False)])
def test_local_array_pointer_uses_the_same_bounded_resolver(monkeypatch, reference, accepted):
    calls = _record_retrieval(monkeypatch)
    document = _schema({"$ref": reference})
    document["examples"] = [{"type": "string"}]
    report = _admit(document)
    assert report.admitted is accepted
    if not accepted:
        assert report.results[0].outcome is DomainProfileAdmissionOutcome.SCHEMA_INVALID
    assert calls == []


@pytest.mark.parametrize("referenced", [False, True])
def test_annotation_identity_is_inert_unless_referenced_as_a_schema(monkeypatch, referenced):
    calls = _record_retrieval(monkeypatch)
    document = _schema({"$ref": "#/examples/0"} if referenced else {"type": "string"})
    document["examples"] = [{"$id": "http://127.0.0.1/profile", "type": "string"}]
    report = _admit(document)
    assert report.admitted is not referenced
    if referenced:
        assert report.results[0].outcome is DomainProfileAdmissionOutcome.SCHEMA_INVALID
    assert calls == []
