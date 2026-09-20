"""Portable schema and conformance publication for independent consumers."""

import json

import pytest
from jsonschema import Draft202012Validator
from participant_control_contract_fixtures import evaluation_payload, selection_payload

ROOTS = ("participant-control-selection-v1", "participant-control-evaluation-v1")


def test_control_subdomain_exports_preserve_public_facade():
    from raes_contracts import contracts
    from raes_contracts.contracts import _participant_control_exports as control

    for name in control.PARTICIPANT_CONTROL_EXPORTS:
        assert contracts.__all__.count(name) == 1
        assert getattr(contracts, name) is getattr(control, name)


@pytest.mark.parametrize("contract,payload", [(ROOTS[0], selection_payload), (ROOTS[1], evaluation_payload)])
def test_published_bundle_validates_closed_portable_fixtures(contract, payload):
    from raes_contracts.contracts import schema_bundle
    from raes_contracts.corpus import corpus_family_root

    schema = schema_bundle()[contract]
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload())
    path = corpus_family_root("schemas") / "participant-runtime" / (contract + ".json")
    assert json.loads(path.read_text()) == schema
    for category, valid in (("valid", True), ("invalid", False)):
        files = list((corpus_family_root("fixtures") / "participant-runtime" / contract / category).glob("*.json"))
        assert files
        for fixture in files:
            assert Draft202012Validator(schema).is_valid(json.loads(fixture.read_text())) is valid
            if valid:
                from raes_contracts.contracts import ParticipantControlEvaluationModel, ParticipantControlSelectionModel

                model = ParticipantControlEvaluationModel if contract == ROOTS[1] else ParticipantControlSelectionModel
                model.model_validate_json(fixture.read_text())


def test_evaluation_conformance_requires_trusted_context():
    from raes_conformance.conformance.validators import contract_validation_strength, validate_contract_payload
    from test_api_424_control_resolution import record_and_context

    contract = ROOTS[1]
    assert contract_validation_strength(contract) == "structural-context-required"
    record, context = record_and_context()
    diagnostics = validate_contract_payload(contract, record.model_dump(mode="json"))
    assert diagnostics and diagnostics[0].code == "conformance.semantic-context-required"
    assert not validate_contract_payload(
        contract, record.model_dump(mode="json"), control_context_resolver=lambda _: context
    )


def test_modular_capability_uses_governed_evidence_required_feature():
    from raes_contracts.manifest_authority import (
        PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
        PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES,
    )

    feature = "participant_modular_control"
    assert feature in PARTICIPANT_RUNTIME_EVIDENCE_REQUIRED_FEATURES
    assert (
        set(ROOTS)
        <= PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS[
            "capabilities.participant_runtime.supported_behavior_features"
        ][feature]
    )


def test_published_teaching_profile_is_closed_and_has_no_release():
    from raes_contracts.contracts import load_teaching_influence_profile, schema_bundle

    profile = load_teaching_influence_profile()
    Draft202012Validator(schema_bundle()["participant-control-teaching-profile-v1"]).validate(
        profile.model_dump(mode="json")
    )
    assert profile.release == "none"


@pytest.mark.parametrize("name", ["stale", "dishonest"])
def test_schema_valid_contextual_counterexamples_fail_trusted_resolution(name):
    from raes_contracts.contracts import (
        ParticipantControlEvaluationModel,
        validate_participant_control_resolved_context,
    )
    from raes_contracts.corpus import corpus_family_root
    from test_api_424_control_resolution import record_and_context

    _, context = record_and_context()
    path = (
        corpus_family_root("fixtures")
        / "participant-runtime/participant-control-evaluation-v1/context-invalid"
        / (name + ".json")
    )
    record = ParticipantControlEvaluationModel.model_validate_json(path.read_text())
    with pytest.raises(ValueError, match="trusted-context validation failed"):
        validate_participant_control_resolved_context(record, lambda _: context)
