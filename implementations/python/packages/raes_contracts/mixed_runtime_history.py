"""Validate composition state folds and append-only runtime transitions."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from .contracts.mixed_runtime import MixedCompositionRuntimeEventModel, MixedCompositionRuntimeStateModel


def iter_mixed_runtime_snapshot_violations(
    states: Mapping[str, dict[str, object]],
    histories: Mapping[str, list[dict[str, object]]],
) -> Iterator[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    if set(states) != set(histories):
        violations.append(("runtime.composition", "Composition state and history identities must match."))
    for run_id, events in histories.items():
        if not events or len(events) > 4096:
            violations.append((run_id, "Composition history must be nonempty and bounded."))
            continue
        models = _runtime_models(states, run_id, events)
        if models is None:
            violations.append((run_id, "Composition state or history is invalid."))
            continue
        state, chain = models
        violations.extend(_iter_chain_violations(run_id, state, chain))
        if not _state_matches_history(state, chain[-1]):
            violations.append((run_id, "Composition state must fold from the final history event."))
    return iter(violations)


def _runtime_models(
    states: Mapping[str, dict[str, object]],
    run_id: str,
    events: list[dict[str, object]],
) -> tuple[MixedCompositionRuntimeStateModel, list[MixedCompositionRuntimeEventModel]] | None:
    try:
        state = MixedCompositionRuntimeStateModel.model_validate(states[run_id])
        chain = [MixedCompositionRuntimeEventModel.model_validate(event) for event in events]
    except (KeyError, TypeError, ValueError):
        return None
    return state, chain


def _iter_chain_violations(
    run_id: str,
    state: MixedCompositionRuntimeStateModel,
    chain: list[MixedCompositionRuntimeEventModel],
) -> Iterator[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    if state.run_id != run_id or any(event.run_id != run_id for event in chain):
        violations.append((run_id, "Composition map key must match the embedded run identity."))
    if chain[0].event_kind != "phase-activated":
        violations.append((run_id, "Composition history must start with phase activation."))
    if len({event.event_id for event in chain}) != len(chain):
        violations.append((run_id, "Composition event identities must be unique."))
    for previous, current in zip(chain, chain[1:], strict=False):
        violations.extend(_iter_event_transition_violations(run_id, previous, current))
    return iter(violations)


def _iter_event_transition_violations(
    run_id: str,
    previous: MixedCompositionRuntimeEventModel,
    current: MixedCompositionRuntimeEventModel,
) -> Iterator[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    if current.predecessor_event_id != previous.event_id:
        violations.append((run_id, "Composition event predecessor does not match the history head."))
    current_identity = (current.plan_id, current.plan_entry_id, current.profile_id, current.profile_digest)
    previous_identity = (previous.plan_id, previous.plan_entry_id, previous.profile_id, previous.profile_digest)
    if current_identity != previous_identity:
        violations.append((run_id, "Composition plan and profile identity cannot change within a run."))
    if current.event_kind == "phase-transition":
        if current.phase_revision != previous.phase_revision + 1:
            violations.append((run_id, "Composition phase revision must advance exactly once."))
    elif _composition_membership(current) != _composition_membership(previous):
        violations.append((run_id, "Only a phase transition may change active composition membership."))
    return iter(violations)


def _composition_membership(event: MixedCompositionRuntimeEventModel) -> tuple[object, ...]:
    return (
        event.phase_revision,
        event.phase_id,
        event.active_component_ids,
        event.active_allocation_ids,
        event.active_edge_ids,
    )


def _state_matches_history(
    state: MixedCompositionRuntimeStateModel,
    last: MixedCompositionRuntimeEventModel,
) -> bool:
    folded = state.model_dump(mode="json", exclude={"history_head"})
    expected = last.model_dump(
        mode="json",
        include={
            "run_id",
            "plan_id",
            "plan_entry_id",
            "profile_id",
            "profile_digest",
            "phase_id",
            "phase_revision",
            "active_component_ids",
            "active_allocation_ids",
            "active_edge_ids",
        },
    )
    return folded == expected and state.history_head == last.event_id


def iter_mixed_runtime_transition_violations(
    before: Mapping[str, list[dict[str, object]]],
    after: Mapping[str, list[dict[str, object]]],
) -> Iterator[tuple[str, str]]:
    for run_id, prior in before.items():
        current = after.get(run_id)
        if current is None or current[: len(prior)] != prior:
            yield run_id, "Composition history must remain append-only."
