"""Validate composition state folds and append-only runtime transitions."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from .contracts.mixed_runtime import MixedCompositionRuntimeEventModel, MixedCompositionRuntimeStateModel


def iter_mixed_runtime_snapshot_violations(
    states: Mapping[str, dict[str, object]],
    histories: Mapping[str, list[dict[str, object]]],
) -> Iterator[tuple[str, str]]:
    if set(states) != set(histories):
        yield "runtime.composition", "Composition state and history identities must match."
    for run_id, events in histories.items():
        if not events or len(events) > 4096:
            yield run_id, "Composition history must be nonempty and bounded."
            continue
        try:
            state = MixedCompositionRuntimeStateModel.model_validate(states[run_id])
            chain = [MixedCompositionRuntimeEventModel.model_validate(event) for event in events]
        except (KeyError, TypeError, ValueError):
            yield run_id, "Composition state or history is invalid."
            continue
        if state.run_id != run_id or any(event.run_id != run_id for event in chain):
            yield run_id, "Composition map key must match the embedded run identity."
        if chain[0].event_kind != "phase-activated":
            yield run_id, "Composition history must start with phase activation."
        if len({event.event_id for event in chain}) != len(chain):
            yield run_id, "Composition event identities must be unique."
        for previous, current in zip(chain, chain[1:], strict=False):
            if current.predecessor_event_id != previous.event_id:
                yield run_id, "Composition event predecessor does not match the history head."
            if (current.plan_id, current.plan_entry_id, current.profile_id, current.profile_digest) != (
                previous.plan_id,
                previous.plan_entry_id,
                previous.profile_id,
                previous.profile_digest,
            ):
                yield run_id, "Composition plan and profile identity cannot change within a run."
            if current.event_kind == "phase-transition":
                if current.phase_revision != previous.phase_revision + 1:
                    yield run_id, "Composition phase revision must advance exactly once."
            elif (
                current.phase_revision != previous.phase_revision
                or current.phase_id != previous.phase_id
                or current.active_component_ids != previous.active_component_ids
                or current.active_allocation_ids != previous.active_allocation_ids
                or current.active_edge_ids != previous.active_edge_ids
            ):
                yield run_id, "Only a phase transition may change active composition membership."
        last = chain[-1]
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
        if folded != expected or state.history_head != last.event_id:
            yield run_id, "Composition state must fold from the final history event."


def iter_mixed_runtime_transition_violations(
    before: Mapping[str, list[dict[str, object]]],
    after: Mapping[str, list[dict[str, object]]],
) -> Iterator[tuple[str, str]]:
    for run_id, prior in before.items():
        current = after.get(run_id)
        if current is None or current[: len(prior)] != prior:
            yield run_id, "Composition history must remain append-only."
