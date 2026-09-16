"""Scope restrictions are checked against a pure, bound prospective SDL report."""

import json
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes_backend_protocols.augmentation import augmentation_preparation
from raes_contracts.planning import PlanScope
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from test_issue_1241_materialization_context import attesting_plan


def scoped_plan(policy=None, *, negotiated=True, content=None):
    execution, _ = attesting_plan()
    manifest = replace(
        execution.manifest,
        supported_contract_versions=(
            execution.manifest.supported_contract_versions | {"backend-augmentation-scope-v1"}
            if negotiated
            else execution.manifest.supported_contract_versions
        ),
    )
    source = {"name": "scoped", "realization": {"default": "open"}, "nodes": {"host": {"type": "compute"}}}
    source.update(content or {})
    if policy is not None:
        source["augmentation_scope"] = policy
    model = compile_runtime_model(parse_sdl(json.dumps(source)))
    return plan(model, manifest, scope=PlanScope(run_id="run-1"))


@pytest.mark.parametrize("permission", ["open", "closed"])
def test_explicit_policy_requires_negotiated_enforcement(permission):
    execution = scoped_plan({"default": permission}, negotiated=False)
    assert not execution.is_valid
    assert "augmentation.scope-unsupported" in {item.code for item in execution.diagnostics}


def test_omitted_policy_preserves_previous_negotiation():
    assert scoped_plan(negotiated=False).is_valid


def preview(execution, *, policy_effect=False, affected=("/nodes/host",)):
    from raes_contracts.augmentation_preparation import AugmentationEffect
    from raes_contracts.runtime_state import RuntimeSnapshot

    request = replace(execution.provisioning, operation_id="operation-1")
    content = json.loads(request.materialization_source.snapshot)["scenario"]
    content.pop("instantiation_provenance")
    if policy_effect:
        content["augmentation_scope"]["default"] = "open"
        pointer = "/augmentation_scope/default"
    else:
        content["nodes"]["host"]["runtime"] = {"environment": [{"name": "COLLECTOR", "value": "enabled"}]}
        pointer = "/nodes/host/runtime"
    report = augmentation_preparation(
        request,
        execution.manifest,
        RuntimeSnapshot(),
        content=json.dumps(content),
        effects=(
            AugmentationEffect(
                field_pointer=pointer,
                requirement_refs=("backend-operational",),
                affected_scopes=affected,
            ),
        ),
    )
    return request, report


def test_closed_scope_refusal_names_the_needed_effect_and_requirement():
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.planner.augmentation_admission import admit_augmentation_preparation

    execution = scoped_plan({"default": "closed"})
    request, report = preview(execution)
    admission = admit_augmentation_preparation(report, request, execution.manifest, RuntimeSnapshot())
    assert not admission.is_valid
    diagnostic = admission.diagnostics[0]
    assert diagnostic.code == "augmentation.scope-closed"
    assert "/nodes/host/runtime" in diagnostic.message
    assert "backend-operational" in diagnostic.message


def test_open_scope_accepts_the_same_in_world_effect():
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.planner.augmentation_admission import admit_augmentation_preparation

    execution = scoped_plan({"default": "open"})
    request, report = preview(execution)
    assert admit_augmentation_preparation(report, request, execution.manifest, RuntimeSnapshot()).is_valid


@pytest.mark.parametrize("tamper", ["binding", "effects", "policy", "impact"])
def test_unbound_incomplete_or_permission_changing_reports_are_refused(tamper):
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.planner.augmentation_admission import admit_augmentation_preparation

    execution = scoped_plan({"default": "closed" if tamper == "policy" else "open"})
    request, report = preview(
        execution, policy_effect=tamper == "policy", affected=("/missing",) if tamper == "impact" else ("/nodes/host",)
    )
    if tamper == "binding":
        request = replace(request, operation_id="other-operation")
    elif tamper == "effects":
        report = report.model_copy(update={"effects": ()})
    with pytest.raises(ValueError):
        admit_augmentation_preparation(report, request, execution.manifest, RuntimeSnapshot())


def test_scope_checks_all_impacts_not_only_installation_location():
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.planner.augmentation_admission import admit_augmentation_preparation

    execution = scoped_plan({"default": "open", "scopes": [{"scope": "/nodes/host", "permission": "closed"}]})
    request, report = preview(execution)
    # Claiming a permissive installation scope must not hide the changed host.
    report = report.model_copy(update={"effects": (report.effects[0].model_copy(update={"affected_scopes": ("",)}),)})
    assert not admit_augmentation_preparation(report, request, execution.manifest, RuntimeSnapshot()).is_valid


def test_ordinary_delegated_os_selection_does_not_need_addition_permission():
    from raes_contracts.augmentation_preparation import AugmentationEffect
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.planner.augmentation_admission import admit_augmentation_preparation

    execution = scoped_plan({"default": "closed"})
    request = replace(execution.provisioning, operation_id="operation-1")
    content = json.loads(request.materialization_source.snapshot)["scenario"]
    content.pop("instantiation_provenance")
    content["nodes"]["host"]["os"] = "linux"
    report = augmentation_preparation(
        request,
        execution.manifest,
        RuntimeSnapshot(),
        content=json.dumps(content),
        effects=(
            AugmentationEffect(
                field_pointer="/nodes/host/os",
                requirement_refs=("backend-operational",),
                affected_scopes=("/nodes/host/os",),
            ),
        ),
    )
    assert admit_augmentation_preparation(report, request, execution.manifest, RuntimeSnapshot()).is_valid


def test_closed_keyed_member_follows_its_identity_across_reordering():
    from raes_contracts.augmentation_preparation import AugmentationEffect
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.planner.augmentation_admission import admit_augmentation_preparation

    execution = scoped_plan(
        {"default": "open", "scopes": [{"scope": "/nodes/host/services/0", "permission": "closed"}]},
        content={
            "nodes": {
                "host": {
                    "type": "compute",
                    "services": [{"name": "protected", "port": 80}, {"name": "other", "port": 443}],
                }
            }
        },
    )
    request = replace(execution.provisioning, operation_id="operation-1")
    content = json.loads(request.materialization_source.snapshot)["scenario"]
    content.pop("instantiation_provenance")
    content["nodes"]["host"]["services"].reverse()
    content["nodes"]["host"]["services"][1]["port"] = 8080
    report = augmentation_preparation(
        request,
        execution.manifest,
        RuntimeSnapshot(),
        content=json.dumps(content),
        effects=(
            AugmentationEffect(
                field_pointer="/nodes/host/services/1/port",
                requirement_refs=("backend-operational",),
                affected_scopes=("/nodes/host/services/1",),
            ),
        ),
    )
    assert not admit_augmentation_preparation(report, request, execution.manifest, RuntimeSnapshot()).is_valid


def test_replacing_an_open_ancestor_cannot_erase_a_closed_child():
    from raes_contracts.augmentation_preparation import AugmentationEffect
    from raes_contracts.runtime_state import RuntimeSnapshot
    from raes_processor.planner.augmentation_admission import admit_augmentation_preparation

    execution = scoped_plan(
        {"default": "open", "scopes": [{"scope": "/nodes/host/runtime/environment", "permission": "closed"}]},
        content={
            "nodes": {"host": {"type": "compute", "runtime": {"environment": [{"name": "KEEP", "value": "fixed"}]}}}
        },
    )
    request = replace(execution.provisioning, operation_id="operation-1")
    content = json.loads(request.materialization_source.snapshot)["scenario"]
    content.pop("instantiation_provenance")
    content["nodes"]["host"]["runtime"] = None
    report = augmentation_preparation(
        request,
        execution.manifest,
        RuntimeSnapshot(),
        content=json.dumps(content),
        effects=(
            AugmentationEffect(
                field_pointer="/nodes/host/runtime",
                requirement_refs=("backend-operational",),
                affected_scopes=("/nodes/host/runtime",),
            ),
        ),
    )
    assert not admit_augmentation_preparation(report, request, execution.manifest, RuntimeSnapshot()).is_valid


def test_preparation_bounds_aggregate_scope_resolution_work():
    from raes_contracts.augmentation_preparation import AugmentationEffect, AugmentationPreparation

    effects = tuple(
        AugmentationEffect(
            field_pointer=f"/nodes/host/runtime/{index}",
            requirement_refs=("backend-operational",),
            affected_scopes=("/nodes/host",) * 256,
        )
        for index in range(64)
    )
    with pytest.raises(ValueError):
        AugmentationPreparation(binding_digest="sha256:" + "0" * 64, content="{}", effects=effects)


def test_publishing_a_contract_does_not_claim_unimplemented_backend_support():
    from raes_backend_stubs.stubs import create_stub_manifest
    from raes_reference_backend.manifest import create_reference_backend_manifest

    for manifest in (create_stub_manifest(), create_reference_backend_manifest()):
        assert "backend-augmentation-scope-v1" not in manifest.supported_contract_versions
