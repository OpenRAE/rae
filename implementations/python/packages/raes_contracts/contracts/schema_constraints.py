"""Contract JSON-schema constraint helpers and the RAES semantic-invariant profile models.

The SDL schema transforms are in ``raes.schema_contributions``, and the schema
composition with its validator-locator checks is in ``raes_schemas`` (ADR-121).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import Field

from ..addressing import COMPILED_ADDRESS_JSON_SCHEMA
from ..concept_binding_scopes import (
    BACKEND_CONCEPT_BINDING_SCOPES,
    PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES,
    PROCESSOR_CONCEPT_BINDING_SCOPES,
)
from ..identifiers import portable_property_names_schema
from ..planning import PLAN_ADDRESS_ROOT_BY_DOMAIN, PLAN_RESOURCE_TYPES_BY_DOMAIN, RuntimeDomain
from .base import (
    _RAES_SEMANTIC_INVARIANT_PROFILE_URI,
    ContractModel,
    JsonInstancePathString,
    NonEmptyString,
)
from .schema_invariants import _DEFS_KEY


def attach_instantiation_request_identifier_constraints(contract_id: str, schema: dict[str, Any]) -> None:
    """Constrain instantiation-request parameter names to portable identifiers."""

    if contract_id != "scenario-instantiation-request-v1":
        return
    parameters = schema.get("properties", {}).get("parameters")
    if isinstance(parameters, dict):
        parameters["propertyNames"] = portable_property_names_schema()


def _schema_id_for_contract_id(contract_id: str) -> str:
    if contract_id == "raes-semantic-invariants-v1":
        return _RAES_SEMANTIC_INVARIANT_PROFILE_URI
    return f"https://openrae.github.io/rae/schemas/{contract_id}.json"


def attach_json_schema_metadata(contract_id: str, json_schema: dict[str, Any]) -> None:
    json_schema.setdefault("$schema", _JSON_SCHEMA_DRAFT_2020_12)
    json_schema.setdefault("$id", _schema_id_for_contract_id(contract_id))


def attach_compiled_address_map_constraints(contract_id: str, json_schema: dict[str, Any]) -> None:
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


def attach_plan_identity_constraints(contract_id: str, json_schema: dict[str, Any]) -> None:
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
    "processing": PROCESSOR_CONCEPT_BINDING_SCOPES,
    "execution": BACKEND_CONCEPT_BINDING_SCOPES | PARTICIPANT_IMPLEMENTATION_CONCEPT_BINDING_SCOPES,
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


def raes_semantic_invariant_profile_schema() -> dict[str, Any]:
    json_schema = RaesSemanticInvariantProfileModel.model_json_schema()
    json_schema.setdefault(_DEFS_KEY, {})["RaesSemanticInvariantProfileReferenceModel"] = (
        RaesSemanticInvariantProfileReferenceModel.model_json_schema()
    )
    return json_schema
