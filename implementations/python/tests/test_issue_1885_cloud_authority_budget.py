"""Full cloud inventories retain bounded exact authority through public planning."""

from copy import deepcopy
from dataclasses import replace

import pytest
from cloud_authority_budget_fixtures import (
    CloudPreparingProvisioner,
    alter_inventory,
    apply_inventory,
    cloud_value,
    inventory_plan,
    inventory_source,
)
from raes_contracts.contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
from raes_contracts.realization_structure import (
    RealizationLiteral,
    evaluate_realization_constraint,
    validate_realization_value,
)
from raes_contracts.runtime_value_limits import PLAN_AUTHORITY_LIMITS
from raes_processor.planner import realization_authority_diagnostics
from raes_processor.planner.prepared_node_projection import prepared_node_document, prepared_node_payload_projection
from raes_processor.semantics.realization import project_realization_concern
from raes_runtime.control_plane_api_models import _provisioning_plan


@pytest.fixture(scope="module")
def full_inventory():
    return inventory_plan(2048)


def test_public_planner_admits_full_size_cloud_inventory(full_inventory):
    execution, _ = full_inventory
    assert execution.is_valid, execution.diagnostics
    application = cloud_value(execution.provisioning.operations, "secrets")
    assert len(application["secrets"]) == 2048
    assert application["secrets"][-1]["native_id"] == "secret-2047"
    assert not validate_realization_value(application).conformant


def _portable(execution):
    wire = provisioning_plan_model(execution.provisioning)
    return _provisioning_plan(type(wire).model_validate_json(wire.model_dump_json()))


@pytest.fixture(scope="module")
def selected_inventory(full_inventory):
    execution, manifest = full_inventory
    assert execution.is_valid, execution.diagnostics
    # Keep the transport codec's normalized selection. The dedicated transport
    # test covers JSON encoding and decoding; mutation cases share this value.
    return _provisioning_plan(provisioning_plan_model(execution.provisioning)), manifest


def test_full_size_authority_survives_transport_preparation_and_delivery(full_inventory):
    execution, manifest = full_inventory
    assert execution.is_valid, execution.diagnostics
    request = _portable(execution)
    assert runtime_plan_digest(request) == runtime_plan_digest(execution.provisioning)
    assert realization_authority_diagnostics(request, manifest) == []
    backend = CloudPreparingProvisioner()
    _, result = apply_inventory(request, manifest, backend)
    assert result.success, result.diagnostics
    assert backend.applies == 1
    delivered = cloud_value(list(result.snapshot.entries.values()), "secrets")
    expected = cloud_value(request.operations, "secrets")
    assert len(delivered["secrets"]) == 2048
    assert project_realization_concern(
        "runtime-platform-applications", [delivered], observed=True, recursive=True
    ) == project_realization_concern("runtime-platform-applications", [expected], observed=True, recursive=True)


@pytest.mark.parametrize("boundary", ["plan", "preparation", "delivery"])
@pytest.mark.parametrize("field", ["role", "subject", "id", "secret-id", "payload"])
def test_changed_full_size_authority_is_refused(selected_inventory, boundary, field):
    selected, manifest = selected_inventory
    request = deepcopy(selected)
    if boundary == "plan":
        alter_inventory(request.operations, field)
        assert realization_authority_diagnostics(request, manifest)
        return
    backend = CloudPreparingProvisioner(
        preparation_change=field if boundary == "preparation" else None,
        delivery_change=field if boundary == "delivery" else None,
    )
    previous, result = apply_inventory(request, manifest, backend)
    assert not result.success
    assert backend.applies == (1 if boundary == "delivery" else 0)
    assert result.snapshot == previous
    assert result.changed_addresses == []
    assert result.details == {}


def test_full_size_authority_rejects_changed_payload_pointer(full_inventory):
    execution, manifest = full_inventory
    assert execution.is_valid, execution.diagnostics
    request = deepcopy(execution.provisioning)
    request = replace(
        request,
        realization_authority=tuple(
            replace(item, payload_pointer="/spec/node/runtime/changed_applications")
            if item.requirement_kind == "runtime-platform-applications" and item.constraint_document is not None
            else item
            for item in request.realization_authority
        ),
    )
    assert (
        realization_authority_diagnostics(request, manifest)[0].code == "realization.authority-payload-pointer-invalid"
    )


def test_over_budget_cloud_inventory_has_specific_limit_diagnostic():
    raw = inventory_source(1)
    app = raw["nodes"]["secrets"]["runtime"]["platform_applications"][0]
    # Application-owned attributes permit model-valid nested JSON.
    nested = {}
    app["content_objects"] = [{"content_object_id": "object", "kind": "dashboard", "attributes": nested}]
    for _ in range(40):
        nested["nested"] = {}
        nested = nested["nested"]
    execution, _ = inventory_plan(source=raw)
    errors = [item for item in execution.diagnostics if item.is_error]
    assert errors
    assert any(item.code == "realization.limit-exceeded" and "max_depth" in item.message for item in errors), errors
    assert not any(item.code == "realization.authority-bound-unavailable" for item in errors)


def test_serialized_authority_refuses_exceeded_budget(full_inventory):
    execution, _ = full_inventory
    wire = provisioning_plan_model(execution.provisioning)
    request = deepcopy(execution.provisioning)
    oversized = RealizationLiteral(kind="literal", value="x" * (PLAN_AUTHORITY_LIMITS.max_scalar_bytes + 1))
    request = replace(
        request,
        realization_authority=tuple(
            replace(item, constraint_document=item.constraint_document.model_copy(update={"root": oversized}))
            if item.requirement_kind == "runtime-platform-applications" and item.constraint_document is not None
            else item
            for item in request.realization_authority
        ),
    )
    with pytest.raises(ValueError, match="max_scalar_bytes"):
        provisioning_plan_model(request)
    payload = wire.model_dump(mode="json")
    selected = next(
        item
        for item in payload["realization_authority"]
        if item["requirement_kind"] == "runtime-platform-applications" and "constraint_document" in item
    )
    selected["constraint_document"]["root"] = oversized.model_dump(mode="json")
    model_type = type(wire)
    with pytest.raises(ValueError, match="max_scalar_bytes"):
        model_type.model_validate(payload)


def test_larger_inventory_exceeds_fixed_authority_budget():
    execution, _ = inventory_plan(3000)
    errors = [item for item in execution.diagnostics if item.is_error]
    assert errors
    assert any(item.code == "realization.limit-exceeded" and "max_" in item.message for item in errors), errors
    assert not any(item.code == "realization.authority-bound-unavailable" for item in errors)


def test_planning_rejects_evaluation_exhaustion_even_when_normalization_fits(monkeypatch):
    # This inventory normalized and bound under the old profile, but could not
    # pass unchanged completion because evaluation also traverses its value.
    monkeypatch.setattr(
        "raes_processor.compiler.realization_recursive_constraints.PLAN_AUTHORITY_LIMITS",
        PLAN_AUTHORITY_LIMITS.model_copy(update={"max_nodes": 65536}),
    )
    execution, _ = inventory_plan(2048)
    errors = [item for item in execution.diagnostics if item.is_error]
    assert any(
        item.code == "realization.limit-exceeded"
        and "Recursive realization evaluation exceeded max_nodes" in item.message
        for item in errors
    ), errors
    assert not execution.is_valid


def test_prepared_node_projection_retains_the_supported_inventory_scale(full_inventory):
    execution, _ = full_inventory
    operation = next(item for item in execution.provisioning.operations if item.address == "provision.node.secrets")
    document = prepared_node_document(operation.payload)
    projected = prepared_node_payload_projection(operation.payload)
    assert evaluate_realization_constraint(document, projected, limits=PLAN_AUTHORITY_LIMITS).conformant
