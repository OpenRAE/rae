"""Context-required conformance adapter for participant control-context assets."""

from raes_contracts.contracts.participant_control_context import (
    ParticipantControlContextAssetModel,
    ParticipantControlContextChangeModel,
    ParticipantControlContextRecordModel,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_control_context import (
    ParticipantControlContextValidationContext,
    validate_control_context_asset,
    validate_control_context_change,
    validate_control_context_record,
)

from .diagnostics import _diagnostic


def _control_context_asset_diagnostics(
    contract_name: str,
    payload: object,
    context: ParticipantControlContextValidationContext | None,
) -> list[Diagnostic]:
    if context is None or (contract_name == "participant-control-context-asset-v1" and context.content_binding is None):
        return [
            _diagnostic(
                "conformance.semantic-context-required", contract_name, "Trusted control-context inputs are required"
            )
        ]
    try:
        if contract_name == "participant-control-context-record-v1":
            diagnostics = validate_control_context_record(
                ParticipantControlContextRecordModel.model_validate(payload), context
            )
        elif contract_name == "participant-control-context-change-v1":
            diagnostics = validate_control_context_change(
                ParticipantControlContextChangeModel.model_validate(payload), context
            )
        else:
            binding = context.content_binding
            diagnostics = validate_control_context_asset(
                ParticipantControlContextAssetModel.model_validate(payload),
                context=context,
                manifest=binding.manifest,
                parent=binding.parent,
                artifact_readers=binding.artifact_readers,
                limits=binding.limits,
            )
        return list(diagnostics)
    except Exception:  # noqa: BLE001 -- public diagnostics must not expose resolver or private-content exceptions.
        return [
            _diagnostic("conformance.context-resolution-failed", contract_name, "Control-context validation failed")
        ]
