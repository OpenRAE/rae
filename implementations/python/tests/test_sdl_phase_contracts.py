"""Issue #724: closed SDL phase types and portable derivation provenance."""

from __future__ import annotations

import inspect
import json

import pytest
import raes
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import SDLInstantiationError, SDLValidationError
from raes.canonical import (
    INSTANTIATED_SNAPSHOT_PROFILE,
    canonical_instantiated_sdl_bytes,
    canonical_instantiated_sdl_digest,
)
from raes.instantiate import (
    _bind_scenario_content,
    admit_instantiated_scenario,
    instantiate_scenario,
)
from raes.parser import parse_sdl_file
from raes.phase_contracts import (
    BindingOrigin,
    CapabilityConstraint,
    InstantiationProvenance,
    ParameterBinding,
    ResolvedImportProvenance,
    SemanticDigest,
)
from raes.scenario import ExpandedScenario, InstantiatedScenario, Scenario, ScenarioContent
from raes_contracts.contracts import schema_bundle
from raes_processor.compiler import compile_runtime_model


def _digest() -> SemanticDigest:
    return SemanticDigest(
        profile="raes-sdl-semantic/v2",
        algorithm="sha256",
        value="sha256:" + "a" * 64,
    )


def _provenance(
    *,
    bindings: tuple[ParameterBinding, ...] = (),
    constraints: tuple[CapabilityConstraint, ...] = (),
) -> InstantiationProvenance:
    return InstantiationProvenance(
        authored_digest=_digest(),
        bindings=bindings,
        capability_constraints=constraints,
    )


def test_phase_models_have_disjoint_authoring_and_instantiated_fields() -> None:
    shared = set(ScenarioContent.model_fields)
    assert not issubclass(InstantiatedScenario, Scenario)
    assert set(Scenario.model_fields) == shared | {
        "module",
        "imports",
        "realization",
        "variables",
        "variation_points",
    }
    assert set(ExpandedScenario.model_fields) == shared | {
        "variables",
        "variation_points",
        "expansion_provenance",
    }
    assert set(InstantiatedScenario.model_fields) == shared | {"instantiation_provenance"}
    assert "ExpandedScenario" not in raes.__all__


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("variables", {}),
        ("variation_points", {}),
        ("imports", []),
        ("module", None),
        ("realization", None),
    ),
)
def test_instantiated_model_forbids_authoring_machinery_even_when_empty(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InstantiatedScenario.model_validate(
            {
                "name": "concrete",
                "instantiation_provenance": _provenance().model_dump(mode="json"),
                field: value,
            }
        )


def test_instantiated_model_requires_provenance() -> None:
    with pytest.raises(ValidationError, match="instantiation_provenance"):
        InstantiatedScenario.model_validate({"name": "concrete"})


def test_instantiation_serializes_binding_origin_without_live_variables() -> None:
    scenario = Scenario.model_validate(
        {
            "name": "parameterized",
            "variables": {
                "image": {
                    "type": "string",
                    "default": "linux",
                    "allowed_values": ["linux"],
                }
            },
            "nodes": {
                "host": {
                    "type": "compute",
                    "os": "${image}",
                    "resources": {"ram": "1 gib", "cpu": 1},
                }
            },
            "infrastructure": {"host": {"count": 1}},
        }
    )
    scenario._set_semantic_validated(True)

    concrete = instantiate_scenario(scenario)
    payload = concrete.model_dump(mode="json")

    assert {"module", "imports", "realization", "variables"}.isdisjoint(payload)
    assert payload["nodes"]["host"]["os"] == "linux"
    assert payload["instantiation_provenance"]["bindings"] == [
        {"parameter": ["image"], "origin": "default", "value": "linux"}
    ]
    assert concrete.instantiation_provenance.root_binding_values == {"image": "linux"}
    assert concrete.instantiation_provenance.bindings[0].origin is BindingOrigin.DEFAULT
    assert not hasattr(concrete, "variables")
    assert not hasattr(concrete, "imports")
    assert not hasattr(concrete, "module")


def test_instantiation_moves_realization_designations_to_provenance() -> None:
    scenario = Scenario.model_validate(
        {
            "name": "designated",
            "realization": {"default": "open"},
        }
    )
    scenario._set_semantic_validated(True)

    concrete = instantiate_scenario(scenario)
    payload = concrete.model_dump(mode="json")

    assert "realization" not in payload
    assert payload["instantiation_provenance"]["realization_designations"] == [
        {"namespace": [], "field_pointer": "", "posture": "open"}
    ]


def test_instantiated_artifact_round_trips_without_private_state() -> None:
    binding = ParameterBinding(parameter=("region",), origin=BindingOrigin.PROVIDED, value="eu-central")
    first = InstantiatedScenario(
        name="round-trip",
        description="eu-central",
        instantiation_provenance=_provenance(bindings=(binding,)),
    )

    restored = InstantiatedScenario.model_validate_json(first.model_dump_json())

    assert restored == first
    assert restored.instantiation_provenance.root_binding_values == {"region": "eu-central"}
    assert restored.model_dump(mode="json") == first.model_dump(mode="json")


def test_instantiated_snapshot_has_distinct_deterministic_profile() -> None:
    artifact = InstantiatedScenario(
        name="snapshot",
        instantiation_provenance=_provenance(),
    )

    first = canonical_instantiated_sdl_bytes(artifact)
    second = canonical_instantiated_sdl_bytes(InstantiatedScenario.model_validate_json(artifact.model_dump_json()))
    decoded = json.loads(first)

    assert first == second
    assert decoded["profile"] == INSTANTIATED_SNAPSHOT_PROFILE
    assert decoded["scenario"]["name"] == "snapshot"
    assert decoded["scenario"]["instantiation_provenance"]["authored_digest"]["value"] == "sha256:" + "a" * 64
    digest = canonical_instantiated_sdl_digest(artifact)
    assert digest.profile == INSTANTIATED_SNAPSHOT_PROFILE
    assert digest.value.startswith("sha256:")


def test_snapshot_schema_is_published_as_a_distinct_contract() -> None:
    artifact = InstantiatedScenario.model_validate(
        {
            "name": "snapshot",
            "nodes": {
                "shared.host": {
                    "type": "compute",
                    "os": "linux",
                    "resources": {"ram": "1 gib", "cpu": 1},
                }
            },
            "instantiation_provenance": _provenance().model_dump(mode="json"),
        }
    )
    snapshot = json.loads(canonical_instantiated_sdl_bytes(artifact))

    bundle = schema_bundle()
    assert "instantiated-scenario-snapshot-v1" in bundle
    Draft202012Validator(bundle["instantiated-scenario-snapshot-v1"]).validate(snapshot)


def test_snapshot_digest_changes_when_replay_provenance_changes() -> None:
    first = InstantiatedScenario(
        name="snapshot",
        instantiation_provenance=_provenance(
            bindings=(ParameterBinding(parameter=("region",), origin="provided", value="eu-central"),)
        ),
    )
    second = InstantiatedScenario(
        name="snapshot",
        instantiation_provenance=_provenance(
            bindings=(ParameterBinding(parameter=("region",), origin="provided", value="us-east"),)
        ),
    )

    assert canonical_instantiated_sdl_digest(first) != canonical_instantiated_sdl_digest(second)


def test_public_instantiation_has_no_semantic_validation_bypass() -> None:
    assert "validate_semantics" not in inspect.signature(instantiate_scenario).parameters
    bound = _bind_scenario_content(Scenario(name="private-boundary"))
    assert not isinstance(bound.content, InstantiatedScenario)


def test_compiler_and_snapshot_admit_direct_artifacts_semantically() -> None:
    artifact = InstantiatedScenario.model_validate(
        {
            "name": "invalid-direct-artifact",
            "events": {"kickoff": {"injects": ["missing"]}},
            "instantiation_provenance": _provenance().model_dump(mode="json"),
        }
    )

    with pytest.raises(SDLValidationError, match="undefined inject"):
        compile_runtime_model(artifact)
    with pytest.raises(SDLValidationError, match="undefined inject"):
        canonical_instantiated_sdl_bytes(artifact)


def test_json_round_trip_preserves_compiler_capability_and_explicitness_semantics() -> None:
    authored = Scenario.model_validate(
        {
            "name": "portable-compile",
            "variables": {
                "image": {
                    "type": "string",
                    "default": "linux",
                    "allowed_values": ["linux", "windows"],
                }
            },
            "nodes": {
                "host": {
                    "type": "compute",
                    "os": "${image}",
                    "resources": {"ram": "1 gib", "cpu": 1},
                }
            },
            "infrastructure": {"host": {"count": 1}},
        }
    )
    concrete = instantiate_scenario(authored)
    restored = InstantiatedScenario.model_validate_json(concrete.model_dump_json())

    assert concrete.instantiation_provenance.capability_constraints
    assert concrete.instantiation_provenance.explicitness
    assert compile_runtime_model(restored) == compile_runtime_model(concrete)
    compiled = compile_runtime_model(restored)
    assert not hasattr(compiled, "variable_specs")
    assert not hasattr(compiled, "node_variable_refs")
    assert len(compiled.capability_constraints) == 1
    constraint = compiled.capability_constraints[0]
    assert constraint.address == "provision.node.host"
    assert constraint.concern == "nodes.os"
    assert constraint.parameter == ("image",)
    assert constraint.allowed_values == ("linux", "windows")


def test_capability_constraint_is_limited_to_the_normative_field_surface() -> None:
    with pytest.raises(ValidationError, match="nodes.*os.*infrastructure.*count"):
        CapabilityConstraint(
            field_pointer="/description",
            parameter=("value",),
            allowed_values=("concrete",),
        )


def test_provenance_uses_json_value_equality_not_python_boolean_integer_equality() -> None:
    binding = ParameterBinding(parameter=("count",), origin="provided", value=True)
    constraint = CapabilityConstraint(
        field_pointer="/infrastructure/host/count",
        parameter=("count",),
        allowed_values=(1,),
    )

    with pytest.raises(ValidationError, match="does not satisfy"):
        InstantiationProvenance(
            authored_digest=_digest(),
            bindings=(binding,),
            capability_constraints=(constraint,),
        )

    distinct = CapabilityConstraint(
        field_pointer="/infrastructure/host/count",
        parameter=("count",),
        allowed_values=(True, 1),
    )
    assert distinct.allowed_values == (True, 1)


def test_provenance_rejects_non_finite_json_numbers() -> None:
    with pytest.raises(ValidationError, match="finite"):
        ParameterBinding(parameter=("scale",), origin="provided", value=float("nan"))


def test_capability_provenance_must_match_the_concrete_field() -> None:
    binding = ParameterBinding(parameter=("image",), origin="provided", value="linux")
    provenance = _provenance(
        bindings=(binding,),
        constraints=(
            CapabilityConstraint(
                field_pointer="/nodes/host/os",
                parameter=("image",),
                allowed_values=("linux", "windows"),
            ),
        ),
    )

    with pytest.raises(ValidationError, match="does not match the concrete field"):
        InstantiatedScenario.model_validate(
            {
                "name": "mismatched-evidence",
                "nodes": {
                    "host": {
                        "type": "compute",
                        "os": "windows",
                        "resources": {"ram": "1 gib", "cpu": 1},
                    }
                },
                "instantiation_provenance": provenance.model_dump(mode="json"),
            }
        )


def test_binding_failures_do_not_echo_supplied_values_or_allowed_domains() -> None:
    marker = "s3cr3t-marker-68f5"
    authored = Scenario.model_validate(
        {
            "name": "bounded-diagnostic",
            "description": "${token}",
            "variables": {
                "token": {
                    "type": "string",
                    "allowed_values": ["public-value"],
                    "required": True,
                }
            },
        }
    )

    with pytest.raises(SDLInstantiationError) as caught:
        instantiate_scenario(authored, {"token": marker})
    diagnostic = str(caught.value)
    assert marker not in diagnostic
    assert "public-value" not in diagnostic


def test_direct_artifact_admission_wraps_structural_errors_without_value_echo() -> None:
    marker = "s3cr3t-marker-a41c"

    with pytest.raises(SDLInstantiationError, match="Instantiated artifact is invalid") as caught:
        admit_instantiated_scenario(
            {
                "name": "direct-admission",
                "variables": {"token": marker},
                "instantiation_provenance": _provenance().model_dump(mode="json"),
            }
        )
    assert marker not in str(caught.value)


@pytest.mark.parametrize(
    ("field", "source"),
    (
        ("requested_source", "local:/home/researcher/private/module.yaml"),
        ("resolved_source", "C:\\Users\\researcher\\module.yaml"),
        ("requested_source", "oci:https://user:token@registry.example/raes/module"),
        (
            "resolved_source",
            "user:token@registry.example/raes/module@sha256:" + "b" * 64,
        ),
    ),
)
def test_import_provenance_rejects_host_paths_and_registry_credentials(
    field: str,
    source: str,
) -> None:
    payload = {
        "namespace": ["shared"],
        "requested_source": "local:module.yaml",
        "module_id": "raes/module",
        "module_version": "1.0.0",
        "resolved_source": "module.yaml",
        field: source,
    }

    with pytest.raises(ValidationError, match="absolute host path|registry credentials"):
        ResolvedImportProvenance.model_validate(payload)


def test_imported_explicitness_projects_only_surviving_namespaced_fields(tmp_path) -> None:
    for module_name in ("first", "second"):
        (tmp_path / f"{module_name}.yaml").write_text(
            f"""
name: {module_name}
version: 1.0.0
module:
  id: raes/{module_name}
  version: 1.0.0
  exports: {{nodes: [host]}}
behavior_specifications: {{}}
nodes:
  host:
    type: compute
    os: linux
    resources: {{ram: 1 gib, cpu: 1}}
""",
            encoding="utf-8",
        )
    root = tmp_path / "root.yaml"
    root.write_text(
        """
name: root
version: 1.0.0
imports:
  - path: first.yaml
    namespace: first
    version: 1.0.0
  - path: second.yaml
    namespace: second
    version: 1.0.0
""",
        encoding="utf-8",
    )

    expanded = parse_sdl_file(root)
    paths = [record.model_path for record in expanded.expansion_provenance.explicitness]

    assert len(paths) == len(set(paths))
    assert {"name", "version", "behavior_specifications"}.isdisjoint(paths)
    assert {
        "nodes.first.host.os",
        "nodes.second.host.os",
    }.issubset(paths)
    assert all(path.startswith("nodes.") for path in paths)

    concrete = instantiate_scenario(expanded)
    instantiated_paths = {record.model_path for record in concrete.instantiation_provenance.explicitness}
    assert set(paths).issubset(instantiated_paths)


def test_nested_import_provenance_is_ordered_portable_and_replay_complete(tmp_path) -> None:
    inner = tmp_path / "inner.yaml"
    inner.write_text(
        """
name: inner
version: 1.0.0
module:
  id: raes/inner
  version: 1.0.0
  parameters: [image]
  exports: {nodes: [host]}
variables:
  image:
    type: string
    required: true
    allowed_values: [linux, windows]
nodes:
  host:
    type: compute
    os: '${image}'
    resources: {ram: 1 gib, cpu: 1}
""",
        encoding="utf-8",
    )
    outer = tmp_path / "outer.yaml"
    outer.write_text(
        """
name: outer
version: 2.0.0
module:
  id: raes/outer
  version: 2.0.0
  parameters: [flavor]
  exports: {nodes: [inner.host]}
variables:
  flavor: {type: string, default: standard}
imports:
  - path: inner.yaml
    namespace: inner
    version: 1.0.0
    parameters: {image: linux}
""",
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        """
name: root
imports:
  - path: outer.yaml
    namespace: outer
    version: 2.0.0
""",
        encoding="utf-8",
    )

    expanded = parse_sdl_file(root)
    portable_explicitness = {record.model_path: record for record in expanded.expansion_provenance.explicitness}
    assert portable_explicitness["nodes.outer.inner.host.os"].parameters == (("outer", "inner", "image"),)

    concrete = instantiate_scenario(expanded)
    imports = concrete.instantiation_provenance.imports

    assert [record.namespace for record in imports] == [("outer",), ("outer", "inner")]
    assert imports[0].bindings[0].parameter == ("flavor",)
    assert imports[0].bindings[0].origin is BindingOrigin.DEFAULT
    assert imports[1].bindings[0].parameter == ("image",)
    assert imports[1].bindings[0].origin is BindingOrigin.PROVIDED
    assert imports[0].resolved_source == "outer.yaml"
    assert imports[1].resolved_source == "inner.yaml"
    assert all(not record.resolved_source.startswith(str(tmp_path)) for record in imports)
    assert all(record.content_digest.startswith("sha256:") for record in imports)
    assert all(record.export_hash.startswith("sha256:") for record in imports)
    constraint = concrete.instantiation_provenance.capability_constraints[0]
    assert constraint.parameter == ("outer", "inner", "image")
    assert constraint.field_pointer == "/nodes/outer.inner.host/os"
    instantiated_explicitness = {record.model_path: record for record in concrete.instantiation_provenance.explicitness}
    assert instantiated_explicitness["nodes.outer.inner.host.os"] == portable_explicitness["nodes.outer.inner.host.os"]
