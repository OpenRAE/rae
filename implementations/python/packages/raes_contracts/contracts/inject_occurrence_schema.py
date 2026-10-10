"""Published inject trigger, occurrence and readback schemas and their semantic validation bindings."""

from __future__ import annotations

from typing import Any

from .inject_occurrence import InjectOccurrenceModel, InjectTriggerRequestModel
from .inject_occurrence_outcome import InjectOccurrenceCorrelationModel, InjectOccurrenceOutcomeModel
from .schema_invariants import _add_raes_invariant

_REQUEST = {"contract_id": "inject-trigger-request-v1", "instance_path": "#"}
_OCCURRENCE = {"contract_id": "inject-occurrence-v1", "instance_path": "#"}
_OUTCOME = {"contract_id": "inject-occurrence-outcome-v1", "instance_path": "#"}
_CORRELATION = {"contract_id": "inject-occurrence-correlation-v1", "instance_path": "#"}
_INVOCATION = {"contract_id": "backend-operation-request-v1", "instance_path": "#"}
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
    (
        _OUTCOME,
        InjectOccurrenceOutcomeModel,
        "inject-occurrence-outcome-local-consistency",
        "Validate per-binding readback bases, the fan-out effect aggregate and settlement by a start refusal with "
        "proven absence or a backend outcome; structural validity proves no effect, delivery or observation.",
    ),
    (
        _CORRELATION,
        InjectOccurrenceCorrelationModel,
        "inject-occurrence-correlation-local-consistency",
        "Validate that the correlation joins an inject occurrence and an outcome of that same occurrence; structural "
        "validity proves no effect, delivery or observation.",
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
    _add_raes_invariant(
        schemas["inject-occurrence-outcome-v1"],
        "inject-occurrence-outcome-binding",
        "Readback answers one backend invocation that commands the exact claimed occurrence under its operation and "
        "admission context, carries its evidence requirements and keeps attempt identities distinct from the claims. "
        "It reports every selected binding in request order, and binding residual effects stay inside an admitted "
        "resource scope. This grants no dispatch; an adopting runtime still validates and commits the terminal state.",
        validator="raes_contracts.contracts.validate_inject_occurrence_outcome",
        inputs=[_OCCURRENCE, _INVOCATION, _OUTCOME],
    )
    _add_raes_invariant(
        schemas["inject-occurrence-correlation-v1"],
        "inject-occurrence-correlation-source",
        "A received correlation equals the join recomputed from its occurrence, invocation and validated outcome; "
        "only a successful applied world effect with a produced result yields one.",
        validator="raes_contracts.contracts.validate_inject_occurrence_correlation",
        inputs=[_OCCURRENCE, _INVOCATION, _OUTCOME, _CORRELATION],
    )
    return schemas
