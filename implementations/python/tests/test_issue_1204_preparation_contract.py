"""Closed portable carriage of a backend's proposed joint completion."""

from copy import deepcopy

import pytest


def test_preparation_response_schema_and_codec_roundtrip():
    from jsonschema import Draft202012Validator
    from raes_contracts.contracts import schema_bundle
    from raes_contracts.contracts.backend_preparation import preparation_response_model
    from raes_contracts.realization_preparation import BACKEND_PREPARATION_CONTRACT
    from raes_contracts.runtime_state import RuntimeSnapshot
    from test_issue_1204_backend_preparation import _PreparingBackend, _request

    request, _ = _request()
    response = _PreparingBackend().prepare(request, RuntimeSnapshot())
    model = preparation_response_model(response)
    wire = model.model_dump(mode="json")
    schema = schema_bundle()[BACKEND_PREPARATION_CONTRACT]
    Draft202012Validator(schema).validate(wire)
    assert type(model).model_validate(wire).to_runtime() == response
    for mutation in ("unknown-field", "action", "domain", "binding"):
        invalid = deepcopy(wire)
        if mutation == "unknown-field":
            invalid["observation"] = "not-observed"
        elif mutation == "action":
            invalid["operations"][0]["action"] = "execute"
        elif mutation == "domain":
            invalid["operations"][0]["address"] = "evaluation.objective.other"
        else:
            invalid["request_digest"] = "not-a-digest"
        assert not Draft202012Validator(schema).is_valid(invalid)
        with pytest.raises(ValueError):
            type(model).model_validate(invalid)


@pytest.mark.parametrize("value_count, admitted", [(200, True), (400, False)])
def test_response_aggregate_is_bounded_before_portable_serialization(monkeypatch, value_count, admitted):
    from raes_contracts.contracts import backend_preparation
    from raes_contracts.planning import ChangeAction, ProvisionOp
    from raes_contracts.realization_preparation import RealizationPreparation

    calls = []
    serialize = backend_preparation.to_jsonable_python

    def recording_serialize(value, **kwargs):
        calls.append(True)
        return serialize(value, **kwargs)

    monkeypatch.setattr(backend_preparation, "to_jsonable_python", recording_serialize)
    response = RealizationPreparation(
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
        tuple(
            ProvisionOp(ChangeAction.CREATE, f"provision.node.n{index}", "node", {"items": list(range(value_count))})
            for index in range(200)
        ),
    )
    if admitted:
        assert len(backend_preparation.preparation_response_model(response).operations) == 200
        assert calls
    else:
        with pytest.raises(ValueError):
            backend_preparation.preparation_response_model(response)
        assert calls == []
