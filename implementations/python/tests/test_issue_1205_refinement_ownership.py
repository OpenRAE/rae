"""Every software refinement attaches only to its canonical state owner."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import SDLError, parse_sdl
from raes.runtime_configuration import RuntimeConfiguration
from raes_processor.compiler import compile_runtime_model
from test_issue_1205_software_profiles import _refinement

_OWNERS = {
    "component": ("RuntimeSoftwareComponent", {"acquisition", "version-correspondence"}),
    "repository": ("RuntimeSoftwareRepository", {"repository-state"}),
    "trust": ("RuntimeSoftwareTrustBinding", {"repository-trust"}),
}
_CONTEXTS = {
    "acquisition": "artifact-acquisition",
    "version-correspondence": "software-version-correspondence",
    "repository-state": "software-repository-state",
    "repository-trust": "software-repository-trust",
}
_SCHEMAS = (
    "sdl/sdl-authoring-input-v1.json",
    "sdl/instantiated-scenario-v1.json",
    "sdl/instantiated-scenario-snapshot-v1.json",
    "satisfiability/scenario-satisfiability-evidence-v1.json",
)


def _attachment(owner, purpose):
    identity = {
        "component": {"component_id": "shared", "name": "tool"},
        "repository": {"repository_id": "shared"},
        "trust": {"trust_id": "shared"},
    }[owner]
    return {**identity, "refinements": [{**_refinement(), "purpose": purpose}]}


def _runtime(owner, purpose):
    attachment = _attachment(owner, purpose)
    if owner == "component":
        return {"software_components": [attachment]}
    collection = "repositories" if owner == "repository" else "trust_bindings"
    return {"repository_state": {collection: [attachment]}}


@pytest.mark.parametrize("owner", _OWNERS)
@pytest.mark.parametrize("purpose", _CONTEXTS)
def test_runtime_refinement_rejects_every_wrong_owner(owner, purpose):
    payload = _runtime(owner, purpose)
    if purpose not in _OWNERS[owner][1]:
        with pytest.raises(ValidationError):
            RuntimeConfiguration.model_validate(payload)
    else:
        validated = RuntimeConfiguration.model_validate(payload)
        assert validated.model_dump(mode="json", exclude_unset=True) == payload


@pytest.mark.parametrize("owner", _OWNERS)
@pytest.mark.parametrize("purpose", _CONTEXTS)
def test_parser_and_compiler_preserve_refinement_ownership(owner, purpose):
    source = yaml.safe_dump(
        {"name": "owner-contract", "nodes": {"host": {"type": "compute", "runtime": _runtime(owner, purpose)}}}
    )
    if purpose not in _OWNERS[owner][1]:
        with pytest.raises(SDLError):
            parse_sdl(source)
    else:
        authority = compile_runtime_model(parse_sdl(source)).profile_authority
        (binding,) = authority.bindings
        assert binding.owner.context == _CONTEXTS[purpose]
        identity_field = {"component": "component_id", "repository": "repository_id", "trust": "trust_id"}[owner]
        assert binding.provenance.source_ref == f"software:{identity_field}:shared/route"


@pytest.mark.parametrize("schema_path", _SCHEMAS)
@pytest.mark.parametrize("owner", _OWNERS)
@pytest.mark.parametrize("purpose", _CONTEXTS)
def test_published_refinement_attachment_contract_is_owner_closed(schema_path, owner, purpose):
    path = Path(__file__).resolve().parents[3] / "contracts/schemas" / schema_path
    schema = json.loads(path.read_text())
    owner_type, allowed = _OWNERS[owner]
    validator = Draft202012Validator({"$ref": f"#/$defs/{owner_type}", "$defs": schema["$defs"]})
    errors = list(validator.iter_errors(_attachment(owner, purpose)))
    assert (not errors) is (purpose in allowed), errors
