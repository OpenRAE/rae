"""Runtime control archives preserve the exact API-409 lineage."""

import pytest
from mixed_control_v2_support import History
from raes_contracts.contracts.realization_plans import RuntimeSnapshotEnvelopeModel
from raes_contracts.participant_control_history import iter_participant_control_history_snapshot_violations
from raes_runtime.participant_control_intents import ParticipantProposalControlIntent


def test_runtime_history_reader_accepts_a_valid_v2_occurrence():
    event = History().accept("take")
    history = {event.participant_address: [event.model_dump(mode="json")]}

    assert iter_participant_control_history_snapshot_violations(history) == []


def test_snapshot_envelope_preserves_the_v2_lineage():
    event = History().accept("take")
    envelope = RuntimeSnapshotEnvelopeModel.model_validate(
        {"participant_control_history": {event.participant_address: [event.model_dump(mode="json")]}}
    )

    assert envelope.participant_control_history[event.participant_address][0].schema_version == "2.0.0"


def application_intent(**changes):
    return ParticipantProposalControlIntent.model_validate(
        {
            "declaration_ref": "participant.behavior-specification.controlled.permitted-transition.propose",
            "episode_id": "episode-1",
            "client_correlation_id": "request-1",
            "policy_revision": "1.0.0",
            "expected_state_revision": 0,
            "provenance_refs": ["provenance:test"],
            "evidence_refs": ["evidence:test"],
            "object_marking_refs": ["marking:test"],
            "limitation_refs": ["limitation:none"],
            "proposal_id": "proposal-1",
            "proposal_revision": 1,
            "action_contract_ref": "participant.action-contract.contain",
            "payload_ref": "payload:proposal-1",
            "application": {
                "semantics": "mixed-control-policy-occurrence/rev1",
                "policy_ref": "participant.behavior-specification.controlled.mixed-control-policy",
                "prior_state_ref": "participant.behavior-specification.controlled.controller-state.autonomous",
                "expected_history_head": 0,
                "effective_order": 1,
            },
            **changes,
        }
    )


def test_reusable_application_intent_preserves_explicit_coordinates():
    intent = application_intent()

    assert intent.application.effective_order == 1
    assert intent.application.expected_history_head == 0


@pytest.mark.parametrize("value", [True, "1", 1.0, -1, 1_000_001])
def test_reusable_intent_does_not_coerce_state_revisions(value):
    with pytest.raises(ValueError):
        application_intent(expected_state_revision=value)
