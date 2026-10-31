"""Schema parts and schema transforms that the SDL owns (ADR-121).

``raes_schemas`` composes the published schemas. This module gives the SDL
contract schemas and the transforms that need the SDL catalogs or the SDL
instantiation rules.
"""

from __future__ import annotations

from typing import Any

from raes_contracts.contracts.schema_invariants import SCHEMA_MAP_KEYS, SCHEMA_SUBSCHEMA_KEYS, add_raes_invariant
from raes_contracts.identifiers import portable_property_names_schema, qualified_property_names_schema
from raes_contracts.variable_references import VARIABLE_REFERENCE_SCHEMA_MARKER, VARIABLE_TOKEN_PATTERN

from .artifact_requirement_contract import ArtifactRequirementContractModel
from .canonical import InstantiatedScenarioSnapshot
from .materialization import MaterializedScenario
from .scenario import InstantiatedScenario, Scenario
from .schema_catalogs import HASHMAP_SECTIONS, RUNTIME_SERVICE_FAMILIES, RuntimeReferenceChild
from .semantic_migration_context import SDLSemanticMigrationContext

_DEFS_KEY = "$defs"
_INSTANTIATION_INVARIANT_CONTRACT_ID = "instantiated-scenario-v1"
_INSTANTIATED_SNAPSHOT_CONTRACT_ID = "instantiated-scenario-snapshot-v1"
_SATISFIABILITY_EVIDENCE_CONTRACT_ID = "scenario-satisfiability-evidence-v1"
_SDL_AUTHORING_CONTRACT_ID = "sdl-authoring-input-v1"
_SDL_IDENTIFIER_CONTRACT_IDS = frozenset(
    {
        _SDL_AUTHORING_CONTRACT_ID,
        "materialized-scenario-v1",
        _INSTANTIATION_INVARIANT_CONTRACT_ID,
        _INSTANTIATED_SNAPSHOT_CONTRACT_ID,
    }
)


def sdl_contract_schemas() -> dict[str, dict[str, Any]]:
    """Return the raw schemas of the SDL contracts, with their SDL invariant annotations."""

    schemas = {
        "sdl-authoring-input-v1": Scenario.model_json_schema(),
        "sdl-semantic-migration-context-v1": SDLSemanticMigrationContext.model_json_schema(),
        "instantiated-scenario-v1": InstantiatedScenario.model_json_schema(),
        "materialized-scenario-v1": MaterializedScenario.model_json_schema(),
        "instantiated-scenario-snapshot-v1": InstantiatedScenarioSnapshot.model_json_schema(),
        "artifact-requirement-v1": ArtifactRequirementContractModel.model_json_schema(),
    }
    add_raes_invariant(
        schemas["sdl-authoring-input-v1"],
        "required-evidence-media-type-provable",
        "Every declared required evidence media type must have a registered content-proof path; an explicit "
        "output_contract must support every declared type.",
        validator="raes_contracts.evidence_requirements.EvidenceRequirement._validate_capture_intent",
        inputs=[{"contract_id": "sdl-authoring-input-v1", "instance_path": "#/evidence_requirements"}],
    )
    return schemas


def attach_sdl_identifier_constraints(contract_id: str, schema: dict[str, Any]) -> None:
    """Constrain the SDL mapping keys and runtime identifiers of the SDL scenario schemas."""

    if contract_id in _SDL_IDENTIFIER_CONTRACT_IDS:
        _attach_scenario_identifier_constraints(contract_id, schema)


def _resolve_local_ref(schema: dict[str, Any], node: object) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        resolved = schema.get(_DEFS_KEY, {}).get(ref.removeprefix("#/$defs/"))
        return resolved if isinstance(resolved, dict) else None
    return node


def _collection_item_schema(
    schema: dict[str, Any], owner: dict[str, Any], collection_name: str
) -> dict[str, Any] | None:
    collection = owner.get("properties", {}).get(collection_name)
    collection = _resolve_local_ref(schema, collection)
    if not isinstance(collection, dict):
        return None
    items = collection.get("items")
    return _resolve_local_ref(schema, items)


def _constrain_runtime_children(
    schema: dict[str, Any],
    owner: dict[str, Any],
    children: tuple[RuntimeReferenceChild, ...],
) -> None:
    for child in children:
        child_schema = _collection_item_schema(schema, owner, child.collection_name)
        if child_schema is None:
            continue
        child_schema.setdefault("properties", {})[child.id_field] = portable_property_names_schema()
        _constrain_runtime_children(schema, child_schema, child.children)


def _attach_runtime_identifier_constraints(schema: dict[str, Any]) -> None:
    runtime = schema.get(_DEFS_KEY, {}).get("RuntimeConfiguration")
    if not isinstance(runtime, dict):
        return
    for family in RUNTIME_SERVICE_FAMILIES:
        item_schema = _collection_item_schema(schema, runtime, family.collection_name)
        if item_schema is None:
            continue
        if family.collection_name != "forwarding_agents":
            item_schema.setdefault("properties", {})[family.id_field] = portable_property_names_schema()
        _constrain_runtime_children(schema, item_schema, family.child_refs)


def _constrain_collection_item_field(
    owner: dict[str, Any],
    collection_name: str,
    field_name: str,
    field_schema: dict[str, Any],
) -> None:
    collection = owner.get("properties", {}).get(collection_name)
    if not isinstance(collection, dict):
        return
    items = collection.get("items")
    if not isinstance(items, dict):
        return
    collection["items"] = {
        "allOf": [
            items,
            {"properties": {field_name: field_schema}, "type": "object"},
        ]
    }


def _scenario_schema_for_identifier_constraints(
    contract_id: str,
    schema: dict[str, Any],
) -> dict[str, Any] | None:
    if contract_id != _INSTANTIATED_SNAPSHOT_CONTRACT_ID:
        return schema
    nested = schema.get(_DEFS_KEY, {}).get("InstantiatedScenario")
    return nested if isinstance(nested, dict) else None


def _attach_scenario_identifier_constraints(contract_id: str, schema: dict[str, Any]) -> None:
    scenario_schema = _scenario_schema_for_identifier_constraints(contract_id, schema)
    if scenario_schema is None:
        return
    qualified = contract_id != _SDL_AUTHORING_CONTRACT_ID
    for section_name in HASHMAP_SECTIONS:
        section = scenario_schema.get("properties", {}).get(section_name)
        if not isinstance(section, dict):
            continue
        local_maximum = 35 if section_name == "nodes" else 64
        section["propertyNames"] = (
            qualified_property_names_schema(local_maximum=local_maximum)
            if qualified
            else portable_property_names_schema(maximum=local_maximum)
        )
    _attach_runtime_identifier_constraints(schema)
    binding = schema.get(_DEFS_KEY, {}).get("MaterializedResourceBinding")
    if isinstance(binding, dict):
        properties = binding["properties"]
        properties["node_name"] = qualified_property_names_schema()
        properties["source_node"] = {"anyOf": [qualified_property_names_schema(), {"type": "null"}], "default": None}
    forwarding_id_schema = qualified_property_names_schema() if qualified else portable_property_names_schema()
    _constrain_collection_item_field(
        scenario_schema,
        "forwarding_agents",
        "forwarding_agent_id",
        forwarding_id_schema,
    )
    runtime = schema.get(_DEFS_KEY, {}).get("RuntimeConfiguration")
    if isinstance(runtime, dict):
        _constrain_collection_item_field(
            runtime,
            "forwarding_agents",
            "forwarding_agent_id",
            portable_property_names_schema(),
        )


def _apply_string_token_constraint(node: dict[str, Any]) -> None:
    """Forbid the ``${name}`` token on a single free string subschema.

    Targets scalar ``"type": "string"`` only, skipping fixed ``enum`` / ``const``
    values, which avoids the nullable-string and fixed-value pitfalls. The
    ``${var}`` branch of every ``*_or_var`` field (``InfraNode.count``,
    ``ACLRule.ports``, ``SimpleProperties.internal`` …) is a bare
    ``{"type": "string"}`` branch, so it is covered.
    """
    if node.get("type") != "string" or "enum" in node or "const" in node:
        return
    constraint = {"pattern": VARIABLE_TOKEN_PATTERN}
    if "not" in node:
        node.setdefault("allOf", []).append({"not": constraint})
    else:
        node["not"] = constraint


def _child_subschemas(node: dict[str, Any]) -> list[Any]:
    """Return the applicator subschemas reachable from ``node``.

    Mapping keys are not substitution sites, so ``propertyNames`` is
    intentionally excluded.
    """
    children: list[Any] = []
    for key in SCHEMA_MAP_KEYS:
        child = node.get(key)
        if isinstance(child, dict):
            children.extend(child.values())
    for key in SCHEMA_SUBSCHEMA_KEYS:
        if key in node:
            children.append(node[key])
    return children


def _forbid_variable_tokens_in_strings(node: object) -> None:
    """Remove variable-only alternatives and forbid tokens in remaining strings."""
    if isinstance(node, list):
        for item in node:
            _forbid_variable_tokens_in_strings(item)
        return
    if not isinstance(node, dict):
        return
    _remove_variable_reference_union_branches(node)
    _apply_string_token_constraint(node)
    for child in _child_subschemas(node):
        _forbid_variable_tokens_in_strings(child)


def _remove_variable_reference_union_branches(node: dict[str, Any]) -> None:
    """Collapse authoring unions to their concrete branches for phase artifacts."""
    for keyword in ("anyOf", "oneOf"):
        branches = node.get(keyword)
        if not isinstance(branches, list):
            continue
        retained = [
            branch
            for branch in branches
            if not (isinstance(branch, dict) and branch.get(VARIABLE_REFERENCE_SCHEMA_MARKER) is True)
        ]
        if len(retained) == len(branches):
            continue
        node.pop(keyword)
        if len(retained) == 1 and isinstance(retained[0], dict):
            outer_keywords = dict(node)
            node.clear()
            node.update(retained[0])
            node.update(outer_keywords)
        else:
            node[keyword] = retained or [{"not": {}}]


def attach_instantiation_invariants(contract_id: str, json_schema: dict[str, Any]) -> None:
    """Apply the no-substitution-token invariant to concrete SDL artifacts.

    An instantiated scenario is fully concrete, so its payload and canonical
    snapshot forbid unresolved ``${var}`` tokens in string values. The matching
    model-level invariant lives on ``InstantiatedScenario``.
    """
    if contract_id not in {
        _INSTANTIATION_INVARIANT_CONTRACT_ID,
        "materialized-scenario-v1",
        _INSTANTIATED_SNAPSHOT_CONTRACT_ID,
        _SATISFIABILITY_EVIDENCE_CONTRACT_ID,
    }:
        return
    _forbid_variable_tokens_in_strings(json_schema)


def attach_stateful_resource_invariants(contract_id: str, json_schema: dict[str, Any]) -> None:
    if contract_id not in {
        "sdl-authoring-input-v1",
        "materialized-scenario-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
    }:
        return
    input_contract = [{"contract_id": contract_id, "instance_path": "#"}]
    add_raes_invariant(
        json_schema,
        "stateful-generated-artifact-semantics",
        "Generated artifact output names and paths, consumers, and dependency entries must be unique, and "
        "generated artifact consumers must be read-only. Explicit selections must name declared consumer-selectable "
        "outputs; SSH artifact consumers must select outputs and every consumer-selectable SSH output must be "
        "selected.",
        validator="raes.stateful_resources.GeneratedArtifact._unique_outputs_and_consumers",
        inputs=input_contract,
    )
    add_raes_invariant(
        json_schema,
        "stateful-persistent-volume-semantics",
        "Persistent volume consumers and dependency entries must be unique and access cardinality must match "
        "the declared portable access mode.",
        validator="raes.stateful_resources.PersistentVolume._unique_consumers",
        inputs=input_contract,
    )
    add_raes_invariant(
        json_schema,
        "stateful-cross-resource-semantics",
        "Stateful resource consumers and dependencies must resolve unambiguously, use the POSIX v1 path dialect, "
        "and must not collide on a consumer node mount destination.",
        validator="raes._stateful_resource_references.stateful_resource_reference_errors",
        inputs=input_contract,
    )


def attach_initial_service_state_invariants(contract_id: str, json_schema: dict[str, Any]) -> None:
    if contract_id not in {
        "sdl-authoring-input-v1",
        "materialized-scenario-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
        "scenario-satisfiability-evidence-v1",
    }:
        return
    add_raes_invariant(
        json_schema,
        "initial-service-state-semantics",
        "Service-target content must resolve to one named service, retain exact tenant/reset ownership and "
        "content ordering, and bind observed-state postconditions to participant observation boundaries.",
        validator="raes.validator.SemanticValidator._verify_service_materialization",
        inputs=[{"contract_id": contract_id, "instance_path": "#"}],
    )


def attach_sdl_participant_temporal_invariants(contract_id: str, json_schema: dict[str, Any]) -> None:
    """Publish the shared-time source-binding invariant of the SDL scenario schemas."""

    if contract_id in _SDL_IDENTIFIER_CONTRACT_IDS:
        add_raes_invariant(
            json_schema,
            "participant-shared-time-source-bindings",
            (
                "Explicit temporal bindings must resolve the action's shared clock, constraint and selected event. "
                "Dwell conditions require authorized observation boundaries and observable support and evidence. "
                "Numeric parameters are revalidated after binding."
            ),
            validator="raes.semantics.participant_temporal_bindings.participant_temporal_binding_errors",
            inputs=[{"contract_id": contract_id, "instance_path": "#"}],
        )


__all__ = [
    "attach_initial_service_state_invariants",
    "attach_instantiation_invariants",
    "attach_sdl_identifier_constraints",
    "attach_sdl_participant_temporal_invariants",
    "attach_stateful_resource_invariants",
    "sdl_contract_schemas",
]
