"""Trusted contextual admission for mixed-participant composition profiles."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..vocabulary import ParticipantFeatureSupportLevel
from .experiment_manifest_references import ExperimentManifestReferenceModel
from .experiment_references import ExperimentReferenceModel
from .mixed_composition import (
    AllocationTargetKind,
    CompositionFeatureRequirementModel,
    MixedCompositionAllocationModel,
    MixedCompositionComponentModel,
    MixedCompositionEdgeModel,
    MixedCompositionEvidenceBindingModel,
    MixedCompositionFailureBehaviorModel,
    MixedCompositionMappingLossModel,
    MixedCompositionTimeBindingModel,
    MixedCompositionTransitionModel,
    MixedCompositionValidationLimits,
    MixedParticipantCompositionProfileModel,
    _validate_profile_limits,
)
from .participant_crossing import (
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectReferenceModel,
)
from .realization_plans import RealizationEnvelopeIdentityModel
from .time_model import TimeModelDeclarationModel


@dataclass(frozen=True)
class MixedCompositionTrustedComponent:
    """Trusted relationship joining one component to its admitted identities."""

    profile_id: str
    component_id: str
    apparatus_identity_ref: str
    manifest_ref: ExperimentManifestReferenceModel
    realization_envelope: RealizationEnvelopeIdentityModel
    native_ownership_ref: str | None


@dataclass(frozen=True)
class MixedCompositionTrustedAllocation:
    """Trusted relationship joining one allocation to its semantic authority."""

    profile_id: str
    allocation_id: str
    target_kind: AllocationTargetKind
    target_address: str
    provider_component_id: str
    participant_identity_ref: str
    controller_ref: str
    action_authority_ref: str
    routing_ref: str


@dataclass(frozen=True)
class MixedCompositionTrustedEdge:
    """Trusted relationship joining one crossing to all of its authorities."""

    profile_id: str
    edge_id: str
    source_component_id: str
    target_component_id: str
    crossing_scope_address: str
    crossing_subject: ParticipantCrossingSubjectReferenceModel
    audience_scope_ref: str
    policy: ParticipantCrossingPolicyReferenceModel
    controller_ref: str
    authority_ref: str
    routing_ref: str
    disclosure_authority_ref: str
    native_ownership_ref: str | None
    time_binding: MixedCompositionTimeBindingModel
    mapping_loss: MixedCompositionMappingLossModel
    failure_behavior: MixedCompositionFailureBehaviorModel


@dataclass(frozen=True)
class MixedCompositionTrustedTransition:
    """Trusted relationship joining one staged transition to its evaluator."""

    profile_id: str
    transition_id: str
    source_phase_id: str
    target_phase_id: str
    trigger_ref: str
    evaluator_ref: str


@dataclass(frozen=True)
class MixedCompositionFeatureDowngradeAuthorization:
    """Exact trusted authorization for one weaker API-407 feature level."""

    profile_id: str
    provider_component_id: str
    feature: str
    required_level: ParticipantFeatureSupportLevel
    allowed_downgrade_level: ParticipantFeatureSupportLevel
    policy_ref: str
    provenance_ref: str


MixedCompositionFeatureSupportResolver = Callable[[str, str, CompositionFeatureRequirementModel], None]


@dataclass(frozen=True)
class MixedCompositionResolutionContext:
    """Trusted, caller-supplied indexes used for contextual profile validation."""

    scenario_snapshots: Mapping[str, ExperimentReferenceModel]
    compiled_targets: Mapping[str, str]
    components: Mapping[tuple[str, str], MixedCompositionTrustedComponent]
    allocations: Mapping[tuple[str, str], MixedCompositionTrustedAllocation]
    edges: Mapping[tuple[str, str], MixedCompositionTrustedEdge]
    transitions: Mapping[tuple[str, str], MixedCompositionTrustedTransition]
    feature_support_resolver: MixedCompositionFeatureSupportResolver
    feature_downgrade_authorizations: frozenset[MixedCompositionFeatureDowngradeAuthorization]
    time_models: Mapping[str, TimeModelDeclarationModel]
    time_model_digests: Mapping[str, str]
    evidence_satisfaction: Mapping[tuple[str, str], frozenset[str]]
    nested_profiles: Mapping[str, MixedParticipantCompositionProfileModel]


class _WorkBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def charge(self, amount: int = 1) -> None:
        self.used += amount
        if self.used > self.limit:
            raise ValueError("mixed composition contextual validation exceeded its work limit")


def _validate_component_context(
    profile_id: str,
    component: MixedCompositionComponentModel,
    context: MixedCompositionResolutionContext,
    budget: _WorkBudget,
) -> None:
    budget.charge()
    observed = MixedCompositionTrustedComponent(
        profile_id=profile_id,
        component_id=component.component_id,
        apparatus_identity_ref=component.apparatus_identity_ref,
        manifest_ref=component.manifest_ref,
        realization_envelope=component.realization_envelope,
        native_ownership_ref=component.native_ownership_ref,
    )
    if context.components.get((profile_id, component.component_id)) != observed:
        raise ValueError("composition component identity relationship is unresolved or stale")


def _validate_feature_requirements(
    profile_id: str,
    allocation: MixedCompositionAllocationModel,
    context: MixedCompositionResolutionContext,
    budget: _WorkBudget,
) -> None:
    for requirement in allocation.feature_requirements:
        budget.charge()
        if requirement.downgrade_policy_ref is not None:
            authorization = MixedCompositionFeatureDowngradeAuthorization(
                profile_id=profile_id,
                provider_component_id=allocation.provider_component_id,
                feature=requirement.feature,
                required_level=requirement.required_level,
                allowed_downgrade_level=requirement.allowed_downgrade_level,
                policy_ref=requirement.downgrade_policy_ref,
                provenance_ref=requirement.downgrade_provenance_ref,
            )
            if authorization not in context.feature_downgrade_authorizations:
                raise ValueError("composition feature downgrade authorization is unresolved")
        try:
            context.feature_support_resolver(profile_id, allocation.provider_component_id, requirement)
        except Exception:
            raise ValueError("composition allocation feature support resolution failed") from None


def _validate_allocation_context(
    profile_id: str,
    allocation: MixedCompositionAllocationModel,
    context: MixedCompositionResolutionContext,
    budget: _WorkBudget,
) -> None:
    budget.charge()
    if context.compiled_targets.get(allocation.target_address) != allocation.target_kind:
        raise ValueError("composition allocation compiled target is unresolved or has the wrong kind")
    observed = MixedCompositionTrustedAllocation(
        profile_id=profile_id,
        allocation_id=allocation.allocation_id,
        target_kind=allocation.target_kind,
        target_address=allocation.target_address,
        provider_component_id=allocation.provider_component_id,
        participant_identity_ref=allocation.participant_identity_ref,
        controller_ref=allocation.controller_ref,
        action_authority_ref=allocation.action_authority_ref,
        routing_ref=allocation.routing_ref,
    )
    if context.allocations.get((profile_id, allocation.allocation_id)) != observed:
        raise ValueError("composition allocation authority relationship is unresolved or stale")
    _validate_feature_requirements(profile_id, allocation, context, budget)


def _validate_evidence_binding(
    profile_id: str,
    binding: MixedCompositionEvidenceBindingModel,
    context: MixedCompositionResolutionContext,
    budget: _WorkBudget,
) -> None:
    budget.charge()
    accepted = context.evidence_satisfaction.get((profile_id, binding.obligation_ref), frozenset())
    if binding.evidence_ref not in accepted:
        raise ValueError("composition obligation-to-evidence relationship is unresolved")


def _validate_edge_context(
    profile_id: str,
    edge: MixedCompositionEdgeModel,
    context: MixedCompositionResolutionContext,
    budget: _WorkBudget,
) -> None:
    budget.charge()
    observed = MixedCompositionTrustedEdge(
        profile_id=profile_id,
        edge_id=edge.edge_id,
        source_component_id=edge.source_component_id,
        target_component_id=edge.target_component_id,
        crossing_scope_address=edge.crossing_scope_address,
        crossing_subject=edge.crossing_subject,
        audience_scope_ref=edge.audience_scope_ref,
        policy=edge.policy,
        controller_ref=edge.controller_ref,
        authority_ref=edge.authority_ref,
        routing_ref=edge.routing_ref,
        disclosure_authority_ref=edge.disclosure_authority_ref,
        native_ownership_ref=edge.native_ownership_ref,
        time_binding=edge.time_binding,
        mapping_loss=edge.mapping_loss,
        failure_behavior=edge.failure_behavior,
    )
    if context.edges.get((profile_id, edge.edge_id)) != observed:
        raise ValueError("composition edge authority relationship is unresolved or stale")
    for binding in edge.evidence_bindings:
        _validate_evidence_binding(profile_id, binding, context, budget)

    time_binding = edge.time_binding
    time_model = context.time_models.get(time_binding.time_model_ref)
    if (
        time_model is None
        or context.time_model_digests.get(time_binding.time_model_ref) != time_binding.time_model_digest
    ):
        raise ValueError("composition edge time model is unresolved or stale")
    source_clock = time_model.clocks.get(time_binding.source_clock_address)
    target_clock = time_model.clocks.get(time_binding.target_clock_address)
    mapping = time_model.mappings.get(time_binding.mapping_address)
    if source_clock is None or target_clock is None or mapping is None:
        raise ValueError("composition edge clock or mapping reference is unresolved")
    if (
        mapping.source_domain_address != source_clock.time_domain_address
        or mapping.target_domain_address != target_clock.time_domain_address
    ):
        raise ValueError("composition edge time mapping endpoints do not match its clocks")


def _validate_phase_evidence(
    profile: MixedParticipantCompositionProfileModel,
    context: MixedCompositionResolutionContext,
    budget: _WorkBudget,
) -> None:
    for carrier in (*profile.phases.values(), *profile.transitions.values()):
        for binding in carrier.evidence_bindings:
            _validate_evidence_binding(profile.profile_id, binding, context, budget)


def _validate_transition_context(
    profile_id: str,
    transition: MixedCompositionTransitionModel,
    context: MixedCompositionResolutionContext,
    budget: _WorkBudget,
) -> None:
    budget.charge()
    observed = MixedCompositionTrustedTransition(
        profile_id=profile_id,
        transition_id=transition.transition_id,
        source_phase_id=transition.source_phase_id,
        target_phase_id=transition.target_phase_id,
        trigger_ref=transition.trigger_ref,
        evaluator_ref=transition.evaluator_ref,
    )
    if context.transitions.get((profile_id, transition.transition_id)) != observed:
        raise ValueError("composition transition trigger or evaluator relationship is unresolved or stale")


def validate_mixed_composition_context(
    profile: MixedParticipantCompositionProfileModel,
    context: MixedCompositionResolutionContext,
    *,
    limits: MixedCompositionValidationLimits | None = None,
) -> None:
    """Resolve all external profile authority through bounded trusted indexes.

    The function performs no I/O, mutation, provider selection, compilation, or
    repair. A successful return establishes only contextual contract validity.
    """

    selected = limits or MixedCompositionValidationLimits()
    _validate_profile_limits(profile, selected)
    budget = _WorkBudget(selected.max_context_work)
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(current: MixedParticipantCompositionProfileModel) -> None:
        budget.charge()
        if current.profile_id in visiting:
            raise ValueError("mixed composition nested profile cycle detected")
        if current.profile_id in visited:
            return
        if len(visited) >= selected.max_nested_profiles:
            raise ValueError("mixed composition nested profile limit exceeded")
        visiting.add(current.profile_id)
        scenario = current.scenario_snapshot_ref
        if context.scenario_snapshots.get(scenario.ref_id) != scenario:
            raise ValueError("composition scenario snapshot is unresolved or stale")
        for component in current.components.values():
            _validate_component_context(current.profile_id, component, context, budget)
        for allocation in current.allocations.values():
            _validate_allocation_context(current.profile_id, allocation, context, budget)
        for edge in current.edges.values():
            _validate_edge_context(current.profile_id, edge, context, budget)
        for transition in current.transitions.values():
            _validate_transition_context(current.profile_id, transition, context, budget)
        _validate_phase_evidence(current, context, budget)
        for child_id, child_digest in current.nested_profile_refs.items():
            budget.charge()
            child = context.nested_profiles.get(child_id)
            if child is None or child.profile_id != child_id or child.profile_digest != child_digest:
                raise ValueError("composition nested profile is unresolved or stale")
            visit(child)
        visiting.remove(current.profile_id)
        visited.add(current.profile_id)

    visit(profile)


__all__ = [
    "MixedCompositionFeatureDowngradeAuthorization",
    "MixedCompositionFeatureSupportResolver",
    "MixedCompositionResolutionContext",
    "MixedCompositionTrustedAllocation",
    "MixedCompositionTrustedComponent",
    "MixedCompositionTrustedEdge",
    "MixedCompositionTrustedTransition",
    "validate_mixed_composition_context",
]
