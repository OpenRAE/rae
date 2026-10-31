"""Application constraints retain semantics within the default finite budget."""

from __future__ import annotations

import copy

import pytest
import yaml
from raes import parse_sdl
from raes_contracts.realization_structure import RealizationRelationStatus, evaluate_realization_constraint
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization import project_realization_concern


@pytest.fixture(params=[5, 15, 30])
def applications(request):
    return [
        {
            "application_id": "portal",
            "framework": "flask",
            "routes": [
                {"route_id": f"route-{i}", "path": f"/route-{i}", "methods": ["GET"], "auth_required": False}
                for i in range(request.param)
            ],
        }
    ]


def _requirement(applications):
    source = {
        "name": "application-budget",
        "nodes": {
            "webapp": {
                "type": "compute",
                "os": "linux",
                "runtime": {"applications": applications},
            }
        },
    }
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    return next(r for r in model.realization_requirements if r.requirement_kind == "runtime-applications")


@pytest.mark.parametrize("observed", [False, True])
def test_compiled_applications_fit_default_budget(applications, observed):
    requirement = _requirement(applications)
    value = project_realization_concern("runtime-applications", applications, observed=observed, recursive=True)
    result = evaluate_realization_constraint(requirement.constraint_document, value)
    assert result.status is RealizationRelationStatus.CONFORMANT, result.diagnostics


def test_changed_exact_route_is_rejected(applications):
    requirement = _requirement(applications)
    changed = copy.deepcopy(applications)
    changed[0]["routes"][0]["path"] = "/wrong"
    value = project_realization_concern("runtime-applications", changed, observed=True, recursive=True)
    assert evaluate_realization_constraint(requirement.constraint_document, value).status is (
        RealizationRelationStatus.NONCONFORMANT
    )


def test_scope_tree_construction_and_lookup_spend_budget():
    from raes_contracts.realization_structure import (
        RealizationClosure,
        RealizationConstraintDocument,
        RealizationConstraintLimits,
        RealizationDelegatedValue,
        RealizationScope,
    )
    from raes_contracts.realization_structure._common import RelationBudget
    from raes_contracts.realization_structure._scope_index import ScopeIndex

    closed = RealizationClosure(posture="closed", universe="test", profile="test/v1")
    document = RealizationConstraintDocument(
        semantic_profile="test/v1",
        root=RealizationDelegatedValue(kind="delegated"),
        scopes=(RealizationScope(field_pointer="/a/b/c", closure=closed),),
    )
    tiny = RealizationConstraintLimits(max_operations=2)
    budget = RelationBudget(tiny)
    assert ScopeIndex.build(document, budget) is None
    assert budget.operations == 3
    index = ScopeIndex.build(document, RelationBudget(RealizationConstraintLimits()))
    assert index is not None
    assert index.inherited_closure(("a", "b", "c"), closed, RelationBudget(tiny)) is None
    assert index.declared_children(("a", "b", "c"), RelationBudget(tiny)) is None
    assert index.declared_children(("a", "b"), RelationBudget(tiny)) is None


def test_scope_tree_uses_decoded_tokens_and_most_specific_closure():
    from raes_contracts.realization_structure import (
        RealizationClosure,
        RealizationConstraintDocument,
        RealizationDelegatedValue,
        RealizationScope,
    )

    opened = RealizationClosure(posture="open", universe="test", profile="test/v1")
    closed = RealizationClosure(posture="closed", universe="test", profile="test/v1")
    document = RealizationConstraintDocument(
        semantic_profile="test/v1",
        default_closure=opened,
        root=RealizationDelegatedValue(kind="delegated"),
        scopes=(
            RealizationScope(field_pointer="/a", closure=closed),
            RealizationScope(field_pointer="/a/~1~0", closure=opened),
            RealizationScope(field_pointer="/a/~1~0/", closure=closed),
        ),
    )
    actual = {"a": {"/~": {"": {}, "permitted": 1}}, "ab": {"permitted": 2}}
    assert evaluate_realization_constraint(document, actual).conformant
    actual["a"]["/~"][""]["forbidden"] = 3
    assert evaluate_realization_constraint(document, actual).status is RealizationRelationStatus.NONCONFORMANT
