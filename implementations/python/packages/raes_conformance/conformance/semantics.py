"""Semantic-diagnostic dispatch and fixture-case gating."""

from __future__ import annotations

from collections.abc import Callable

from raes_contracts.contracts import ParticipantInformationStateContextResolver
from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.evaluation import EvaluationExecutionState
from raes_contracts.participant_episode import (
    ParticipantEpisodeExecutionState,
    ParticipantEpisodeHistoryEvent,
)
from raes_contracts.workflow import WorkflowExecutionState
from raes_processor.models import ParticipantBehaviorHistoryEvent

from raes_conformance.conformance.diagnostics import (
    _SEMANTIC_INVALID_DIAGNOSTIC_CODE,
    _diagnostic,
    sanitized_failure_message,
)
from raes_conformance.conformance.observability import observability_evidence_conformance_diagnostics
from raes_conformance.conformance.snapshot_semantics import (
    _participant_behavior_history_diagnostics,
    _runtime_snapshot_semantic_diagnostics,
)
from raes_conformance.conformance.validators import _SEMANTIC_CONTEXT_REQUIRED_CONTRACTS, _validate_payload

_SEMANTIC_CONTEXT_REQUIRED_MESSAGES = {
    **dict.fromkeys(
        (
            "participant-control-context-asset-v1",
            "participant-control-context-change-v1",
            "participant-control-context-record-v1",
        ),
        "Full control-context conformance requires trusted version, lifecycle, authority, recipient, cut "
        "and content inputs; fixture validation is structural only",
    ),
    "associated-artifact-manifest-v1": (
        "full associated-artifact conformance requires a concrete parent and bounded byte readers; "
        "the generic fixture runner establishes structural validity only"
    ),
    "external-concept-bindings-v1": (
        "full external-concept binding conformance requires explicit exact RAES subjects and pinned local "
        "scheme snapshots; the generic fixture runner establishes structural validity only"
    ),
    "participant-information-state-record-v1": (
        "full participant information-state conformance requires governed source, occurrence-history, proof, "
        "and decision-surface resolution"
    ),
}


def _state_semantic_diagnostics(
    contract_name: str,
    payload: object,
    state_model: type,
    invalid_message: str,
) -> list[Diagnostic]:
    try:
        state_model.from_payload(payload)
    except (TypeError, ValueError) as exc:
        return [
            _diagnostic(
                _SEMANTIC_INVALID_DIAGNOSTIC_CODE,
                contract_name,
                f"{invalid_message}: {sanitized_failure_message(exc)}",
            )
        ]
    return []


def _event_stream_semantic_diagnostics(
    contract_name: str,
    payload: object,
    event_model: type,
    payload_type_message: str,
    invalid_message: str,
) -> list[Diagnostic]:
    if not isinstance(payload, list):
        return [
            _diagnostic(
                _SEMANTIC_INVALID_DIAGNOSTIC_CODE,
                contract_name,
                payload_type_message,
            )
        ]

    diagnostics: list[Diagnostic] = []
    for index, event in enumerate(payload):
        try:
            event_model.from_payload(event)
        except (TypeError, ValueError) as exc:
            diagnostics.append(
                _diagnostic(
                    _SEMANTIC_INVALID_DIAGNOSTIC_CODE,
                    f"{contract_name}[{index}]",
                    f"{invalid_message}: {sanitized_failure_message(exc)}",
                )
            )
    return diagnostics


def _participant_behavior_stream_diagnostics(contract_name: str, payload: object) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if isinstance(payload, list):
        for index, event in enumerate(payload):
            try:
                ParticipantBehaviorHistoryEvent.from_payload(event)
            except (TypeError, ValueError) as exc:
                diagnostics.append(
                    _diagnostic(
                        _SEMANTIC_INVALID_DIAGNOSTIC_CODE,
                        f"{contract_name}[{index}]",
                        f"participant behavior history event semantics are invalid: {sanitized_failure_message(exc)}",
                    )
                )
    diagnostics.extend(_participant_behavior_history_diagnostics(contract_name, payload))
    return diagnostics


_SEMANTIC_DISPATCH: dict[str, Callable[[str, object], list[Diagnostic]]] = {
    "workflow-result-envelope-v1": lambda name, payload: _state_semantic_diagnostics(
        name, payload, WorkflowExecutionState, "workflow result semantics are invalid"
    ),
    "evaluation-result-envelope-v1": lambda name, payload: _state_semantic_diagnostics(
        name, payload, EvaluationExecutionState, "evaluation result semantics are invalid"
    ),
    "participant-episode-state-envelope-v1": lambda name, payload: _state_semantic_diagnostics(
        name, payload, ParticipantEpisodeExecutionState, "participant episode state semantics are invalid"
    ),
    "participant-episode-history-event-stream-v1": lambda name, payload: _event_stream_semantic_diagnostics(
        name,
        payload,
        ParticipantEpisodeHistoryEvent,
        "participant episode history payload must be a list",
        "participant episode history event semantics are invalid",
    ),
    "participant-behavior-history-event-stream-v1": _participant_behavior_stream_diagnostics,
    "experiment-run-v1": lambda name, payload: list(observability_evidence_conformance_diagnostics(payload)),
    "runtime-snapshot-v1": lambda name, payload: _runtime_snapshot_semantic_diagnostics(payload),
}


def _semantic_diagnostics(
    contract_name: str,
    payload: object,
    *,
    information_state_context_resolver: ParticipantInformationStateContextResolver | None = None,
) -> list[Diagnostic]:
    if contract_name == "runtime-snapshot-v1":
        return _runtime_snapshot_semantic_diagnostics(
            payload,
            information_state_context_resolver=information_state_context_resolver,
        )
    handler = _SEMANTIC_DISPATCH.get(contract_name)
    if handler is None:
        return []
    return handler(contract_name, payload)


def _fixture_case_diagnostics(contract_name: str, payload: object) -> list[Diagnostic]:
    """Schema-gate first; only run semantic analysis on a schema-valid payload.

    Semantic checks (for example ``_runtime_snapshot_semantic_diagnostics``)
    deserialize the payload through its closed-world contract model and assume it
    is already schema-valid. Running them on a schema-invalid fixture would raise
    instead of reporting a diagnostic, so a schema failure short-circuits.
    """

    schema_diagnostics = _validate_payload(contract_name, payload)
    if schema_diagnostics:
        return schema_diagnostics
    if contract_name in _SEMANTIC_CONTEXT_REQUIRED_CONTRACTS:
        return [
            Diagnostic(
                code="conformance.semantic-context-required",
                domain="conformance",
                address="#",
                message=_SEMANTIC_CONTEXT_REQUIRED_MESSAGES.get(
                    contract_name,
                    "Full conformance requires trusted semantic context; fixture validation is structural only",
                ),
                severity=Severity.ERROR,
            )
        ]
    return _semantic_diagnostics(contract_name, payload)
