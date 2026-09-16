"""Portable exchange exposes a structural promise, not proof of authorization."""

import pytest
from jsonschema import Draft202012Validator
from raes_conformance.conformance import contract_validation_strength, validate_contract_payload
from raes_contracts.contracts import schema_bundle
from test_issue_1242_scope_admission import preview, scoped_plan


def test_preparation_conformance_does_not_claim_source_bound_admission():
    _, report = preview(scoped_plan({"default": "closed"}))
    payload = report.model_dump(mode="json")
    assert not validate_contract_payload("backend-augmentation-scope-v1", payload)
    assert contract_validation_strength("backend-augmentation-scope-v1") == "structural"
    assert not list(Draft202012Validator(schema_bundle()["backend-augmentation-scope-v1"]).iter_errors(payload))


@pytest.mark.parametrize(
    "update",
    [
        {"unexpected": "raw backend prose"},
        {"coverage_profile": "partial"},
        {"binding_digest": "unbound"},
    ],
)
def test_published_preparation_and_model_reject_weakened_wire_promises(update):
    _, report = preview(scoped_plan({"default": "open"}))
    payload = {**report.model_dump(mode="json"), **update}
    assert validate_contract_payload("backend-augmentation-scope-v1", payload)
    assert list(Draft202012Validator(schema_bundle()["backend-augmentation-scope-v1"]).iter_errors(payload))
