"""Generic software conformance through portable plan and result boundaries."""

import pytest
from raes_contracts.software_versions import version_relation
from test_issue_1200_mixed_runtime_constraints import _apply, _fixture


def _component(**changes):
    return {"component_id": "scanner", "name": "scanner", **changes}


@pytest.mark.parametrize("actual,accepted", [("7.10.0", True), ("7.8.0", False), ("8.0.0", False)])
def test_version_range_survives_portable_plan_and_result_admission(actual, accepted):
    component = _component(
        version_constraint={
            "relation": version_relation("numeric-triplet").model_dump(),
            "lower": "7.9.0",
            "upper": "8.0.0",
            "upper_closed": False,
        }
    )
    _, request, manifest = _fixture(
        {"software_components": [component]}, scope="/nodes/host/runtime/software_components"
    )
    result = _apply(request, manifest, {"software_components": [_component(version=actual)]}, observe=False)
    assert result.success is accepted, result.diagnostics
    if not accepted:
        assert result.snapshot.entries == {}
        assert result.changed_addresses == []


def test_sparse_software_does_not_require_collection_or_package_detail():
    _, request, manifest = _fixture(
        {"software_components": [_component()]}, scope="/nodes/host/runtime/software_components"
    )
    result = _apply(request, manifest, {"software_components": [_component(version="1.2.3")]}, observe=False)
    assert result.success, result.diagnostics
    assert result.snapshot.realization_observations == ()


def test_component_collection_matches_stable_identity_after_reordering():
    components = [_component(), {"component_id": "library", "name": "library"}]
    _, request, manifest = _fixture(
        {"software_components": components}, scope="/nodes/host/runtime/software_components"
    )
    result = _apply(request, manifest, {"software_components": list(reversed(components))}, observe=False)
    assert result.success, result.diagnostics


def test_exact_version_is_not_broadened_by_a_compatible_range():
    component = _component(
        version="7.10.0",
        version_constraint={
            "relation": version_relation("numeric-triplet").model_dump(),
            "lower": "7.0.0",
            "upper": "8.0.0",
        },
    )
    _, request, manifest = _fixture(
        {"software_components": [component]}, scope="/nodes/host/runtime/software_components"
    )
    result = _apply(request, manifest, {"software_components": [_component(version="7.11.0")]}, observe=False)
    assert not result.success


def test_unknown_required_version_semantics_fail_plan_admission():
    relation = version_relation("numeric-triplet").model_dump()
    relation["authority"] = "urn:private:version-semantics"
    _, execution, _ = _fixture(
        {"software_components": [_component(version_constraint={"relation": relation, "lower": "1.0.0"})]},
        scope="/nodes/host/runtime/software_components",
        allow_invalid=True,
    )
    assert not execution.is_valid
    assert any(item.code == "realization.unsupported-version-relation" for item in execution.diagnostics)


def test_exact_only_support_does_not_admit_version_predicates():
    from dataclasses import replace

    from raes_processor.planner import plan

    model, _, manifest = _fixture(
        {
            "software_components": [
                _component(
                    version_constraint={
                        "relation": version_relation("numeric-triplet").model_dump(),
                        "lower": "1.0.0",
                    }
                )
            ]
        },
        scope="/nodes/host/runtime/software_components",
    )
    manifest = replace(
        manifest,
        realization_support=tuple(
            replace(item, supported_constraint_kinds=frozenset()) for item in manifest.realization_support
        ),
    )
    execution = plan(model, manifest)
    assert not execution.is_valid
    assert any(item.code == "realization.unsupported-constraint-requirement" for item in execution.diagnostics)


@pytest.mark.parametrize(
    "presence,actual,accepted",
    [
        ("optional", [], True),
        ("optional", [_component(version="1.0.0")], True),
        ("optional", [_component(version="2.0.0")], False),
        ("forbidden", [], True),
        ("forbidden", [_component(version="1.0.0")], False),
    ],
)
def test_explicit_component_presence_is_independent_of_version(presence, actual, accepted):
    _, request, manifest = _fixture(
        {"software_components": [_component(presence=presence, version="1.0.0")]},
        scope="/nodes/host/runtime/software_components",
    )
    result = _apply(request, manifest, {"software_components": actual}, observe=False)
    assert result.success is accepted, result.diagnostics
