"""Pure policy evaluation for run-local runtime fact bindings."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from raes_contracts.contracts.runtime_facts import (
    RuntimeFactAbsenceDisposition,
    RuntimeFactAudience,
    RuntimeFactBindingDisposition,
    RuntimeFactBindingRequestModel,
    RuntimeFactDeclarationModel,
    RuntimeFactSensitivity,
    RuntimeFactSinkModel,
    RuntimeFactSourceKind,
    RuntimeFactVersionModel,
)

from .runtime_fact_dispatch import RuntimeFactBindingAdmission, _parse_datetime


class RuntimeFactActionDisposition(str, Enum):
    """Aggregate action-dispatch outcome across all compiled sinks."""

    BOUND = "bound"
    BLOCKED = "blocked"
    FAILED = "failed"
    INAPPLICABLE = "inapplicable"


def candidate_visible(
    request: RuntimeFactBindingRequestModel,
    sink: RuntimeFactSinkModel,
    declaration: RuntimeFactDeclarationModel,
    version: RuntimeFactVersionModel,
) -> bool:
    """Return whether a candidate is in scope and visible to the sink audience."""

    scope_visible = all(
        (
            version.scope.run_id == request.run_id,
            version.scope.participant_address in {None, request.participant_address},
            version.scope.episode_id in {None, request.episode_id},
            version.scope.workflow_address in {None, request.workflow_address},
        )
    )
    if sink.audience is RuntimeFactAudience.WORKFLOW:
        audience_visible = request.workflow_address in declaration.visibility.workflow_addresses
    else:
        audience_visible = request.participant_address in declaration.visibility.participant_addresses
    return scope_visible and audience_visible


def projection_visible(
    *,
    run_id: str,
    participant_address: str | None,
    episode_id: str | None,
    workflow_address: str | None,
    declaration: RuntimeFactDeclarationModel,
    version: RuntimeFactVersionModel,
) -> bool:
    """Return whether an immutable fact version belongs in a requested projection."""

    visible = version.scope.run_id == run_id
    if participant_address is not None:
        visible = visible and all(
            (
                participant_address in declaration.visibility.participant_addresses,
                version.scope.participant_address in {None, participant_address},
                version.scope.episode_id in {None, episode_id},
            )
        )
    elif workflow_address is not None:
        visible = visible and all(
            (
                workflow_address in declaration.visibility.workflow_addresses,
                version.scope.workflow_address in {None, workflow_address},
            )
        )
    return visible


def validate_binding(
    admission: RuntimeFactBindingAdmission,
    sink: RuntimeFactSinkModel,
    declaration: RuntimeFactDeclarationModel,
    version: RuntimeFactVersionModel,
    supported_source_kinds: frozenset[RuntimeFactSourceKind],
) -> RuntimeFactBindingDisposition:
    """Evaluate a visible candidate against compiled and trusted sink policy."""

    required_authority = set(declaration.authority_refs) | set(sink.authority_refs)
    checks = (
        (version.source_kind in supported_source_kinds, RuntimeFactBindingDisposition.UNSUPPORTED),
        (version.value_type == sink.value_type, RuntimeFactBindingDisposition.WRONG_TYPE),
        (version.source_kind in sink.allowed_source_kinds, RuntimeFactBindingDisposition.UNSUPPORTED),
        (version.scope.kind in sink.allowed_scope_kinds, RuntimeFactBindingDisposition.WRONG_SCOPE),
        (version.sensitivity in sink.allowed_sensitivities, RuntimeFactBindingDisposition.UNAUTHORIZED),
        (
            sink.audience is RuntimeFactAudience.PROTECTED_SINK
            or version.sensitivity is not RuntimeFactSensitivity.SECRET,
            RuntimeFactBindingDisposition.UNAUTHORIZED,
        ),
        (required_authority.issubset(admission.authority_refs), RuntimeFactBindingDisposition.UNAUTHORIZED),
    )
    disposition = next((failure for passed, failure in checks if not passed), RuntimeFactBindingDisposition.BOUND)
    if disposition is RuntimeFactBindingDisposition.BOUND:
        disposition = _validate_freshness(admission, sink, version)
    return disposition


def _validate_freshness(
    admission: RuntimeFactBindingAdmission,
    sink: RuntimeFactSinkModel,
    version: RuntimeFactVersionModel,
) -> RuntimeFactBindingDisposition:
    requested_at = _parse_datetime(admission.requested_at, "requested_at")
    observed_at = _parse_datetime(version.observed_at, "observed_at")
    within_max_age = sink.max_age_seconds is None or (
        observed_at <= requested_at and (requested_at - observed_at).total_seconds() <= sink.max_age_seconds
    )
    unexpired = version.expires_at is None or requested_at <= _parse_datetime(version.expires_at, "expires_at")
    if within_max_age and unexpired:
        disposition = RuntimeFactBindingDisposition.BOUND
    else:
        disposition = RuntimeFactBindingDisposition.STALE
    return disposition


def absence_action_disposition(disposition: RuntimeFactAbsenceDisposition) -> RuntimeFactActionDisposition:
    """Map a compiled absence policy to its aggregate action outcome."""

    return {
        RuntimeFactAbsenceDisposition.BLOCK: RuntimeFactActionDisposition.BLOCKED,
        RuntimeFactAbsenceDisposition.FAIL: RuntimeFactActionDisposition.FAILED,
        RuntimeFactAbsenceDisposition.INAPPLICABLE: RuntimeFactActionDisposition.INAPPLICABLE,
    }[disposition]


def aggregate_action_disposition(failures: list[RuntimeFactActionDisposition]) -> RuntimeFactActionDisposition:
    """Resolve aggregate action outcome using deterministic failure precedence."""

    precedence = (
        RuntimeFactActionDisposition.FAILED,
        RuntimeFactActionDisposition.BLOCKED,
        RuntimeFactActionDisposition.INAPPLICABLE,
    )
    return next(
        (disposition for disposition in precedence if disposition in failures), RuntimeFactActionDisposition.BOUND
    )


def parse_datetime(value: str, field_name: str = "timestamp") -> datetime:
    """Parse an offset-qualified timestamp for comparison; reject naive values with ``ValueError``."""

    return _parse_datetime(value, field_name)
