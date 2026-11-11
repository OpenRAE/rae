"""Exact reuse of scenario-derived results across related scenarios.

Relationship completion validates one scenario per candidate, and variation
member admission validates one scenario per member. Those scenarios share
almost every top-level field object with the scenario they derive from. A
:class:`ValidationSession` records, for every reusable step (a validation pass
or a declaration-index adder), which top-level fields and private attributes it
read, and reuses the step outputs when a later scenario holds the identical
objects for all of them under the same step scope.

Exactness preconditions: steps are deterministic functions of what they read,
the declaration index holds values only, and callers do not mutate a scenario
object that a live session holds. The tracking view records every field when a
step serializes, copies, compares, or iterates the scenario, because those
paths read the instance dictionary without a per-field attribute lookup.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._errors import SDLValidationFinding

# Pseudo read names: every field, and the set of fields the author supplied.
ALL_FIELDS = "*"
FIELDS_SET = "__pydantic_fields_set__"
DECLARATION_INDEX = "__declaration_index__"
_BYPASS_ATTRIBUTES = frozenset(
    {
        "__copy__",
        "__deepcopy__",
        "__dict__",
        "__eq__",
        "__getstate__",
        "__iter__",
        "__reduce__",
        "__reduce_ex__",
        "__repr_args__",
        "model_copy",
        "model_dump",
        "model_dump_json",
    }
)


type _AttributeGetter = Callable[[object, str], object]

_FIELDS_SET_ATTRIBUTES = frozenset({"model_fields_set", "__pydantic_fields_set__"})


class ReadSink:
    """The reads of the pass that is running, or nothing outside a pass."""

    def __init__(self) -> None:
        self.reads: set[str] | None = None

    def note(self, name: str) -> None:
        if self.reads is not None:
            self.reads.add(name)

    def note_all(self, names: frozenset[str]) -> None:
        if self.reads is not None:
            self.reads.update(names)


_VIEW_TYPES: dict[type, type] = {}


def _view_type(scenario_type: type) -> type:
    """Return the cached tracking subclass of one scenario type."""

    view_type = _VIEW_TYPES.get(scenario_type)
    if view_type is None:
        fields = frozenset(scenario_type.model_fields)
        private = frozenset(getattr(scenario_type, "__private_attributes__", {}))

        def tracked_getattribute(self: object, name: str, _get: _AttributeGetter = object.__getattribute__) -> object:
            sink: ReadSink | None = _get(self, "__dict__").get("__raes_read_sink__")
            if sink is not None:
                if name in fields or name in private:
                    sink.note(name)
                elif name in _FIELDS_SET_ATTRIBUTES:
                    sink.note(FIELDS_SET)
                elif name in _BYPASS_ATTRIBUTES:
                    sink.note(ALL_FIELDS)
            return _get(self, name)

        view_type = type(
            f"_Tracked{scenario_type.__name__}",
            (scenario_type,),
            {"__getattribute__": tracked_getattribute, "__module__": __name__},
        )
        _VIEW_TYPES[scenario_type] = view_type
    return view_type


def tracking_view(scenario: object, sink: ReadSink) -> object:
    """Return a view that shares the scenario's state and reports its reads to ``sink``.

    The view shares the instance and private dictionaries, so writes through
    the view land on the scenario. The sink lives in a separate dictionary slot
    because the instance dictionary holds only model fields.
    """

    view = object.__new__(_view_type(type(scenario)))
    instance_dict = object.__getattribute__(scenario, "__dict__")
    tracked = _TrackedDict(instance_dict, sink)
    object.__setattr__(view, "__dict__", tracked)
    for name in ("__pydantic_fields_set__", "__pydantic_extra__", "__pydantic_private__"):
        object.__setattr__(view, name, object.__getattribute__(scenario, name))
    return view


_INDEX_VIEW_TYPES: dict[type, type] = {}


def tracking_index(index: object, sink: ReadSink) -> object:
    """Return a view of a declaration index that reports any use to ``sink``.

    The index carries values only, so a pass that consults it depends on the
    index fingerprint rather than on scenario field identities.
    """

    index_type = type(index)
    view_type = _INDEX_VIEW_TYPES.get(index_type)
    if view_type is None:

        def tracked_getattribute(self: object, name: str, _get: _AttributeGetter = object.__getattribute__) -> object:
            if not name.startswith("__"):
                _get(self, "_raes_read_sink").note(DECLARATION_INDEX)
            return _get(self, name)

        view_type = type(
            f"_Tracked{index_type.__name__}",
            (index_type,),
            {"__getattribute__": tracked_getattribute, "__module__": __name__},
        )
        _INDEX_VIEW_TYPES[index_type] = view_type
    view = object.__new__(view_type)
    view.__dict__.update(object.__getattribute__(index, "__dict__"))
    object.__setattr__(view, "_raes_read_sink", sink)
    return view


class _TrackedDict(dict[str, object]):
    """The scenario's field dictionary plus the hidden read sink."""

    def __init__(self, fields: dict[str, object], sink: ReadSink) -> None:
        super().__init__(fields)
        self.__raes_read_sink__ = sink

    def get(self, key: object, default: object = None) -> object:
        if key == "__raes_read_sink__":
            return self.__raes_read_sink__
        return super().get(key, default)


@dataclass(frozen=True)
class PassOutputs:
    errors: tuple[SDLValidationFinding, ...]
    warnings: tuple[str, ...]
    private_writes: tuple[tuple[str, object], ...]


@dataclass
class _StepEntry:
    """Outputs for one step, keyed by the identities of everything it read."""

    keep_alive: tuple[object, ...]
    outputs: object


@dataclass
class ValidationSession:
    """Reusable step and walker results for one validation tree.

    ``memoize=False`` disables reuse; tests use it as the reference behavior.
    """

    memoize: bool = True
    _steps: dict[tuple[object, ...], dict[tuple[str, ...], dict[tuple[int, ...], _StepEntry]]] = field(
        default_factory=dict
    )
    _walkers: dict[tuple[object, ...], tuple[object, object]] = field(default_factory=dict)
    _index_tokens: dict[tuple[object, ...], object] = field(default_factory=dict)

    def index_token(self, declarations: tuple[object, ...], collisions: tuple[str, ...]) -> object:
        """Intern a declaration-index fingerprint so keys compare it by identity."""

        key = (declarations, collisions)
        token = self._index_tokens.get(key)
        if token is None:
            token = object()
            self._index_tokens[key] = token
        return token

    def walker_result(self, key: tuple[object, ...], value: object) -> object | None:
        if not self.memoize:
            return None
        entry = self._walkers.get(key)
        return entry[1] if entry is not None and entry[0] is value else None

    def store_walker_result(self, key: tuple[object, ...], value: object, result: object) -> None:
        if self.memoize:
            self._walkers[key] = (value, result)

    def lookup(self, scope: tuple[object, ...], values: dict[str, object]) -> object | None:
        """Return stored outputs whose recorded reads all hold identical objects."""

        if not self.memoize:
            return None
        for read_names, entries in self._steps.get(scope, {}).items():
            entry = entries.get(tuple(id(values.get(name, MISSING)) for name in read_names))
            if entry is not None:
                return entry.outputs
        return None

    def store(self, scope: tuple[object, ...], reads: set[str], values: dict[str, object], outputs: object) -> None:
        """Keep ``outputs`` under the identities of the values the step read."""

        if not self.memoize:
            return
        read_names = tuple(sorted(values if ALL_FIELDS in reads else reads))
        read_values = tuple(values.get(name, MISSING) for name in read_names)
        by_reads = self._steps.setdefault(scope, {}).setdefault(read_names, {})
        by_reads[tuple(id(value) for value in read_values)] = _StepEntry(read_values, outputs)


def scenario_values(scenario: object) -> dict[str, object]:
    """Every top-level field, private attribute, and the authored field set, by name."""

    values: dict[str, object] = dict(object.__getattribute__(scenario, "__dict__"))
    values.update(object.__getattribute__(scenario, "__pydantic_private__") or {})
    values[FIELDS_SET] = object.__getattribute__(scenario, "__pydantic_fields_set__")
    return values


MISSING = object()


@contextmanager
def recording(sink: ReadSink) -> Iterator[set[str]]:
    """Collect the reads of one pass."""

    previous = sink.reads
    sink.reads = set()
    try:
        yield sink.reads
    finally:
        reads = sink.reads
        sink.reads = previous
        if previous is not None:
            previous.update(reads)


__all__ = [
    "ALL_FIELDS",
    "DECLARATION_INDEX",
    "FIELDS_SET",
    "MISSING",
    "PassOutputs",
    "ReadSink",
    "ValidationSession",
    "recording",
    "scenario_values",
    "tracking_index",
    "tracking_view",
]
