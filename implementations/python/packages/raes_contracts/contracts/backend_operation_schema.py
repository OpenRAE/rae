"""Published operation schemas and their mandatory semantic validation bindings."""

from __future__ import annotations

from typing import Any

from .backend_operation import (
    BackendOperationCapabilitiesModel,
    BackendOperationControlModel,
    BackendOperationRequestModel,
)
from .backend_operation_response import BackendOperationResponseModel
from .schema_invariants import _add_raes_invariant


def backend_operation_schema_bundle() -> dict[str, dict[str, Any]]:
    models = {
        "backend-operation-request-v1": BackendOperationRequestModel,
        "backend-operation-capabilities-v1": BackendOperationCapabilitiesModel,
        "backend-operation-control-v1": BackendOperationControlModel,
        "backend-operation-response-v1": BackendOperationResponseModel,
    }
    schemas = {}
    for contract_id, model in models.items():
        schema = model.model_json_schema()
        _add_raes_invariant(
            schema,
            "backend-operation-local-consistency",
            "Validate unique collections, calendar instants, budget bounds, scope and honest effect/outcome claims; "
            "structural validity does not prove backend truth or runtime authority.",
            validator=f"raes_contracts.contracts.{model.__name__}.model_validate",
            inputs=[{"contract_id": contract_id, "instance_path": "#"}],
        )
        schemas[contract_id] = schema
    _add_raes_invariant(
        schemas["backend-operation-response-v1"],
        "backend-operation-response-binding",
        "Require exact request binding and commitment, scoped residuals and independently bound controls when present.",
        validator="raes_contracts.contracts.validate_backend_operation_response",
        inputs=[
            {"contract_id": "backend-operation-request-v1", "instance_path": "#"},
            {"contract_id": "backend-operation-response-v1", "instance_path": "#"},
        ],
    )
    _add_raes_invariant(
        schemas["backend-operation-capabilities-v1"],
        "backend-operation-contextual-admission",
        "Before invocation require installed support, matching declaration and current exact-context willingness.",
        validator="raes_contracts.contracts.require_backend_operation_admission",
        inputs=[
            {"contract_id": "backend-operation-request-v1", "instance_path": "#"},
            {"contract_id": "backend-operation-capabilities-v1", "instance_path": "#"},
            {"contract_id": "backend-operation-response-v1", "instance_path": "#"},
        ],
    )
    return schemas
