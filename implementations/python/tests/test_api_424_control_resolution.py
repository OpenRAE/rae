"""Trusted context must independently establish portable API-424 claims."""

from dataclasses import replace

import pytest
from participant_control_contract_fixtures import crossing_payload, delivery_payload, evaluation_payload


def record_and_context():
    from raes_contracts.contracts.participant_control_composition import (
        ParticipantControlEvaluationModel,
        control_digest,
    )
    from raes_contracts.contracts.participant_control_resolution import (
        ParticipantControlValidationContext,
        control_references,
    )

    record = ParticipantControlEvaluationModel.model_validate(evaluation_payload())
    from raes.participant_inject_delivery import ParticipantInjectDelivery
    from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel

    crossing = ParticipantCrossingOccurrenceModel.model_validate(
        crossing_payload(record.request.context.model_dump(mode="json"))
    )
    context = ParticipantControlValidationContext(
        admitted_request=record.request,
        safe_references=frozenset(control_references(record)),
        installed_bindings={"influence": record.request.selection.bindings[0]},
        effective_support={"influence": record.support[0]},
        resolved_results={"result-fact": record.results[0], "result-rule": record.results[1]},
        authorized_effects={control_digest(record.results[1].payload): record.request.context},
        incumbent_gate_evidence=record.composition.incumbent_gate_evidence,
        incumbent_gate_disposition="permit",
        support_resolver=lambda binding, support: support.declared_level,
        realization_receipts={},
        crossing_records=(crossing,),
        crossing_subjects=(crossing.occurrence.subject,),
        crossing_policies=(crossing.occurrence.policy,),
        inject_deliveries={"delivery-binding": ParticipantInjectDelivery.model_validate(delivery_payload())},
    )
    return record, context


def test_resolver_backed_contract_accepts_exact_trusted_relationships():
    from raes_contracts.contracts.participant_control_resolution import validate_participant_control_context

    record, context = record_and_context()
    validate_participant_control_context(record, context)


@pytest.mark.parametrize(
    "field,value",
    [
        ("safe_references", frozenset()),
        ("installed_bindings", {}),
        ("effective_support", {}),
        ("resolved_results", {}),
        ("authorized_effects", {}),
        ("incumbent_gate_disposition", "deny"),
        ("inject_deliveries", {}),
    ],
)
def test_self_reported_support_authority_or_evidence_is_insufficient(field, value):
    from raes_contracts.contracts.participant_control_resolution import validate_participant_control_context

    record, context = record_and_context()
    untrusted = replace(context, **{field: value})
    with pytest.raises(ValueError):
        validate_participant_control_context(record, untrusted)


def test_legacy_missing_support_strength_is_not_modular_support():
    from raes_contracts.contracts.participant_control_resolution import validate_participant_control_context

    record, context = record_and_context()
    unresolved = replace(context, support_resolver=lambda *_: None)
    with pytest.raises(ValueError):
        validate_participant_control_context(record, unresolved)


def test_context_resolver_failure_is_value_independent():
    from raes_contracts.contracts.participant_control_resolution import validate_participant_control_resolved_context

    record, _ = record_and_context()

    def fail(*args):
        raise RuntimeError("private-provider-state")

    for resolver in (None, fail, lambda *_: object()):
        with pytest.raises(ValueError) as caught:
            validate_participant_control_resolved_context(record, resolver)
        assert "private-provider-state" not in str(caught.value)


def test_effectful_provider_protocol_is_not_inferred_from_method_presence():
    from raes_backend_protocols.protocols import ParticipantControlProvider

    assert ParticipantControlProvider.resolve.__annotations__
    assert not getattr(ParticipantControlProvider, "_is_runtime_protocol", False)
