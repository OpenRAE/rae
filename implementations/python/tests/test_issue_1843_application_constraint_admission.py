"""Authored applications compile within the existing finite relation limits."""

import copy

import pytest
import yaml
from raes import parse_sdl
from raes_contracts.explicitness import ExplicitnessClass
from raes_contracts.realization_structure import (
    RealizationConstraintLimits,
    RealizationNormalizationMetadata,
    RealizationRelationStatus,
    evaluate_realization_constraint,
    normalize_realization_literal,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization import project_realization_concern


@pytest.fixture(params=[30, 40])
def compiled_application(request):
    applications = [
        {
            "application_id": "portal",
            "framework": "flask",
            "routes": [
                {
                    "route_id": f"route-{i}",
                    "path": f"/route-{i}",
                    "methods": ["GET", "POST"],
                    "parameters": [{"name": "query", "location": "query"}],
                    "responses": [{"status_code": 200}],
                }
                for i in range(request.param)
            ],
        }
    ]
    source = {
        "name": "application-admission",
        "realization": {"default": "open"},
        "nodes": {"webapp": {"type": "compute", "os": "linux", "runtime": {"applications": applications}}},
    }
    model = compile_runtime_model(parse_sdl(yaml.safe_dump(source)))
    requirement = next(r for r in model.realization_requirements if r.requirement_kind == "runtime-applications")
    assert not requirement.structure_error
    assert requirement.explicitness is ExplicitnessClass.OPEN
    assert requirement.constraint_document is not None
    assert requirement.constraint_binding is not None
    return requirement.constraint_document, applications


@pytest.mark.parametrize("observed", [False, True])
def test_application_retains_executable_constraint(compiled_application, observed):
    document, applications = compiled_application
    value = project_realization_concern("runtime-applications", applications, observed=observed, recursive=True)
    assert evaluate_realization_constraint(document, value).conformant
    limited = evaluate_realization_constraint(document, value, limits=RealizationConstraintLimits(max_operations=1))
    assert limited.status is RealizationRelationStatus.LIMIT_EXCEEDED
    assert len(limited.diagnostics) <= 16


def test_authored_path_remains_exact_with_open_additions(compiled_application):
    document, applications = compiled_application
    changed = copy.deepcopy(applications)
    changed[0]["routes"].append({"route_id": "additional", "path": "/additional", "methods": ["GET"]})
    value = project_realization_concern("runtime-applications", changed, observed=True, recursive=True)
    assert evaluate_realization_constraint(document, value).conformant
    changed[0]["routes"][0]["path"] = "/wrong"
    value = project_realization_concern("runtime-applications", changed, observed=True, recursive=True)
    assert evaluate_realization_constraint(document, value).status is RealizationRelationStatus.NONCONFORMANT


@pytest.mark.parametrize("origins", [{"/" + "x" * 64: "author"}, {"": "x" * 64}])
def test_origin_values_still_consume_scalar_budget(origins):
    result = normalize_realization_literal(
        1,
        semantic_profile="test/v1",
        metadata=RealizationNormalizationMetadata(origins=origins),
        limits=RealizationConstraintLimits(max_scalar_bytes=32),
    )
    assert result.status is RealizationRelationStatus.LIMIT_EXCEEDED
    assert "max_scalar_bytes" in result.diagnostics[0].message


@pytest.mark.parametrize("name", ["kind", "presence", "origin"])
def test_each_header_value_still_consumes_scalar_budget(name):
    from raes_contracts.realization_structure import RealizationDelegatedValue
    from raes_contracts.realization_structure._common import RelationBudget
    from raes_contracts.realization_structure._limits import _admit_node

    node = RealizationDelegatedValue(kind="delegated").model_copy(update={name: "x" * 64})
    violation = _admit_node(node, (), 0, RelationBudget(RealizationConstraintLimits(max_scalar_bytes=32)))
    assert violation is not None
    assert "max_scalar_bytes" in violation.message
