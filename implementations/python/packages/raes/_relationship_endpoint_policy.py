"""Endpoint decisions for every relationship type and typed detail field.

Part of the reference-eligibility policy in :mod:`raes._reference_targetability`.
Each relationship type and typed detail field has one explicit decision: the
endpoint purposes it requires of ``source`` and ``target``, a binding to the
type whose rule it shares, or none. Where several rules apply to one endpoint,
the endpoint must satisfy all of them.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from ._base import normalize_enum_value
from ._reference_targetability import ReferencePurpose

_P = ReferencePurpose
_ORDER: Mapping[ReferencePurpose, int] = {purpose: position for position, purpose in enumerate(ReferencePurpose)}

# Endpoint purposes per relationship type and typed detail field, as (source, target).
# None leaves that side on the generic relationship-endpoint purpose.
_GENERIC: tuple[ReferencePurpose | None, ReferencePurpose | None] = (None, None)
RELATIONSHIP_TYPE_ENDPOINTS: Mapping[str, tuple[ReferencePurpose | None, ReferencePurpose | None]] = {
    **dict.fromkeys(
        ("authenticates_with", "trusts", "federates_with", "connects_to", "depends_on", "manages", "replicates_to"),
        _GENERIC,
    ),
    "domain_controller_for": (_P.NODE_ENDPOINT, _P.IDENTITY_DOMAIN_ENDPOINT),
    "joins_domain": (_P.NODE_ENDPOINT, _P.IDENTITY_DOMAIN_ENDPOINT),
    "forest_trusts": (_P.IDENTITY_FOREST_ENDPOINT, _P.IDENTITY_FOREST_ENDPOINT),
    "directory_federates_to": (_P.IDENTITY_AUTHORITY_ENDPOINT, _P.IDENTITY_FACADE_ENDPOINT),
    "placed_on_carrier": (_P.NODE_ENDPOINT, _P.NODE_ENDPOINT),
    "uses_shared_service": (_P.DEPLOYMENT_TENANT_ENDPOINT, _P.NODE_SERVICE_ENDPOINT),
    "participant": (_P.PARTICIPANT_ENDPOINT, _P.PARTICIPANT_ENDPOINT),
}
# Details that the semantic modules pair with one type select that type's rule.
RELATIONSHIP_DETAIL_BINDINGS: Mapping[str, str] = {
    "domain_controller": "domain_controller_for",
    "domain_join": "joins_domain",
    "forest_trust": "forest_trusts",
    "identity_federation": "directory_federates_to",
    "carrier_placement": "placed_on_carrier",
    "shared_service": "uses_shared_service",
    "participant": "participant",
}
# Details checked independently of the type carry their own rule, or none.
RELATIONSHIP_DETAIL_ENDPOINTS: Mapping[str, tuple[ReferencePurpose | None, ReferencePurpose | None]] = {
    "database_access": (_P.RUNTIME_APPLICATION_ENDPOINT, _P.DATABASE_ENDPOINT),
    "mail_access": (None, _P.MAIL_SERVICE_ENDPOINT),
    "forwarding_edge": _GENERIC,
    "service_integration": _GENERIC,
    "proxy_upstream": _GENERIC,
}
RELATIONSHIP_EDGE_FIELDS = frozenset({"type", "source", "target", "description", "properties"})


def _relationship_fields(relationship: object) -> Mapping[str, object]:
    """Return an authored relationship's fields, refusing a model field or type value without a decision."""

    if isinstance(relationship, Mapping):
        return relationship
    names = tuple(getattr(type(relationship), "model_fields", ()))
    decided = RELATIONSHIP_EDGE_FIELDS | RELATIONSHIP_DETAIL_BINDINGS.keys() | RELATIONSHIP_DETAIL_ENDPOINTS.keys()
    undecided = [name for name in names if name not in decided]
    relationship_type = getattr(relationship, "type", None)
    if isinstance(relationship_type, Enum):
        types = (member.value for member in type(relationship_type))
        undecided.extend(f"type {value}" for value in types if value not in RELATIONSHIP_TYPE_ENDPOINTS)
    if undecided:
        raise RuntimeError(f"relationship {', '.join(undecided)} has no explicit endpoint-eligibility decision")
    return {name: getattr(relationship, name) for name in names}


def relationship_endpoint_purposes(relationship: object, side: str) -> tuple[ReferencePurpose, ...]:
    """Return every endpoint purpose that a relationship's type and typed details require of *side*.

    Works on a ``Relationship`` model or a raw mapping from a document that does not
    validate yet. A detail counts when its key holds a non-null value, and a detail
    bound to a type selects that type's rule. The result is canonical, so one set of
    rules gives one tuple whichever fields carry them; without a rule it is the
    generic relationship-endpoint purpose.
    """

    position = ("source", "target").index(side)
    fields = _relationship_fields(relationship)
    raw_type = fields.get("type")
    type_name = normalize_enum_value(raw_type.value if isinstance(raw_type, Enum) else raw_type)
    rules = [RELATIONSHIP_TYPE_ENDPOINTS.get(type_name, _GENERIC)] if isinstance(type_name, str) else []
    for name, value in fields.items():
        if value is None or name in RELATIONSHIP_EDGE_FIELDS:
            continue
        bound = RELATIONSHIP_DETAIL_BINDINGS.get(name)
        rules.append(RELATIONSHIP_TYPE_ENDPOINTS[bound] if bound else RELATIONSHIP_DETAIL_ENDPOINTS.get(name, _GENERIC))
    purposes = {rule[position] for rule in rules} - {None}
    return tuple(sorted(purposes, key=_ORDER.__getitem__)) or (_P.RELATIONSHIP_ENDPOINT,)


__all__ = [
    "RELATIONSHIP_DETAIL_BINDINGS",
    "RELATIONSHIP_DETAIL_ENDPOINTS",
    "RELATIONSHIP_EDGE_FIELDS",
    "RELATIONSHIP_TYPE_ENDPOINTS",
    "relationship_endpoint_purposes",
]
