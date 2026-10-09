"""Inject trigger and occurrence facade exports (ADR-112); claims, never execution."""

from ..versions import INJECT_OCCURRENCE_SCHEMA_VERSION, INJECT_TRIGGER_REQUEST_SCHEMA_VERSION
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

__all__ = [
    "INJECT_TRIGGER_REQUEST_SCHEMA_VERSION",
    "INJECT_OCCURRENCE_SCHEMA_VERSION",
    "InjectEventPlacementModel",
    "InjectIndependentPlacementModel",
    "InjectOccurrenceModel",
    "InjectOrderModel",
    "InjectSchedulePlacementModel",
    "InjectTargetBindingModel",
    "InjectTriggerRequestModel",
    "inject_occurrence_digest",
    "inject_retry_key",
    "inject_trigger_request_digest",
    "require_inject_trigger_retry",
    "validate_inject_occurrence_claims",
]

INJECT_OCCURRENCE_EXPORTS = __all__
