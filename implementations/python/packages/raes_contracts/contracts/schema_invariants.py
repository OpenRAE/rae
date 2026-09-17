"""RAES semantic-invariant JSON-schema attach helpers and reported-value constraints."""

from __future__ import annotations

from typing import Any

from pydantic.json_schema import JsonSchemaValue
from raes.observability_plane_semantics import classify_contract_plane

from .base import _RAES_SEMANTIC_INVARIANT_PROFILE_URI

# Shared instance_path for the ASR-515 carrier-embedded
# validation_basis_disclosures invariant inputs. Defined once here and
# re-exported for validation_disclosure.py so both call sites (this module's
# _add_carrier_validation_basis_disclosure_invariant and
# ValidationBasisDisclosureModel.__get_pydantic_json_schema__) share one
# canonical literal rather than each declaring their own copy.
_CARRIER_DISCLOSURES_INSTANCE_PATH = "#/validation_basis_disclosures"


def _add_raes_invariant(
    json_schema: JsonSchemaValue,
    invariant_id: str,
    description: str,
    *,
    validator: str,
    inputs: list[dict[str, str]],
) -> None:
    invariants = json_schema.setdefault("x-raes-invariants", [])
    if isinstance(invariants, list):
        invariants.append(
            {
                "id": invariant_id,
                "description": description,
                "level": "error",
                "validator": validator,
                "inputs": inputs,
            }
        )


def _add_raes_plane(json_schema: JsonSchemaValue, contract_id: str) -> None:
    """Publish the carrier's single SEM-224 observability/evidence plane.

    Plane ownership is sourced from the carrier-oriented classifier so the
    portable ``x-raes-plane`` annotation cannot drift from
    ``raes.observability_plane_semantics`` (ADR-066 / SEM-224).
    """

    json_schema["x-raes-plane"] = classify_contract_plane(contract_id).value


def _schema_contains_raes_invariants(schema_node: object) -> bool:
    if isinstance(schema_node, dict):
        return "x-raes-invariants" in schema_node or any(
            _schema_contains_raes_invariants(value) for value in schema_node.values()
        )
    if isinstance(schema_node, list):
        return any(_schema_contains_raes_invariants(value) for value in schema_node)
    return False


def _attach_raes_semantic_profile(contract_id: str, json_schema: dict[str, Any]) -> None:
    if _schema_contains_raes_invariants(json_schema):
        json_schema["x-raes-semantic-profile"] = {
            "id": "raes-semantic-invariants-v1",
            "uri": _RAES_SEMANTIC_INVARIANT_PROFILE_URI,
            "contract_id": contract_id,
            "keyword": "x-raes-invariants",
            "required": True,
            "entry_schema_contract_id": "raes-semantic-invariants-v1",
            "entry_schema_pointer": "#/$defs/RaesSemanticInvariantEntryModel",
        }


def _attach_experiment_datetime_invariants(contract_id: str, json_schema: dict[str, Any]) -> None:
    invariant_by_contract = {
        "experiment-task-v1": (
            "task-archival-times-rfc3339-valid",
            "Task artifact_refs created_at values must be valid RFC 3339 date-times, including only known "
            "valid UTC leap-second instants.",
            "raes_contracts.contracts.validate_experiment_task_archival_datetimes",
            [{"contract_id": "experiment-task-v1", "instance_path": "#/artifact_refs"}],
        ),
        "experiment-apparatus-context-v1": (
            "apparatus-archival-times-rfc3339-valid",
            "Apparatus declared_at and observed_setup_evidence created_at values must be valid RFC 3339 "
            "date-times, including only known valid UTC leap-second instants.",
            "raes_contracts.contracts.validate_experiment_apparatus_context_archival_datetimes",
            [
                {"contract_id": "experiment-apparatus-context-v1", "instance_path": "#/declared_at"},
                {"contract_id": "experiment-apparatus-context-v1", "instance_path": "#/observed_setup_evidence"},
            ],
        ),
        "experiment-run-v1": (
            "run-archival-times-rfc3339-valid",
            "Run started_at, ended_at, invalidation invalidated_at, and evidence_artifacts created_at values "
            "must be valid RFC 3339 date-times, including only known valid UTC leap-second instants.",
            "raes_contracts.contracts.validate_experiment_run_archival_datetimes",
            [
                {"contract_id": "experiment-run-v1", "instance_path": "#/started_at"},
                {"contract_id": "experiment-run-v1", "instance_path": "#/ended_at"},
                {"contract_id": "experiment-run-v1", "instance_path": "#/invalidation"},
                {"contract_id": "experiment-run-v1", "instance_path": "#/evidence_artifacts"},
            ],
        ),
        "experiment-study-v1": (
            "study-archival-times-rfc3339-valid",
            "Study report_artifacts and export_artifacts created_at values must be valid RFC 3339 date-times, "
            "including only known valid UTC leap-second instants.",
            "raes_contracts.contracts.validate_experiment_study_archival_datetimes",
            [
                {"contract_id": "experiment-study-v1", "instance_path": "#/report_artifacts"},
                {"contract_id": "experiment-study-v1", "instance_path": "#/export_artifacts"},
            ],
        ),
    }
    invariant = invariant_by_contract.get(contract_id)
    if invariant is None:
        return
    invariant_id, description, validator, inputs = invariant
    _add_raes_invariant(
        json_schema,
        invariant_id,
        description,
        validator=validator,
        inputs=inputs,
    )


def _attach_stateful_resource_invariants(contract_id: str, json_schema: dict[str, Any]) -> None:
    if contract_id not in {
        "sdl-authoring-input-v1",
        "materialized-scenario-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
    }:
        return
    input_contract = [{"contract_id": contract_id, "instance_path": "#"}]
    _add_raes_invariant(
        json_schema,
        "stateful-generated-artifact-semantics",
        "Generated artifact output names and paths, consumers, and dependency entries must be unique, and "
        "generated artifact consumers must be read-only. Explicit selections must name declared consumer-selectable "
        "outputs; SSH artifact consumers must select outputs and every consumer-selectable SSH output must be "
        "selected.",
        validator="raes.stateful_resources.GeneratedArtifact._unique_outputs_and_consumers",
        inputs=input_contract,
    )
    _add_raes_invariant(
        json_schema,
        "stateful-persistent-volume-semantics",
        "Persistent volume consumers and dependency entries must be unique and access cardinality must match "
        "the declared portable access mode.",
        validator="raes.stateful_resources.PersistentVolume._unique_consumers",
        inputs=input_contract,
    )
    _add_raes_invariant(
        json_schema,
        "stateful-cross-resource-semantics",
        "Stateful resource consumers and dependencies must resolve unambiguously, use the POSIX v1 path dialect, "
        "and must not collide on a consumer node mount destination.",
        validator="raes._stateful_resource_references.stateful_resource_reference_errors",
        inputs=input_contract,
    )


def _add_carrier_validation_basis_disclosure_invariant(
    json_schema: JsonSchemaValue, *, contract_id: str, subject_kind: str
) -> None:
    """Attach the shared ASR-515 carrier-embedded disclosure identity invariant.

    Reused by ``ExperimentTaskModel``/``ExperimentRunModel``/``ExperimentStudyModel``
    so the wording and validator pointer live in one place; ``subject_kind``
    derives the carrier label the same way
    ``validate_carrier_validation_basis_disclosures`` does.
    """
    carrier_label = subject_kind.removeprefix("experiment_")
    _add_raes_invariant(
        json_schema,
        f"{carrier_label}-validation-basis-disclosure-identity-matches",
        f"Every validation_basis_disclosures entry must declare subject_kind={subject_kind!r} and a subject_ref "
        f"matching this {carrier_label}'s {carrier_label}_id/{carrier_label}_version.",
        validator="raes_contracts.contracts.validation_disclosure.validate_carrier_validation_basis_disclosures",
        inputs=[{"contract_id": contract_id, "instance_path": _CARRIER_DISCLOSURES_INSTANCE_PATH}],
    )


def _attach_initial_service_state_invariants(contract_id: str, json_schema: dict[str, Any]) -> None:
    if contract_id not in {
        "sdl-authoring-input-v1",
        "materialized-scenario-v1",
        "instantiated-scenario-v1",
        "instantiated-scenario-snapshot-v1",
        "scenario-satisfiability-evidence-v1",
    }:
        return
    _add_raes_invariant(
        json_schema,
        "initial-service-state-semantics",
        "Service-target content must resolve to one named service, retain exact tenant/reset ownership and "
        "content ordering, and bind observed-state postconditions to participant observation boundaries.",
        validator="raes.validator.SemanticValidator._verify_service_materialization",
        inputs=[{"contract_id": contract_id, "instance_path": "#"}],
    )


def _validate_reported_value_status(
    value_status: str,
    value: object | None,
    *,
    reported_message: str,
    non_reported_message: str,
) -> None:
    if value_status == "reported" and value is None:
        raise ValueError(reported_message)
    if value_status != "reported" and value is not None:
        raise ValueError(non_reported_message)


def _extend_reported_value_status_schema(json_schema: JsonSchemaValue) -> None:
    json_schema.setdefault("allOf", []).extend(
        [
            {
                "if": {
                    "properties": {"value_status": {"const": "reported"}},
                    "required": ["value_status"],
                },
                "then": {"required": ["value"], "properties": {"value": {"not": {"type": "null"}}}},
            },
            {
                "if": {
                    "properties": {"value_status": {"enum": ["missing", "withheld", "not-applicable"]}},
                    "required": ["value_status"],
                },
                "then": {"properties": {"value": {"type": "null"}}},
            },
        ]
    )


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


_SCHEMA_MAP_KEYS = ("properties", "patternProperties", _DEFS_KEY)


_SCHEMA_SUBSCHEMA_KEYS = (
    "additionalProperties",
    "items",
    "contains",
    "anyOf",
    "allOf",
    "oneOf",
    "prefixItems",
)
