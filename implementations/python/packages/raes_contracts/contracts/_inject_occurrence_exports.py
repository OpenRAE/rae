"""Inject trigger, occurrence and readback facade exports (ADR-112); claims, never execution."""

from ..versions import (
    INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS,
    INJECT_OCCURRENCE_CORRELATION_SCHEMA_VERSION,
    INJECT_OCCURRENCE_OUTCOME_SCHEMA_VERSION,
    INJECT_OCCURRENCE_SCHEMA_VERSION,
    INJECT_TRIGGER_REQUEST_SCHEMA_VERSION,
)
from .inject_occurrence import (
    InjectEventPlacementModel,
    InjectIndependentPlacementModel,
    InjectOccurrenceModel,
    InjectOrderModel,
    InjectSchedulePlacementModel,
    InjectTargetBindingModel,
    InjectTriggerRequestModel,
    inject_occurrence_digest,
    inject_retry_key,
    inject_trigger_request_digest,
    require_inject_trigger_retry,
    validate_inject_occurrence_claims,
)
from .inject_occurrence_outcome import (
    InjectBindingOutcomeModel,
    InjectOccurrenceCorrelationModel,
    InjectOccurrenceOutcomeModel,
    inject_occurrence_correlation,
    inject_occurrence_effect,
    inject_occurrence_outcome_digest,
    inject_occurrence_reference,
    require_inject_occurrence_invocation,
    validate_inject_occurrence_outcome,
)

__all__ = [
    "INJECT_TRIGGER_REQUEST_SCHEMA_VERSION",
    "INJECT_OCCURRENCE_SCHEMA_VERSION",
    "INJECT_OCCURRENCE_OUTCOME_SCHEMA_VERSION",
    "INJECT_OCCURRENCE_CORRELATION_SCHEMA_VERSION",
    "INJECT_OCCURRENCE_BACKEND_CONTRACT_IDS",
    "InjectBindingOutcomeModel",
    "InjectEventPlacementModel",
    "InjectIndependentPlacementModel",
    "InjectOccurrenceCorrelationModel",
    "InjectOccurrenceModel",
    "InjectOccurrenceOutcomeModel",
    "InjectOrderModel",
    "InjectSchedulePlacementModel",
    "InjectTargetBindingModel",
    "InjectTriggerRequestModel",
    "inject_occurrence_correlation",
    "inject_occurrence_digest",
    "inject_occurrence_effect",
    "inject_occurrence_outcome_digest",
    "inject_occurrence_reference",
    "inject_retry_key",
    "inject_trigger_request_digest",
    "require_inject_occurrence_invocation",
    "require_inject_trigger_retry",
    "validate_inject_occurrence_claims",
    "validate_inject_occurrence_outcome",
]

INJECT_OCCURRENCE_EXPORTS = __all__
