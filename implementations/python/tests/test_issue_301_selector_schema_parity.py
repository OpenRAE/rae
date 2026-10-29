"""Published selector validation agrees with the canonical binding model."""

import json

import pytest
from jsonschema import Draft202012Validator
from paths import REPO_ROOT

SCHEMAS = (
    "sdl/sdl-authoring-input-v1.json",
    "sdl/instantiated-scenario-v1.json",
    "sdl/instantiated-scenario-snapshot-v1.json",
    "sdl/materialized-scenario-v1.json",
    "satisfiability/scenario-satisfiability-evidence-v1.json",
)


@pytest.fixture(params=SCHEMAS)
def validator(request):
    schema = json.loads((REPO_ROOT / "contracts/schemas" / request.param).read_text())
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/ParticipantToolAffordance"})


@pytest.mark.parametrize("field", ("participant_refs", "participant_role_refs"))
@pytest.mark.parametrize("refs", ([""], [" \t\n"], ["subject", "subject"]))
def test_published_selectors_reject_blank_and_duplicate_items(validator, field, refs):
    binding = {"action_contract_refs": ["scan"], "observation_boundary_refs": ["view"], field: refs}
    assert not validator.is_valid(binding)


@pytest.mark.parametrize("refs", ([], ["subject"]))
@pytest.mark.parametrize("field", ("participant_refs", "participant_role_refs"))
def test_published_selectors_keep_empty_and_nonblank_unique_lists(validator, refs, field):
    binding = {"action_contract_refs": ["scan"], "observation_boundary_refs": ["view"], field: refs}
    assert validator.is_valid(binding)
