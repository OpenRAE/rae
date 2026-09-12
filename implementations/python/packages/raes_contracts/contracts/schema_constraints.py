"""JSON-schema identifier/plan constraint helpers and RAES semantic-invariant models."""

from __future__ import annotations

import importlib
from copy import deepcopy
from functools import cache
from typing import Any, Literal

from pydantic import Field
from raes import VARIABLE_TOKEN_PATTERN
from raes.identifiers import PORTABLE_IDENTIFIER_JSON_SCHEMA, QUALIFIED_IDENTIFIER_MAX_LENGTH
from raes.schema_catalogs import (
    HASHMAP_SECTIONS,
    RUNTIME_SERVICE_FAMILIES,
    RuntimeReferenceChild,
)
from raes.value_parsing import VARIABLE_REFERENCE_SCHEMA_MARKER

from ..addressing import COMPILED_ADDRESS_JSON_SCHEMA
from ..planning import PLAN_ADDRESS_ROOT_BY_DOMAIN, PLAN_RESOURCE_TYPES_BY_DOMAIN, RuntimeDomain
from .base import (
    _BACKEND_CONCEPT_BINDING_SCOPES,
    _PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES,
    _PROCESSOR_CONCEPT_BINDING_SCOPES,
    _RAES_SEMANTIC_INVARIANT_PROFILE_URI,
    ContractModel,
    JsonInstancePathString,
    NonEmptyString,
)
from .schema_invariants import (
    _DEFS_KEY,
    _INSTANTIATED_SNAPSHOT_CONTRACT_ID,
    _INSTANTIATION_INVARIANT_CONTRACT_ID,
    _SATISFIABILITY_EVIDENCE_CONTRACT_ID,
    _SCHEMA_MAP_KEYS,
    _SCHEMA_SUBSCHEMA_KEYS,
    _SDL_AUTHORING_CONTRACT_ID,
    _SDL_IDENTIFIER_CONTRACT_IDS,
)


def _portable_property_names(*, maximum: int = 64) -> dict[str, Any]:
    schema = deepcopy(PORTABLE_IDENTIFIER_JSON_SCHEMA)
    schema["maxLength"] = maximum
    return schema


def _qualified_property_names(*, local_maximum: int = 64) -> dict[str, Any]:
    local_tail = local_maximum - 1
    segment = r"(?:[a-z0-9][a-z0-9_-]{0,63}|__private)"
    return {
        "type": "string",
        "minLength": 1,
        "maxLength": QUALIFIED_IDENTIFIER_MAX_LENGTH,
        "pattern": rf"^(?:{segment}\.)*[a-z0-9][a-z0-9_-]{{0,{local_tail}}}$",
        "not": {"pattern": "[^a-z0-9_.-]"},
    }


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
        child_schema.setdefault("properties", {})[child.id_field] = _portable_property_names()
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
            item_schema.setdefault("properties", {})[family.id_field] = _portable_property_names()
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


def _attach_instantiation_request_identifier_constraints(schema: dict[str, Any]) -> None:
    parameters = schema.get("properties", {}).get("parameters")
    if isinstance(parameters, dict):
        parameters["propertyNames"] = _portable_property_names()


def _attach_sdl_identifier_constraints(contract_id: str, schema: dict[str, Any]) -> None:
    if contract_id == "scenario-instantiation-request-v1":
        _attach_instantiation_request_identifier_constraints(schema)
    elif contract_id in _SDL_IDENTIFIER_CONTRACT_IDS:
        _attach_scenario_identifier_constraints(contract_id, schema)


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
            _qualified_property_names(local_maximum=local_maximum)
            if qualified
            else _portable_property_names(maximum=local_maximum)
        )
    _attach_runtime_identifier_constraints(schema)
    forwarding_id_schema = _qualified_property_names() if qualified else _portable_property_names()
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
            _portable_property_names(),
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
    for key in _SCHEMA_MAP_KEYS:
        child = node.get(key)
        if isinstance(child, dict):
            children.extend(child.values())
    for key in _SCHEMA_SUBSCHEMA_KEYS:
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


def _attach_instantiation_invariants(contract_id: str, json_schema: dict[str, Any]) -> None:
    """Apply the no-substitution-token invariant to concrete SDL artifacts.

    An instantiated scenario is fully concrete, so its payload and canonical
    snapshot forbid unresolved ``${var}`` tokens in string values. The matching
    model-level invariant lives on ``InstantiatedScenario``.
    """
    if contract_id not in {
        _INSTANTIATION_INVARIANT_CONTRACT_ID,
        _INSTANTIATED_SNAPSHOT_CONTRACT_ID,
        _SATISFIABILITY_EVIDENCE_CONTRACT_ID,
    }:
        return
    _forbid_variable_tokens_in_strings(json_schema)


def _schema_id_for_contract_id(contract_id: str) -> str:
    if contract_id == "raes-semantic-invariants-v1":
        return _RAES_SEMANTIC_INVARIANT_PROFILE_URI
    return f"https://openrae.github.io/rae/schemas/{contract_id}.json"


def _attach_json_schema_metadata(contract_id: str, json_schema: dict[str, Any]) -> None:
    json_schema.setdefault("$schema", _JSON_SCHEMA_DRAFT_2020_12)
    json_schema.setdefault("$id", _schema_id_for_contract_id(contract_id))


def _attach_compiled_address_map_constraints(contract_id: str, json_schema: dict[str, Any]) -> None:
    if contract_id != "runtime-snapshot-v1":
        return
    entries = json_schema.get("properties", {}).get("entries")
    if not isinstance(entries, dict):
        return
    entries["propertyNames"] = deepcopy(COMPILED_ADDRESS_JSON_SCHEMA)
    entries["additionalProperties"] = False


_PLAN_CONTRACT_DOMAIN = {
    "backend-realization-preparation-v1": RuntimeDomain.PROVISIONING,
    "provisioning-plan-v1": RuntimeDomain.PROVISIONING,
    "orchestration-plan-v1": RuntimeDomain.ORCHESTRATION,
    "evaluation-plan-v1": RuntimeDomain.EVALUATION,
}


def _attach_plan_identity_constraints(contract_id: str, json_schema: dict[str, Any]) -> None:
    domain = _PLAN_CONTRACT_DOMAIN.get(contract_id)
    if domain is None:
        return
    model_name = (
        "PreparationOperationModel" if contract_id == "backend-realization-preparation-v1" else "PlanOperationModel"
    )
    operation = json_schema.get(_DEFS_KEY, {}).get(model_name)
    if not isinstance(operation, dict):
        return
    properties = operation.get("properties", {})
    if domain is not RuntimeDomain.PROVISIONING and "profile_bindings" in properties:
        properties["profile_bindings"]["maxItems"] = 0
    address = properties.get("address")
    resource_type = properties.get("resource_type")
    if isinstance(address, dict):
        address.setdefault("allOf", []).append({"pattern": rf"^{PLAN_ADDRESS_ROOT_BY_DOMAIN[domain]}\."})
    if isinstance(resource_type, dict):
        resource_type["enum"] = sorted(PLAN_RESOURCE_TYPES_BY_DOMAIN[domain])


_SEMANTIC_PROFILE_PHASE_ALLOWED_BINDING_SCOPES = {
    "authoring": frozenset(),
    "exchange": frozenset(),
    "processing": _PROCESSOR_CONCEPT_BINDING_SCOPES,
    "execution": _BACKEND_CONCEPT_BINDING_SCOPES | _PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES,
}


_JSON_SCHEMA_KEY = "$schema"


_JSON_SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


_RAES_SEMANTIC_INVARIANTS_SCHEMA_VERSION = "raes-semantic-invariants/v1"


class RaesSemanticInvariantInputModel(ContractModel):
    """Input contract and instance path required by one RAES semantic invariant."""

    contract_id: NonEmptyString
    instance_path: JsonInstancePathString


class RaesSemanticInvariantEntryModel(ContractModel):
    """Machine-readable semantic invariant annotation entry."""

    id: NonEmptyString
    description: NonEmptyString
    level: Literal["error"]
    validator: NonEmptyString
    inputs: list[RaesSemanticInvariantInputModel] = Field(min_length=1)


class RaesSemanticInvariantProfileModel(ContractModel):
    """Published shape for RAES semantic-invariant annotations."""

    schema_version: Literal[_RAES_SEMANTIC_INVARIANTS_SCHEMA_VERSION]
    profile_id: Literal["raes-semantic-invariants-v1"]
    uri: Literal["https://openrae.github.io/rae/schemas/semantic-invariants/v1"]
    keyword: Literal["x-raes-invariants"]
    invariant_entry_schema: Literal["#/$defs/RaesSemanticInvariantEntryModel"]
    profile_reference_schema: Literal["#/$defs/RaesSemanticInvariantProfileReferenceModel"]
    invariants: list[RaesSemanticInvariantEntryModel]


class RaesSemanticInvariantProfileReferenceModel(ContractModel):
    """Host-schema reference to the RAES semantic-invariant profile."""

    id: Literal["raes-semantic-invariants-v1"]
    uri: Literal["https://openrae.github.io/rae/schemas/semantic-invariants/v1"]
    contract_id: NonEmptyString
    keyword: Literal["x-raes-invariants"]
    required: Literal[True]
    entry_schema_contract_id: Literal["raes-semantic-invariants-v1"]
    entry_schema_pointer: Literal["#/$defs/RaesSemanticInvariantEntryModel"]


def _raes_semantic_invariant_profile_schema_for_bundle() -> dict[str, Any]:
    json_schema = RaesSemanticInvariantProfileModel.model_json_schema()
    json_schema.setdefault(_DEFS_KEY, {})["RaesSemanticInvariantProfileReferenceModel"] = (
        RaesSemanticInvariantProfileReferenceModel.model_json_schema()
    )
    return json_schema


def _iter_raes_semantic_invariant_entries(schema_node: object) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if isinstance(schema_node, dict):
        invariants = schema_node.get("x-raes-invariants")
        if invariants is not None:
            if not isinstance(invariants, list):
                raise ValueError("x-raes-invariants must be an array")
            entries.extend(invariants)
        for value in schema_node.values():
            entries.extend(_iter_raes_semantic_invariant_entries(value))
    elif isinstance(schema_node, list):
        for value in schema_node:
            entries.extend(_iter_raes_semantic_invariant_entries(value))
    return entries


def _resolve_semantic_validator(validator: str) -> object:
    parts = validator.split(".")
    for index in range(len(parts), 0, -1):
        module_name = ".".join(parts[:index])
        try:
            module_spec = importlib.util.find_spec(module_name)
        except (ModuleNotFoundError, ValueError):
            continue
        if module_spec is None:
            continue
        target: object = importlib.import_module(module_name)
        try:
            for attr in parts[index:]:
                target = getattr(target, attr)
        except AttributeError as exc:
            raise ValueError(
                f"semantic invariant validator '{validator}' does not resolve to an importable object"
            ) from exc
        return target
    raise ValueError(f"semantic invariant validator '{validator}' does not resolve to an importable object")


def _validate_raes_semantic_invariant_annotations(
    *,
    contract_id: str,
    json_schema: dict[str, Any],
    known_contract_ids: frozenset[str],
) -> None:
    invariant_entries = _iter_raes_semantic_invariant_entries(json_schema)
    profile_payload = json_schema.get("x-raes-semantic-profile")
    if not invariant_entries:
        if profile_payload is not None:
            raise ValueError(f"schema '{contract_id}' declares a semantic profile without semantic invariants")
        return

    profile = RaesSemanticInvariantProfileReferenceModel.model_validate(profile_payload)
    if profile.contract_id != contract_id:
        raise ValueError(f"schema '{contract_id}' semantic profile contract_id must match the published contract id")

    seen_invariant_ids: set[str] = set()
    for invariant_payload in invariant_entries:
        invariant = RaesSemanticInvariantEntryModel.model_validate(invariant_payload)
        if not callable(_resolve_semantic_validator(invariant.validator)):
            raise ValueError(f"semantic invariant validator '{invariant.validator}' must resolve to a callable")
        if invariant.id in seen_invariant_ids:
            raise ValueError(f"schema '{contract_id}' has duplicate semantic invariant id '{invariant.id}'")
        seen_invariant_ids.add(invariant.id)
        for invariant_input in invariant.inputs:
            if invariant_input.contract_id not in known_contract_ids:
                raise ValueError(
                    f"semantic invariant '{invariant.id}' references unknown input contract "
                    f"'{invariant_input.contract_id}'"
                )


@cache
def _published_contract_ids() -> frozenset[str]:
    from .bundle import _schema_bundle_template

    return frozenset(_schema_bundle_template())


def validate_raes_semantic_invariant_annotations(contract_id: str, json_schema: dict[str, Any]) -> None:
    """Validate RAES semantic-invariant metadata on a published JSON Schema."""

    _validate_raes_semantic_invariant_annotations(
        contract_id=contract_id,
        json_schema=json_schema,
        known_contract_ids=_published_contract_ids(),
    )
