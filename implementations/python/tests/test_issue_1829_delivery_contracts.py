"""Published delivery invocation examples match their structural and local contracts."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes_contracts.contracts import (
    ParticipantCrossingEvidence,
    ParticipantDeliveryInvocationContextModel,
    ParticipantDeliveryInvocationOutcomeModel,
    ParticipantDeliveryInvocationRequestModel,
)

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = {
    "participant-crossing-evidence-v1": ParticipantCrossingEvidence,
    "participant-delivery-invocation-request-v1": ParticipantDeliveryInvocationRequestModel,
    "participant-delivery-invocation-context-v1": ParticipantDeliveryInvocationContextModel,
    "participant-delivery-invocation-outcome-v1": ParticipantDeliveryInvocationOutcomeModel,
}


@pytest.mark.parametrize("contract_id,model", CONTRACTS.items())
def test_published_delivery_examples(contract_id, model):
    schema = json.loads((ROOT / "contracts/schemas/participant-runtime" / (contract_id + ".json")).read_text())
    validator = Draft202012Validator(schema)
    directory = ROOT / "contracts/fixtures/participant-runtime" / contract_id
    for path in (directory / "valid").glob("*.json"):
        payload = json.loads(path.read_text())
        validator.validate(payload)
        model.model_validate(payload)
    for path in (directory / "invalid").glob("*.json"):
        payload = json.loads(path.read_text())
        with pytest.raises(ValueError):
            model.model_validate(payload)


def test_autonomous_and_delivery_claims_can_offer_distinct_actions():
    from dataclasses import replace

    from raes import parse_sdl
    from raes_backend_protocols.manifest import backend_manifest_v2_model
    from raes_contracts.contracts.participant_invocation_tools import ParticipantInvocationToolActionCapabilitiesModel
    from raes_processor.compiler import compile_runtime_model
    from test_issue_1740_invocation_tool_actions import _tool_manifest, _tool_scenario_yaml

    manifest = _tool_manifest(compile_runtime_model(parse_sdl(_tool_scenario_yaml())))
    capability = manifest.participant_runtime
    extra = replace(
        capability.execution_bindings[0],
        binding_id="delivery-extra",
        action_contract_address="participant.action-contract.delivery-only",
    )
    claim = ParticipantInvocationToolActionCapabilitiesModel(
        semantic_versions=["participant-invocation-tool-actions/v1", "participant-invocation-tool-actions/v2"],
        max_tool_actions_per_invocation=4,
        max_concurrent_tool_actions_per_invocation=2,
    )
    updated = replace(
        capability, invocation_tool_actions=claim, execution_bindings=(*capability.execution_bindings, extra)
    )
    combined = replace(manifest, capabilities=replace(manifest.capabilities, participant_runtime=updated))
    assert backend_manifest_v2_model(combined).capabilities.participant_runtime.invocation_tool_actions == claim
