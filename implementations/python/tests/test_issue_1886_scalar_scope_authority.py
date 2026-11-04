"""Scalar delegation preserves closed authority through public contracts."""

from copy import deepcopy
from dataclasses import replace

import pytest
from raes import parse_sdl
from raes.instantiate import instantiate_scenario
from raes_backend_stubs.stubs import StubProvisioner, create_stub_target
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.contracts import ProvisioningPlanModel
from raes_contracts.contracts.backend_preparation import preparation_response_model
from raes_contracts.contracts.plan_projection import provisioning_plan_model
from raes_contracts.contracts.realization_preparation import RealizationPreparation
from raes_contracts.planning import RealizationAuthorityMode, RuntimeDomain
from raes_contracts.realization_structure import evaluate_realization_constraint
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope
from raes_processor.planner import prepared_delivery_violation, prepared_realization_violation
from raes_processor.semantics.realization_concerns import project_realization_concern
from raes_runtime import RuntimeManager


@pytest.fixture(params=["closed", "unspecified"])
def scalar_scope_plan(request):
    scenario = instantiate_scenario(
        parse_sdl(f"""
name: synthetic-scoped-project
realization:
  default: {request.param}
  scopes:
  - field_pointer: /nodes/cloud/runtime/identity_authorities/0/resource_scopes/0/native_id
    posture: open
nodes:
  cloud:
    type: compute
    runtime:
      identity_authorities:
      - identity_authority_id: iam
        kind: cloud_iam
        resource_scopes:
        - scope_id: project
          provider: gcp
          scope_kind: project
""")
    )
    target = create_stub_target()
    support = target.manifest.realization_support[0]
    kind = "runtime-identity-authorities"
    # Synthetic support for this one concern, with no provider or broad open-family support.
    manifest = replace(
        target.manifest,
        supported_contract_versions=target.manifest.supported_contract_versions
        | {"backend-realization-preparation-v1"},
        realization_support=(
            replace(
                support,
                supported_exact_requirement_kinds=support.supported_exact_requirement_kinds | {kind},
                supported_constraint_kinds=support.supported_constraint_kinds | {kind},
                observation_capabilities={
                    **support.observation_capabilities,
                    kind: RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                },
            ),
        ),
    )
    provisioner = _PreparingProvisioner(manifest.realization_envelope)
    execution = RuntimeManager(replace(target, manifest=manifest, provisioner=provisioner)).plan(scenario)
    assert not [diagnostic for diagnostic in execution.diagnostics if diagnostic.is_error]
    return execution.provisioning, manifest


def _cloud(plan):
    return next(operation for operation in plan.operations if operation.address == "provision.node.cloud")


def _authorities(plan):
    return _cloud(plan).payload["spec"]["node"]["runtime"]["identity_authorities"]


def _selected(request):
    operations = deepcopy(request.operations)
    proposal = replace(request, operations=operations)
    _authorities(proposal)[0]["resource_scopes"][0]["native_id"] = "synthetic-project"
    response = RealizationPreparation.for_request(request, RuntimeSnapshot(), operations=tuple(operations))
    wire = preparation_response_model(response).model_dump_json()
    decoded = type(preparation_response_model(response)).model_validate_json(wire).to_runtime()
    return replace(request, operations=list(decoded.operations))


class _PreparingProvisioner(StubProvisioner):
    def prepare(self, request, snapshot):
        return RealizationPreparation.for_request(request, snapshot, operations=tuple(_selected(request).operations))


def test_scalar_scope_preparation_and_completion(scalar_scope_plan):
    request, manifest = scalar_scope_plan
    selected = _selected(request)
    authority = next(
        item for item in request.realization_authority if item.requirement_kind == "runtime-identity-authorities"
    )
    assert authority.mode is RealizationAuthorityMode.CONSTRAINED
    assert prepared_realization_violation(request, selected, manifest) is None
    operation = _cloud(selected)
    snapshot = RuntimeSnapshot(
        entries={
            operation.address: SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.PROVISIONING,
                resource_type=operation.resource_type,
                payload=deepcopy(operation.payload),
            )
        }
    )
    assert prepared_delivery_violation(selected, snapshot) is None
    delivered = snapshot.entries[operation.address].payload["spec"]["node"]["runtime"]
    delivered["identity_authorities"][0]["resource_scopes"][0]["native_id"] = "different-project"
    assert prepared_delivery_violation(selected, snapshot) is not None


@pytest.mark.parametrize(
    "change",
    ["kind", "provider", "scope_kind", "scope_id", "authority_id", "add_scope", "add_authority", "remove_scope"],
)
def test_closed_siblings_and_collections_reject_changes(scalar_scope_plan, change):
    request, manifest = scalar_scope_plan
    selected = _selected(request)
    authorities = _authorities(selected)
    authority, scope = authorities[0], authorities[0]["resource_scopes"][0]
    if change == "kind":
        authority["kind"] = "x-test:changed"
    elif change == "authority_id":
        authority["identity_authority_id"] = "renamed"
    elif change == "add_authority":
        authorities.append({**deepcopy(authority), "identity_authority_id": "extra"})
    elif change == "add_scope":
        authority["resource_scopes"].append({**scope, "scope_id": "extra"})
    elif change == "remove_scope":
        authority["resource_scopes"].clear()
    else:
        scope[change] = "changed"
    assert prepared_realization_violation(request, selected, manifest) is not None


def test_serialized_authority_matches_recursive_document(scalar_scope_plan):
    request, _ = scalar_scope_plan
    portable = ProvisioningPlanModel.model_validate_json(provisioning_plan_model(request).model_dump_json())
    authority = next(
        item for item in portable.realization_authority if item.requirement_kind == "runtime-identity-authorities"
    )
    projected = project_realization_concern(
        authority.requirement_kind, _authorities(_selected(request)), recursive=True
    )
    assert evaluate_realization_constraint(authority.constraint_document, projected).conformant
    assert authority.mode is RealizationAuthorityMode.CONSTRAINED


def test_unrelated_omissions_remain_closed(scalar_scope_plan):
    request, manifest = scalar_scope_plan
    omitted = {
        item.requirement_kind: item for item in request.realization_authority if item.address == "provision.node.cloud"
    }
    for kind in ("os-family", "runtime-database-services", "runtime-packages"):
        assert omitted[kind].mode is RealizationAuthorityMode.CLOSED
        assert kind not in manifest.realization_support[0].supported_constraint_kinds or kind == "os-family"
    selected = _selected(request)
    _cloud(selected).payload["spec"]["node"]["runtime"]["database_services"] = [
        {"database_service_id": "extra", "engine": "sqlite"}
    ]
    assert prepared_realization_violation(request, selected, manifest) is not None
