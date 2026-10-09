"""Published inject trigger/occurrence schemas and their semantic validation bindings."""

from __future__ import annotations

from typing import Any

from .inject_occurrence import InjectOccurrenceModel, InjectTriggerRequestModel
from .schema_invariants import _add_raes_invariant

_REQUEST = {"contract_id": "inject-trigger-request-v1", "instance_path": "#"}
_OCCURRENCE = {"contract_id": "inject-occurrence-v1", "instance_path": "#"}
_LOCAL = (
    (
        _REQUEST,
        InjectTriggerRequestModel,
        "inject-trigger-request-local-consistency",
        "Validate compiled inject, node, event, script and story address families, the pinned orchestration plan, "
        "binding addresses rendered exactly from their node and the requested inject, and unique binding/instance "
        "pairs; structural validity grants no trigger authority and does not resolve bindings against the plan.",
    ),
    (
        _OCCURRENCE,
        InjectOccurrenceModel,
        "inject-occurrence-local-consistency",
        "Validate the embedded request, an orchestration admission context for its target and run, an order token "
        "whose scope is that run and whose predecessor is the requested head, and distinct request key, occurrence, "
        "operation and slot identities; structural validity grants no trigger authority.",
    ),
)


def inject_occurrence_schema_bundle() -> dict[str, dict[str, Any]]:
    schemas = {}
    for inputs, model, invariant_id, description in _LOCAL:
        schema = model.model_json_schema()
        _add_raes_invariant(
            schema,
            invariant_id,
            description,
            validator=f"raes_contracts.contracts.{model.__name__}.model_validate",
            inputs=[inputs],
        )
        schemas[inputs["contract_id"]] = schema
    _add_raes_invariant(
        schemas["inject-trigger-request-v1"],
        "inject-trigger-exact-retry",
        "Only the original actor, key and request commitment retrieve the original claim; changed content conflicts "
        "and no retry admits, rebases or dispatches again.",
        validator="raes_contracts.contracts.require_inject_trigger_retry",
        inputs=[_OCCURRENCE, _REQUEST],
    )
    _add_raes_invariant(
        schemas["inject-occurrence-v1"],
        "inject-occurrence-unique-claims",
        "Retry keys, occurrences, operations, schedule slots, order positions and order predecessors are each claimed "
        "at most once in one target/run store, so no two claims follow the same head; head tokens are opaque, so the "
        "head chain itself is not checked.",
        validator="raes_contracts.contracts.validate_inject_occurrence_claims",
        inputs=[_OCCURRENCE],
    )
    return schemas
