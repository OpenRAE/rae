"""Finite sem-235/rev1 oracle; no wire parser, provider, scheduler or store.

Refs stand for trusted, revision/digest-resolved apparatus and owner results.
The tests falsify finite relations; they cannot establish instrumentation,
authentication, durable atomicity or external realization.
"""

from dataclasses import dataclass, replace
from itertools import combinations

TOKENS = ("coached-hint", "worked-example")
TEACHING = "teaching-influence/rev1"
KINDS = frozenset({"fact", "decision", "advice", "request"})


@dataclass(frozen=True)
class Influence:
    ref: str
    labels: frozenset[str] | None
    ancestors: frozenset[str] = frozenset()
    revision: str = TEACHING


def join(a: frozenset[str], b: frozenset[str]) -> frozenset[str]:
    if not (a | b) <= set(TOKENS):
        raise ValueError("domain")
    return a | b


def derive(ref: str, inputs: tuple[Influence, ...]) -> Influence:
    ancestors = frozenset(x for value in inputs for x in (value.ref, *value.ancestors))
    if not ref or ref in ancestors:
        raise ValueError("fresh identity required")
    if any(value.revision != TEACHING for value in inputs):
        raise ValueError("revision")
    labels = frozenset()
    for value in inputs:
        if value.labels is not None:
            labels = join(labels, value.labels)
    # Empty known source is supplied explicitly. No inputs means no coverage.
    known = bool(inputs) and all(value.labels is not None for value in inputs)
    return Influence(ref, labels if known else None, ancestors)


@dataclass(frozen=True)
class Slot:
    ref: str
    kind: str
    mandatory: bool = True
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Result:
    slot: str
    kind: str
    status: str = "resolved"
    cut: str = "K0"
    payload: str = "known"


def _ordered_slots(slots: tuple[Slot, ...]) -> tuple[Slot, ...]:
    by_ref = {slot.ref: slot for slot in slots}
    if len(by_ref) != len(slots) or len(slots) > 16:
        raise ValueError("selection")
    pending = set(by_ref)
    ordered = []
    for slot in slots:
        if not slot.ref or slot.kind not in KINDS or len(set(slot.dependencies)) != len(slot.dependencies):
            raise ValueError("slot")
        for dep in slot.dependencies:
            if dep not in by_ref or (slot.mandatory and not by_ref[dep].mandatory):
                raise ValueError("dependency")
    while pending:
        layer = sorted(ref for ref in pending if not pending.intersection(by_ref[ref].dependencies))
        if not layer:
            raise ValueError("cycle")
        ordered.extend(by_ref[ref] for ref in layer)
        pending.difference_update(layer)
    return tuple(ordered)


def compose(slots: tuple[Slot, ...], results: tuple[Result, ...], *, cut: str, incumbent: bool = True):
    ordered = _ordered_slots(slots)
    by_slot = {result.slot: result for result in results}
    if len(by_slot) != len(results) or not by_slot.keys() <= {slot.ref for slot in slots}:
        raise ValueError("result binding")
    failures: dict[str, str] = {}
    for slot in ordered:
        result = by_slot.get(slot.ref)
        if result is None:
            reason = "missing"
        elif result.cut != cut:
            reason = "stale"
        elif result.status != "resolved":
            reason = (
                result.status
                if result.status in {"missing", "unknown", "unsupported", "stale", "failed", "weakened"}
                else "unsupported"
            )
        elif result.kind != slot.kind:
            reason = "kind"
        elif any(dep in failures for dep in slot.dependencies):
            reason = "dependency"
        elif slot.kind == "decision" and result.payload != "permit":
            reason = result.payload if result.payload in {"deny", "withhold", "abstain"} else "unsupported"
        else:
            reason = ""
        if reason:
            failures[slot.ref] = reason
    blocking = {f"{slot.ref}:{failures[slot.ref]}" for slot in slots if slot.mandatory and slot.ref in failures}
    if not incumbent:
        blocking.add("incumbent")
    return tuple(sorted(blocking))


EFFECTS = frozenset(
    {
        "permit",
        "deny",
        "withhold",
        "transform",
        "mask",
        "inject",
        "delay",
        "route",
        "audit",
        "handoff",
        "request-review",
        "interrupt",
        "shutdown",
    }
)


@dataclass(frozen=True)
class Request:
    rule: str
    kind: str
    subject: str
    target: str
    content: str = "artifact:one"
    slot: int = 0
    epoch: int = 0
    phase: str = "subsequent"
    window: tuple[int, int] = (0, 10)
    clock: str = "clock:one"
    parent: str | None = None

    @property
    def key(self):
        # Run and root are held by State, not caller retry/cut/transport ids.
        return self.rule, self.slot, self.epoch


def delay_window(requests: tuple[Request, ...]) -> tuple[int, int]:
    return max(r.window[0] for r in requests), min(r.window[1] for r in requests)


def _pair_conflict(left, right, reach, independent):
    pair = frozenset({left.rule, right.rule})
    ordered = (left.rule, right.rule) in reach or (right.rule, left.rule) in reach
    if left.subject == right.subject:
        if left.kind in {"transform", "mask"} and right.kind in {"transform", "mask"}:
            return (
                not ordered or left.content != right.content or left.kind != right.kind or left.target != right.target
            )
        if left.kind == right.kind and left.kind in {"route", "handoff"}:
            return not ordered or left.target != right.target
        if left.kind == right.kind == "delay":
            low, high = delay_window((left, right))
            return left.clock != right.clock or low > high
    shared = left.subject == right.subject or left.target == right.target
    if shared:
        if left.kind == "shutdown" and (left.rule, right.rule) in reach:
            return True
        if right.kind == "shutdown" and (right.rule, left.rule) in reach:
            return True
        return not ordered
    return not ordered and pair not in independent


def effect_plan(requests: tuple[Request, ...], *, order=frozenset(), independent=frozenset()):
    if len(requests) > 16 or any(r.kind not in EFFECTS for r in requests):
        return ("unsupported",)
    if any(r.phase not in {"predecessor", "subsequent"} or not all((r.rule, r.subject, r.target)) for r in requests):
        return ("invalid-binding",)
    if any(r.kind == "delay" and r.window[0] > r.window[1] for r in requests):
        return ("invalid-window",)
    unique = {}
    for request in requests:
        if request.key in unique and unique[request.key] != request:
            return ("key-conflict",)
        unique[request.key] = request
    nodes = {r.rule for r in requests}
    if len(nodes) != len(unique):
        return ("unsupported",)
    reach = set(order)
    if any(a not in nodes or b not in nodes for a, b in reach):
        return ("invalid-order",)
    for mid in sorted(nodes):
        reach.update((a, b) for a in nodes for b in nodes if (a, mid) in reach and (mid, b) in reach)
    if any((node, node) in reach for node in nodes):
        return ("invalid-order",)
    if any(_pair_conflict(a, b, reach, independent) for a, b in combinations(unique.values(), 2)):
        return ("conflict",)
    return ()


@dataclass(frozen=True)
class Claim:
    request: Request
    identity: str
    depth: int
    phase: str = "committed"


@dataclass(frozen=True)
class State:
    """One admitted run/root; immutable atomic states are a model assumption."""

    run: str = "run:one"
    root: str = "root:one"
    claims: tuple[Claim, ...] = ()
    calls: tuple[str, ...] = ()
    limit: int = 2
    depth_limit: int = 2
    rule_limit: int = 1


def claim(state, request, *, expected="K0", current="K0", allowed=True, committed=True):
    prior = next((c for c in state.claims if c.request.key == request.key), None)
    if prior:
        return state, prior.phase if prior.request == request else "key-conflict"
    if expected != current:
        return state, "stale"
    if not allowed or request.kind in {"permit", "deny", "withhold"} or effect_plan((request,)):
        return state, "refused"
    parents = [c for c in state.claims if c.identity == request.parent]
    if request.parent is not None and not parents:
        return state, "unknown-parent"
    depth = parents[0].depth + 1 if parents else 1
    firings = sum(c.request.rule == request.rule for c in state.claims)
    if len(state.claims) >= state.limit or depth > state.depth_limit or firings >= state.rule_limit:
        return state, "exhausted"
    if not committed:
        return state, "commit-failed"
    # Fresh allocation also excludes all source identities in this finite state.
    used = {c.identity for c in state.claims} | {c.request.subject for c in state.claims} | {request.subject}
    n = len(state.claims)
    identity = f"{state.run}/{state.root}/occurrence:{n}"
    while identity in used:
        n += 1
        identity = f"{state.run}/{state.root}/occurrence:{n}"
    entry = Claim(request, identity, depth)
    return replace(state, claims=(*state.claims, entry)), "committed"


def observe(state, identity, outcome):
    entry = next(c for c in state.claims if c.identity == identity)
    if entry.phase not in {"dispatching", "indeterminate"} or outcome not in {"applied", "failed", "indeterminate"}:
        raise ValueError("realization transition")
    return replace(
        state, claims=tuple(replace(c, phase=outcome) if c.identity == identity else c for c in state.claims)
    )


def dispatch(state, identity, *, expected="K0", current="K0", allowed=True, fenced=True):
    entry = next(c for c in state.claims if c.identity == identity)
    if entry.phase != "committed":
        return state, entry.phase
    if expected != current or not allowed or not fenced:
        return state, "refused"
    claims = tuple(replace(c, phase="dispatching") if c.identity == identity else c for c in state.claims)
    return replace(state, claims=claims, calls=(*state.calls, identity)), "dispatching"
