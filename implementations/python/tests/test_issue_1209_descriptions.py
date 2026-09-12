"""Partial descriptions retain knowledge without acquiring author authority."""

from __future__ import annotations

import json
from copy import deepcopy
from functools import cache
from pathlib import Path

import pytest
from pydantic import ValidationError
from raes_contracts.contracts import ExperimentEvidenceRecordModel, ExperimentRealizedFormDisclosureModel


def description_payload():
    return {
        "schema_version": "realization-description/v1",
        "description_id": "capture-1",
        "description_version": "1",
        "semantic_profile": "example-state/v1",
        "authored_ref": {
            "ref_kind": "scenario",
            "ref_id": "original",
            "ref_version": "1",
            "ref_digest": "sha256:" + "a" * 64,
        },
        "provenance": {
            "observer_ref": {"ref_kind": "backend", "ref_id": "example", "ref_version": "1"},
            "recorded_at": "2026-09-12T10:00:00Z",
            "basis": "backend-selected",
            "window_ref": "selection-1",
        },
        "facts": [
            {
                "fact_id": "family",
                "subject": "/nodes/a/family",
                "state": "known",
                "value": {"kind": "literal", "value": "linux", "origin": "backend"},
            },
            {"fact_id": "release", "subject": "/nodes/a/release", "state": "not-observed"},
            {"fact_id": "absent", "subject": "/nodes/a/optional", "state": "known-absent"},
            {
                "fact_id": "private",
                "subject": "/nodes/a/private",
                "state": "withheld",
                "limitations": ["Not disclosed under the selected policy."],
            },
        ],
        "coverage": [
            {
                "subject": "/nodes/a",
                "kind": "field",
                "universe": "node-fields/v1",
                "profile": "example-state/v1",
                "status": "partial",
                "fact_ids": ["family", "release", "absent", "private"],
            }
        ],
    }


def evidence_payload():
    return deepcopy(_committed_evidence_payload())


@cache
def _committed_evidence_payload():
    root = Path(__file__).resolve().parents[3]
    return json.loads(
        (root / "contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/reference.json").read_text()
    )


def test_partial_description_round_trips_through_existing_evidence_envelope():
    payload = evidence_payload()
    payload["typed_description"] = description_payload()
    record = ExperimentEvidenceRecordModel.model_validate(payload)
    restored = ExperimentEvidenceRecordModel.model_validate_json(record.model_dump_json(exclude_none=True))
    facts = {fact.fact_id: fact for fact in restored.typed_description.facts}
    assert facts["family"].value.value == "linux"
    assert facts["release"].state == "not-observed" and facts["release"].value is None
    assert facts["absent"].state == "known-absent" and facts["absent"].value is None
    assert facts["private"].state == "withheld" and facts["private"].limitations
    assert restored.typed_description.provenance.basis.value == "backend-selected"
    assert restored.typed_description.coverage[0].status == "partial"
    assert restored.typed_description == record.typed_description


@pytest.mark.parametrize("value", [None, False, 0, ""])
def test_known_empty_values_are_not_missing(value):
    payload = description_payload()
    payload["facts"] = [
        {
            "fact_id": "known",
            "subject": "/value",
            "state": "known",
            "value": {"kind": "literal", "value": value, "origin": "backend"},
        }
    ]
    payload["coverage"] = []
    disclosure = ExperimentRealizedFormDisclosureModel.model_validate(
        {
            "concern_id": "selection",
            "concern_kind": "backend-selection",
            "basis": "backend-realized",
            "realized_by_ref": payload["provenance"]["observer_ref"],
            "realized_value_summary": "Requested detail",
            "disclosure": "Backend selection only.",
            "typed_description": payload,
        }
    )
    restored = ExperimentRealizedFormDisclosureModel.model_validate_json(disclosure.model_dump_json(exclude_none=True))
    actual = restored.typed_description.facts[0].value.value
    assert type(actual) is type(value) and actual == value


@pytest.mark.parametrize("state", ["not-observed", "known-absent", "withheld", "contradictory", "not-applicable"])
def test_nonknown_state_cannot_smuggle_a_value(state):
    payload = evidence_payload()
    description = description_payload()
    description["facts"][0]["state"] = state
    payload["typed_description"] = description
    with pytest.raises(ValidationError, match="nonknown facts cannot carry values"):
        ExperimentEvidenceRecordModel.model_validate(payload)


def test_withheld_evidence_cannot_add_a_value_bearing_description():
    payload = evidence_payload()
    payload.update(
        redaction_state="withheld", redaction_policy="private-policy", typed_description=description_payload()
    )
    payload["raw_content"]["loss_disclosure"] = "Withheld by policy."
    with pytest.raises(ValidationError, match="withheld evidence cannot carry known descriptive values"):
        ExperimentEvidenceRecordModel.model_validate(payload)


def test_collection_identity_must_match_the_supplied_member():
    payload = evidence_payload()
    description = description_payload()
    description["facts"][0]["value"] = {
        "kind": "keyed-collection",
        "origin": "backend",
        "collection_kind": "components",
        "identity_fields": ["id"],
        "members": [
            {
                "identity": ["a"],
                "constraint": {
                    "kind": "recursive-record",
                    "origin": "backend",
                    "fields": {"id": {"kind": "literal", "origin": "backend", "value": "b"}},
                },
            }
        ],
    }
    payload["typed_description"] = description
    with pytest.raises(ValidationError, match="descriptive member identity"):
        ExperimentEvidenceRecordModel.model_validate(payload)


def test_private_offline_carriage_requires_explicit_host_admission_policy(monkeypatch):
    from raes_contracts.contracts.realization_descriptions import TypedRealizationDescriptionModel
    from raes_contracts.description_reporting import admit_description_profiles
    from raes_contracts.domain_profiles import (
        DomainProfileAdmissionPolicyModel,
        DomainProfileBindingBasis,
        DomainProfileBindingUse,
        DomainProfileNamespaceAdmissionModel,
        DomainProfileResolutionContextModel,
    )
    from test_issue_1202_domain_profiles import _binding, _definition

    definition = _definition(
        namespace="com.example.private", authority="urn:example:authority", profile_id="private-detail"
    )
    binding = _binding(
        definition,
        value={"name": "private-detail"},
        use=DomainProfileBindingUse.OPAQUE_EXCHANGE,
        basis=DomainProfileBindingBasis.BACKEND_SELECTED,
    )
    payload = description_payload()
    binding_payload = binding.model_dump(mode="json")
    binding_payload["owner"].update(
        owning_contract_id="experiment-evidence-record-v1",
        canonical_address="#/nodes/a/family",
        lifecycle_phase="capture",
    )
    payload["facts"][0]["profile_bindings"] = [binding_payload]
    description = TypedRealizationDescriptionModel.model_validate(payload)
    import socket

    monkeypatch.setattr(
        socket, "create_connection", lambda *_args, **_kwargs: pytest.fail("profile admission attempted network access")
    )
    empty_context = DomainProfileResolutionContextModel(
        namespace_admissions=(
            DomainProfileNamespaceAdmissionModel(
                namespace=definition.coordinate.namespace,
                authority=definition.coordinate.authority,
                trust_decision_id="local-admission",
            ),
        ),
        definitions=(),
    )
    refused = admit_description_profiles(description, empty_context, policy=DomainProfileAdmissionPolicyModel())
    assert not refused.admitted
    admitted = admit_description_profiles(
        description, empty_context, policy=DomainProfileAdmissionPolicyModel(allow_opaque_exchange=True)
    )
    assert admitted.admitted and admitted.results[0].opaque
    restored = TypedRealizationDescriptionModel.model_validate_json(description.model_dump_json())
    assert restored.facts[0].profile_bindings[0].coordinate == binding.coordinate
    assert restored.facts[0].profile_bindings[0].value == {"name": "private-detail"}


def test_description_json_ingress_rejects_duplicate_members_without_echoing_values():
    from raes_contracts.description_reporting import parse_realization_description

    source = '{"description_id":"operator-private-sentinel","description_id":"duplicate"}'
    with pytest.raises(ValueError, match="duplicate JSON member") as error:
        parse_realization_description(source)
    assert "operator-private-sentinel" not in str(error.value)


def test_published_envelope_schema_accepts_partial_description_and_rejects_false_state():
    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / "contracts/schemas/experiment-core/experiment-evidence-record-v1.json").read_text())
    payload = evidence_payload()
    payload["typed_description"] = description_payload()
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(payload))
    payload["typed_description"]["facts"][0]["state"] = "withheld"
    assert list(validator.iter_errors(payload))


def test_excluded_descendants_cannot_leak_inside_a_selected_record():
    from raes_contracts.contracts.realization_descriptions import TypedRealizationDescriptionModel
    from raes_contracts.description_reporting import project_description
    from raes_contracts.observation_demand import ObservationBasis, ObservationSelector

    payload = description_payload()
    payload["coverage"] = []
    payload["facts"] = [
        {
            "fact_id": "node",
            "subject": "/nodes/a",
            "state": "known",
            "value": {
                "kind": "recursive-record",
                "origin": "backend",
                "fields": {"private": {"kind": "literal", "origin": "backend", "value": "private-sentinel"}},
            },
        }
    ]
    projected = project_description(
        TypedRealizationDescriptionModel.model_validate(payload),
        ObservationSelector(
            semantic_scope="/nodes", data_kind="field", names=("a",), excluded_scopes=("/nodes/a/private",)
        ),
        ObservationBasis.BACKEND_SELECTED,
    )
    assert projected.facts == ()
    assert "private-sentinel" not in projected.model_dump_json()
