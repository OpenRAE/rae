"""Published inject trigger/occurrence schemas and their semantic validation bindings."""

from __future__ import annotations

from typing import Any

from .inject_occurrence import InjectOccurrenceModel, InjectTriggerRequestModel
from .schema_invariants import _add_raes_invariant

_REQUEST = {"contract_id": "inject-trigger-request-v1", "instance_path": "#"}
_OCCURRENCE = {"contract_id": "inject-occurrence-v1", "instance_path": "#"}


def inject_occurrence_schema_bundle() -> dict[str, dict[str, Any]]:
    schemas = {}
    for inputs, model in ((_REQUEST, InjectTriggerRequestModel), (_OCCURRENCE, InjectOccurrenceModel)):
        schema = model.model_json_schema()
        _add_raes_invariant(
            schema,
            "inject-occurrence-local-consistency",
            "Validate compiled address families, bindings of the requested inject, unique selected instances, the "
            "orchestration admission context, unrebased order and distinct claim identities; structural validity "
            "grants no trigger authority.",
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
        "Retry keys, occurrences, operations, schedule slots and order positions are each claimed at most once "
        "in one target/run store.",
        validator="raes_contracts.contracts.validate_inject_occurrence_claims",
        inputs=[_OCCURRENCE],
    )
    return schemas
