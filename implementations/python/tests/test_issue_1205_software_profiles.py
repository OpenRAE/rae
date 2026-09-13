"""Software refinements reuse pinned profile authority without acquiring effects."""

from dataclasses import replace

import pytest
import yaml
from pydantic import ValidationError
from raes import parse_sdl
from raes.runtime_configuration import RuntimeConfiguration
from raes_contracts.domain_profiles import DomainProfileBindingBasis, DomainProfileOperation
from raes_contracts.realization_profiles import profile_context_digest, profile_selection_violation
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from test_issue_1200_mixed_runtime_constraints import _fixture
from test_issue_1202_domain_profiles import _context, _definition, _support


def _profile():
    return _definition(namespace="com.example.private", authority="urn:example:software", profile_id="acquisition")


def _refinement(value="cache"):
    return {
        "refinement_id": "route",
        "purpose": "acquisition",
        "definition": _profile().model_dump(mode="json"),
        "profile_value": {"name": value},
    }


def test_authored_private_acquisition_lowers_into_existing_profile_carriage():
    source = {
        "name": "software",
        "realization": {
            "default": "closed",
            "scopes": [{"field_pointer": "/nodes/host/runtime/software_components", "posture": "open"}],
        },
        "nodes": {
            "host": {
                "type": "compute",
                "runtime": {
                    "software_components": [{"component_id": "tool", "name": "tool", "refinements": [_refinement()]}]
                },
            }
        },
    }
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    authority = model.profile_authority
    assert authority is not None
    binding = authority.bindings[0]
    assert binding.owner.context == "artifact-acquisition"
    assert binding.owner.canonical_address == "#/resources/provision.node.host"
    assert binding.coordinate == _profile().coordinate
    assert binding.value == {"name": "cache"}
    assert "package_version" not in binding.value
    _, _, manifest = _fixture(
        {"software_components": [{"component_id": "tool", "name": "tool"}]},
        scope="/nodes/host/runtime/software_components",
    )
    refused = plan(model, manifest)
    assert any(item.code == "realization.profile-unsupported" for item in refused.diagnostics)
    definition = _profile()
    context = _context(definition, support_declarations=(_support(definition, *DomainProfileOperation),))
    manifest = replace(
        manifest,
        domain_profile_context_digest=profile_context_digest(context),
        supported_contract_versions=manifest.supported_contract_versions
        | {"plan-realization-profiles-v1", "backend-realization-preparation-v1"},
    )
    admitted = plan(model, manifest, profile_context=context)
    assert admitted.is_valid, admitted.diagnostics
    selected = binding.model_copy(
        update={
            "provenance": binding.provenance.model_copy(update={"basis": DomainProfileBindingBasis.BACKEND_SELECTED})
        }
    )
    assert profile_selection_violation(authority, (selected,), context) is None
    altered = selected.model_copy(update={"value": {"name": "network"}})
    assert profile_selection_violation(authority, (altered,), context)


def test_profile_details_are_not_required_for_software_presence():
    model = compile_runtime_model(
        parse_sdl(
            "name: sparse\nnodes:\n  host:\n    type: compute\n    runtime:\n      software_components:\n        - {component_id: tool, name: tool}\n"
        )
    )
    assert model.profile_authority is None


def test_explicit_package_correspondence_is_conjunctive_and_not_inferred():
    package = {"manager": "apt", "name": "tool-bin", "version": "1.2-3"}
    component = {
        "component_id": "tool",
        "name": "tool",
        "version": "1.2",
        "package_version": "1.2-3",
        "package_ref": {"manager": "apt", "name": "tool-bin"},
    }
    assert RuntimeConfiguration(packages=[package], software_components=[component])
    with pytest.raises(ValidationError, match="package.*reference"):
        RuntimeConfiguration(packages=[], software_components=[component])
    with pytest.raises(ValidationError, match="package.*version"):
        RuntimeConfiguration(packages=[{**package, "version": "1.2-4"}], software_components=[component])
    assert RuntimeConfiguration(
        packages=[package], software_components=[{"component_id": "tool", "name": "tool-bin", "version": "9.0"}]
    )


@pytest.mark.parametrize("route", ["apt", "rpm", "private-apt", "private", "offline", "cache", "prebuilt-image"])
def test_route_selection_is_an_explicit_profile_constraint_not_a_core_installer(route):
    source = {
        "name": "route-contract",
        "nodes": {
            "host": {
                "type": "compute",
                "runtime": {
                    "software_components": [
                        {"component_id": "tool", "name": "tool", "refinements": [_refinement(route)]}
                    ],
                },
            }
        },
    }
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    binding = model.profile_authority.bindings[0]
    assert binding.value == {"name": route}
    assert binding.owner.use.value == "constraint"
    # These names are private profile values, not built-in execution support.
    _, _, manifest = _fixture({"software_components": [{"component_id": "tool", "name": "tool"}]})
    refused = plan(model, manifest)
    assert not refused.is_valid
    assert any(item.code == "realization.profile-unsupported" for item in refused.diagnostics)


def test_profile_data_keys_are_not_structural_sdl_fields():
    refinement = _refinement()
    refinement["profile_value"] = {"name": {"MiXeD-Key": {"additionalProperties": False}}}
    source = {
        "name": "data-keys",
        "nodes": {
            "host": {
                "type": "compute",
                "runtime": {
                    "software_components": [{"component_id": "tool", "name": "tool", "refinements": [refinement]}],
                },
            }
        },
    }
    parsed = parse_sdl(yaml.safe_dump(source))
    actual = parsed.nodes["host"].runtime.software_components[0].refinements[0]
    assert actual.profile_value == refinement["profile_value"]
    assert actual.definition == _profile()


@pytest.mark.parametrize("posture,accepted", [("open", True), ("closed", False)])
def test_profile_value_inherits_enclosing_realization_posture(posture, accepted):
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:software",
        profile_id="acquisition",
        extra_property="option",
    )
    refinement = {**_refinement(), "definition": definition.model_dump(mode="json")}
    source = {
        "name": "profile-closure",
        "realization": {"default": posture},
        "nodes": {
            "host": {
                "type": "compute",
                "runtime": {
                    "software_components": [{"component_id": "tool", "name": "tool", "refinements": [refinement]}]
                },
            }
        },
    }
    authority = compile_runtime_model(parse_sdl(yaml.safe_dump(source))).profile_authority
    context = _context(definition, support_declarations=(_support(definition, *DomainProfileOperation),))
    binding = authority.bindings[0]
    selected = binding.model_copy(
        update={
            "value": {"name": "cache", "option": 1},
            "provenance": binding.provenance.model_copy(update={"basis": DomainProfileBindingBasis.BACKEND_SELECTED}),
        }
    )
    assert (profile_selection_violation(authority, (selected,), context) is None) is accepted


@pytest.mark.parametrize(
    "purpose,collection,id_field",
    [
        ("repository-state", "repositories", "repository_id"),
        ("repository-trust", "trust_bindings", "trust_id"),
    ],
)
def test_insecure_final_state_profile_does_not_grant_acquisition_authority(purpose, collection, id_field):
    from raes_contracts.domain_profiles import (
        DomainProfileSchemaModel,
        draft_domain_profile_definition,
        seal_domain_profile_definition,
    )
    from raes_contracts.realization_profiles import profile_authority_violation

    initial = _profile()
    schema = DomainProfileSchemaModel(
        dialect="https://json-schema.org/draft/2020-12/schema",
        schema_id="urn:example:trust",
        revision="1",
        schema_document={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:example:trust",
            "type": "object",
            "properties": {"uri": {"type": "string"}, "signature_verification": {"type": "boolean"}},
            "required": ["uri", "signature_verification"],
            "additionalProperties": False,
        },
    )
    definition = seal_domain_profile_definition(
        draft_domain_profile_definition(
            namespace=initial.coordinate.namespace,
            authority=initial.coordinate.authority,
            profile_id="described-trust",
            revision="1",
            schema=schema,
            semantic_contract=initial.semantic_contract,
            allowed_contexts=(f"software-{purpose}",),
        )
    )
    refinement = {
        "refinement_id": "described-posture",
        "purpose": purpose,
        "definition": definition.model_dump(mode="json"),
        "profile_value": {"uri": "http://mirror.invalid/archive", "signature_verification": False},
    }
    source = {
        "name": "described-insecure-state",
        "nodes": {
            "host": {
                "type": "compute",
                "runtime": {
                    "repository_state": {collection: [{id_field: "shared", "refinements": [refinement]}]},
                },
            }
        },
    }
    authority = compile_runtime_model(parse_sdl(yaml.safe_dump(source))).profile_authority
    binding = authority.bindings[0]
    assert binding.owner.use.value == "constraint"
    assert binding.owner.context == f"software-{purpose}"
    assert binding.value["signature_verification"] is False
    assert profile_authority_violation(authority, _context(definition))
