"""Relationship completion refinements reuse semantic owners and their validator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ._declarations import Declaration
from ._errors import SDLValidationError
from ._language_context import PurposeResolver
from ._reference_targetability import ReferencePurpose
from ._relationship_endpoint_policy import RELATIONSHIP_DETAIL_BINDINGS
from .nodes import Node
from .participant_behavior_specification import MixedControlParticipantOperation
from .scenario import ScenarioContent
from .semantics._domain_topology_types import resolve_section_ref
from .semantics.deployment_tenancy import placement_context_allowed, placement_node_allowed
from .semantics.domain_topology import topology_source_allowed
from .semantics.enterprise_identity import distinct_forest_endpoints
from .validator import SemanticValidator
from .validator._participant_relationships import participant_relation_controller_states


@dataclass(frozen=True)
class _RelationshipContext:
    pointer: list[str]
    name: str
    relationship: dict[str, Any]
    scenario: ScenarioContent | None
    incomplete: bool
    resolver: PurposeResolver
    baseline: set[str]


def filter_relationship_candidates(
    items: list[dict[str, str]],
    pointer: list[str],
    data: dict[str, Any],
    scenario: ScenarioContent | None,
    partial: ScenarioContent | None,
    resolver: PurposeResolver,
) -> list[dict[str, str]]:
    if len(pointer) < 3 or pointer[0] != "relationships":
        return items
    name = pointer[1]
    relationship = data.get("relationships", {}).get(name)
    if not isinstance(relationship, dict):
        return items
    typed = scenario or partial
    baseline = _semantic_errors(typed) if typed is not None else set()
    context = _RelationshipContext(pointer, name, relationship, typed, scenario is None, resolver, baseline)
    return [item for item in items if _candidate_allowed(item, context)]


def _semantic_errors(scenario: ScenarioContent) -> set[str]:
    try:
        SemanticValidator(scenario).validate()
    except SDLValidationError as exc:
        return set(exc.errors)
    return set()


def _candidate_allowed(item: dict[str, str], context: _RelationshipContext) -> bool:
    if not _field_allowed(item["detail"], context):
        return False
    declaration = context.resolver.index.declaration_for(item["detail"])
    if context.incomplete and declaration is not None and not declaration.model_tokens:
        return True
    return _semantic_candidate_allowed(item["label"], context)


def _field_allowed(address: str, context: _RelationshipContext) -> bool:
    pointer = context.pointer
    if pointer[-1] in {"source", "target"} and not _endpoint_allowed(
        address, pointer[-1], context.relationship, context.scenario, context.resolver
    ):
        return False
    return _policy_scope_allowed(address, context)


def _semantic_candidate_allowed(label: str, context: _RelationshipContext) -> bool:
    typed = context.scenario
    if typed is None:
        return True
    # Only the edited relationship changes. Other declarations and provenance
    # remain read-only during validation; copying them per suggestion is costly.
    relationships = dict(typed.relationships)
    if context.name in relationships:
        relationships[context.name] = relationships[context.name].model_copy(deep=True)
    candidate = typed.model_copy(update={"relationships": relationships})
    owner = _field_owner(candidate.relationships.get(context.name), context.pointer[2:-1])
    applied = _apply_candidate(owner, context.pointer[-1], label)
    if applied is None:
        return True
    # Existing subtype owners and participant/control checks remain authoritative.
    # An incomplete context may already contain unrelated failures; do not turn
    # those into new constraints on this field. Known endpoint attributes and
    # selected control bounds are checked independently, even on an invalid edge.
    return applied and _semantic_errors(candidate).issubset(context.baseline)


def _field_owner(owner: object, tokens: list[str]) -> object:
    for token in tokens:
        if isinstance(owner, list):
            position = _list_position(token)
            owner = owner[position] if position is not None and position < len(owner) else None
        else:
            owner = owner.get(token) if isinstance(owner, Mapping) else getattr(owner, token, None)
    return owner


def _list_position(token: str) -> int | None:
    return int(token) if token.isdecimal() and len(token) <= 9 else None


def _apply_candidate(owner: object, token: str, label: str) -> bool | None:
    """Return None for an incomplete field, or whether an edit fits its owner."""
    if owner is None:
        return None
    if isinstance(owner, list):
        return _apply_list_candidate(owner, token, label)
    applied = None
    if isinstance(owner, dict) or hasattr(owner, token):
        current = owner.get(token) if isinstance(owner, dict) else getattr(owner, token)
        value = [label] if isinstance(current, list) else label
        if isinstance(owner, dict):
            owner[token] = value
        else:
            setattr(owner, token, value)
        applied = True
    return applied


def _apply_list_candidate(owner: list, token: str, label: str) -> bool | None:
    position = _list_position(token)
    if position is None:
        return None
    if position == len(owner):
        owner.append(label)
    elif position < len(owner):
        owner[position] = label
    return position <= len(owner)


def _policy_scope_allowed(address: str, context: _RelationshipContext) -> bool:
    control = _scope_control(context)
    endpoints = _participant_endpoints(context.relationship, context.resolver) if control is not None else None
    if control is None or endpoints is None:
        return True
    source, target = endpoints
    detail = context.relationship["participant"]
    controlled, controller = (source, target) if detail.get("kind") == "delegation" else (target, source)
    states = participant_relation_controller_states(control, controlled, controller)
    return address in {
        candidate
        for state in states
        for ref in state.scope_refs
        for candidate in context.resolver.resolve(ref, ReferencePurpose.OPERATING_SCOPE)
    }


def _scope_control(context: _RelationshipContext) -> MixedControlParticipantOperation | None:
    pointer, relationship, scenario = context.pointer, context.relationship, context.scenario
    field = pointer[-2] if pointer[-1].isdecimal() else pointer[-1]
    detail = relationship.get("participant")
    if field != "scope_refs" or not isinstance(detail, dict) or scenario is None:
        return None
    name = resolve_section_ref(
        detail.get("control_specification_ref"), "behavior_specifications", scenario.behavior_specifications
    )
    return scenario.behavior_specifications[name].mixed_control if name is not None else None


def _participant_endpoints(relationship: dict[str, Any], resolver: PurposeResolver) -> list[str] | None:
    endpoints = []
    for side in ("source", "target"):
        matches = resolver.resolve(relationship.get(side, ""), ReferencePurpose.PARTICIPANT_ENDPOINT)
        declaration = resolver.index.declaration_for(next(iter(matches))) if len(matches) == 1 else None
        if declaration is None or not declaration.model_tokens:
            return None
        endpoints.append(declaration.model_tokens[1])
    return endpoints


def _relationship_kind(relationship: dict[str, Any]) -> str | None:
    kind = relationship.get("type")
    if kind not in RELATIONSHIP_DETAIL_BINDINGS.values():
        implied = {
            bound for detail, bound in RELATIONSHIP_DETAIL_BINDINGS.items() if relationship.get(detail) is not None
        }
        kind = implied.pop() if len(implied) == 1 else kind
    return kind


def _endpoint_allowed(
    address: str,
    side: str,
    relationship: dict[str, Any],
    scenario: ScenarioContent | None,
    resolver: PurposeResolver,
) -> bool:
    declaration = resolver.index.declaration_for(address)
    if declaration is None:
        return False
    opposite = "target" if side == "source" else "source"
    matches = resolver.resolve(relationship.get(opposite, ""), ReferencePurpose.RELATIONSHIP_ENDPOINT)
    peer = resolver.index.declaration_for(next(iter(matches))) if len(matches) == 1 else None
    kind = _relationship_kind(relationship)
    return _peer_allowed(address, kind, peer) and _node_endpoint_allowed(
        declaration.model_tokens, side, kind, peer, scenario
    )


def _peer_allowed(address: str, kind: str | None, peer: Declaration | None) -> bool:
    if kind == "participant" and peer is not None and peer.kind == "agents" and peer.address == address:
        return False
    if kind == "forest_trusts" and peer is not None:
        return distinct_forest_endpoints(address, peer.address)
    return True


def _node_endpoint_allowed(
    tokens: tuple[str, ...], side: str, kind: str | None, peer: Declaration | None, scenario: ScenarioContent | None
) -> bool:
    if scenario is None or not tokens:
        return True
    name = tokens[1]
    node = scenario.nodes.get(name)
    if kind in {"domain_controller_for", "joins_domain"} and side == "source":
        return topology_source_allowed(node)
    return kind != "placed_on_carrier" or _placement_allowed(name, node, side, peer, scenario)


def _placement_allowed(
    name: str, node: Node | None, side: str, peer: Declaration | None, scenario: ScenarioContent
) -> bool:
    if not placement_node_allowed(node, side):
        return False
    if peer is not None and peer.kind == "node" and peer.model_tokens:
        source, target = (name, peer.model_tokens[1]) if side == "source" else (peer.model_tokens[1], name)
        return placement_context_allowed(source, target, scenario)
    return True
