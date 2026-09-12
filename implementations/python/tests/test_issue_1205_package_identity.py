"""Legacy package coordinates retain exact values and multi-architecture identity."""

import pytest
from test_issue_1200_mixed_runtime_constraints import _apply, _fixture


def test_multiarch_packages_match_reordered_semantic_identity():
    from raes_contracts.realization_structure import (
        RealizationClosure,
        RealizationCollectionProfile,
        RealizationNormalizationMetadata,
        evaluate_realization_constraint,
        normalize_realization_literal,
    )
    from raes_processor.semantics.software_identity import package_collection_identity

    packages = [
        {"manager": "dnf", "name": "library", "version": "1.2-1", "architecture": arch}
        for arch in ("x86_64", "aarch64")
    ]
    # Exercise the package relation independently of node architecture
    # compatibility. This does not relax the latter's separate policy.
    normalized = normalize_realization_literal(
        packages,
        semantic_profile="raes/runtime-packages/v1",
        default_closure=RealizationClosure(posture="closed", universe="runtime-packages", profile="test"),
        metadata=RealizationNormalizationMetadata(
            collection_profiles=(
                RealizationCollectionProfile(
                    field_pointer="",
                    collection_kind="runtime-packages",
                    identity_fields=package_collection_identity(packages),
                    closure=RealizationClosure(posture="closed", universe="runtime-packages", profile="test"),
                ),
            )
        ),
    )
    assert normalized.document is not None, normalized.diagnostics
    result = evaluate_realization_constraint(normalized.document, packages[::-1])
    assert result.conformant, result.diagnostics


@pytest.mark.parametrize("architecture", ["x86_64", "aarch64", "x-private:machine"])
def test_omitted_package_architecture_remains_delegated_in_open_scope(architecture):
    package = {"manager": "private", "name": "library", "version": "1.2"}
    _, request, manifest = _fixture({"packages": [package]}, scope="/nodes/host/runtime/packages")
    result = _apply(request, manifest, {"packages": [{**package, "architecture": architecture}]})
    assert result.success, result.diagnostics


@pytest.mark.parametrize("version,accepted", [("1.2-3", True), ("9.0-1", False)])
def test_explicit_package_reference_enforces_joint_returned_coordinates(version, accepted):
    package = {"manager": "apt", "name": "tool-bin", "version": "1.2-3"}
    component = {"component_id": "tool", "name": "tool", "package_ref": {"manager": "apt", "name": "tool-bin"}}
    _, request, manifest = _fixture(
        {"packages": [package], "software_components": [component]}, scope="/nodes/host/runtime/software_components"
    )
    actual = {**component, "package_manager": "apt", "package_name": "tool-bin", "package_version": version}
    result = _apply(request, manifest, {"packages": [package], "software_components": [actual]})
    assert result.success is accepted, result.diagnostics


@pytest.mark.parametrize("version,accepted", [("1.2-3", True), ("9.0-1", False)])
def test_canonical_component_exact_package_retains_legacy_coordinate_meaning(version, accepted):
    package = {"manager": "apt", "name": "tool-bin", "version": "1.2-3"}
    component = {"component_id": "tool", "name": "tool", "package": package}
    _, request, manifest = _fixture(
        {"software_components": [component]}, scope="/nodes/host/runtime/software_components"
    )
    result = _apply(
        request,
        manifest,
        {"software_components": [{**component, "package": {**package, "version": version}}]},
        observe=False,
    )
    assert result.success is accepted, result.diagnostics


@pytest.mark.parametrize("architecture", [None, "aarch64"])
def test_forbidden_embedded_package_does_not_require_a_compatible_node_architecture(architecture):
    import yaml
    from raes import parse_sdl
    from raes_contracts.realization_structure import evaluate_realization_constraint
    from raes_processor.compiler import compile_runtime_model
    from raes_processor.semantics.realization_concerns import realization_concern_descriptor

    node = {
        "type": "compute",
        "runtime": {
            "software_components": [
                {
                    "component_id": "tool",
                    "name": "tool",
                    "presence": "forbidden",
                    "package": {"manager": "apt", "name": "tool", "version": "1", "architecture": "x86_64"},
                }
            ]
        },
    }
    if architecture is not None:
        node["architecture"] = architecture
    model = compile_runtime_model(parse_sdl(yaml.safe_dump({"name": "absence", "nodes": {"host": node}})))
    requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "runtime-software-components"
    )
    project = realization_concern_descriptor("runtime-software-components").project
    assert evaluate_realization_constraint(requirement.constraint_document, project([], recursive=True)).conformant


@pytest.mark.parametrize("legacy", [False, True])
def test_positive_exact_package_still_requires_compatible_node_architecture(legacy):
    import yaml
    from raes import SDLError, parse_sdl

    package = {"manager": "apt", "name": "tool", "version": "1", "architecture": "x86_64"}
    runtime = (
        {"packages": [package]}
        if legacy
        else {
            "software_components": [
                {
                    "component_id": "tool",
                    "name": "tool",
                    "package": package,
                }
            ]
        }
    )
    payload = yaml.safe_dump(
        {
            "name": "presence",
            "nodes": {"host": {"type": "compute", "architecture": "aarch64", "runtime": runtime}},
        }
    )
    with pytest.raises(SDLError, match="incompatible"):
        parse_sdl(payload)
