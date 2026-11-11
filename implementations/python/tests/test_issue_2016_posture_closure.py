"""Closure metadata admission agrees with the published recursive contract."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.realization_structure import RealizationClosure, RealizationConstraintDocument


@pytest.mark.parametrize("posture", ["open", "closed", "undefined", "omitted"])
@pytest.mark.parametrize("universe", [None, "scenario-fields/v1", "omitted"])
@pytest.mark.parametrize("profile", [None, "raes-recursive-realization/v1", "omitted"])
def test_closure_metadata_matches_published_admission(posture, universe, profile):
    closure = {"posture": posture, "universe": universe, "profile": profile}
    closure = {key: value for key, value in closure.items() if value != "omitted"}
    payload = {
        "semantic_profile": "raes-recursive-realization/v1",
        "default_closure": closure,
        "root": {"kind": "literal", "value": "fixed"},
    }
    schema_path = (
        Path(__file__).parents[3] / "contracts/schemas/realization-constraints/recursive-realization-constraint-v1.json"
    )
    validator = Draft202012Validator(json.loads(schema_path.read_text()))
    effective_posture = closure.get("posture", "undefined")
    named = (closure.get("universe") is not None, closure.get("profile") is not None)
    valid = named == ((False, False) if effective_posture == "undefined" else (True, True))
    assert validator.is_valid(payload) is valid

    if valid:
        assert RealizationClosure.model_validate(closure).posture.value == effective_posture
        assert RealizationConstraintDocument.model_validate(payload).default_closure.posture.value == effective_posture
    else:
        with pytest.raises(ValidationError, match="defined closure requires both universe and profile"):
            RealizationClosure.model_validate(closure)
        with pytest.raises(ValidationError, match="defined closure requires both universe and profile"):
            RealizationConstraintDocument.model_validate(payload)
