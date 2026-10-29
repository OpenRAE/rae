"""Disclose delivered preparation additions under their enclosing authority."""

from dataclasses import replace

from pydantic import TypeAdapter
from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes.nodes import Node
from raes_backend_protocols.manifest import BackendManifest
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ProvisioningPlan, ProvisionOp
from raes_contracts.runtime_state import RealizationProvenanceEntry, RuntimeSnapshot

from ..semantics.artifact_realization import evaluate_artifact_realization
from ..semantics.realization_compute_substrate import evaluate_compute_substrate
from ..semantics.realization_concern_observations import typed_runtime_observation_shape
from ..semantics.realization_requirement import CompiledRealizationRequirement
from .backend_node_provenance import backend_node_concern_provenance
from .prepared_node_projection import prepared_additional_node_operations


def prepared_node_disclosure(
    selected: ProvisioningPlan,
    snapshot: RuntimeSnapshot,
    *,
    manifest: BackendManifest | None,
    artifact_availability: ArtifactAvailabilityContext | None = None,
) -> tuple[list[Diagnostic], tuple[RealizationProvenanceEntry, ...]]:
    """Reuse registered concerns and dedicated substrate/artifact evaluation owners."""

    diagnostics: list[Diagnostic] = []
    records: list[RealizationProvenanceEntry] = []
    operations = {operation.address: operation for operation in selected.operations}
    for operation in prepared_additional_node_operations(selected):
        supplied = operation.payload["spec"]["node"]
        node = typed_runtime_observation_shape(supplied, adapter=TypeAdapter(Node))
        authority = selected.preparation.node_collection
        scope = authority.governing_scope or authority.scope_pointer
        name = operation.payload["node_name"]
        records.extend(backend_node_concern_provenance(operation.address, name, node, supplied, governing_scope=scope))
        for requirement in _dedicated_requirements(operation, node, scope):
            if requirement.requirement_kind == "compute-substrate":
                pointer_name = name.replace("~", "~0").replace("/", "~1")
                diagnostic, record = evaluate_compute_substrate(
                    replace(requirement, governing_scope=f"#/nodes/{pointer_name}"), selected, snapshot, manifest
                )
            else:
                diagnostic, record = evaluate_artifact_realization(
                    requirement, operations, snapshot, manifest=manifest, availability=artifact_availability
                )
            if diagnostic is not None:
                diagnostics.append(diagnostic)
            if record is not None:
                records.append(replace(record, explicitness=ExplicitnessClass.OPEN, governing_scope=scope))
    return diagnostics, tuple(records)


def _dedicated_requirements(
    operation: ProvisionOp, node: Node, scope: str
) -> tuple[CompiledRealizationRequirement, ...]:
    """Keep non-registry concerns with their existing contract-specific evaluators."""

    name = operation.payload["node_name"]
    requirements = []
    if operation.resource_type == "node":
        requirements.append(
            CompiledRealizationRequirement(
                address=operation.address,
                domain="runtime-realization",
                provenance=ExplicitnessProvenance.BACKEND_REALIZED,
                governing_scope=scope,
                field_path=f"nodes.{name}.realization.compute-substrate",
                requirement_kind="compute-substrate",
                explicitness=ExplicitnessClass.OPEN,
            )
        )
    artifact = node.source.artifact_requirement if node.source is not None else None
    if artifact is not None:
        requirements.append(
            CompiledRealizationRequirement(
                address=operation.address,
                domain="runtime-realization",
                provenance=ExplicitnessProvenance.BACKEND_REALIZED,
                governing_scope=scope,
                field_path=f"nodes.{name}.source.artifact_requirement",
                requirement_kind="source-artifact",
                explicitness=artifact.explicitness,
                artifact_requirement=artifact,
            )
        )
    return tuple(requirements)
