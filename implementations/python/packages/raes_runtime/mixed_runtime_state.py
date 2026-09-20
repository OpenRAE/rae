"""Validated state-fold helpers shared by mixed-runtime operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raes_contracts.contracts.mixed_runtime import (
    MixedCompositionRuntimeEventModel,
    MixedCompositionRuntimeStateModel,
)
from raes_contracts.runtime_state import RuntimeSnapshot

if TYPE_CHECKING:
    from .mixed_runtime import MixedRuntimeBinding


def runtime_state(
    binding: MixedRuntimeBinding,
    snapshot: RuntimeSnapshot,
) -> MixedCompositionRuntimeStateModel:
    payload = snapshot.mixed_composition_states.get(binding.entry.run_id)
    if payload is None:
        raise ValueError("mixed composition must be activated before dispatch")
    state = MixedCompositionRuntimeStateModel.model_validate(payload)
    if (
        state.plan_id != binding.plan.plan_id
        or state.plan_entry_id != binding.entry.plan_entry_id
        or state.profile_id != binding.profile.profile_id
        or state.profile_digest != binding.profile.profile_digest
    ):
        raise ValueError("mixed composition runtime state differs from the admitted binding")
    phase = binding.profile.phases.get(state.phase_id)
    if phase is None or (
        state.active_component_ids != phase.active_component_ids
        or state.active_allocation_ids != phase.active_allocation_ids
        or state.active_edge_ids != phase.active_edge_ids
    ):
        raise ValueError("mixed composition runtime membership differs from the admitted phase")
    return state


def append_runtime_events(
    binding: MixedRuntimeBinding,
    snapshot: RuntimeSnapshot,
    state: MixedCompositionRuntimeStateModel,
    events: list[MixedCompositionRuntimeEventModel],
) -> RuntimeSnapshot:
    history = list(snapshot.mixed_composition_history[binding.entry.run_id])
    history.extend(event.model_dump(mode="json", exclude_none=True) for event in events)
    final = events[-1]
    next_state = MixedCompositionRuntimeStateModel(
        run_id=state.run_id,
        plan_id=state.plan_id,
        plan_entry_id=state.plan_entry_id,
        profile_id=state.profile_id,
        profile_digest=state.profile_digest,
        phase_id=final.phase_id,
        phase_revision=final.phase_revision,
        active_component_ids=final.active_component_ids,
        active_allocation_ids=final.active_allocation_ids,
        active_edge_ids=final.active_edge_ids,
        history_head=final.event_id,
    )
    return snapshot.with_entries(
        dict(snapshot.entries),
        mixed_composition_states={
            **snapshot.mixed_composition_states,
            binding.entry.run_id: next_state.model_dump(mode="json"),
        },
        mixed_composition_history={
            **snapshot.mixed_composition_history,
            binding.entry.run_id: history,
        },
    )


__all__ = ("append_runtime_events", "runtime_state")
