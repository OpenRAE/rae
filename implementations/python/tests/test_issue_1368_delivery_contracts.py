"""Published application/delivery carriers require shape and contextual validation."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.contracts import (
    ParticipantInjectApplicationModel,
    ParticipantInjectContentModel,
    ParticipantInjectDeliveryReceiptModel,
)

ROOT = Path(__file__).resolve().parents[3]
MODELS = {
    "participant-inject-application-v1": ParticipantInjectApplicationModel,
    "participant-inject-delivery-v1": ParticipantInjectContentModel,
    "participant-inject-delivery-receipt-v1": ParticipantInjectDeliveryReceiptModel,
}
CASES = [
    (name, category, path)
    for name in MODELS
    for category in ("valid", "invalid", "context-invalid")
    for path in sorted((ROOT / "contracts/fixtures/control-plane" / name / category).glob("*.json"))
]


@pytest.mark.parametrize("name,category,path", CASES)
def test_published_carriers_and_contextual_invariants(name, category, path):
    schema = json.loads((ROOT / "contracts/schemas/control-plane" / f"{name}.json").read_text())
    payload = json.loads(path.read_text())
    validator = Draft202012Validator(schema)
    if category == "invalid":
        assert list(validator.iter_errors(payload))
    else:
        validator.validate(payload)
    if category == "valid":
        MODELS[name].model_validate(payload)
    else:
        with pytest.raises(ValueError):
            MODELS[name].model_validate(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"content_encoding": "base64", "content": "%%%invalid"},
        {"content": "ü" * 40_000},
        {"content_encoding": "base64", "content": "YQ==" * 30_000},
    ],
)
def test_content_encoding_and_decoded_byte_bounds_are_enforced(changes):
    payload = json.loads(
        (ROOT / "contracts/fixtures/control-plane/participant-inject-delivery-v1/valid/basic.json").read_text()
    )
    with pytest.raises(ValueError):
        ParticipantInjectContentModel.model_validate({**payload, **changes})


def test_resolved_required_parameter_instance_does_not_reinstantiate_its_parent():
    from raes import canonical_instantiated_sdl_digest, parse_sdl
    from raes.associated_artifacts import require_instantiated_scenario_reference
    from raes.instantiate import instantiate_scenario
    from raes_contracts.contracts import OperationArtifactReferenceModel

    parent = parse_sdl(
        "name: parameterized\ndescription: ${briefing}\nvariables:\n  briefing: {type: string, required: true}\n"
    )
    resolved = instantiate_scenario(parent, parameters={"briefing": "Approved briefing"})
    reference = OperationArtifactReferenceModel(
        contract_id="instantiated-scenario-v1",
        artifact_id=resolved.name,
        digest=canonical_instantiated_sdl_digest(resolved).value,
    )
    require_instantiated_scenario_reference(parent, reference, instantiated=resolved)
    require_instantiated_scenario_reference(resolved, reference)
