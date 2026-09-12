"""Shared final repository state is independent of transient acquisition."""

import pytest
from pydantic import ValidationError
from raes.runtime_configuration import RuntimeConfiguration
from test_issue_1200_mixed_runtime_constraints import _apply, _fixture


def _state():
    return {
        "repositories": [{"repository_id": "shared", "trust_ref": "team"}],
        "trust_bindings": [{"trust_id": "team"}],
    }


def test_two_components_reference_one_final_repository_and_trust_identity():
    runtime = RuntimeConfiguration.model_validate(
        {
            "repository_state": _state(),
            "software_components": [
                {"component_id": "one", "name": "one", "repository_refs": ["shared"]},
                {"component_id": "two", "name": "two", "repository_refs": ["shared"]},
            ],
        }
    )
    assert len(runtime.repository_state.repositories) == 1
    assert len(runtime.repository_state.trust_bindings) == 1


@pytest.mark.parametrize(
    "mutation", ["dangling-trust", "duplicate-repository", "duplicate-trust", "dangling-component", "forbidden-trust"]
)
def test_shared_references_reject_dangling_or_conflicting_state(mutation):
    state = _state()
    components = [{"component_id": "tool", "name": "tool", "repository_refs": ["shared"]}]
    if mutation == "dangling-trust":
        state["trust_bindings"] = []
    elif mutation == "duplicate-repository":
        state["repositories"].append({"repository_id": "shared"})
    elif mutation == "duplicate-trust":
        state["trust_bindings"].append({"trust_id": "team"})
    elif mutation == "dangling-component":
        components[0]["repository_refs"] = ["missing"]
    elif mutation == "forbidden-trust":
        state["trust_bindings"][0]["presence"] = "forbidden"
    with pytest.raises(ValidationError):
        RuntimeConfiguration(repository_state=state, software_components=components)


@pytest.mark.parametrize("retained,accepted", [(False, True), (True, False)])
def test_explicit_repository_absence_is_checked_after_software_realization(retained, accepted):
    authored = {
        "software_components": [{"component_id": "tool", "name": "tool"}],
        "repository_state": {"repositories": [{"repository_id": "temporary", "presence": "forbidden"}]},
    }
    _, request, manifest = _fixture(authored, scope="/nodes/host/runtime")
    actual = {
        "software_components": [{"component_id": "tool", "name": "tool"}],
        "repository_state": {"repositories": [{"repository_id": "temporary"}] if retained else []},
    }
    result = _apply(request, manifest, actual, observe=False)
    assert result.success is accepted, result.diagnostics


def test_present_optional_component_cannot_return_a_dangling_repository_reference():
    component = {"component_id": "tool", "name": "tool", "presence": "optional", "repository_refs": ["shared"]}
    state = {"repositories": [{"repository_id": "shared", "presence": "optional"}]}
    _, request, manifest = _fixture(
        {"software_components": [component], "repository_state": state}, scope="/nodes/host/runtime"
    )
    actual = {
        "software_components": [{"component_id": "tool", "name": "tool", "repository_refs": ["shared"]}],
        "repository_state": {"repositories": []},
    }
    result = _apply(request, manifest, actual, observe=False)
    assert not result.success
    assert result.snapshot.entries == {}


@pytest.mark.parametrize("actual_refs,accepted", [(["b", "a"], True), (["a", "c"], False)])
def test_final_repository_reference_identity_is_unordered_and_binding(actual_refs, accepted):
    from copy import deepcopy

    from raes_processor.semantics.realization_snapshot_sanitization import realization_payloads_match

    component = {"component_id": "tool", "name": "tool", "repository_refs": ["a", "b"]}
    state = {"repositories": [{"repository_id": name} for name in ("a", "b", "c")]}
    model, request, manifest = _fixture(
        {"software_components": [component], "repository_state": state},
        scope="/nodes/host/runtime",
        closed_scopes=("/nodes/host/runtime/software_components/0/repository_refs",),
    )
    result = _apply(
        request,
        manifest,
        {
            "software_components": [{**component, "repository_refs": actual_refs}],
            "repository_state": state,
        },
        observe=False,
    )
    assert result.success is accepted, result.diagnostics
    if accepted:
        entry = next(iter(result.snapshot.entries.values()))
        refs = entry.payload["spec"]["node"]["runtime"]["software_components"][0]["repository_refs"]
        assert refs == sorted(actual_refs)
        reordered = deepcopy(entry.payload)
        reordered["spec"]["node"]["runtime"]["software_components"][0]["repository_refs"] = refs[::-1]
        assert realization_payloads_match(entry.address, entry.payload, reordered, model.realization_requirements)
    else:
        assert result.snapshot.entries == {}


def test_open_repository_reference_set_accepts_additions_before_authored_reference():
    component = {"component_id": "tool", "name": "tool", "repository_refs": ["b"]}
    state = {"repositories": [{"repository_id": name} for name in ("a", "b")]}
    _, request, manifest = _fixture(
        {"software_components": [component], "repository_state": state},
        scope="/nodes/host/runtime",
    )
    result = _apply(
        request,
        manifest,
        {
            "software_components": [{**component, "repository_refs": ["a", "b"]}],
            "repository_state": state,
        },
        observe=False,
    )
    assert result.success, result.diagnostics
