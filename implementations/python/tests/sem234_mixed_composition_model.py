"""Finite SEM-234 oracle, not a runtime coordinator or portable contract.

Context is a trusted finite interpretation of compiled scopes, effective support
and revision/digest resolution. It does not authenticate a backend or prove an
evidence artifact's contents. All effects below are symbolic model events.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from sem230_information_flow_model import project_history

Pin = tuple[str, str, str, str]  # kind, identity, revision, digest
EDGE_KINDS = frozenset({"adapter", "authority", "mapping", "policy", "release", "time", "failure", "observer"})
SCOPE_KINDS = frozenset(
    {"participant-runtime", "controlled-scope", "action-family", "observation-source", "crossing-boundary"}
)
FORMS = frozenset({"simulation", "emulation-or-operational", "hardware-or-native", "federated-composition"})


@dataclass(frozen=True)
class Scope:
    ref: str
    kind: str
    atoms: frozenset[str]


@dataclass(frozen=True)
class Component:
    ref: str
    form: str
    clock: str
    supported: frozenset[str]
    strength: int
    evidence: frozenset[str]


@dataclass(frozen=True)
class Edge:
    source: str
    destination: str
    scope: str
    pins: frozenset[Pin]
    clocks: tuple[str, str]
    loss: frozenset[str] = frozenset()

    @property
    def key(self) -> tuple[str, str, str]:
        return self.source, self.destination, self.scope


@dataclass(frozen=True)
class Phase:
    ref: str
    members: frozenset[str]
    allocations: tuple[tuple[str, str], ...]
    edges: tuple[Edge, ...]
    exchanges: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class Plan:
    scenario: str
    policy: str
    plan: str
    entry: str
    run: str
    mode: str
    components: tuple[str, ...]
    phases: tuple[Phase, ...]
    required: frozenset[str]
    loop: str = "closed-loop"
    world: str = "closed-world"
    membership: str = "fixed"
    allowed_loss: frozenset[str] = frozenset()
    authority_revision: str = "sem-234/rev1"
    transitions: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class Context:
    scopes: tuple[Scope, ...]
    components: tuple[Component, ...]
    pins: frozenset[Pin]
    clock_maps: tuple[tuple[Pin, tuple[str, str]], ...]


def _edge_errors(edge: Edge, phase: Phase, plan: Plan, context: Context) -> set[str]:
    errors: set[str] = set()
    components = {component.ref: component for component in context.components}
    scopes = {scope.ref: scope for scope in context.scopes}
    if edge.source not in phase.members or edge.destination not in phase.members:
        errors.add("edge-endpoint")
    if edge.scope not in scopes or scopes[edge.scope].kind != "crossing-boundary":
        errors.add("edge-scope")
    if edge.scope not in dict(phase.allocations):
        errors.add("edge-scope")
    if len(edge.pins) != len(EDGE_KINDS) or {pin[0] for pin in edge.pins} != EDGE_KINDS:
        errors.add("edge-binding")
    if not edge.pins <= context.pins:
        errors.add("edge-binding")
    if not edge.loss <= plan.allowed_loss:
        errors.add("unadmitted-loss")
    actual_clocks = tuple(
        components[ref].clock if ref in components else None for ref in (edge.source, edge.destination)
    )
    time_pins = [pin for pin in edge.pins if pin[0] == "time"]
    matches = [clocks for pin, clocks in context.clock_maps if pin in time_pins]
    if edge.clocks != actual_clocks or matches != [edge.clocks]:
        errors.add("clock-mapping")
    return errors


def _phase_errors(phase: Phase, plan: Plan, context: Context) -> set[str]:
    errors: set[str] = set()
    components = {component.ref: component for component in context.components}
    scopes = {scope.ref: scope for scope in context.scopes}
    if not phase.members or not phase.members <= set(plan.components):
        errors.add("unadmitted-member")
    providers: dict[str, set[str]] = {}
    allocated_scopes: set[str] = set()
    for scope_ref, provider in phase.allocations:
        if scope_ref in allocated_scopes:
            errors.add("duplicate-allocation")
        allocated_scopes.add(scope_ref)
        if provider not in phase.members or provider not in components:
            errors.add("inactive-provider")
            continue
        scope = scopes.get(scope_ref)
        if scope is None or scope.kind not in SCOPE_KINDS or not scope.atoms:
            errors.add("unresolved-scope")
            continue
        component = components[provider]
        if not scope.atoms <= component.supported or component.strength < 2:
            errors.add("unsupported-effect")
        if not component.evidence:
            errors.add("support-evidence")
        for atom in scope.atoms:
            providers.setdefault(atom, set()).add(provider)
    if not plan.required <= providers.keys():
        errors.add("incomplete-allocation")
    if any(len(owners) != 1 for owners in providers.values()):
        errors.add("competing-providers")
    keys = [edge.key for edge in phase.edges]
    if len(set(keys)) != len(keys) or len(set(phase.exchanges)) != len(phase.exchanges):
        errors.add("ambiguous-edge")
    if set(keys) != set(phase.exchanges):
        errors.add("exchange-edge")
    for edge in phase.edges:
        errors.update(_edge_errors(edge, phase, plan, context))
    return errors


def admit(plan: Plan, context: Context, *, limit: int = 256) -> tuple[str, ...]:
    """Check the complete finite graph, never infer support or discard a suffix."""
    work = len(context.scopes) + len(context.components) + len(context.pins) + len(context.clock_maps)
    work += len(plan.components) + len(plan.phases) + len(plan.required) + len(plan.transitions)
    work += sum(len(s.atoms) for s in context.scopes)
    work += sum(len(c.supported) + len(c.evidence) for c in context.components)
    work += sum(
        len(p.members) + len(p.allocations) + len(p.exchanges) + sum(1 + len(e.pins) + len(e.loss) for e in p.edges)
        for p in plan.phases
    )
    if work > limit:
        return ("work-limit",)
    errors: set[str] = set()
    if plan.authority_revision != "sem-234/rev1":
        errors.add("profile-revision")
    if not all((plan.scenario, plan.policy, plan.plan, plan.entry, plan.run)):
        errors.add("identity")
    components = {component.ref: component for component in context.components}
    if len(components) != len(context.components) or len({s.ref for s in context.scopes}) != len(context.scopes):
        errors.add("ambiguous-context")
    if len(set(plan.components)) != len(plan.components) or not set(plan.components) <= components.keys():
        errors.add("component-resolution")
    if any(components[ref].form not in FORMS for ref in plan.components if ref in components):
        errors.add("realization-form")
    if any(components[ref].form == "federated-composition" for ref in plan.components if ref in components):
        errors.add("nested-profile-required")
    if not plan.phases or len({phase.ref for phase in plan.phases}) != len(plan.phases):
        errors.add("phase-schedule")
    expected_pairs = {(left.ref, right.ref) for left, right in zip(plan.phases, plan.phases[1:], strict=False)}
    if (
        {(left, right) for left, right, _ in plan.transitions} != expected_pairs
        or len(plan.transitions) != len(expected_pairs)
        or any(not trigger for _, _, trigger in plan.transitions)
    ):
        errors.add("phase-schedule")
    if plan.loop not in {"open-loop", "closed-loop"} or plan.world not in {"closed-world", "bounded-open-world"}:
        errors.add("axes")
    if plan.membership not in {"fixed", "pre-admitted-dynamic"}:
        errors.add("axes")
    if plan.membership == "fixed" and len({phase.members for phase in plan.phases}) > 1:
        errors.add("fixed-membership")
    if plan.mode == "alternative-realization":
        if any(len(phase.members) != 1 for phase in plan.phases):
            errors.add("alternative-components")
    elif plan.mode == "simultaneous-mixed-realization":
        if not any(
            len({components[ref].form for _, ref in phase.allocations if ref in phase.members and ref in components})
            >= 2
            for phase in plan.phases
        ):
            errors.add("mixed-forms")
    else:
        errors.add("composition-mode")
    for phase in plan.phases:
        errors.update(_phase_errors(phase, plan, context))
    return tuple(sorted(errors))


@dataclass(frozen=True)
class Cut:
    ref: str
    participant: str
    episode: str
    controller: str
    authority: str
    policy_revision: str
    capability: str
    revision: int
    heads: tuple[str, str]
    authority_status: str = "active"
    order_ref: str = "order:one"


@dataclass(frozen=True)
class State:
    plan: Plan
    phase: int
    cut: Cut
    history: tuple[str, ...] = ()
    effects: tuple[tuple[str, str, str], ...] = ()
    knowledge: frozenset[str] = frozenset()
    pending: tuple[str, ...] = ()


def _record(state: State, outcome: str) -> State:
    revision = state.cut.revision + 1
    cut = replace(
        state.cut, ref=f"cut:{revision}", revision=revision, heads=(state.cut.heads[0], f"crossing:{revision}")
    )
    return replace(state, cut=cut, history=(*state.history, outcome))


def _cut_error(state: State, context: Context, expected: Cut) -> str | None:
    if expected != state.cut:
        return "stale"
    if state.cut.authority_status != "active":
        return "inactive-authority"
    if type(state.cut.controller) is not str or not state.cut.controller or not state.cut.authority:
        return "controller-authority"
    if admit(state.plan, context) or not 0 <= state.phase < len(state.plan.phases):
        return "invalid-plan"
    return None


def _order_error(order: frozenset[tuple[str, str]], before: str, after: str) -> str | None:
    nodes = {node for pair in order for node in pair}
    if len(nodes) > 32 or len(order) > 256:
        return "work-limit"
    reach = set(order)
    for middle in sorted(nodes):
        reach.update(
            (left, right) for left in nodes for right in nodes if (left, middle) in reach and (middle, right) in reach
        )
    if any((node, node) in reach for node in nodes):
        return "invalid-order"
    return None if (before, after) in reach else "unresolved-order"


def deliver(
    state: State,
    context: Context,
    *,
    edge_key,
    expected,
    crossings,
    policies,
    emitted,
    before,
    after,
    order,
    action,
    action_admitted,
    committed,
    result,
):
    """One bounded symbolic attempt/result; projection delegates to SEM-230.

    Policies and mapped order are trusted owner outputs in this model, not
    caller-granted permissions. The result is synthetic, never backend evidence.
    """
    error = _cut_error(state, context, expected)
    if error is None:
        phase = state.plan.phases[state.phase]
        edge = next((edge for edge in phase.edges if edge.key == edge_key), None)
        if edge is None:
            error = "unadmitted-edge"
        elif next(pin[1] for pin in edge.pins if pin[0] == "authority") != state.cut.authority:
            error = "authority-binding"
        elif (
            next(pin[1:3] for pin in edge.pins if pin[0] == "policy") != (state.plan.policy, state.cut.policy_revision)
            or not policies
            or any(
                (policy.policy_id, policy.revision, policy.decision_cut_ref)
                != (state.plan.policy, state.cut.policy_revision, state.cut.ref)
                for policy in policies
            )
        ):
            error = "policy-binding"
        elif action and state.plan.loop == "open-loop":
            error = "open-loop-actuation"
        elif action and not action_admitted:
            error = "action-denied"
        else:
            error = _order_error(order, before, after)
    if error is None:
        if any(
            c.decision_cut_ref != state.cut.ref or c.policy_revision != state.cut.policy_revision for c in crossings
        ):
            error = "stale-projection"
        else:
            projected = project_history(
                crossings, policies, participant=state.cut.participant, audience=f"participant:{state.cut.participant}"
            )
            if not emitted <= {source for _, source, _ in projected}:
                error = "projection-widened"
    if error is None and result not in {"delivered", "failed", "unknown"}:
        error = "invalid-result"
    if not committed:
        return state, "commit-failed"
    if error:
        return _record(state, error), error
    recorded = _record(state, result)
    return replace(
        recorded,
        effects=(*state.effects, edge_key),
        knowledge=state.knowledge | emitted if result == "delivered" else state.knowledge,
    ), result


def advance(state: State, context: Context, *, expected: Cut, trigger: str, committed: bool):
    """Quiescent consecutive phase commit; no controller or history rewrite."""
    error = _cut_error(state, context, expected)
    next_phase = state.phase + 1
    if error is None:
        if next_phase >= len(state.plan.phases):
            error = "terminal-phase"
        elif (
            state.plan.phases[state.phase].ref,
            state.plan.phases[next_phase].ref,
            trigger,
        ) not in state.plan.transitions:
            error = "unadmitted-trigger"
        elif state.pending:
            error = "in-flight"
    if not committed:
        return state, "commit-failed"
    if error:
        return _record(state, error), error
    return replace(_record(state, "phase-committed"), phase=next_phase), "phase-committed"


def link_trials(source: Plan, target: Plan, context: Context) -> tuple[str, str, str, str]:
    """Lineage for alternative realizations, without an equivalence assertion."""
    if (
        source.scenario != target.scenario
        or source.policy != target.policy
        or source.entry == target.entry
        or source.run == target.run
        or admit(source, context)
        or admit(target, context)
    ):
        raise ValueError("trial-lineage")
    return source.entry, source.run, target.entry, target.run
