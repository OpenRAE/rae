"""Resource-governance integration for participant scheduler actions."""

from typing import Protocol

from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceMeasurementModel,
    ParticipantResourceMeasurementRequirementModel,
    participant_resource_budget_state_ref,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest, ParticipantActionApplyResult
from raes_contracts.runtime_state import ApplyResult

from .participant_resource_accounting import (
    commit_participant_resource_reservation,
    release_participant_resource_reservation,
)
from .participant_resource_budgets import (
    reserve_participant_resources,
)
from .participant_resource_rejection import (
    is_participant_resource_rejection,
    resource_exhausted_pre_dispatch_result,
)
from .participant_scheduler_types import SchedulerRunState, _DueActionContext

_RESOURCE_GOVERNED_PROFILE = "participant-autonomous-execution/v3"


class _MeasurementDemand(Protocol):
    budget_id: str
    resource_kind: str
    unit: str
    meter_profile_ref: str
    reservation: int


class _MeasurementPolicy(Protocol):
    address: str
    profile: str
    resource_demands: tuple[_MeasurementDemand, ...]


def measurement_requirements(
    policy: _MeasurementPolicy,
) -> tuple[ParticipantResourceMeasurementRequirementModel, ...]:
    if policy.profile != _RESOURCE_GOVERNED_PROFILE:
        return ()
    return tuple(
        ParticipantResourceMeasurementRequirementModel(
            budget_state_ref=participant_resource_budget_state_ref(policy.address, demand.budget_id),
            resource_kind=demand.resource_kind,
            unit=demand.unit,
            meter_profile_ref=demand.meter_profile_ref,
            reserved=demand.reservation,
        )
        for demand in policy.resource_demands
    )


def _record_resource_failure(run: SchedulerRunState) -> None:
    run.failure = ApplyResult(
        success=False,
        snapshot=run.working,
        diagnostics=run.diagnostics,
        changed_addresses=list(dict.fromkeys(run.changed)),
    )


def reserve_activity_resources(
    context: _DueActionContext,
    request: ParticipantActionAdmissionRequest,
    run: SchedulerRunState,
    *,
    episode_id: str,
) -> tuple[bool, ParticipantActionApplyResult | None]:
    """Reserve the complete v3 resource vector before native execution.

    A logical-budget rejection (SEM-223 T10) is not a runtime failure: it is
    returned as an undispatched SEM-211 ``resource_exhausted`` attempt that the
    ordinary failure policy then settles (T11). Throttling and accounting
    errors still fail the scheduler pass.
    """

    if context.policy.profile != _RESOURCE_GOVERNED_PROFILE:
        return True, None
    reservation = reserve_participant_resources(
        run.working,
        context.policy,
        operation_id=request.action_instance_id,
        execution_generation=request.execution_generation,
    )
    run.working = reservation.snapshot
    if is_participant_resource_rejection(reservation):
        rejection = resource_exhausted_pre_dispatch_result(
            request,
            run.working,
            episode_id=episode_id,
            diagnostics=reservation.diagnostics,
        )
        return False, rejection
    run.diagnostics.extend(reservation.diagnostics)
    if not reservation.success:
        _record_resource_failure(run)
    return reservation.success, None


def _trusted_measurements(
    request: ParticipantActionAdmissionRequest,
    result: ParticipantActionApplyResult,
    protocol_failure: bool,
) -> dict[str, ParticipantResourceMeasurementModel] | None:
    action_result = result.action_result
    requirements = {item.budget_state_ref: item for item in request.resource_measurement_requirements}
    measurements = {
        item.budget_state_ref: item for item in (() if action_result is None else action_result.resource_measurements)
    }
    trusted = (
        not protocol_failure
        and request.execution_generation is not None
        and set(measurements) == set(requirements)
        and all(
            measurement.operation_id == request.action_instance_id
            and measurement.execution_generation == request.execution_generation
            and measurement.resource_kind == requirements[state_ref].resource_kind
            and measurement.unit == requirements[state_ref].unit
            and measurement.meter_profile_ref == requirements[state_ref].meter_profile_ref
            for state_ref, measurement in measurements.items()
        )
    )
    return measurements if trusted else None


def _release_untrusted_measurements(
    context: _DueActionContext,
    request: ParticipantActionAdmissionRequest,
    protocol_failure: bool,
    run: SchedulerRunState,
) -> bool:
    released = release_participant_resource_reservation(
        run.working,
        operation_id=request.action_instance_id,
        execution_generation=request.execution_generation or 0,
        evidence_refs=(f"evidence:{request.action_instance_id}:resource-release",),
    )
    run.working = released.snapshot
    run.diagnostics.extend(released.diagnostics)
    if not protocol_failure:
        run.diagnostics.append(
            Diagnostic(
                code="runtime.participant-resource-measurement-untrusted",
                domain="participant-runtime",
                address=context.policy.address,
                message="native action did not return the exact trusted resource measurement vector",
            )
        )
    _record_resource_failure(run)
    return False


def _commit_trusted_measurements(
    request: ParticipantActionAdmissionRequest,
    measurements: dict[str, ParticipantResourceMeasurementModel],
    run: SchedulerRunState,
) -> bool:
    evidence_refs = tuple(
        dict.fromkeys(
            evidence_ref for measurement in measurements.values() for evidence_ref in measurement.evidence_refs
        )
    )
    committed = commit_participant_resource_reservation(
        run.working,
        operation_id=request.action_instance_id,
        execution_generation=request.execution_generation,
        measured_quantities={state_ref: measurement.measured for state_ref, measurement in measurements.items()},
        evidence_refs=evidence_refs,
    )
    run.working = committed.snapshot
    run.diagnostics.extend(committed.diagnostics)
    if not committed.success:
        _record_resource_failure(run)
    return committed.success


def commit_activity_resources(
    context: _DueActionContext,
    request: ParticipantActionAdmissionRequest,
    result: ParticipantActionApplyResult,
    *,
    protocol_failure: bool,
    run: SchedulerRunState,
) -> bool:
    """Commit only a complete, trusted native measurement vector."""

    if context.policy.profile != _RESOURCE_GOVERNED_PROFILE:
        return True
    measurements = _trusted_measurements(request, result, protocol_failure)
    if measurements is None:
        return _release_untrusted_measurements(context, request, protocol_failure, run)
    return _commit_trusted_measurements(request, measurements, run)


__all__ = [
    "commit_activity_resources",
    "measurement_requirements",
    "reserve_activity_resources",
]
