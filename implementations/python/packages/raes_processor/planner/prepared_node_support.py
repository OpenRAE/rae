"""Use existing support and artifact admission for backend-selected node values."""

from __future__ import annotations

from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes.nodes import Node
from raes.realization_envelope import member_projection
from raes.runtime_resource_limits import process_resource_limit_identity_digest
from raes_backend_protocols.manifest import BackendManifest
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.vocabulary import ProcessResourceLimitScope

from ..compiler.realization_value_domains import nested_authored_value
from ..semantics.artifact_realization import artifact_requirement_diagnostics
from ..semantics.realization_concerns import realization_concern_descriptors
from ..semantics.realization_process_limits import ProcessResourceLimitDemand
from ..semantics.realization_requirement import CompiledRealizationRequirement
from ..semantics.realization_support import realization_support_diagnostics


def validate_prepared_node_support(
    resource: object,
    node: Node,
    manifest: BackendManifest | None,
    availability: ArtifactAvailabilityContext | None,
) -> None:
    """A concrete backend choice is not authored intent or an observation demand."""

    requirements = []
    for descriptor in realization_concern_descriptors():
        if descriptor.section != "nodes" or descriptor.authored_path[0] != "runtime":
            continue
        value = nested_authored_value(node, descriptor.authored_path)
        if value is None or value == [] or value == {} or value == "":
            continue
        demands = ()
        if descriptor.concern_kind == "process-resource-limits":
            demands = tuple(
                ProcessResourceLimitDemand(
                    identity_digest=process_resource_limit_identity_digest(limit),
                    resource=limit.resource,
                    scope=ProcessResourceLimitScope(limit.scope.value),
                    soft=limit.soft,
                    hard=limit.hard,
                )
                for limit in value
            )
        requirements.append(
            CompiledRealizationRequirement(
                field_path=f"nodes.{resource.name}.{descriptor.authored_suffix}",
                address=resource.address,
                domain="runtime-realization",
                requirement_kind=descriptor.concern_kind,
                explicitness=ExplicitnessClass.EXACT,
                provenance=ExplicitnessProvenance.BACKEND_REALIZED,
                process_resource_limits=demands,
            )
        )
    if node.source is not None and node.source.artifact_requirement is not None:
        artifact = node.source.artifact_requirement
        requirements.append(
            CompiledRealizationRequirement(
                field_path=f"nodes.{resource.name}.source.artifact_requirement",
                address=resource.address,
                domain="runtime-realization",
                requirement_kind="source-artifact",
                explicitness=artifact.explicitness,
                provenance=ExplicitnessProvenance.BACKEND_REALIZED,
                artifact_requirement=artifact,
            )
        )
    if any(
        diagnostic.is_error
        for diagnostic in (
            *realization_support_diagnostics(tuple(requirements), manifest),
            *artifact_requirement_diagnostics(tuple(requirements), manifest, availability=availability),
        )
    ):
        raise ValueError("prepared node lacks existing concern or artifact admission")
    if (
        manifest.realization_envelope is None
        or not member_projection(
            resource.spec["node"],
            f"nodes.{resource.name}",
            manifest.realization_envelope.expression,
            typed_value=node,
        ).holds
    ):
        raise ValueError("prepared node is outside its configured realization offer")
