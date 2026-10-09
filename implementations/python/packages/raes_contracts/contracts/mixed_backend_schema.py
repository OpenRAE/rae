"""Published mixed-backend schemas and their mandatory semantic validation bindings."""

from __future__ import annotations

from typing import Any

from .mixed_backend_binding import MixedBackendExecutionBindingModel
from .mixed_backend_stages import MixedBackendStageReportModel
from .schema_invariants import _add_raes_invariant

_BINDING = "mixed-backend-execution-binding-v1"
_STAGE_REPORT = "mixed-backend-stage-report-v1"
_MODELS = {_BINDING: MixedBackendExecutionBindingModel, _STAGE_REPORT: MixedBackendStageReportModel}
_STRUCTURAL_LIMIT = "structural validity does not prove backend truth, installation or runtime authority."
_LOCAL_CONSISTENCY = {
    _BINDING: "Validate closed bounded fields, unique collections, a preserved compiled subject, distinct handoff "
    "components and a distinct pinned service for each role, so no two roles share a service reference or digest; "
    + _STRUCTURAL_LIMIT,
    _STAGE_REPORT: "Validate closed bounded fields, unique collections and honest stage evidence; " + _STRUCTURAL_LIMIT,
}


def _inputs(*contract_ids: str) -> list[dict[str, str]]:
    return [{"contract_id": contract_id, "instance_path": "#"} for contract_id in contract_ids]


def mixed_backend_schema_bundle() -> dict[str, dict[str, Any]]:
    schemas = {}
    for contract_id, model in _MODELS.items():
        schema = model.model_json_schema()
        _add_raes_invariant(
            schema,
            "mixed-backend-local-consistency",
            _LOCAL_CONSISTENCY[contract_id],
            validator=f"raes_contracts.contracts.{model.__name__}.model_validate",
            inputs=_inputs(contract_id),
        )
        schemas[contract_id] = schema
    _add_raes_invariant(
        schemas[_BINDING],
        "mixed-backend-binding-profile-join",
        "Require exactly one matching binding per active edge and one-to-one component-changing transition of the "
        "admitted sealed profile, with governed order, preserved compiled subjects, declared loss and the edge's "
        "admitted temporal coupling.",
        validator="raes_contracts.contracts.validate_mixed_backend_bindings",
        inputs=_inputs("mixed-participant-composition-profile-v1", _BINDING),
    )
    _add_raes_invariant(
        schemas[_BINDING],
        "mixed-backend-contextual-admission",
        "Before invocation require the shared request to commit to this binding, its operation kind and its "
        "installed bridge or transfer service, then installed support and current exact-context willingness.",
        validator="raes_contracts.contracts.require_mixed_backend_admission",
        inputs=_inputs(
            _BINDING,
            "backend-operation-request-v1",
            "backend-operation-capabilities-v1",
            "backend-operation-response-v1",
        ),
    )
    _add_raes_invariant(
        schemas[_STAGE_REPORT],
        "mixed-backend-stage-transcript",
        "Require exact invocation binding and commitment, a trusted time model resolved under the binding's "
        "time-model reference and digest, prerequisite stage order, the pinned producer for each stage, grant "
        "coordinates equal to the committed time readback, a committed composition state that still activates "
        "the edge or holds the handoff's source component without its destination, a handoff fenced on that "
        "state's head and phase revision, an ordered grant and accepted start before invocation stages, success "
        "or failure outcomes equal to the state the stages and trusted readbacks establish, and shared evidence "
        "that cites only supplied stage reports.",
        validator="raes_contracts.contracts.validate_mixed_backend_stage_reports",
        inputs=[
            *_inputs(
                _BINDING,
                "backend-operation-request-v1",
                "backend-operation-response-v1",
                _STAGE_REPORT,
                "time-model-v1",
                "time-runtime-state-v1",
            ),
            {"contract_id": "runtime-snapshot-v1", "instance_path": "#/mixed_composition_states"},
        ],
    )
    return schemas
