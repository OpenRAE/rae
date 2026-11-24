"""Negotiation and wire projections expose the same closed inventory contract."""

from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.contracts.plan_projection import provisioning_plan_model, runtime_plan_digest
from raes_runtime.control_plane_api_models import _provisioning_plan
from raes_schemas import schema_bundle
from runtime_descendant_fixtures import CONTRACT, descendant_runtime


def test_inventory_contract_and_refresh_plan_roundtrip_are_published(tmp_path):
    manager, _backend, plan, target, _archive = descendant_runtime(tmp_path)
    assert CONTRACT in backend_manifest_v2_model(target.manifest).supported_contract_versions
    refresh = replace(plan.provisioning, inventory_refresh=True, inventory_attempt_id="attempt:1")
    wire = provisioning_plan_model(refresh)
    restored = _provisioning_plan(wire)
    assert restored.inventory_refresh is True
    assert restored.inventory_attempt_id == "attempt:1"
    assert runtime_plan_digest(restored) == runtime_plan_digest(refresh)
    assert runtime_plan_digest(refresh) != runtime_plan_digest(plan.provisioning)
    result = manager.apply(plan)
    assert result.success, result.diagnostics
    report = result.snapshot.materialization_attestations[-1].inventory
    validator = Draft202012Validator(schema_bundle()[CONTRACT])
    assert not list(validator.iter_errors(report.model_dump(mode="json")))
    invalid = report.model_dump(mode="json")
    invalid["unexpected"] = True
    assert list(validator.iter_errors(invalid))
    manager.close()


@pytest.mark.parametrize("value", [1, "true", None])
def test_refresh_discriminator_rejects_non_boolean_values(tmp_path, value):
    manager, _backend, plan, _target, _archive = descendant_runtime(tmp_path)
    wire = provisioning_plan_model(plan.provisioning).model_dump(mode="json")
    wire["inventory_refresh"] = value
    model = type(provisioning_plan_model(plan.provisioning))
    with pytest.raises(ValueError):
        model.model_validate(wire)
    manager.close()
