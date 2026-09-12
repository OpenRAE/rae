"""Finite lifecycle examples for #1201, separate from production evidence APIs."""

from __future__ import annotations

from dataclasses import dataclass

from .partial_description import ABSENT, Atom, Field, Record, _Budget, _validate_value, accepts, denotation


def version_domain(
    values, *, relation="numeric-triplet/v1", lower=None, upper=None, lower_closed=True, upper_closed=True
):
    """Toy ordered profile, deliberately not Debian/RPM/SemVer equivalence."""
    if relation != "numeric-triplet/v1":
        raise ValueError("unsupported-version-relation")
    if len(values) > 256:
        raise ValueError("limit-exceeded")

    def key(value):
        parts = value.split(".")
        if len(value) > 64 or len(parts) != 3 or any(not p.isascii() or not p.isdigit() for p in parts):
            raise ValueError("incomparable-version")
        return tuple(map(int, parts))

    low, high = key(lower) if lower is not None else None, key(upper) if upper is not None else None
    result = []
    for value in values:
        current = key(value)
        above = low is None or current > low or (lower_closed and current == low)
        below = high is None or current < high or (upper_closed and current == high)
        if above and below:
            result.append(value)
    return Atom(tuple(result))


@dataclass(frozen=True)
class Fact:
    path: tuple[str, ...]
    state: str
    value: object = ABSENT


@dataclass(frozen=True)
class ChoiceReport:
    basis: str
    facts: tuple[Fact, ...]


def _lookup(value, path):
    for part in path:
        if not isinstance(value, dict) or part not in value:
            return ABSENT
        value = value[part]
    return value


def _validate_facts(facts):
    budget = _Budget(4096)
    for fact in facts:
        budget.spend(len(fact.path))
        if fact.state not in {"known", "absent", "unknown", "redacted", "not-applicable"}:
            raise ValueError("invalid-knowledge-state")
        if fact.state == "known":
            if isinstance(fact.value, dict):
                raise ValueError("fact-needs-leaf")
            _validate_value(fact.value, budget)
        elif fact.value is not ABSENT:
            raise ValueError("knowledge-value-forbidden")


def _consistent(fact, world):
    value = _lookup(world, fact.path)
    if fact.state == "absent":
        return value is ABSENT
    if fact.state == "known":
        return type(value) is type(fact.value) and value == fact.value
    return True  # unknown/redacted/not-applicable cannot invent a fact


def assess(rules, facts, universe):
    """Possible-world assessment; no claim of real-world exhaustive coverage."""
    _validate_facts(facts)
    permitted = denotation(rules, universe)
    possible = {i for i, world in enumerate(universe) if all(_consistent(f, world) for f in facts)}
    if not possible:
        return "contradictory-or-unrepresented"
    if possible <= permitted:
        return "satisfied-in-finite-universe"
    return "violated" if possible.isdisjoint(permitted) else "unresolved"


def report_choice(selection, paths):
    _validate_value(selection, _Budget(4096))
    if len(paths) > 256:
        raise ValueError("limit-exceeded")
    facts = []
    for path in paths:
        value = _lookup(selection, path)
        if value is ABSENT:
            raise ValueError("unavailable-report-depth")
        # Only scalar projections in this prototype: no accidental subtree dump.
        if isinstance(value, dict):
            raise ValueError("report-needs-leaf-path")
        facts.append(Fact(path, "known", value))
    return ChoiceReport("backend-selected", tuple(facts))


def promote(facts, paths):
    """Deliberately create a new constraint tree from selected known scalar facts."""
    _validate_facts(facts)
    tree = {}
    for path in paths:
        matches = [fact for fact in facts if fact.path == path]
        if len(matches) != 1 or matches[0].state != "known" or isinstance(matches[0].value, dict) or not path:
            raise ValueError("promotion-needs-known-fact")
        node = tree
        for part in path[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ValueError("promotion-path-conflict")
        if path[-1] in node:
            raise ValueError("promotion-path-conflict")
        node[path[-1]] = Atom((matches[0].value,))

    def build(node):
        return Record(
            tuple(Field(key, build(value) if isinstance(value, dict) else value) for key, value in sorted(node.items()))
        )

    result = build(tree)
    accepts(result, {})  # run the same bounded description validation
    return result


@dataclass(frozen=True)
class Demand:
    scope: tuple[str, ...]
    mode: str
    streams: tuple[str, ...] = ()
    retain: bool = False
    export: bool = False
    forbid_experimental: bool = False
    forbidden: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaptureResult:
    collected: tuple
    retained: tuple
    exported: tuple
    operational_count: int


def _applies(scope, path):
    return path[: len(scope)] == scope


def _demand(path, demands):
    applicable = [d for d in demands if _applies(d.scope, path)]
    concrete = [d for d in applicable if d.mode != "inherit"]
    return max(concrete, key=lambda d: len(d.scope), default=Demand((), "operational")), applicable


def capture(demands, producers, supported, *, operational=frozenset()):
    """Admit the entire finite capture plan before invoking any synthetic source.

    Supported keys are (semantic scope tuple, stream). Exhaustive refers to the
    complete finite tuple returned by that declared source, not the whole world.
    """
    if len(demands) + len(producers) + len(supported) > 256:
        raise ValueError("limit-exceeded")
    if len({d.scope for d in demands}) != len(demands):
        raise ValueError("duplicate-demand-scope")
    for demand in demands:
        if demand.mode not in {"none", "operational", "inherit", "selected", "exhaustive"}:
            raise ValueError("invalid-demand")
        if demand.mode in {"selected", "exhaustive"} and not demand.streams:
            raise ValueError("capture-scope-required")
        for stream in demand.streams:
            if not any(_applies(demand.scope, path) and kind == stream for path, kind in producers):
                raise ValueError("unsupported-capture")
    if not operational <= producers.keys():
        raise ValueError("operational-input-unavailable")
    plan = []
    for key in producers:
        path, stream = key
        demand, ancestors = _demand(path, demands)
        experimental = demand.mode in {"selected", "exhaustive"} and stream in demand.streams
        needed = key in operational
        if (experimental and any(d.forbid_experimental for d in ancestors)) or (
            (experimental or needed) and any(stream in d.forbidden for d in ancestors)
        ):
            raise ValueError("policy-conflict")
        if experimental and key not in supported:
            raise ValueError("unsupported-capture")
        if experimental or needed:
            plan.append((key, demand, experimental, needed))
    collected, retained, exported = [], [], []
    operational_count = 0
    budget = _Budget(4096)
    for key, demand, experimental, needed in plan:
        values = producers[key]()
        if not isinstance(values, tuple):
            raise ValueError("invalid-source-result")
        for value in values:
            _validate_value(value, budget)
        if experimental:
            item = (key, values)
            collected.append(item)
            if demand.retain:
                retained.append(item)
            if demand.export:
                exported.append(item)
        operational_count += int(needed)
    return CaptureResult(tuple(collected), tuple(retained), tuple(exported), operational_count)


def abstract_run(schedule, *, limit=256, record_trace=False):
    """Two counters connected by directional single-slot mailboxes.

    increment: n -> n+1. send: copy local n into an empty peer mailbox.
    receive: replace local n from a nonempty mailbox, then empty that mailbox.
    These three transitions are the entire declared computer semantics.
    """
    state = {"a": 0, "b": 0}
    mailbox = {"a": None, "b": None}
    trace = []
    for index, (actor, action) in enumerate(schedule):
        if index >= limit:
            raise ValueError("limit-exceeded")
        if actor not in state or action not in {"increment", "send", "receive"}:
            raise ValueError("unknown-action")
        before = state[actor]
        peer = "b" if actor == "a" else "a"
        if action == "increment":
            state[actor] += 1
        elif action == "send":
            if mailbox[peer] is not None:
                raise ValueError("action-not-enabled")
            mailbox[peer] = state[actor]
        else:
            if mailbox[actor] is None:
                raise ValueError("action-not-enabled")
            state[actor], mailbox[actor] = mailbox[actor], None
        if record_trace:
            trace.append({"actor": actor, "action": action, "before": before, "after": state[actor]})
    return state, tuple(trace)
