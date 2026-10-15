"""Relationship completion refinements reuse semantic owners and their validator."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._errors import SDLValidationError
from ._language_context import PurposeResolver
from ._reference_targetability import ReferencePurpose
from ._relationship_endpoint_policy import RELATIONSHIP_DETAIL_BINDINGS
from .scenario import ScenarioContent
from .semantics._domain_topology_types import resolve_section_ref
from .semantics.deployment_tenancy import placement_context_allowed, placement_node_allowed
from .semantics.domain_topology import topology_source_allowed
from .semantics.enterprise_identity import distinct_forest_endpoints
from .validator import SemanticValidator
from .validator._participant_relationships import participant_relation_controller_states


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
    return [
        item
        for item in items
        if _candidate_allowed(item, pointer, name, relationship, scenario, partial, resolver, baseline)
    ]


def _semantic_errors(scenario: ScenarioContent) -> set[str]:
    try:
        SemanticValidator(scenario).validate()
    except SDLValidationError as exc:
        return set(exc.errors)
    return set()


def _candidate_allowed(
    item: dict[str, str],
    pointer: list[str],
    name: str,
    relationship: dict[str, Any],
    scenario: ScenarioContent | None,
    partial: ScenarioContent | None,
    resolver: PurposeResolver,
    baseline: set[str],
) -> bool:
    if pointer[-1] in {"source", "target"} and not _endpoint_allowed(
        item["detail"], pointer[-1], relationship, scenario or partial, resolver
    ):
        return False
    if not _policy_scope_allowed(item["detail"], pointer, relationship, scenario or partial, resolver):
        return False
    declaration = resolver.index.declaration_for(item["detail"])
    if scenario is None and declaration is not None and not declaration.model_tokens:
        return True
    typed = scenario or partial
    if typed is None:
        return True
    # Only the edited relationship changes. Other declarations and provenance
    # remain read-only during validation; copying them per suggestion is costly.
    relationships = dict(typed.relationships)
    if name in relationships:
        relationships[name] = relationships[name].model_copy(deep=True)
    candidate = typed.model_copy(update={"relationships": relationships})
    owner: Any = candidate.relationships.get(name)
    if owner is None:
        return True
    for token in pointer[2:-1]:
        if owner is None:
            return True
        if isinstance(owner, list):
            if not token.isdecimal() or len(token) > 9 or int(token) >= len(owner):
                return True
            owner = owner[int(token)]
        else:
            owner = owner.get(token) if isinstance(owner, Mapping) else getattr(owner, token, None)
    if owner is None:
        return True
    token = pointer[-1]
    if isinstance(owner, list):
        if not token.isdecimal() or len(token) > 9:
            return True
        position = int(token)
        if position == len(owner):
            owner.append(item["label"])
        elif position < len(owner):
            owner[position] = item["label"]
        else:
            return False
    else:
        if not isinstance(owner, Mapping) and not hasattr(owner, token):
            return True
        current = owner.get(token) if isinstance(owner, Mapping) else getattr(owner, token)
        value = [item["label"]] if isinstance(current, list) else item["label"]
        if isinstance(owner, dict):
            owner[token] = value
        else:
            setattr(owner, token, value)
    # Existing subtype owners and participant/control checks remain authoritative.
    # An incomplete context may already contain unrelated failures; do not turn
    # those into new constraints on this field. Known endpoint attributes and
    # selected control bounds are checked independently, even on an invalid edge.
    return _semantic_errors(candidate).issubset(baseline)


def _policy_scope_allowed(
    address: str,
    pointer: list[str],
    relationship: dict[str, Any],
    scenario: ScenarioContent | None,
    resolver: PurposeResolver,
) -> bool:
    field = pointer[-2] if pointer[-1].isdecimal() else pointer[-1]
    detail = relationship.get("participant")
    if field != "scope_refs" or not isinstance(detail, dict) or scenario is None:
        return True
    name = resolve_section_ref(
        detail.get("control_specification_ref"), "behavior_specifications", scenario.behavior_specifications
    )
    control = scenario.behavior_specifications[name].mixed_control if name is not None else None
    if control is None:
        return True
    endpoints = []
    for side in ("source", "target"):
        matches = resolver.resolve(relationship.get(side, ""), ReferencePurpose.PARTICIPANT_ENDPOINT)
        declaration = resolver.index.declaration_for(next(iter(matches))) if len(matches) == 1 else None
        if declaration is None or not declaration.model_tokens:
            return True
        endpoints.append(declaration.model_tokens[1])
    source, target = endpoints
    controlled, controller = (source, target) if detail.get("kind") == "delegation" else (target, source)
    states = participant_relation_controller_states(control, controlled, controller)
    return address in {
        candidate
        for state in states
        for ref in state.scope_refs
        for candidate in resolver.resolve(ref, ReferencePurpose.OPERATING_SCOPE)
    }


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
    kind = relationship.get("type")
    if kind not in RELATIONSHIP_DETAIL_BINDINGS.values():
        implied = {
            bound for detail, bound in RELATIONSHIP_DETAIL_BINDINGS.items() if relationship.get(detail) is not None
        }
        if len(implied) == 1:
            kind = implied.pop()
    if kind == "participant" and peer is not None and peer.kind == "agents" and peer.address == address:
        return False
    if kind == "forest_trusts" and peer is not None:
        return distinct_forest_endpoints(address, peer.address)
    if scenario is None or not declaration.model_tokens:
        return True
    name = declaration.model_tokens[1]
    node = scenario.nodes.get(name)
    if kind in {"domain_controller_for", "joins_domain"} and side == "source":
        return topology_source_allowed(node)
    if kind == "placed_on_carrier":
        if not placement_node_allowed(node, side):
            return False
        if peer is not None and peer.kind == "node" and peer.model_tokens:
            source, target = (name, peer.model_tokens[1]) if side == "source" else (peer.model_tokens[1], name)
            return placement_context_allowed(source, target, scenario)
    return True
