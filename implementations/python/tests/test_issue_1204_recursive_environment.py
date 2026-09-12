"""The existing environment projection participates in recursive authority."""

from copy import deepcopy

import pytest
from test_issue_1200_mixed_runtime_constraints import _apply, _fixture


@pytest.mark.parametrize("opened", [False, True])
def test_environment_constraints_keep_identity_and_committed_values(opened):
    runtime = {
        "environment": [
            {"name": "Z", "value": "fixed-z", "value_classification": "plain", "provenance": "runtime"},
            {"name": "A", "value": "fixed-a", "value_classification": "plain", "provenance": "runtime"},
        ]
    }
    model, request, manifest = _fixture(runtime, scope="/nodes/host/runtime/environment" if opened else None)
    requirement = next(
        item for item in model.realization_requirements if item.requirement_kind == "runtime-environment"
    )
    authority = next(item for item in request.realization_authority if item.requirement_kind == "runtime-environment")
    assert authority.constraint_document is not None
    assert authority.constraint_document == requirement.constraint_document
    assert authority.constraint_document.root.identity_fields == ("name",)
    assert "fixed-z" not in authority.constraint_document.model_dump_json()
    assert "fixed-a" not in authority.constraint_document.model_dump_json()
    assert _apply(request, manifest, {"environment": list(reversed(runtime["environment"]))}).success
    changed = deepcopy(runtime)
    changed["environment"][0]["value"] = "changed-value"
    assert not _apply(request, manifest, changed).success
    extra = deepcopy(runtime)
    extra["environment"].append(
        {"name": "B", "value": "extra", "value_classification": "plain", "provenance": "runtime"}
    )
    assert _apply(request, manifest, extra).success is opened
