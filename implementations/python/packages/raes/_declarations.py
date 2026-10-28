"""Typed SDL declaration indexing and canonical-address collision checks."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ._declaration_adders import DECLARATION_ADDERS
from ._declaration_index import Declaration, DeclarationIndex, Purposes, preferred_spelling
from ._incremental_reuse import ReadSink, ValidationSession, recording, scenario_values, tracking_view

if TYPE_CHECKING:
    from .scenario import ScenarioContent


class _RecordingIndex(DeclarationIndex):
    """Records an adder's declarations so a later index can replay them in order."""

    def __init__(self) -> None:
        super().__init__()
        self.operations: list[tuple[Declaration, tuple[str, ...]]] = []

    def add(self, declaration: Declaration, *, aliases: Iterable[str] = ()) -> None:
        self.operations.append((declaration, tuple(aliases)))


@dataclass(frozen=True)
class _ReplayContext:
    """One scenario's identities, tracking view, and session for adder replay."""

    scenario_type: type
    values: dict[str, object]
    view: ScenarioContent
    sink: ReadSink
    session: ValidationSession


def _run_adder(
    index: DeclarationIndex,
    adder: Callable[[DeclarationIndex, ScenarioContent], None],
    context: _ReplayContext,
) -> None:
    """Replay an adder's declarations when it read the identical scenario objects."""

    scope = ("declaration-adder", adder.__name__, context.scenario_type)
    operations = cast(
        "tuple[tuple[Declaration, tuple[str, ...]], ...] | None",
        context.session.lookup(scope, context.values),
    )
    if operations is None:
        recorder = _RecordingIndex()
        with recording(context.sink) as reads:
            adder(recorder, context.view)
        operations = tuple(recorder.operations)
        context.session.store(scope, reads, context.values, operations)
    for declaration, aliases in operations:
        index.add(declaration, aliases=aliases)


def build_declaration_index(
    scenario: ScenarioContent,
    *,
    raise_on_collision: bool = True,
    session: ValidationSession | None = None,
) -> DeclarationIndex:
    """Index every catalogued declaration and reject non-injective rendering.

    With a ``session``, an adder that read only identical scenario objects
    replays its recorded declarations into the new index in the same order.
    """

    index = DeclarationIndex()
    if session is None:
        for adder in DECLARATION_ADDERS:
            adder(index, scenario)
    else:
        sink = ReadSink()
        context = _ReplayContext(
            scenario_type=type(scenario),
            values=scenario_values(scenario),
            view=cast("ScenarioContent", tracking_view(scenario, sink)),
            sink=sink,
            session=session,
        )
        for adder in DECLARATION_ADDERS:
            _run_adder(index, adder, context)
    index.attach_sources(scenario.declaration_sources)
    if raise_on_collision:
        index.raise_for_collisions()
    return index


__all__ = [
    "Declaration",
    "DeclarationIndex",
    "Purposes",
    "build_declaration_index",
    "preferred_spelling",
]
