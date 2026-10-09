"""Trusted joins for mixed-backend bindings and their shared operation requests.

These pure validators compare the published carriers with trusted inputs
resolved by the caller: the sealed composition profile and its resolution
context, and the shared backend operation request, capabilities and admission
response. They perform no I/O, dispatch or state mutation. Passing them proves
neither backend truth nor runtime adoption.
"""

from __future__ import annotations

from collections.abc import Sequence

from .backend_operation import BackendOperationCapabilitiesModel, BackendOperationRequestModel
from .backend_operation_response import BackendOperationResponseModel
from .backend_operation_validation import require_backend_operation_admission
from .mixed_backend_binding import (
    MixedBackendEdgeBindingModel,
    MixedBackendExecutionBindingModel,
    MixedBackendHandoffBindingModel,
    MixedBackendTimeRequirementModel,
    mixed_backend_binding_reference,
)
from .mixed_composition import (
    MixedCompositionEdgeModel,
    MixedCompositionTransitionModel,
    MixedParticipantCompositionProfileModel,
)
from .mixed_composition_resolution import MixedCompositionResolutionContext, validate_mixed_composition_context

_MAX_BINDINGS = 2048
_UNGOVERNED_ORDERING = frozenset({"wall_clock_only", "unknown", "unsupported"})


def validate_mixed_backend_bindings(
    profile: MixedParticipantCompositionProfileModel,
    context: MixedCompositionResolutionContext,
    bindings: Sequence[MixedBackendExecutionBindingModel],
) -> None:
    """Require exactly one matching installed binding for each executable obligation.

    Every edge active in an admitted phase needs a bridge binding, and every
    transition that changes the active components needs a one-to-one native
    handoff binding. Alternative profiles have no such obligation and admit no
    binding. Missing, foreign, duplicate or contradictory bindings and
    unsupported coordination refuse the whole set.
    """

    validate_mixed_composition_context(profile, context)
    edges, handoffs = _index_bindings(profile, bindings)
    for edge_id in sorted({edge_id for phase in profile.phases.values() for edge_id in phase.active_edge_ids}):
        _validate_edge_binding(profile, profile.edges[edge_id], edges.pop(edge_id, None))
    for transition_id in sorted(profile.transitions):
        transition = profile.transitions[transition_id]
        _validate_handoff_binding(profile, context, transition, handoffs.pop(transition_id, None))
    if edges or handoffs:
        raise ValueError("mixed backend bindings must name admitted edges or component-changing transitions")


def _index_bindings(
    profile: MixedParticipantCompositionProfileModel,
    bindings: Sequence[MixedBackendExecutionBindingModel],
) -> tuple[dict[str, MixedBackendEdgeBindingModel], dict[str, MixedBackendHandoffBindingModel]]:
    if len(bindings) > _MAX_BINDINGS:
        raise ValueError("mixed backend binding set exceeds its bound")
    if len({binding.binding_id for binding in bindings}) != len(bindings):
        raise ValueError("mixed backend binding identities must be unique")
    identity = (profile.profile_id, profile.profile_revision, profile.profile_digest)
    edges: dict[str, MixedBackendEdgeBindingModel] = {}
    handoffs: dict[str, MixedBackendHandoffBindingModel] = {}
    for binding in bindings:
        if (binding.profile_id, binding.profile_revision, binding.profile_digest) != identity:
            raise ValueError("mixed backend binding names another composition profile")
        subject = binding.subject
        index, key = (edges, subject.edge_id) if subject.kind == "edge" else (handoffs, subject.transition_id)
        if key in index:
            raise ValueError("mixed backend binding set binds one obligation twice")
        index[key] = subject
    return edges, handoffs


def _validate_edge_binding(
    profile: MixedParticipantCompositionProfileModel,
    edge: MixedCompositionEdgeModel,
    installed: MixedBackendEdgeBindingModel | None,
) -> None:
    if edge.time_binding.ordering_basis in _UNGOVERNED_ORDERING:
        raise ValueError("mixed edge requires an ungoverned order that no binding can execute")
    if installed is None:
        raise ValueError("active mixed edge requires an executable binding")
    if not _owns_destination_action(profile, edge, installed):
        raise ValueError("mixed edge binding must own the destination provider's action allocation")
    observed = (
        installed.owner_component_id,
        installed.participant_address,
        installed.audience_scope_ref,
        installed.bridge.service_ref,
        installed.mapping_loss,
        frozenset(installed.required_evidence_refs),
        _time_coordinates(installed.time),
    )
    binding = edge.time_binding
    admitted = (
        edge.target_component_id,
        edge.crossing_subject.participant_address,
        edge.audience_scope_ref,
        edge.routing_ref,
        edge.mapping_loss,
        frozenset(item.evidence_ref for item in edge.evidence_bindings),
        (
            binding.time_model_ref,
            binding.time_model_digest,
            binding.source_clock_address,
            binding.target_clock_address,
            binding.mapping_address,
            binding.ordering_basis,
        ),
    )
    if observed != admitted:
        raise ValueError("mixed edge binding differs from the admitted edge")


def _owns_destination_action(
    profile: MixedParticipantCompositionProfileModel,
    edge: MixedCompositionEdgeModel,
    installed: MixedBackendEdgeBindingModel,
) -> bool:
    # The owner is the destination provider's action allocation for the bound
    # address, active in at least one phase where the edge is active.
    allocation = profile.allocations.get(installed.owner_allocation_id)
    return (
        allocation is not None
        and allocation.target_kind == "action-family"
        and allocation.provider_component_id == edge.target_component_id
        and allocation.target_address == installed.destination_action_address
        and not set(allocation.phase_ids).isdisjoint(edge.phase_ids)
    )


def _validate_handoff_binding(
    profile: MixedParticipantCompositionProfileModel,
    context: MixedCompositionResolutionContext,
    transition: MixedCompositionTransitionModel,
    installed: MixedBackendHandoffBindingModel | None,
) -> None:
    source = set(profile.phases[transition.source_phase_id].active_component_ids)
    target = set(profile.phases[transition.target_phase_id].active_component_ids)
    if source == target:
        if installed is not None:
            raise ValueError("a transition that keeps its components needs no native handoff binding")
        return
    leaving, joining = sorted(source - target), sorted(target - source)
    if len(leaving) != 1 or len(joining) != 1:
        raise ValueError("staged transition changes components outside one-to-one native handoff")
    if installed is None:
        raise ValueError("component-changing transition requires an executable handoff binding")
    observed = (
        installed.source_component_id,
        installed.destination_component_id,
        installed.source_owner_ref,
        installed.destination_owner_ref,
        frozenset(installed.required_evidence_refs),
    )
    admitted = (
        leaving[0],
        joining[0],
        profile.components[leaving[0]].native_ownership_ref,
        profile.components[joining[0]].native_ownership_ref,
        frozenset(item.evidence_ref for item in transition.evidence_bindings),
    )
    if observed != admitted:
        raise ValueError("mixed handoff binding differs from the admitted transition ownership")
    _require_resolved_time(context, installed.time)


def _time_coordinates(time: MixedBackendTimeRequirementModel) -> tuple[str, ...]:
    return (
        time.time_model_ref,
        time.time_model_digest,
        time.source_clock_address,
        time.destination_clock_address,
        time.mapping_ref,
        time.ordering_basis,
    )


def _require_resolved_time(context: MixedCompositionResolutionContext, time: MixedBackendTimeRequirementModel) -> None:
    declaration = context.time_models.get(time.time_model_ref)
    if declaration is None or context.time_model_digests.get(time.time_model_ref) != time.time_model_digest:
        raise ValueError("mixed handoff time model is unresolved or stale")
    mapping = declaration.mappings.get(time.mapping_ref)
    source = declaration.clocks.get(time.source_clock_address)
    destination = declaration.clocks.get(time.destination_clock_address)
    endpoints = (source.time_domain_address, destination.time_domain_address) if source and destination else ()
    if mapping is None or endpoints != (mapping.source_domain_address, mapping.target_domain_address):
        raise ValueError("mixed handoff clocks and mapping are unresolved")


def require_mixed_backend_request(
    binding: MixedBackendExecutionBindingModel,
    request: BackendOperationRequestModel,
) -> None:
    """Require a shared request to commit to this exact binding, operation kind and installed service.

    The request's backend is the edge bridge or native transfer service the
    binding pins, so shared capabilities and admission answer for that service.
    """

    if request.command != mixed_backend_binding_reference(binding):
        raise ValueError("backend operation request does not commit to the installed mixed binding")
    if request.binding.context.operation_kind != binding.subject.operation_kind:
        raise ValueError("backend operation kind differs from the mixed binding obligation")
    subject = binding.subject
    service = subject.bridge if subject.kind == "edge" else subject.transfer
    if request.binding.backend_id != service.service_ref:
        raise ValueError("backend operation request is not addressed to the installed mixed service")


def require_mixed_backend_admission(
    binding: MixedBackendExecutionBindingModel,
    request: BackendOperationRequestModel,
    capabilities: BackendOperationCapabilitiesModel,
    response: BackendOperationResponseModel,
) -> None:
    """Join shared contextual admission to one installed binding; grants no invocation authority."""

    require_mixed_backend_request(binding, request)
    require_backend_operation_admission(request, capabilities, response)


__all__ = [
    "require_mixed_backend_admission",
    "require_mixed_backend_request",
    "validate_mixed_backend_bindings",
]
