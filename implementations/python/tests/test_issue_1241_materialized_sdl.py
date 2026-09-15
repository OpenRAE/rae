"""Materialization descriptions use the ordinary, closed SDL ingestion path."""

import json

import pytest
from raes import SDLParseError, parse_sdl


def materialization_provenance(**updates):
    payload = {
        "profile": "raes-materialization-attestation/v1",
        "attestation_id": "materialization-1",
        "authored_digest": {
            "profile": "raes-sdl-semantic/v2",
            "algorithm": "sha256",
            "value": "sha256:" + "a" * 64,
        },
        "instantiated_digest": {
            "profile": "raes-sdl-instantiated-snapshot/v2",
            "algorithm": "sha256",
            "value": "sha256:" + "b" * 64,
        },
        "plan_digest": "sha256:" + "c" * 64,
        "predecessor_digest": "sha256:" + "d" * 64,
        "operation_id": "operation-1",
        "run_id": "run-1",
        "recorded_at": "2026-09-14T12:00:00Z",
        "boundary": "post-materialization",
        "producer": {
            "name": "test-backend",
            "version": "1.0.0",
            "configuration_digest": "sha256:" + "e" * 64,
            "manifest_digest": "sha256:" + "f" * 64,
        },
        "coverage_profile": "raes-materialization-effects/v1",
        "origins": [],
        "resource_bindings": [],
    }
    return {**payload, **updates}


def materialized_payload(**updates):
    return {
        "name": "materialized-example",
        "materialization_provenance": materialization_provenance(),
        **updates,
    }


def test_ordinary_parser_admits_a_distinct_materialized_phase():
    parsed = parse_sdl(json.dumps(materialized_payload()))

    assert type(parsed).__name__ == "MaterializedScenario"
    assert parsed.semantic_validated
    assert parsed.materialization_provenance.boundary == "post-materialization"
    assert not hasattr(parsed, "instantiation_provenance")
    assert not hasattr(parsed, "variables")
    assert parse_sdl(json.dumps(parsed.model_dump(mode="json", exclude_unset=True))) == parsed


def test_materialized_parser_preserves_qualified_names_and_native_runtime_models():
    payload = materialized_payload(
        nodes={
            "lab.host": {
                "type": "compute",
                "services": [{"port": 22, "name": "ssh"}],
                "runtime": {
                    "ssh_servers": [
                        {
                            "ssh_server_id": "login",
                            "service": "ssh",
                            "forced_command": {
                                "command_kind": "redacted",
                                "command_redacted": True,
                            },
                        }
                    ]
                },
            }
        }
    )
    parsed = parse_sdl(json.dumps(payload))

    assert list(parsed.nodes) == ["lab.host"]
    command = parsed.nodes["lab.host"].runtime.ssh_servers[0].forced_command
    assert command.command == ""
    assert command.command_redacted is True


@pytest.mark.parametrize("field,value", [("variables", {}), ("imports", []), ("module", None)])
def test_materialized_phase_rejects_authoring_machinery(field, value):
    with pytest.raises(SDLParseError):
        parse_sdl(json.dumps(materialized_payload(**{field: value})))


def test_materialized_phase_never_resolves_an_import(monkeypatch, tmp_path):
    import raes.composition

    calls = []

    def unexpected_resolution(*args, **kwargs):
        calls.append(True)
        raise AssertionError("materialized SDL must not invoke import resolution")

    monkeypatch.setattr(raes.composition, "expand_sdl_modules", unexpected_resolution)
    with pytest.raises(SDLParseError):
        parse_sdl(
            json.dumps(materialized_payload(imports=[{"path": "untrusted.sdl", "as": "external"}])),
            path=tmp_path / "attestation.sdl",
        )
    assert calls == []


def test_materialized_phase_rejects_unresolved_substitution():
    with pytest.raises(SDLParseError):
        parse_sdl(json.dumps(materialized_payload(description="unresolved ${input}")))


def test_authored_identifiers_remain_unqualified():
    with pytest.raises(SDLParseError):
        parse_sdl(json.dumps({"name": "authored", "nodes": {"lab.host": {"type": "compute"}}}))


def test_materialized_roundtrip_uses_the_normal_renderer_and_its_own_digest():
    from raes.canonical import canonical_materialized_sdl_digest, canonical_sdl_digest
    from raes.formatting import render_sdl_source

    parsed = parse_sdl(json.dumps(materialized_payload()))
    rendered = render_sdl_source(parsed)
    assert rendered.scenario == parsed
    digest = canonical_materialized_sdl_digest(parsed)
    assert digest.profile == "raes-sdl-materialized/v1"
    assert digest == canonical_materialized_sdl_digest(parse_sdl(rendered.content))
    with pytest.raises(SDLParseError):
        canonical_sdl_digest(parsed)


def test_materialized_sdl_uses_the_existing_compiler_and_planner_without_becoming_authority():
    from raes_contracts.vocabulary import RealizationSupportMode
    from raes_processor.compiler import compile_scenario_runtime_model
    from raes_processor.planner import plan
    from test_sem_218_realization_designation import _manifest

    parsed = parse_sdl(
        json.dumps(
            materialized_payload(
                nodes={"host": {"type": "compute"}},
                infrastructure={"host": {}},
            )
        )
    )
    model = compile_scenario_runtime_model(parsed)
    assert model.materialization_description == parsed
    assert model.realization_instance is None
    assert not model.realization_authority
    assert not model.realization_requirements
    result = plan(model, _manifest(RealizationSupportMode.OPEN_REALIZATION))
    assert "provision.node.host" in result.provisioning.resources
    assert result.provisioning.purpose == "inspection"
    assert result.orchestration.purpose == "inspection"
    assert result.evaluation.purpose == "inspection"


def test_materialized_sdl_cannot_be_implicitly_reinstantiated():
    from raes import SDLInstantiationError, instantiate_scenario

    parsed = parse_sdl(json.dumps(materialized_payload()))
    with pytest.raises(SDLInstantiationError):
        instantiate_scenario(parsed)


def test_shared_canonical_comparison_preserves_materialization_artifact_kind():
    from raes import compare_canonical_artifacts

    left = parse_sdl(json.dumps(materialized_payload()))
    same = parse_sdl(json.dumps(materialized_payload()))
    different = parse_sdl(json.dumps(materialized_payload(description="changed")))
    comparison = compare_canonical_artifacts(left, same)
    assert comparison.equivalent
    assert comparison.artifact_kind.value == "sdl-materialization"
    assert not compare_canonical_artifacts(left, different).equivalent


def test_materialized_phase_keeps_the_existing_semantic_reference_gate():
    from raes import SDLValidationError

    with pytest.raises(SDLValidationError):
        parse_sdl(
            json.dumps(
                materialized_payload(
                    nodes={"host": {"type": "compute"}},
                    infrastructure={"host": {"links": ["missing-network"]}},
                )
            )
        )


@pytest.mark.parametrize("index", ["-1", "00", "+0"])
def test_materialization_origin_requires_canonical_array_indices(index):
    payload = materialized_payload(nodes={"host": {"type": "compute", "services": [{"name": "ssh", "port": 22}]}})
    payload["materialization_provenance"]["origins"] = [
        {
            "change": "added",
            "field_pointer": f"/nodes/host/services/{index}",
            "origin": "backend-realized",
        }
    ]
    with pytest.raises(SDLParseError):
        parse_sdl(json.dumps(payload))


def test_direct_description_is_bounded_before_serialization():
    from raes import admit_materialized_scenario

    parsed = parse_sdl(json.dumps(materialized_payload()))
    forged = parsed.model_copy(update={"description": "x" * (1048576 + 1)})
    with pytest.raises(ValueError, match="bound"):
        admit_materialized_scenario(forged)


@pytest.mark.parametrize("classification", ["operator_secret", "redacted"])
def test_added_environment_cannot_embed_values_marked_as_redacted(classification):
    payload = materialized_payload(
        nodes={
            "host": {
                "type": "compute",
                "runtime": {
                    "environment": [
                        {"name": "TOKEN", "value": "private-test-marker", "value_classification": classification}
                    ]
                },
            }
        }
    )
    with pytest.raises(SDLParseError) as error:
        parse_sdl(json.dumps(payload))
    assert "private-test-marker" not in str(error.value)


def test_materialization_provenance_is_concrete_too():
    payload = materialized_payload()
    payload["materialization_provenance"]["operation_id"] = "${unbound}"
    with pytest.raises(SDLParseError):
        parse_sdl(json.dumps(payload))


def test_canonical_materialization_revalidates_direct_objects():
    from raes import canonical_materialized_sdl_digest

    parsed = parse_sdl(json.dumps(materialized_payload()))
    forged = parsed.model_copy(update={"description": "${unbound}"})
    with pytest.raises((ValueError, SDLParseError)):
        canonical_materialized_sdl_digest(forged)
