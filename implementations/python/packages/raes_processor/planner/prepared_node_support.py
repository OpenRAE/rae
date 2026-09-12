"""Use existing support and artifact admission for backend-selected node values."""

from __future__ import annotations

from collections.abc import Sequence

from raes.explicitness import ExplicitnessClass, ExplicitnessProvenance
from raes.nodes import Node
from raes.realization_envelope import member_projection
from raes.runtime_resource_limits import (
    RuntimeProcessResourceLimit,
    process_resource_limit_identity_digest,
)
from raes_backend_protocols.manifest import BackendManifest
from raes_contracts.artifact_requirements import ArtifactAvailabilityContext
from raes_contracts.vocabulary import ProcessResourceLimitScope

from ..compiler.realization_value_domains import nested_authored_value
from ..semantics.artifact_realization import artifact_requirement_diagnostics
from ..semantics.realization_concerns import realization_concern_descriptors
from ..semantics.realization_process_limits import ProcessResourceLimitDemand
from ..semantics.realization_requirement import CompiledRealizationRequirement
from ..semantics.realization_support import realization_support_diagnostics


def _authored_process_limits(value: object) -> tuple[RuntimeProcessResourceLimit, ...]:
    """Admit one authored concern value as the typed process-limit collection.

    ``nested_authored_value`` walks the declaration generically and so reports
    ``object``. The registered concern is declared as
    ``list[RuntimeProcessResourceLimit]``, and anything else is a compiler
    defect rather than an authoring error, so admission fails closed.
    """

    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ValueError("authored process resource limits must be a typed collection")
    limits = tuple(limit for limit in value if isinstance(limit, RuntimeProcessResourceLimit))
    if len(limits) != len(value):
        raise ValueError("authored process resource limits must be typed runtime limit records")
    return limits


def _process_limit_demands(concern_kind: str, value: object) -> tuple[ProcessResourceLimitDemand, ...]:
    """Project typed process-resource limits into their compiled demands."""

    if concern_kind != "process-resource-limits":
        return ()
    return tuple(
        ProcessResourceLimitDemand(
            identity_digest=process_resource_limit_identity_digest(limit),
            resource=limit.resource,
            scope=ProcessResourceLimitScope(limit.scope.value),
            soft=limit.soft,
            hard=limit.hard,
        )
        for limit in _authored_process_limits(value)
    )


def _prepared_node_requirements(resource: object, node: Node) -> tuple[CompiledRealizationRequirement, ...]:
    """Restate one prepared node's concrete choices as backend-realized requirements."""

    requirements = []
    for descriptor in realization_concern_descriptors():
        if descriptor.section != "nodes" or descriptor.authored_path[0] != "runtime":
            continue
        value = nested_authored_value(node, descriptor.authored_path)
        if value is None or value in ([], {}, ""):
            continue
        requirements.append(
            CompiledRealizationRequirement(
                field_path=f"nodes.{resource.name}.{descriptor.authored_suffix}",
                address=resource.address,
                domain="runtime-realization",
                requirement_kind=descriptor.concern_kind,
                explicitness=ExplicitnessClass.EXACT,
                provenance=ExplicitnessProvenance.BACKEND_REALIZED,
                process_resource_limits=_process_limit_demands(descriptor.concern_kind, value),
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
    return tuple(requirements)


def _require_configured_offer(resource: object, node: Node, manifest: BackendManifest | None) -> None:
    """Require one prepared node to fall inside the configured realization offer."""

    envelope = None if manifest is None else manifest.realization_envelope
    holds = (
        envelope is not None
        and member_projection(
            resource.spec["node"],
            f"nodes.{resource.name}",
            envelope.expression,
            typed_value=node,
        ).holds
    )
    if not holds:
        raise ValueError("prepared node is outside its configured realization offer")


def validate_prepared_node_support(
    resource: object,
    node: Node,
    manifest: BackendManifest | None,
    availability: ArtifactAvailabilityContext | None,
) -> None:
    """A concrete backend choice is not authored intent or an observation demand."""

    requirements = _prepared_node_requirements(resource, node)
    unsupported = any(
        diagnostic.is_error
        for diagnostic in (
            *realization_support_diagnostics(requirements, manifest),
            *artifact_requirement_diagnostics(requirements, manifest, availability=availability),
        )
    )
    if unsupported:
        raise ValueError("prepared node lacks existing concern or artifact admission")
    _require_configured_offer(resource, node, manifest)
