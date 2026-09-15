"""Admit a descriptive SDL result without changing original realization authority."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import TypeAlias

from raes import (
    MaterializedScenario,
    admit_instantiated_scenario,
    canonical_materialized_sdl_digest,
    parse_sdl,
    render_sdl_source,
)
from raes.materialization_provenance import MaterializedResourceBinding
from raes.scenario import InstantiatedScenario
from raes_backend_protocols.manifest import BackendManifest, backend_manifest_v2_model
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.materialization_attestation import MaterializationArchiveRecord
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.materialization import (
    MATERIALIZATION_MAX_BYTES,
    MaterializationSource,
    MaterializationSubmission,
    require_materialization_records,
)
from raes_contracts.plan_projection import runtime_plan_digest
from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, PlannedResource, ProvisioningPlan, RuntimeDomain
from raes_contracts.realization_preparation import preparation_snapshot_digest
from raes_contracts.runtime_state import RuntimeSnapshot, SnapshotEntry

from ..compiler import compile_runtime_model, validate_materialization_origins
from ..compiler.materialization_origins import materialization_node_payloads_match
from ..models import RuntimeModel
from .ordering import _entry_matches_resource
from .resources import _collect_resources

MaterializationPlan: TypeAlias = ProvisioningPlan | OrchestrationPlan | EvaluationPlan


def admit_materialization_submission(
    submission: MaterializationSubmission,
    request: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
    manifest: BackendManifest,
    previous: RuntimeSnapshot,
    actual: RuntimeSnapshot,
) -> MaterializationSubmission:
    """Check source, execution binding, origins and complete scoped inventory."""
    submission = MaterializationSubmission.model_validate(submission.model_dump(mode="json"))
    if request.materialization_source is None:
        raise ValueError("materialization requires trusted source context")
    source = MaterializationSource.model_validate(request.materialization_source.model_dump(mode="json"))
    source_payload = parse_bounded_json_object(source.snapshot, max_bytes=MATERIALIZATION_MAX_BYTES)
    original = admit_instantiated_scenario(source_payload["scenario"])
    materialized = parse_sdl(submission.sdl)
    if not isinstance(materialized, MaterializedScenario):
        raise ValueError("materialization requires descriptive SDL")
    _validate_binding(materialized, source, request, manifest, previous)
    validate_materialization_origins(original, materialized)
    _validate_inventory(materialized, original, request, previous, actual)
    return MaterializationSubmission(sdl=render_sdl_source(materialized).content)


def _validate_binding(
    materialized: MaterializedScenario,
    source: MaterializationSource,
    request: MaterializationPlan,
    manifest: BackendManifest,
    previous: RuntimeSnapshot,
) -> None:
    provenance = materialized.materialization_provenance
    envelope = manifest.realization_envelope
    if envelope is None:
        raise ValueError("materialization does not bind this source and execution")
    described = (
        provenance.authored_digest.value,
        provenance.instantiated_digest.value,
        provenance.plan_digest,
        provenance.predecessor_digest,
        provenance.operation_id,
        provenance.run_id,
        provenance.producer.name,
        provenance.producer.version,
        provenance.producer.configuration_digest,
        provenance.producer.manifest_digest,
    )
    expected = (
        source.authored_digest,
        source.instantiated_digest,
        runtime_plan_digest(request),
        preparation_snapshot_digest(previous),
        request.operation_id,
        source.run_id,
        manifest.name,
        manifest.version,
        envelope.configuration.configuration_digest,
        canonical_json_digest(backend_manifest_v2_model(manifest).model_dump(mode="json")),
    )
    if described != expected:
        raise ValueError("materialization does not bind this source and execution")


def _inventory_resources(
    compiled: RuntimeModel, request: MaterializationPlan, previous: RuntimeSnapshot
) -> dict[str, PlannedResource]:
    """Retain planner metadata from admitted operations or the trusted predecessor.

    These projections are not SDL facts. Never take them from the description
    or returned inventory: current selections come from the prepared operation,
    and later phases retain the predecessor's completed selections and scope.
    """
    from .core import _apply_regeneration_scope_bindings

    resources = _collect_resources(compiled)
    operations = {operation.address: operation for operation in request.operations}
    for address, resource in resources.items():
        context = operations.get(address) or previous.get(address)
        if context is None:
            continue
        payload = resource.payload
        if resource.resource_type == "generated-artifact" and "scope_binding" in context.payload:
            payload = {**payload, "scope_binding": context.payload["scope_binding"]}
        resources[address] = replace(
            resource, payload=payload, profile_bindings=getattr(context, "profile_bindings", ())
        )
    if isinstance(request, ProvisioningPlan):
        resources, diagnostics = _apply_regeneration_scope_bindings(
            resources, run_id=request.run_id, instantiation_id=request.instantiation_id
        )
        if diagnostics:
            raise ValueError("materialization inventory lacks admitted regeneration scope")
    return resources


def _validate_inventory(
    materialized: MaterializedScenario,
    original: InstantiatedScenario,
    request: MaterializationPlan,
    previous: RuntimeSnapshot,
    actual: RuntimeSnapshot,
) -> None:
    compiled = compile_runtime_model(materialized)
    resources = _inventory_resources(compiled, request, previous)
    domains = {
        ProvisioningPlan: RuntimeDomain.PROVISIONING,
        OrchestrationPlan: RuntimeDomain.ORCHESTRATION,
        EvaluationPlan: RuntimeDomain.EVALUATION,
    }
    domain = domains[type(request)]
    _validate_current_scope(resources, actual, domain)
    _validate_other_scopes(resources, compile_runtime_model(original), request, previous, actual, domain)
    _validate_node_bindings(materialized, original, resources)


def _validate_current_scope(
    resources: dict[str, PlannedResource], actual: RuntimeSnapshot, domain: RuntimeDomain
) -> None:
    expected = _resources_for_domain(resources, domain)
    observed = actual.for_domain(domain)
    if expected.keys() != observed.keys() or any(
        not _materialized_entry_matches(observed[address], resource) for address, resource in expected.items()
    ):
        raise ValueError("materialization inventory does not match the complete returned scope")


def _resources_for_domain(resources: dict[str, PlannedResource], domain: RuntimeDomain) -> dict[str, PlannedResource]:
    return {address: resource for address, resource in resources.items() if resource.domain == domain}


def _validate_other_scopes(
    resources: dict[str, PlannedResource],
    original_model: RuntimeModel,
    request: MaterializationPlan,
    previous: RuntimeSnapshot,
    actual: RuntimeSnapshot,
    domain: RuntimeDomain,
) -> None:
    original_resources = _inventory_resources(original_model, request, previous)
    for other_domain in RuntimeDomain:
        if other_domain == domain:
            continue
        previous_scope = actual.for_domain(other_domain) or _resources_for_domain(original_resources, other_domain)
        described_scope = _resources_for_domain(resources, other_domain)
        if previous_scope.keys() != described_scope.keys() or any(
            not (
                _entry_matches_resource(previous_scope[address], resource, original_model.realization_requirements)
                or _materialized_entry_matches(previous_scope[address], resource)
            )
            for address, resource in described_scope.items()
        ):
            raise ValueError("materialization cannot invent or omit effects outside its operation domain")


def _validate_binding_origin(binding: MaterializedResourceBinding, original: InstantiatedScenario) -> None:
    if binding.node_name in original.nodes:
        if binding.source_node != binding.node_name:
            raise ValueError("materialization inventory changed an authored resource identity")
    elif binding.source_node is not None:
        raise ValueError("materialization inventory has an invalid added resource origin")


def _validate_node_bindings(
    materialized: MaterializedScenario, original: InstantiatedScenario, resources: dict[str, PlannedResource]
) -> None:
    bindings = materialized.materialization_provenance.resource_bindings
    if {binding.node_name for binding in bindings} != materialized.nodes.keys():
        raise ValueError("materialization inventory lacks complete node bindings")
    instances: dict[str, set[int | None]] = {}
    for binding in bindings:
        resource = resources.get(binding.address)
        if resource is None or resource.payload.get("name") != binding.node_name:
            raise ValueError("materialization inventory has a mismatched resource binding")
        _validate_binding_origin(binding, original)
        instances.setdefault(binding.address, set()).add(binding.instance_index)
    _validate_instance_indices(resources, instances, len(bindings))


def _validate_instance_indices(
    resources: dict[str, PlannedResource], instances: dict[str, set[int | None]], binding_count: int
) -> None:
    for address, indices in instances.items():
        count = resources[address].payload.get("count") or 1
        if count > binding_count or (indices != set(range(count)) and not (count == 1 and indices == {None})):
            raise ValueError("materialization inventory must bind every realized instance exactly once")


def _materialized_entry_matches(entry: SnapshotEntry | PlannedResource, resource: PlannedResource) -> bool:
    if resource.resource_type == "node":
        expected_spec, observed_spec = resource.payload.get("spec"), entry.payload.get("spec")
        if not isinstance(expected_spec, dict) or not isinstance(observed_spec, dict):
            return False
        if not materialization_node_payloads_match(
            resource.payload["name"], expected_spec.get("node"), observed_spec.get("node")
        ):
            return False
        entry = replace(entry, payload={**entry.payload, "spec": {**observed_spec, "node": expected_spec["node"]}})
    return _entry_matches_resource(entry, resource)


def validate_materialization_archive_record(
    submission: MaterializationSubmission, record: MaterializationArchiveRecord
) -> None:
    """An archive adapter cannot substitute different bytes or semantic lineage."""
    require_materialization_records((record,))
    scenario = parse_sdl(submission.sdl)
    if not isinstance(scenario, MaterializedScenario):
        raise ValueError("materialization archive requires descriptive SDL")
    provenance = scenario.materialization_provenance
    data = submission.sdl.encode("utf-8")
    recorded = (
        record.run_id,
        record.operation_id,
        record.reference.ref_id,
        record.reference.ref_digest,
        record.reference.ref_path,
        record.artifact.checksum.value,
        record.artifact.size_bytes,
        record.artifact.source,
        record.artifact.created_at,
    )
    expected = (
        provenance.run_id,
        provenance.operation_id,
        provenance.attestation_id,
        canonical_materialized_sdl_digest(scenario).value,
        f"runs/{provenance.run_id}/attestations/{provenance.attestation_id}.sdl",
        hashlib.sha256(data).hexdigest(),
        len(data),
        provenance.producer.name,
        provenance.recorded_at.isoformat(),
    )
    if recorded != expected:
        raise ValueError("materialization archive record does not bind the admitted result")


__all__ = ["admit_materialization_submission", "validate_materialization_archive_record"]
