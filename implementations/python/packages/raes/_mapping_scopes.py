"""Classify SDL mappings whose keys are authored identifiers rather than fields."""

from __future__ import annotations

from enum import Enum


class MappingScope(str, Enum):
    """Key interpretation for one mapping node."""

    STRUCTURAL = "structural"
    LITERAL = "literal"
    DATA = "data"


PROFILE_JSON_FIELDS = frozenset({"schema_document", "profile_value"})


HASHMAP_SECTIONS = frozenset(
    {
        "nodes",
        "infrastructure",
        "features",
        "conditions",
        "propositions",
        "assertions",
        "entities",
        "injects",
        "events",
        "scripts",
        "stories",
        "content",
        "generated_artifacts",
        "persistent_volumes",
        "accounts",
        "identity_domains",
        "identity_forests",
        "identity_facades",
        "deployment_tenants",
        "deployment_cells",
        "relationships",
        "agents",
        "action_contracts",
        "observation_boundaries",
        "outcome_interpretation_rules",
        "behavior_specifications",
        "evidence_requirements",
        "time_domains",
        "clocks",
        "time_domain_mappings",
        "time_progression_policies",
        "temporal_constraints",
        "objectives",
        "workflows",
        "variables",
        "variation_points",
    }
)

NESTED_HASHMAP_FIELDS = frozenset(
    {
        "features",
        "conditions",
        "injects",
        "roles",
        "log_options",
        "labels",
        "driver_options",
        "ipam_options",
        "facts",
        "entities",
        "events",
        "steps",
        "extensions",
        "interactive_access",
        "controller_states",
        "transitions",
        "alternatives",
        "members",
        "fixed_positions",
        "tool_affordances",
        "participant_inject_deliveries",
        "owners",
        "dimensions",
    }
)


def normalize_field_key(key: str) -> str:
    """Return the canonical spelling of an SDL structural field key."""
    return key.lower().replace("-", "_")


def is_literal_map_field(
    key: str,
    *,
    value_is_mapping: bool,
    value_is_sequence: bool,
) -> bool:
    """Return whether a structural field's immediate child keys are literal."""
    # Historical declaration names remain literal while the compatibility
    # migrator reads them; this does not make the section canonical SDL.
    if key in HASHMAP_SECTIONS or key == "vulnerabilities":
        return value_is_mapping
    if key in NESTED_HASHMAP_FIELDS:
        return True
    return key == "properties" and value_is_sequence
