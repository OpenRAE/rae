"""Compose the published contract schemas from the schema parts of each owner (ADR-121).

Each owner gives its raw schemas and its transforms through public functions:
``raes_contracts`` for the neutral contracts, ``raes`` for the SDL contracts and
``raes_processor`` for the analysis evidence. This module is the only place
that combines them. It applies the transforms in a fixed order, checks every
validator locator, and keeps one cached template.
"""

from __future__ import annotations

import importlib
import importlib.util
from copy import deepcopy
from functools import cache
from typing import Any

from raes.schema_contributions import (
    attach_initial_service_state_invariants,
    attach_instantiation_invariants,
    attach_sdl_identifier_constraints,
    attach_sdl_participant_temporal_invariants,
    attach_stateful_resource_invariants,
    sdl_contract_schemas,
)
from raes_contracts.contracts.materialization_attestation import attach_materialization_invariants
from raes_contracts.contracts.schema_constraints import (
    RaesSemanticInvariantEntryModel,
    RaesSemanticInvariantProfileReferenceModel,
    attach_compiled_address_map_constraints,
    attach_instantiation_request_identifier_constraints,
    attach_json_schema_metadata,
    attach_plan_identity_constraints,
)
from raes_contracts.contracts.schema_factoring import factor_shared_schema
from raes_contracts.contracts.schema_invariants import (
    attach_experiment_datetime_invariants,
    attach_participant_temporal_invariants,
    attach_raes_semantic_profile,
)
from raes_contracts.schema_contributions import contract_schemas
from raes_processor.schema_contributions import processor_contract_schemas


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
        except ModuleNotFoundError, ValueError:
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
def _schema_bundle_template() -> dict[str, dict[str, Any]]:  # NOSONAR
    """Build the immutable-in-practice template used by :func:`schema_bundle`."""

    bundle = {**contract_schemas(), **sdl_contract_schemas(), **processor_contract_schemas()}
    for contract_id, json_schema in bundle.items():
        attach_materialization_invariants(contract_id, json_schema)
        attach_instantiation_request_identifier_constraints(contract_id, json_schema)
        attach_sdl_identifier_constraints(contract_id, json_schema)
        attach_instantiation_invariants(contract_id, json_schema)
        attach_experiment_datetime_invariants(contract_id, json_schema)
        attach_stateful_resource_invariants(contract_id, json_schema)
        attach_initial_service_state_invariants(contract_id, json_schema)
        attach_sdl_participant_temporal_invariants(contract_id, json_schema)
        attach_participant_temporal_invariants(contract_id, json_schema)
        attach_json_schema_metadata(contract_id, json_schema)
        attach_compiled_address_map_constraints(contract_id, json_schema)
        attach_plan_identity_constraints(contract_id, json_schema)
        attach_raes_semantic_profile(contract_id, json_schema)
    known_contract_ids = frozenset(bundle)
    for contract_id, json_schema in bundle.items():
        _validate_raes_semantic_invariant_annotations(
            contract_id=contract_id,
            json_schema=json_schema,
            known_contract_ids=known_contract_ids,
        )
    bundle["materialized-scenario-v1"] = factor_shared_schema(bundle["materialized-scenario-v1"])
    return bundle


def schema_bundle() -> dict[str, dict[str, Any]]:
    """Return an isolated copy of the repo-published external contract schemas.

    Generating the complete bundle is expensive because it traverses every
    Pydantic contract model and attaches the governed RAES annotations.  The
    generated template is process-stable, so build it once while preserving the
    public function's historical fresh-dictionary semantics for callers.
    """

    return deepcopy(_schema_bundle_template())


def validate_raes_semantic_invariant_annotations(contract_id: str, json_schema: dict[str, Any]) -> None:
    """Validate RAES semantic-invariant metadata on a published JSON Schema."""

    _validate_raes_semantic_invariant_annotations(
        contract_id=contract_id,
        json_schema=json_schema,
        known_contract_ids=frozenset(_schema_bundle_template()),
    )


__all__ = ["schema_bundle", "validate_raes_semantic_invariant_annotations"]
