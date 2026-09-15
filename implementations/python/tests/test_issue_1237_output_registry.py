"""Evidence eligibility requires an atomic published-schema/validator entry."""

from __future__ import annotations

from dataclasses import replace
from functools import partial

import pytest
from raes_contracts.contracts import ObservationCaptureOfferModel
from test_issue_1112_capture_admission import _evidence_bundle, _offer, _validate_evidence_bundle


def _validation_call(ingress, payload, bundle, **offer_updates):
    calls = {
        "protocol": partial(_offer, **offer_updates),
        "model": partial(ObservationCaptureOfferModel.model_validate, payload),
        "content": partial(_validate_evidence_bundle, *bundle),
    }
    return calls[ingress]


@pytest.mark.parametrize("contract", ["unknown-output-v1", "experiment-task-v1"])
@pytest.mark.parametrize("ingress", ["protocol", "model", "content"])
def test_missing_output_owner_is_rejected_at_every_boundary(contract: str, ingress: str) -> None:
    payload = {**_offer().to_payload(), "output_contract": contract}
    bundle = _evidence_bundle(output_contract=contract)
    validate = _validation_call(ingress, payload, bundle, output_contract=contract)
    with pytest.raises(ValueError, match="output_contract"):
        validate()


@pytest.mark.parametrize("ingress", ["protocol", "model", "content"])
def test_missing_published_schema_cannot_use_generated_fallback(tmp_path, monkeypatch, ingress: str) -> None:
    import raes_contracts.corpus as corpus

    valid_offer = _offer().to_payload()
    validate = _validation_call(ingress, valid_offer, _evidence_bundle())
    monkeypatch.setattr(corpus, "corpus_root", lambda: tmp_path)
    with pytest.raises(ValueError, match="published schema"):
        validate()


@pytest.mark.parametrize("ingress", ["protocol", "model", "content"])
def test_missing_semantic_validator_never_degrades_to_schema_only(monkeypatch, ingress: str) -> None:
    import raes_contracts.evidence_output_validation as registry

    valid_offer = _offer().to_payload()
    registrations = dict(registry.evidence_output_registrations())
    key = valid_offer["output_contract"]
    registrations[key] = replace(registrations[key], semantic_validator=None)
    validate = _validation_call(ingress, valid_offer, _evidence_bundle())
    monkeypatch.setattr(registry, "evidence_output_registrations", lambda: registrations)
    with pytest.raises(ValueError, match="owning semantic validator"):
        validate()


@pytest.mark.parametrize("ingress", ["protocol", "model"])
def test_offer_encoding_must_have_a_registered_content_validator(ingress: str) -> None:
    payload = _offer().to_payload()
    payload.update(output_contract="experiment-evidence-record-v1", media_types=["application/jsonl"])
    calls = {
        "model": partial(ObservationCaptureOfferModel.model_validate, payload),
        "protocol": partial(
            _offer, output_contract="experiment-evidence-record-v1", media_types=frozenset({"application/jsonl"})
        ),
    }
    validate = calls[ingress]
    with pytest.raises(ValueError, match="media.*output_contract"):
        validate()
