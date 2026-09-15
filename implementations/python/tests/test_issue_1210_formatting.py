"""Current formatting retains policy, identity and safe diagnostics."""

import pytest
import yaml
from raes import SDLParseError, format_sdl_source, parse_sdl
from raes.semantic_revisions import LEGACY_SDL_REVISION, PROGRESSIVE_SDL_REVISION, source_byte_digest


def test_formatter_validation_errors_do_not_echo_rejected_values():
    sentinel = "PRIVATE_REJECTED_VALUE_1210"
    with pytest.raises(SDLParseError) as caught:
        format_sdl_source(f"name: safe\nprivate_extra: {sentinel}\n")
    assert sentinel not in str(caught.value)


def test_formatting_keeps_one_open_scope_and_no_hidden_infrastructure():
    source = (
        f"semantic_revision: {PROGRESSIVE_SDL_REVISION}\n"
        "name: abstract\nrealization: {default: open}\n"
        "nodes: {first: {type: compute}, second: {type: compute}}\n"
    )
    formatted = format_sdl_source(source).content
    assert yaml.safe_load(formatted) == yaml.safe_load(source)
    assert format_sdl_source(formatted).content == formatted
    assert all(node.runtime is None and node.os is None for node in parse_sdl(formatted).nodes.values())


def test_versioned_formatter_refuses_legacy_interpretation():
    from raes import semantic_revisions

    source = "name: legacy\n"
    digest = source_byte_digest(source)
    with pytest.raises(SDLParseError, match="revision"):
        semantic_revisions.format_versioned_sdl_source(
            source, semantic_revision=LEGACY_SDL_REVISION, source_digest=digest
        )


def test_inspection_excludes_authored_module_composition_from_constraints():
    from raes_cli._semantic_sdl import _inspection_payload

    scenario = parse_sdl("name: module\nmodule: {id: example/module, version: 1.0.0}\nimports: []\nnodes: {}\n")
    sections = _inspection_payload(scenario)["semantic_axes"]["constraints"]["authored_sections"]
    assert sections == ["nodes"]


@pytest.mark.parametrize("mode", [None, "inherit", "none", "operational-only"])
def test_observation_modes_round_trip_and_are_presented_separately(mode):
    from raes_cli._semantic_sdl import _inspection_payload

    rule = {"rule_id": "study", "scope": "", "purpose": "experimental", "collection": "inherit"}
    if mode is not None:
        rule["mode"] = mode
    evidence = {
        "source_class": "processor_backend",
        "scope_refs": ["nodes.host"],
        "window": "run",
        "channel": "api_response",
        "sensitivity": "plain",
        "redaction": "redact_sensitive",
        "integrity": "checksum",
        "retention": "not_retained",
        "loss_disclosure": "required",
        "observation_demand": rule,
    }
    data = {
        "semantic_revision": PROGRESSIVE_SDL_REVISION,
        "name": "abstract",
        "realization": {"default": "open"},
        "nodes": {"host": {"type": "compute"}},
        "evidence_requirements": {"study": evidence},
    }
    source = yaml.safe_dump(data)
    formatted = format_sdl_source(source).content
    assert yaml.safe_load(formatted) == data
    scenario = parse_sdl(formatted)
    axes = _inspection_payload(scenario)["semantic_axes"]
    assert axes["delegation"]["default"] == "open"
    assert axes["observation"]["study"] == rule
    assert "evidence_requirements" not in axes["constraints"]["authored_sections"]
    assert scenario.nodes["host"].runtime is None
    assert scenario.nodes["host"].os is None
