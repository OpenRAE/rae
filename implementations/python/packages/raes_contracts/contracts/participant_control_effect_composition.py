"""Pure order-independent effect compatibility and retained-claim accounting."""

from collections import defaultdict
from graphlib import CycleError, TopologicalSorter

from .._canonical import canonical_json_digest
from .participant_control_coordinates import require_unique
from .participant_control_effects import ControlEffectRequestModel


def _effect_subject(target):
    if target.kind in {"transform", "mask", "route"}:
        return target.source.subject_ref
    if target.kind == "request-review":
        return target.parent.subject_ref
    if target.kind in {"interrupt", "shutdown"}:
        return target.target_ref
    if target.kind in {"inject", "handoff"}:
        return target.participant_address
    return target.subject.subject_ref


def _lifecycle_invalidates(lifecycle, operation, context):
    """Pausing/cancelling/terminating cannot precede a live-target operation.

    A workflow/execution's membership is not encoded by these request targets,
    so lack of an enclosing-scope proof is conservative overlap, not independence.
    Audit/review/denial records do not themselves require a live participant.
    """
    if lifecycle.kind not in {"interrupt", "shutdown"}:
        return False
    if operation.kind in {"inject", "handoff"}:
        participant, episode = operation.participant_address, operation.episode_id
    elif operation.kind in {"transform", "mask", "route"}:
        participant, episode = operation.result.participant_address, operation.result.episode_id
    elif operation.kind in {"permit", "delay"}:
        participant, episode = operation.subject.participant_address, operation.subject.episode_id
    else:
        return False
    scopes = {"participant": participant, "episode": episode, "run": context.run.ref}
    return lifecycle.target_kind not in scopes or scopes[lifecycle.target_kind] == lifecycle.target_ref


def _effect_pair_conflicts(left, right, ancestors, context):
    a, b = left.target, right.target
    left_first = left.effect_id in ancestors[right.effect_id]
    right_first = right.effect_id in ancestors[left.effect_id]
    if (left_first and _lifecycle_invalidates(a, b, context)) or (
        right_first and _lifecycle_invalidates(b, a, context)
    ):
        return True
    if _effect_subject(a) != _effect_subject(b):
        return not (left_first or right_first)
    if a.kind == b.kind == "delay":
        return a.clock != b.clock or max(a.earliest_order, b.earliest_order) > min(a.latest_order, b.latest_order)
    if a.kind in {"transform", "mask", "route"} and b.kind in {"transform", "mask", "route"} and a != b:
        return True
    if a.kind == b.kind == "handoff" and a.resulting_controller_ref != b.resulting_controller_ref:
        return True
    if {a.kind, b.kind} == {"interrupt", "shutdown"}:
        return True
    return not (left_first or right_first)


def _effect_ancestors(by_id):
    # Every variant contributes its edges. No arrival-selected representative.
    graph = {
        identity: {dep for effect in variants for dep in effect.predecessor_effect_ids}
        for identity, variants in by_id.items()
    }
    if any(not predecessors <= graph.keys() for predecessors in graph.values()):
        raise ValueError("effect predecessor is unresolved")
    try:
        ordered = tuple(TopologicalSorter(graph).static_order())
    except CycleError:
        raise ValueError("effect predecessor cycle") from None
    ancestors = {}
    for identity in ordered:
        ancestors[identity] = set(graph[identity])
        for predecessor in graph[identity]:
            ancestors[identity].update(ancestors[predecessor])
    return ancestors


def _retained_claims(effects, context, blockers):
    prior_keys = {claim.key: claim for claim in context.prior_effect_claims}
    prior_ids = {claim.effect_id: claim for claim in context.prior_effect_claims}
    for effect in effects:
        prior = prior_keys.get(effect.key)
        if prior is not None and (
            prior.effect_id != effect.effect_id
            or prior.content_digest != canonical_json_digest(effect.model_dump(mode="json"))
        ):
            blockers.add("effect-conflict")
        prior_identity = prior_ids.get(effect.effect_id)
        if prior_identity is not None and prior_identity.key != effect.key:
            blockers.add("effect-conflict")
    return {effect.key for effect in effects} - prior_keys.keys()


def _validate_effect_bounds(effects, new_keys, context, bounds):
    epochs = {(item.rule_id, item.rule_revision): set(item.firing_epochs) for item in context.rule_firings}
    for effect in effects:
        epochs.setdefault((effect.key.rule_id, effect.key.rule_revision), set()).add(effect.key.firing_epoch)
        target = effect.target
        # Replaying an already claimed intent does not re-admit or re-dispatch it.
        if effect.key in new_keys and target.kind in {"delay", "request-review"}:
            if target.clock != context.clock or not context.order <= target.expiry_order <= bounds.expires_at_order:
                raise ValueError("effect clock or expiry is not admitted")
            if target.kind == "delay" and target.latest_order < context.order:
                raise ValueError("delay window is exhausted")
    if any(len(values) > bounds.max_firings_per_rule for values in epochs.values()):
        raise ValueError("effect requests exceed per-rule firing budget")
    if new_keys and context.depth >= bounds.max_depth:
        raise ValueError("effect requests exceed causal depth")
    if len(new_keys) > bounds.max_fanout or len(new_keys) + context.effects_consumed > bounds.max_effects:
        raise ValueError("effect requests exceed causal budget")


def validate_control_effect_composition(document):
    effects = {r.payload for r in document.results if isinstance(r.payload, ControlEffectRequestModel)}
    context = document.request.context
    blockers = set()
    by_id, by_key = defaultdict(set), defaultdict(set)
    for effect in effects:
        by_id[effect.effect_id].add(effect)
        by_key[effect.key].add(effect)
        if (effect.key.run_ref, effect.key.trigger_root) != (context.run.ref, context.trigger_root):
            raise ValueError("effect causal root differs from its request")
        if effect.phase == "required-predecessor":
            blockers.add("predecessor:" + effect.effect_id)
    if any(len(variants) > 1 for variants in (*by_id.values(), *by_key.values())):
        blockers.add("effect-conflict")
    ancestors = _effect_ancestors(by_id)
    new_keys = _retained_claims(effects, context, blockers)
    _validate_effect_bounds(effects, new_keys, context, document.request.selection.bounds)
    # Pairwise checks are symmetric; this ordering does not grant precedence.
    variants = tuple(effects)
    for index, left in enumerate(variants):
        for right in variants[index + 1 :]:
            if _effect_pair_conflicts(left, right, ancestors, context):
                blockers.add("effect-conflict")
    require_unique(tuple(r.effect_id for r in document.realizations))
    if any(r.effect_id not in by_id for r in document.realizations):
        raise ValueError("realization references an absent requested effect")
    return blockers
