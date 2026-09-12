"""Compiled provisioning/resolved-resource records and SEM-211 action-contract validation."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from raes.participant_behavior import ParticipantFailureClass
from raes_backend_protocols.domain_topology import DomainTopologyBinding
from raes_contracts.addressing import require_compiled_address
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.evaluation import EvaluationExecutionContract, EvaluationResultContract
from raes_contracts.participant_episode import PARTICIPANT_EPISODE_CONTROL_EVENTS, PARTICIPANT_EPISODE_TERMINAL_EVENTS

if TYPE_CHECKING:
    # Forward reference only: ParticipantActionResult is defined in the later
    # action_results module. The annotation on validate_participant_action_result_contract
    # is a string, so no runtime import (and no import cycle) is created.
    from .action_results import ParticipantActionResult

_PARTICIPANT_ACTION_CONTRACT_PREFIX = "participant.action-contract."
_PARTICIPANT_OBSERVATION_BOUNDARY_PREFIX = "participant.observation-boundary."
_PARTICIPANT_OUTCOME_RULE_PREFIX = "participant.outcome-interpretation-rule."
_PARTICIPANT_BEHAVIOR_HISTORY_KEY = "runtime.snapshot.participant-behavior-history"
_PARTICIPANT_EPISODE_CONTROL_EVENTS = PARTICIPANT_EPISODE_CONTROL_EVENTS
_PARTICIPANT_EPISODE_TERMINAL_EVENTS = PARTICIPANT_EPISODE_TERMINAL_EVENTS


@dataclass(frozen=True)
class RuntimeTemplate:
    """Reusable SDL definition preserved in compiled form."""

    address: str
    name: str
    spec: dict[str, Any]


@dataclass(frozen=True)
class ResolvedResource:
    """Base class for bound runtime resources."""

    address: str
    name: str
    spec: dict[str, Any]
    ordering_dependencies: tuple[str, ...] = ()
    refresh_dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class NetworkRuntime(ResolvedResource):
    """Compiled switch/network deployment."""

    node_name: str = ""
    node_kind: str = "switch"


@dataclass(frozen=True)
class NodeRuntime(ResolvedResource):
    """Compiled backend-neutral compute deployment."""

    node_name: str = ""
    node_kind: str = ""
    os_family: str = ""
    os_distribution: str = ""
    os_version: str = ""
    architecture: str = ""
    count: int | str | None = None
    network_namespace_target: str = ""
    domain_topology: DomainTopologyBinding | None = None


@dataclass(frozen=True)
class FeatureBinding(ResolvedResource):
    """Feature template bound to a specific node role."""

    node_name: str = ""
    node_address: str = ""
    feature_name: str = ""
    template_address: str = ""
    role_name: str = ""


@dataclass(frozen=True)
class PropositionRuntime(ResolvedResource):
    """Compiled backend-neutral proposition with resolved finite subjects."""

    subject_addresses: tuple[str, ...] = ()
    predicate_kind: str = ""
    quantifier: str = ""
    evaluation_basis: str = ""
    evidence_requirement_refs: tuple[str, ...] = ()
    evidence_channels: tuple[str, ...] = ()
    unresolved_evidence_channel_refs: tuple[str, ...] = ()
    required_time_domain: str = ""


@dataclass(frozen=True)
class AssertionRuntime(ResolvedResource):
    """Compiled assertion use over one proposition."""

    proposition_address: str = ""
    role: str = ""
    polarity: str = ""


@dataclass(frozen=True)
class ConditionBinding(ResolvedResource):
    """Condition template bound to a specific node role."""

    node_name: str = ""
    node_address: str = ""
    condition_name: str = ""
    template_address: str = ""
    role_name: str = ""
    proposition_address: str = ""
    result_contract: "EvaluationResultContract" = field(
        default_factory=lambda: EvaluationResultContract(resource_type="condition-binding")
    )
    execution_contract: "EvaluationExecutionContract" = field(
        default_factory=lambda: EvaluationExecutionContract(resource_type="condition-binding")
    )


@dataclass(frozen=True)
class InjectBinding(ResolvedResource):
    """Inject template bound to a specific node role."""

    node_name: str = ""
    node_address: str = ""
    inject_name: str = ""
    template_address: str = ""
    role_name: str = ""


@dataclass(frozen=True)
class InjectRuntime(ResolvedResource):
    """Resolved top-level inject resource."""


@dataclass(frozen=True)
class ServiceContentMaterializationBinding:
    """Closed compiled requirements for one service-owned content placement."""

    target_service_address: str
    interface_profile: str
    profile_version: str
    content_type: str
    operation: str
    conflict_policy: str
    readback: str
    canonical_content_digest: str
    shared_service_relationship_ref: str = ""
    consumer_tenant_ref: str = ""
    mutable_state_owner: str = ""
    reset_generation_owner: str = ""
    readback_assertion_addresses: tuple[str, ...] = ()
    evidence_requirement_refs: tuple[str, ...] = ()
    observation_boundary_addresses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_compiled_address(
            self.target_service_address,
            field_name="ServiceContentMaterializationBinding.target_service_address",
        )


@dataclass(frozen=True)
class ServiceSearchIndexSchemaMaterializationBinding:
    """Closed compiled requirements for one service-owned search-index schema."""

    target_service_address: str
    interface_profile: str
    profile_version: str
    content_type: str
    operation: str
    conflict_policy: str
    readback: str
    field_semantics: dict[str, str]
    canonical_content_digest: str
    canonical_field_schema_digest: str
    shared_service_relationship_ref: str = ""
    consumer_tenant_ref: str = ""
    mutable_state_owner: str = ""
    reset_generation_owner: str = ""
    readback_assertion_addresses: tuple[str, ...] = ()
    evidence_requirement_refs: tuple[str, ...] = ()
    observation_boundary_addresses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_compiled_address(
            self.target_service_address,
            field_name="ServiceSearchIndexSchemaMaterializationBinding.target_service_address",
        )


ServiceMaterializationBinding = ServiceContentMaterializationBinding | ServiceSearchIndexSchemaMaterializationBinding


@dataclass(frozen=True)
class ContentPlacement(ResolvedResource):
    """Content entry resolved to a concrete node or named service."""

    content_name: str = ""
    target_node: str = ""
    target_address: str = ""
    service_materialization: ServiceMaterializationBinding | None = None


@dataclass(frozen=True)
class AccountPlacement(ResolvedResource):
    """Account entry resolved to a concrete target node."""

    account_name: str = ""
    node_name: str = ""
    target_address: str = ""
    domain_topology: DomainTopologyBinding | None = None


@dataclass(frozen=True, kw_only=True)
class DomainControllerPlacement(ResolvedResource):
    """Identity domain bootstrap intent bound to one controller node."""

    target_address: str
    domain_topology: DomainTopologyBinding

    def __post_init__(self) -> None:
        require_compiled_address(
            self.target_address,
            field_name="DomainControllerPlacement.target_address",
        )
        if self.spec:
            raise ValueError(
                "DomainControllerPlacement.spec must be empty; the payload is restricted to typed non-secret fields"
            )
        if self.domain_topology.role != "controller":
            raise ValueError("DomainControllerPlacement.domain_topology must carry the controller role")
        if self.target_address not in self.domain_topology.controller_addresses:
            raise ValueError("DomainControllerPlacement target must be one of the domain controller addresses")


@dataclass(frozen=True)
class GeneratedArtifactRuntime(ResolvedResource):
    """Compiled generated-artifact desired state."""


@dataclass(frozen=True)
class PersistentVolumeRuntime(ResolvedResource):
    """Compiled persistent-volume desired state."""


@dataclass(frozen=True)
class ParticipantActionContractRuntime(ResolvedResource):
    """Compiled participant action contract."""

    action_name: str = ""
    argument_shape_ref: str = ""
    argument_definitions: tuple[dict[str, Any], ...] = ()
    semantic_version: str = ""
    lifecycle_state: str = ""
    behavioral_granularity: str = ""
    precondition_classes: tuple[str, ...] = ()
    effect_classes: tuple[str, ...] = ()
    failure_classes: tuple[str, ...] = ()
    backend_failure_mappings: tuple[dict[str, str], ...] = ()
    interaction_classes: tuple[str, ...] = ()
    shared_state_refs: tuple[str, ...] = ()
    commutative_interaction_targets: tuple[str, ...] = ()
    merge_rule_refs: tuple[str, ...] = ()
    temporal_contract_ids: tuple[str, ...] = ()
    temporal_kinds: tuple[str, ...] = ()
    time_domains: tuple[str, ...] = ()
    clock_authorities: tuple[str, ...] = ()
    backend_timing_disclosures: tuple[dict[str, Any], ...] = ()


def map_backend_diagnostic_to_participant_failure(
    diagnostic: Diagnostic | Mapping[str, Any] | str,
    contract: ParticipantActionContractRuntime,
) -> ParticipantFailureClass:
    """Map a backend diagnostic to a portable SEM-211 failure class."""

    if isinstance(diagnostic, Diagnostic):
        code = diagnostic.code
    elif isinstance(diagnostic, Mapping):
        code = str(diagnostic.get("code", ""))
    else:
        code = str(diagnostic)

    for mapping in contract.backend_failure_mappings:
        if mapping.get("backend_error_code") == code:
            return ParticipantFailureClass(str(mapping.get("failure_class", ParticipantFailureClass.UNKNOWN.value)))
    return ParticipantFailureClass.BACKEND_ERROR if code else ParticipantFailureClass.UNKNOWN


def _as_string_set(value: object) -> set[str]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Iterable):
        return set()
    return {str(item) for item in value if isinstance(item, str) and item}


def _contract_sem211_precondition_refs(
    contract: ParticipantActionContractRuntime,
) -> dict[tuple[str, str], dict[str, set[str]]]:
    preconditions = contract.spec.get("preconditions", ())
    if isinstance(preconditions, (str, bytes, Mapping)) or not isinstance(preconditions, Iterable):
        return {}
    refs: dict[tuple[str, str], dict[str, set[str]]] = {}
    for item in preconditions:
        if not isinstance(item, Mapping) or not item.get("precondition_id") or not item.get("precondition_class"):
            continue
        key = (str(item.get("precondition_id", "")), str(item.get("precondition_class", "")))
        refs[key] = {
            "support_refs": _as_string_set(item.get("support_refs", ())),
            "evidence_refs": _as_string_set(item.get("evidence_refs", ())),
        }
    return refs


def _contract_sem211_effect_refs(
    contract: ParticipantActionContractRuntime,
) -> dict[tuple[str, str], dict[str, set[str]]]:
    effects = contract.spec.get("effects", ())
    if isinstance(effects, (str, bytes, Mapping)) or not isinstance(effects, Iterable):
        return {}
    refs: dict[tuple[str, str], dict[str, set[str]]] = {}
    for item in effects:
        if not isinstance(item, Mapping) or not item.get("effect_id") or not item.get("effect_class"):
            continue
        key = (str(item.get("effect_id", "")), str(item.get("effect_class", "")))
        refs[key] = {
            "target_refs": _as_string_set(item.get("target_refs", ())),
            "evidence_refs": _as_string_set(item.get("evidence_refs", ())),
        }
    return refs


def _contract_uses_sem211_action_results(contract: ParticipantActionContractRuntime) -> bool:
    return bool(contract.precondition_classes or contract.effect_classes or contract.failure_classes)


_ContractRefMap = dict[tuple[str, str], dict[str, set[str]]]


def _sem211_precondition_violations(
    result: "ParticipantActionResult",
    contract: ParticipantActionContractRuntime,
    declared_precondition_classes: set[str],
    declared_preconditions: set[tuple[str, str]],
    declared_precondition_refs: _ContractRefMap,
) -> list[str]:
    violations: list[str] = []
    reported_preconditions: set[tuple[str, str]] = set()
    for precondition in result.preconditions:
        precondition_key = (precondition.precondition_id, precondition.precondition_class.value)
        reported_preconditions.add(precondition_key)
        if precondition.precondition_class.value not in declared_precondition_classes:
            violations.append(
                f"action_result precondition {precondition.precondition_id!r} uses undeclared "
                f"precondition_class {precondition.precondition_class.value!r}"
            )
        if declared_preconditions and precondition_key not in declared_preconditions:
            violations.append(
                f"action_result precondition {precondition.precondition_id!r}/"
                f"{precondition.precondition_class.value!r} is not declared by {contract.address}"
            )
        declared_refs = declared_precondition_refs.get(precondition_key)
        if declared_refs is not None:
            undeclared_support_refs = set(precondition.support_refs) - declared_refs["support_refs"]
            undeclared_evidence_refs = set(precondition.evidence_refs) - declared_refs["evidence_refs"]
            for ref in sorted(undeclared_support_refs):
                violations.append(
                    f"action_result precondition {precondition.precondition_id!r} reports undeclared "
                    f"support_ref {ref!r}"
                )
            for ref in sorted(undeclared_evidence_refs):
                violations.append(
                    f"action_result precondition {precondition.precondition_id!r} reports undeclared "
                    f"evidence_ref {ref!r}"
                )
    for precondition_id, precondition_class in sorted(declared_preconditions - reported_preconditions):
        violations.append(
            f"action_result is missing declared precondition {precondition_id!r}/"
            f"{precondition_class!r} for {contract.address}"
        )
    return violations


def _sem211_effect_violations(
    result: "ParticipantActionResult",
    contract: ParticipantActionContractRuntime,
    declared_effect_classes: set[str],
    declared_effects: set[tuple[str, str]],
    declared_effect_refs: _ContractRefMap,
) -> list[str]:
    violations: list[str] = []
    for effect in result.effects:
        effect_key = (effect.effect_id, effect.effect_class.value)
        if effect.effect_class.value not in declared_effect_classes:
            violations.append(
                f"action_result effect {effect.effect_id!r} uses undeclared effect_class {effect.effect_class.value!r}"
            )
        if declared_effects and effect_key not in declared_effects:
            violations.append(
                f"action_result effect {effect.effect_id!r}/"
                f"{effect.effect_class.value!r} is not declared by {contract.address}"
            )
        declared_refs = declared_effect_refs.get(effect_key)
        if declared_refs is not None:
            undeclared_target_refs = set(effect.target_refs) - declared_refs["target_refs"]
            undeclared_evidence_refs = set(effect.evidence_refs) - declared_refs["evidence_refs"]
            for ref in sorted(undeclared_target_refs):
                violations.append(f"action_result effect {effect.effect_id!r} reports undeclared target_ref {ref!r}")
            for ref in sorted(undeclared_evidence_refs):
                violations.append(f"action_result effect {effect.effect_id!r} reports undeclared evidence_ref {ref!r}")
    return violations


def _sem211_declared_evidence_refs(
    declared_precondition_refs: _ContractRefMap,
    declared_effect_refs: _ContractRefMap,
) -> set[str]:
    refs: set[str] = set()
    for declared_refs in declared_precondition_refs.values():
        refs.update(declared_refs["evidence_refs"])
    for declared_refs in declared_effect_refs.values():
        refs.update(declared_refs["evidence_refs"])
    return refs


def _sem211_reported_evidence_refs(result: "ParticipantActionResult") -> set[str]:
    refs: set[str] = set()
    for precondition in result.preconditions:
        refs.update(precondition.evidence_refs)
    for effect in result.effects:
        refs.update(effect.evidence_refs)
    return refs


def _sem211_result_evidence_violations(
    result: "ParticipantActionResult",
    declared_precondition_refs: _ContractRefMap,
    declared_effect_refs: _ContractRefMap,
) -> list[str]:
    if not (declared_precondition_refs or declared_effect_refs):
        return []
    declared_result_evidence_refs = _sem211_declared_evidence_refs(declared_precondition_refs, declared_effect_refs)
    reported_result_evidence_refs = _sem211_reported_evidence_refs(result)
    violations: list[str] = []
    for ref in sorted(set(result.evidence_refs) - declared_result_evidence_refs):
        violations.append(f"action_result reports undeclared evidence_ref {ref!r}")
    for ref in sorted(set(result.evidence_refs) & declared_result_evidence_refs - reported_result_evidence_refs):
        violations.append(
            f"action_result evidence_ref {ref!r} is not grounded in reported precondition or effect evidence_refs"
        )
    return violations


def validate_participant_action_result_contract(
    result: "ParticipantActionResult",
    contract: ParticipantActionContractRuntime,
) -> list[str]:
    """Return SEM-211 contract violations for one typed action result."""

    if result.action_contract_address != contract.address:
        return [
            "action_result action_contract_address "
            f"{result.action_contract_address!r} does not match compiled action contract {contract.address!r}"
        ]

    declared_precondition_refs = _contract_sem211_precondition_refs(contract)
    declared_effect_refs = _contract_sem211_effect_refs(contract)
    declared_preconditions = set(declared_precondition_refs)
    declared_effects = set(declared_effect_refs)

    violations: list[str] = []
    violations.extend(
        _sem211_precondition_violations(
            result,
            contract,
            set(contract.precondition_classes),
            declared_preconditions,
            declared_precondition_refs,
        )
    )
    violations.extend(
        _sem211_effect_violations(
            result,
            contract,
            set(contract.effect_classes),
            declared_effects,
            declared_effect_refs,
        )
    )
    violations.extend(_sem211_result_evidence_violations(result, declared_precondition_refs, declared_effect_refs))

    if result.failure_class is not None and result.failure_class.value not in set(contract.failure_classes):
        violations.append(
            f"action_result failure_class {result.failure_class.value!r} is not declared by {contract.address}"
        )
    return violations
