"""Shared runtime planning contracts and safe planned-resource readers.

Backend and provisioner implementations should use the named
``planned_*`` accessors in this module instead of traversing a
:class:`PlannedResource` payload directly.  The accessors are total, perform no
validation or normalization, and return ``None`` when a requested surface is
missing or does not apply to the resource's domain and type.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from raes.explicitness import ExplicitnessProvenance

from raes_contracts.addressing import require_compiled_address
from raes_contracts.bounded_domains import DomainDescriptor
from raes_contracts.compute_substrate import validate_compute_substrate_constraint
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.observation_demand import EffectiveObservationDemand
from raes_contracts.realization_structure import RealizationStructure
from raes_contracts.vocabulary import ObservationStrength, RealizationVerificationScope

if TYPE_CHECKING:
    from raes_contracts.contracts import RealizationEnvelopeIdentityModel


class RuntimeDomain(str, Enum):
    """Top-level runtime concern."""

    PROVISIONING = "provisioning"
    ORCHESTRATION = "orchestration"
    EVALUATION = "evaluation"
    PARTICIPANT = "participant"


PLAN_ADDRESS_ROOT_BY_DOMAIN = {
    RuntimeDomain.PROVISIONING: "provision",
    RuntimeDomain.ORCHESTRATION: "orchestration",
    RuntimeDomain.EVALUATION: "evaluation",
}
PLAN_RESOURCE_TYPES_BY_DOMAIN = {
    RuntimeDomain.PROVISIONING: frozenset(
        {
            "network",
            "node",
            "feature-binding",
            "content-placement",
            "account-placement",
            "domain-controller-placement",
            "generated-artifact",
            "persistent-volume",
        }
    ),
    RuntimeDomain.ORCHESTRATION: frozenset({"inject-binding", "inject", "event", "script", "story", "workflow"}),
    RuntimeDomain.EVALUATION: frozenset({"condition-binding", "proposition", "assertion", "objective"}),
}


def require_plan_operation_identity(domain: RuntimeDomain, address: object, resource_type: object) -> None:
    """Reject operations outside a plan endpoint's closed identity domain."""

    canonical = require_compiled_address(address)
    root = PLAN_ADDRESS_ROOT_BY_DOMAIN.get(domain)
    resource_types = PLAN_RESOURCE_TYPES_BY_DOMAIN.get(domain)
    if root is None or not canonical.startswith(f"{root}."):
        raise ValueError("Plan operation address must belong to its runtime domain")
    if not isinstance(resource_type, str) or resource_types is None or resource_type not in resource_types:
        raise ValueError("Plan operation resource_type must belong to its runtime domain")


class ChangeAction(str, Enum):
    """Planner reconciliation result for a resource."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    UNCHANGED = "unchanged"


class RealizationAuthorityMode(str, Enum):
    """Resolved author permission for one portable realization concern."""

    CLOSED = "closed"
    OPEN = "open"
    CONSTRAINED = "constrained"
    EXACT = "exact"


class RealizationResolutionSource(str, Enum):
    """Canonical source that supplied a resolved realization decision."""

    AUTHORED_LEAF = "authored-leaf"
    AUTHORED_SCOPE = "authored-scope"
    APPARATUS_DEFAULT = "apparatus-default"
    LEGACY_DEFAULT = "legacy-default"
    PROCESSOR_DERIVED = "processor-derived"


_JSON_POINTER_RE = re.compile(r"^(?:/(?:[^~/]|~[01])*)*$")


def _require_json_pointer(value: object, *, field_name: str, allow_root: bool) -> str:
    if not isinstance(value, str) or (not allow_root and not value) or _JSON_POINTER_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical RFC 6901 JSON Pointer")
    return value


@dataclass(frozen=True)
class RealizationAuthorityBound:
    """One publication-safe typed bound over a concern value or owned leaf."""

    value_pointer: str
    domain: DomainDescriptor
    identity_digest: str | None = None

    def __post_init__(self) -> None:
        _require_json_pointer(self.value_pointer, field_name="authority bound value_pointer", allow_root=True)
        if self.identity_digest is not None and not re.fullmatch(r"sha256:[a-f0-9]{64}", self.identity_digest):
            raise ValueError("authority bound identity_digest must be a sha256 digest")


def _require_authority_bounds(
    mode: RealizationAuthorityMode,
    bounds: tuple[RealizationAuthorityBound, ...],
) -> None:
    if mode is RealizationAuthorityMode.CONSTRAINED and not bounds:
        raise ValueError("constrained realization authority requires typed bounds")
    if mode is not RealizationAuthorityMode.CONSTRAINED and bounds:
        raise ValueError("only constrained realization authority may carry typed bounds")


def _require_authority_source(mode: RealizationAuthorityMode, source: RealizationResolutionSource) -> None:
    if source is RealizationResolutionSource.LEGACY_DEFAULT and mode is not RealizationAuthorityMode.CLOSED:
        raise ValueError("legacy realization default must resolve closed")
    if source is RealizationResolutionSource.APPARATUS_DEFAULT and mode not in {
        RealizationAuthorityMode.CLOSED,
        RealizationAuthorityMode.OPEN,
    }:
        raise ValueError("apparatus realization default must resolve open or closed")


@dataclass(frozen=True)
class ResolvedRealizationAuthority:
    """Portable, value-safe author boundary for one planned concern."""

    address: str
    field_path: str
    domain: str
    requirement_kind: str
    payload_pointer: str
    mode: RealizationAuthorityMode
    source: RealizationResolutionSource
    provenance: ExplicitnessProvenance = ExplicitnessProvenance.AUTHOR_DECLARED
    governing_scope: str | None = None
    bounds: tuple[RealizationAuthorityBound, ...] = ()
    verification_scope: RealizationVerificationScope | None = None
    required_observation_strength: ObservationStrength | None = None
    structure: RealizationStructure | None = None

    def __post_init__(self) -> None:
        require_compiled_address(self.address)
        if not self.field_path or not self.domain or not self.requirement_kind:
            raise ValueError("resolved realization authority requires non-empty concern identity")
        _require_json_pointer(
            self.payload_pointer,
            field_name="resolved realization authority payload_pointer",
            allow_root=False,
        )
        _require_authority_bounds(self.mode, self.bounds)
        _require_authority_source(self.mode, self.source)


def planned_realization_authority(
    plan: ProvisioningPlan,
    address: str,
    requirement_kind: str,
) -> ResolvedRealizationAuthority | None:
    """Return one resolved authority entry, or ``None`` when not present."""

    return next(
        (
            entry
            for entry in plan.realization_authority
            if entry.address == address and entry.requirement_kind == requirement_kind
        ),
        None,
    )


@dataclass(frozen=True)
class PlannedResource:
    """Normalized resource used by the planner and snapshot."""

    address: str
    domain: RuntimeDomain
    resource_type: str
    payload: dict[str, Any]
    ordering_dependencies: tuple[str, ...] = ()
    refresh_dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_compiled_address(self.address)
        for dependency in (*self.ordering_dependencies, *self.refresh_dependencies):
            require_compiled_address(dependency, field_name="dependency address")


def planned_resource_payload(resource: PlannedResource) -> Mapping[str, Any] | None:
    """Return the resource's mapping payload, or ``None`` when it is malformed.

    The original mapping is returned without copying or mutation.  This reader
    is domain-neutral; callers should use the narrower provisioning readers
    below for fields whose meaning depends on a runtime domain or resource type.
    """

    payload = resource.payload
    return payload if isinstance(payload, Mapping) else None


def planned_resource_authored_name(resource: PlannedResource) -> str | None:
    """Return the authored top-level resource name, if one is available."""

    payload = planned_resource_payload(resource)
    if payload is None:
        return None
    name = payload.get("name") or payload.get("node_name")
    return name if isinstance(name, str) and name else None


def planned_resource_name(resource: PlannedResource) -> str:
    """Return the authored resource name or its full canonical address.

    The address is a stable, provider-neutral fallback.  Backends that require
    provider-safe native names remain responsible for deriving those names from
    the address.
    """

    return planned_resource_authored_name(resource) or resource.address


def planned_node_spec(resource: PlannedResource) -> Mapping[str, Any] | None:
    """Return ``spec.node`` for a provisioning node, otherwise ``None``."""

    if resource.domain is not RuntimeDomain.PROVISIONING or resource.resource_type != "node":
        return None
    payload = planned_resource_payload(resource)
    spec = payload.get("spec") if payload is not None else None
    node = spec.get("node") if isinstance(spec, Mapping) else None
    return node if isinstance(node, Mapping) else None


def planned_node_source(resource: PlannedResource) -> str | Mapping[str, Any] | None:
    """Return a provisioning node's authored string-or-mapping source.

    Mapping sources retain all source/build inputs and are not collapsed to a
    backend-specific image name.  Empty strings and unsupported value shapes
    are treated as absent.
    """

    node = planned_node_spec(resource)
    source = node.get("source") if node is not None else None
    if isinstance(source, str):
        return source if source else None
    return source if isinstance(source, Mapping) else None


def planned_node_resources(resource: PlannedResource) -> Mapping[str, Any] | None:
    """Return a provisioning node's authored resources mapping, if present."""

    node = planned_node_spec(resource)
    resources = node.get("resources") if node is not None else None
    return resources if isinstance(resources, Mapping) else None


def planned_infrastructure_spec(resource: PlannedResource) -> Mapping[str, Any] | None:
    """Return ``spec.infrastructure`` for a provisioning node or network.

    Infrastructure is intentionally unavailable for other provisioning
    resource types and for other runtime domains rather than being inferred
    from a coincidentally similar payload shape.
    """

    if resource.domain is not RuntimeDomain.PROVISIONING or resource.resource_type not in {"node", "network"}:
        return None
    payload = planned_resource_payload(resource)
    spec = payload.get("spec") if payload is not None else None
    infrastructure = spec.get("infrastructure") if isinstance(spec, Mapping) else None
    return infrastructure if isinstance(infrastructure, Mapping) else None


@dataclass(frozen=True)
class PlanOperation:
    """A reconciliation operation for a planned resource."""

    action: ChangeAction
    address: str
    resource_type: str
    payload: dict[str, Any]
    ordering_dependencies: tuple[str, ...] = ()
    refresh_dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_compiled_address(self.address)
        for dependency in (*self.ordering_dependencies, *self.refresh_dependencies):
            require_compiled_address(dependency, field_name="dependency address")


class ProvisionOp(PlanOperation):
    """Provisioning reconciliation operation."""


@dataclass(frozen=True)
class PlannedRealizationConstraint:
    """Value-bearing author demand carried separately from apparatus choice."""

    address: str
    field_path: str
    concern: str
    posture: str
    value_domain: DomainDescriptor | None
    governing_scope: str
    provenance: str

    def __post_init__(self) -> None:
        require_compiled_address(self.address)
        if self.concern != "compute-substrate":
            raise ValueError("planned realization constraint concern is unsupported")
        if self.posture not in {"open", "constrained", "exact"}:
            raise ValueError("planned realization constraint posture is invalid")
        validate_compute_substrate_constraint(self.posture, self.value_domain)


class OrchestrationOp(PlanOperation):
    """Orchestration reconciliation operation."""


class EvaluationOp(PlanOperation):
    """Evaluation reconciliation operation."""


@dataclass(frozen=True)
class ProvisioningPlan:
    """Provisioning plan over canonical deployment resources."""

    resources: dict[str, PlannedResource] = field(default_factory=dict)
    operations: list[ProvisionOp] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    realization_authority: tuple[ResolvedRealizationAuthority, ...] = ()
    realization_envelope: RealizationEnvelopeIdentityModel | None = None
    realization_constraints: tuple[PlannedRealizationConstraint, ...] = ()
    operation_id: str | None = None
    observation_demands: tuple[EffectiveObservationDemand, ...] = ()

    def __post_init__(self) -> None:
        if self.operation_id is not None and not self.operation_id.strip():
            raise ValueError("ProvisioningPlan operation_id must be non-empty when present")
        _validate_plan_addresses(self.resources, self.operations, domain=RuntimeDomain.PROVISIONING)
        identities = [(item.address, item.concern) for item in self.realization_constraints]
        if len(identities) != len(set(identities)):
            raise ValueError("Provisioning plan realization constraints must identify unique concerns")
        _validate_realization_authority(self.operations, self.realization_authority)

    @property
    def actionable_operations(self) -> list[ProvisionOp]:
        return [op for op in self.operations if op.action != ChangeAction.UNCHANGED]


@dataclass(frozen=True)
class OrchestrationPlan:
    """Resolved orchestration graph and reconciliation actions."""

    resources: dict[str, PlannedResource] = field(default_factory=dict)
    operations: list[OrchestrationOp] = field(default_factory=list)
    startup_order: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    observation_demands: tuple[EffectiveObservationDemand, ...] = ()

    def __post_init__(self) -> None:
        _validate_plan_addresses(
            self.resources,
            self.operations,
            self.startup_order,
            domain=RuntimeDomain.ORCHESTRATION,
        )

    @property
    def actionable_operations(self) -> list[OrchestrationOp]:
        return [op for op in self.operations if op.action != ChangeAction.UNCHANGED]


@dataclass(frozen=True)
class EvaluationPlan:
    """Resolved evaluation graph and reconciliation actions."""

    resources: dict[str, PlannedResource] = field(default_factory=dict)
    operations: list[EvaluationOp] = field(default_factory=list)
    startup_order: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    observation_demands: tuple[EffectiveObservationDemand, ...] = ()

    def __post_init__(self) -> None:
        _validate_plan_addresses(
            self.resources,
            self.operations,
            self.startup_order,
            domain=RuntimeDomain.EVALUATION,
        )

    @property
    def actionable_operations(self) -> list[EvaluationOp]:
        return [op for op in self.operations if op.action != ChangeAction.UNCHANGED]


def _validate_plan_addresses(
    resources: dict[str, PlannedResource],
    operations: list[PlanOperation],
    startup_order: list[str] | None = None,
    *,
    domain: RuntimeDomain,
) -> None:
    for map_key, resource in resources.items():
        require_compiled_address(map_key, field_name="resource map key")
        if map_key != resource.address:
            raise ValueError("Plan resource map key must equal embedded address")
        if resource.domain is not domain:
            raise ValueError("Plan resource domain must equal the plan domain")
        require_plan_operation_identity(domain, resource.address, resource.resource_type)
    operation_addresses = [operation.address for operation in operations]
    for operation in operations:
        require_plan_operation_identity(domain, operation.address, operation.resource_type)
    if len(operation_addresses) != len(set(operation_addresses)):
        raise ValueError("Plan operation addresses must be unique")
    if startup_order is None:
        return
    for address in startup_order:
        require_compiled_address(address, field_name="startup_order address")
    if len(startup_order) != len(set(startup_order)):
        raise ValueError("Plan startup_order addresses must be unique")
    unknown = set(startup_order) - set(operation_addresses)
    if unknown:
        raise ValueError("Plan startup_order must reference admitted operation addresses")


def _validate_realization_authority(
    operations: list[PlanOperation],
    authority: tuple[ResolvedRealizationAuthority, ...],
) -> None:
    identities = [(entry.address, entry.requirement_kind) for entry in authority]
    if len(identities) != len(set(identities)):
        raise ValueError("Provisioning plan realization authority must identify unique concerns")
    pointers = [(entry.address, entry.payload_pointer) for entry in authority]
    if len(pointers) != len(set(pointers)):
        raise ValueError("Provisioning plan realization authority payload pointers must be unique per resource")
    admitted_addresses = {operation.address for operation in operations if operation.action is not ChangeAction.DELETE}
    stale = sorted({entry.address for entry in authority} - admitted_addresses)
    if stale:
        raise ValueError("Provisioning plan realization authority must reference non-delete operations")


__all__ = (
    "ChangeAction",
    "EvaluationOp",
    "EvaluationPlan",
    "OrchestrationOp",
    "OrchestrationPlan",
    "PlanOperation",
    "PLAN_ADDRESS_ROOT_BY_DOMAIN",
    "PLAN_RESOURCE_TYPES_BY_DOMAIN",
    "PlannedResource",
    "ProvisionOp",
    "ProvisioningPlan",
    "RealizationAuthorityBound",
    "RealizationAuthorityMode",
    "RealizationResolutionSource",
    "ResolvedRealizationAuthority",
    "RuntimeDomain",
    "planned_infrastructure_spec",
    "planned_node_resources",
    "planned_node_source",
    "planned_node_spec",
    "planned_resource_authored_name",
    "planned_resource_name",
    "planned_resource_payload",
    "planned_realization_authority",
    "require_plan_operation_identity",
)
