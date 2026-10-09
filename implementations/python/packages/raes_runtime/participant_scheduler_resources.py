"""Resource-governance integration for participant scheduler actions."""

from typing import Protocol

from raes_contracts.contracts.participant_resource_budgets import (
    ParticipantResourceMeasurementModel,
    ParticipantResourceMeasurementRequirementModel,
    participant_resource_budget_state_ref,
)
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest, ParticipantActionApplyResult
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .participant_resource_accounting import (
    commit_participant_resource_reservation,
    release_participant_resource_reservation,
)
from .participant_resource_budgets import (
    reserve_participant_resources,
)
from .participant_resource_rejection import (
    disclosed_rejection_quota,
    is_participant_resource_rejection,
    resource_exhausted_pre_dispatch_result,
)
from .participant_resource_scenario_time import (
    is_scenario_time,
    scenario_time_measurements,
    scenario_time_quantities,
)
from .participant_scheduler_types import SchedulerRunState, _DueActionContext

_RESOURCE_GOVERNED_PROFILE = "participant-autonomous-execution/v3"


class _MeasurementDemand(Protocol):
    budget_id: str
    resource_kind: str
    unit: str
    meter_profile_ref: str
    reservation: int
    reset: str
    action_contract_addresses: tuple[str, ...]


class _MeasurementPolicy(Protocol):
    address: str
    profile: str
    clock_address: str
    resource_demands: tuple[_MeasurementDemand, ...]


def action_resource_quantities(policy: _MeasurementPolicy, action_contract_address: str) -> dict[str, int]:
    """Return what one action reserves; a tool-scoped dimension reserves nothing outside its tools (DSL-121)."""

    return {
        demand.budget_id: (
            demand.reservation
            if not demand.action_contract_addresses or action_contract_address in demand.action_contract_addresses
            else 0
        )
        for demand in policy.resource_demands
    }


def measurement_requirements(
    policy: _MeasurementPolicy,
    action_contract_address: str,
) -> tuple[ParticipantResourceMeasurementRequirementModel, ...]:
    """Return the vector the native backend must measure; RAES meters scenario time itself."""

    if policy.profile != _RESOURCE_GOVERNED_PROFILE:
        return ()
    quantities = action_resource_quantities(policy, action_contract_address)
    return tuple(
        ParticipantResourceMeasurementRequirementModel(
            budget_state_ref=participant_resource_budget_state_ref(policy.address, demand.budget_id),
            resource_kind=demand.resource_kind,
            unit=demand.unit,
            meter_profile_ref=demand.meter_profile_ref,
            reserved=quantities[demand.budget_id],
        )
        for demand in policy.resource_demands
        if not is_scenario_time(demand)
    )


def _requested_quantities(
    policy: _MeasurementPolicy,
    action_contract_address: str,
    snapshot: RuntimeSnapshot,
) -> dict[str, int]:
    quantities = action_resource_quantities(policy, action_contract_address)
    for budget_id, elapsed in scenario_time_quantities(policy, snapshot).items():
        quantities[budget_id] += elapsed
    return quantities


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
        requested_quantities=_requested_quantities(context.policy, request.action_contract_address, run.working),
    )
    run.working = reservation.snapshot
    if is_participant_resource_rejection(reservation):
        rejection = resource_exhausted_pre_dispatch_result(
            request,
            run.working,
            episode_id=episode_id,
            diagnostics=reservation.diagnostics,
            disclosed_quota=disclosed_rejection_quota(context.policy, request.action_instance_id, run.working),
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
    context: _DueActionContext,
    request: ParticipantActionAdmissionRequest,
    measurements: dict[str, ParticipantResourceMeasurementModel],
    run: SchedulerRunState,
) -> bool:
    elapsed, clock_evidence = scenario_time_measurements(context.policy, request.action_instance_id, run.working)
    evidence_refs = tuple(
        dict.fromkeys(
            (
                *(evidence_ref for measurement in measurements.values() for evidence_ref in measurement.evidence_refs),
                *clock_evidence,
            )
        )
    )
    committed = commit_participant_resource_reservation(
        run.working,
        operation_id=request.action_instance_id,
        execution_generation=request.execution_generation,
        measured_quantities={
            **{state_ref: measurement.measured for state_ref, measurement in measurements.items()},
            **elapsed,
        },
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
    return _commit_trusted_measurements(context, request, measurements, run)


__all__ = [
    "action_resource_quantities",
    "commit_activity_resources",
    "measurement_requirements",
    "reserve_activity_resources",
]
