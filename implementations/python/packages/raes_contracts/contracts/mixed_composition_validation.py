"""Root-local graph validation for mixed-participant composition profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mixed_composition import (
        MixedCompositionPhaseModel,
        MixedParticipantCompositionProfileModel,
    )


@dataclass
class _PhaseUsage:
    components: set[str]
    allocations: set[str]
    edges: set[str]
    allocation_phases: dict[str, set[str]]
    edge_phases: dict[str, set[str]]


def _validate_phase_order(profile: MixedParticipantCompositionProfileModel) -> set[str]:
    phase_ids = set(profile.phases)
    if profile.initial_phase_id not in phase_ids:
        raise ValueError("initial_phase_id must resolve inside phases")
    if len(profile.phase_order) != len(set(profile.phase_order)) or set(profile.phase_order) != phase_ids:
        raise ValueError("phase_order must contain every phase exactly once")
    if profile.phase_order[0] != profile.initial_phase_id:
        raise ValueError("phase_order must begin with initial_phase_id")
    return phase_ids


def _new_phase_usage(profile: MixedParticipantCompositionProfileModel) -> _PhaseUsage:
    return _PhaseUsage(
        components=set(),
        allocations=set(),
        edges=set(),
        allocation_phases={key: set() for key in profile.allocations},
        edge_phases={key: set() for key in profile.edges},
    )


def _record_phase_allocations(
    profile: MixedParticipantCompositionProfileModel,
    phase: MixedCompositionPhaseModel,
    components: set[str],
    allocations: set[str],
    usage: _PhaseUsage,
) -> None:
    providers_by_target: dict[tuple[str, str], str] = {}
    for allocation_id in allocations:
        allocation = profile.allocations[allocation_id]
        usage.allocation_phases[allocation_id].add(phase.phase_id)
        if allocation.provider_component_id not in components:
            raise ValueError("phase allocation provider must be an active component")
        target = (allocation.target_kind, allocation.target_address)
        incumbent = providers_by_target.setdefault(target, allocation.provider_component_id)
        if incumbent != allocation.provider_component_id:
            raise ValueError("each phase target must have exactly one canonical provider")


def _record_phase_edges(
    profile: MixedParticipantCompositionProfileModel,
    phase: MixedCompositionPhaseModel,
    components: set[str],
    edges: set[str],
    usage: _PhaseUsage,
) -> None:
    for edge_id in edges:
        edge = profile.edges[edge_id]
        usage.edge_phases[edge_id].add(phase.phase_id)
        if edge.source_component_id not in components or edge.target_component_id not in components:
            raise ValueError("active edge endpoints must both be active components")


def _record_phase_usage(
    profile: MixedParticipantCompositionProfileModel,
    phase: MixedCompositionPhaseModel,
    usage: _PhaseUsage,
) -> None:
    components = set(phase.active_component_ids)
    allocations = set(phase.active_allocation_ids)
    edges = set(phase.active_edge_ids)
    if not components <= set(profile.components):
        raise ValueError("phase references an unknown component")
    if not allocations <= set(profile.allocations):
        raise ValueError("phase references an unknown allocation")
    if not edges <= set(profile.edges):
        raise ValueError("phase references an unknown edge")
    usage.components.update(components)
    usage.allocations.update(allocations)
    usage.edges.update(edges)
    _record_phase_allocations(profile, phase, components, allocations, usage)
    _record_phase_edges(profile, phase, components, edges, usage)


def _collect_phase_usage(profile: MixedParticipantCompositionProfileModel) -> _PhaseUsage:
    usage = _new_phase_usage(profile)
    for phase in profile.phases.values():
        _record_phase_usage(profile, phase, usage)
    return usage


def _validate_activity_coverage(
    profile: MixedParticipantCompositionProfileModel,
    usage: _PhaseUsage,
) -> None:
    if usage.components != set(profile.components):
        raise ValueError("composition profile must not contain orphan components")
    if usage.allocations != set(profile.allocations):
        raise ValueError("composition profile must not contain orphan allocations")
    if usage.edges != set(profile.edges):
        raise ValueError("composition profile must not contain orphan edges")
    for allocation_id, active_phases in usage.allocation_phases.items():
        if active_phases != set(profile.allocations[allocation_id].phase_ids):
            raise ValueError("allocation phase_ids must equal its active phase membership")
    for edge_id, active_phases in usage.edge_phases.items():
        if active_phases != set(profile.edges[edge_id].phase_ids):
            raise ValueError("edge phase_ids must equal its active phase membership")


def _validate_transitions(
    profile: MixedParticipantCompositionProfileModel,
    phase_ids: set[str],
) -> None:
    transition_pairs: set[tuple[str, str]] = set()
    for transition in profile.transitions.values():
        if transition.source_phase_id not in phase_ids or transition.target_phase_id not in phase_ids:
            raise ValueError("transition phases must resolve inside the profile")
        pair = (transition.source_phase_id, transition.target_phase_id)
        if pair in transition_pairs:
            raise ValueError("phase transitions must have one canonical transition per directed pair")
        transition_pairs.add(pair)
    expected_pairs = set(zip(profile.phase_order, profile.phase_order[1:], strict=False))
    if transition_pairs != expected_pairs:
        raise ValueError("transitions must exactly connect adjacent phase_order entries")


def _validate_fixed_membership(profile: MixedParticipantCompositionProfileModel) -> None:
    if profile.federation_membership != "fixed":
        return
    memberships = {tuple(sorted(phase.active_component_ids)) for phase in profile.phases.values()}
    if len(memberships) != 1:
        raise ValueError("fixed federation membership cannot vary by phase")


def validate_mixed_composition_phase_graph(profile: MixedParticipantCompositionProfileModel) -> None:
    """Validate closed phase membership, activity, and transition invariants."""

    phase_ids = _validate_phase_order(profile)
    usage = _collect_phase_usage(profile)
    _validate_activity_coverage(profile, usage)
    _validate_transitions(profile, phase_ids)
    _validate_fixed_membership(profile)


__all__ = ["validate_mixed_composition_phase_graph"]
