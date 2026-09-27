"""Exact executable mapping, time grant, bridge call, and stage readback."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import partial

from raes_contracts.contracts.time_model import TimeRuntimeStateModel, validate_time_runtime_state
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot

from .mixed_runtime_edge import (
    MixedBridgeExecutionEvidence,
    MixedDeliveryReadback,
    MixedEdgeExecutionBinding,
    MixedEdgeExecutionCapture,
    MixedObservationReadback,
    MixedTimeCoordinationEvidence,
)


def _mapped_edge_method(
    binding: object,
    edge: object,
    installed: MixedEdgeExecutionBinding,
    provider_method: Callable[..., object],
    operation_id: str,
    capture: MixedEdgeExecutionCapture,
) -> Callable[..., object]:
    """Execute one admitted edge after its decision and attempt are durable."""

    declaration = binding.context.time_models[edge.time_binding.time_model_ref]
    mapping = declaration.mappings[edge.time_binding.mapping_address]
    source_clock = declaration.clocks[edge.time_binding.source_clock_address]
    destination_clock = declaration.clocks[edge.time_binding.target_clock_address]
    if (
        mapping.source_domain_address != source_clock.time_domain_address
        or mapping.target_domain_address != destination_clock.time_domain_address
    ):
        raise ValueError("executable edge clock domains differ from admission")

    return partial(
        _invoke_mapped_edge,
        installed=installed,
        edge=edge,
        declaration=declaration,
        mapping=mapping,
        provider_method=provider_method,
        operation_id=operation_id,
        capture=capture,
    )


@dataclass
class _AuthorizedProviderCall:
    request: ParticipantActionAdmissionRequest
    authorized: ParticipantActionAdmissionRequest
    expected: ParticipantActionAdmissionRequest
    mapped: ParticipantActionAdmissionRequest
    snapshot: RuntimeSnapshot
    baseline_snapshot: RuntimeSnapshot
    provider_method: Callable[..., object]
    capture: MixedEdgeExecutionCapture

    def __call__(self, value: ParticipantActionAdmissionRequest, current: RuntimeSnapshot) -> object:
        self.capture.provider_calls += 1
        if self.capture.provider_calls != 1:
            raise ValueError("executable edge bridge invoked its provider more than once")
        if value is not self.mapped or current is not self.snapshot:
            raise ValueError("executable edge bridge changed the authorized invocation")
        if (self.snapshot, self.request, self.mapped) != (self.baseline_snapshot, self.authorized, self.expected):
            raise ValueError("executable edge bridge changed the authorized invocation")
        self.capture.provider_started = True
        return self.provider_method(value, current)


def _invoke_mapped_edge(
    request: ParticipantActionAdmissionRequest,
    snapshot: RuntimeSnapshot,
    *,
    installed: MixedEdgeExecutionBinding,
    edge: object,
    declaration: object,
    mapping: object,
    provider_method: Callable[..., object],
    operation_id: str,
    capture: MixedEdgeExecutionCapture,
) -> ApplyResult:
    if request.action_contract_address != installed.source_action_address:
        raise ValueError("executable edge source action differs from admitted subject")
    baseline_snapshot = deepcopy(snapshot)
    authorized = deepcopy(request)
    expected = replace(deepcopy(authorized), action_contract_address=installed.destination_action_address)
    mapped = installed.map_action(deepcopy(authorized))
    if not isinstance(mapped, ParticipantActionAdmissionRequest):
        raise TypeError("executable edge mapping must return a typed action")
    if (request, mapped) != (authorized, expected):
        raise ValueError("executable edge mapping changed an unauthorized subject")
    time_state = installed.time_runtime.state(deepcopy(snapshot))
    if not isinstance(time_state, TimeRuntimeStateModel):
        raise TypeError("executable edge time readback must be typed")
    validate_time_runtime_state(declaration, time_state)
    if snapshot.time_model_state != time_state:
        raise ValueError("executable edge time readback differs from the committed snapshot")
    grant = MixedTimeCoordinationEvidence.model_validate(
        installed.coordinate(operation_id, deepcopy(edge), deepcopy(time_state))
    )
    _require_time_grant(grant, operation_id, edge, mapping, time_state)
    capture.time = grant
    provider_call = _AuthorizedProviderCall(
        request, authorized, expected, mapped, snapshot, baseline_snapshot, provider_method, capture
    )
    bridged = installed.bridge(operation_id, mapped, snapshot, provider_call)
    if not isinstance(bridged, tuple) or len(bridged) != 2 or capture.provider_calls != 1:
        raise ValueError("executable edge bridge must return one correlated provider call")
    result, report_payload = bridged
    if not isinstance(result, ApplyResult):
        raise TypeError("executable edge bridge returned an untyped provider result")
    report = MixedBridgeExecutionEvidence.model_validate(report_payload)
    _require_bridge_report(report, operation_id, installed, result)
    capture.bridge = report
    capture.method_completed = True
    return result


def _stage_readback_method(
    binding: object,
    edge: object,
    installed: MixedEdgeExecutionBinding,
    request: ParticipantActionAdmissionRequest,
    operation_id: str,
    capture: MixedEdgeExecutionCapture,
) -> Callable[[ApplyResult], None]:
    """Confirm external stages only after the backend result gate accepts the provider result."""

    declaration = binding.context.time_models[edge.time_binding.time_model_ref]

    def confirm(result: ApplyResult) -> None:
        report = capture.bridge
        if not result.success or report is None:
            return
        readback = installed.time_runtime.state(deepcopy(result.snapshot))
        if not isinstance(readback, TimeRuntimeStateModel):
            raise TypeError("executable edge post-effect time readback must be typed")
        validate_time_runtime_state(declaration, readback)
        if result.snapshot.time_model_state != readback:
            raise ValueError("executable edge post-effect time readback differs from the result")
        capture.time_confirmed = True
        _require_stage_readbacks(
            installed,
            report,
            edge,
            request,
            operation_id,
            result.snapshot,
            capture,
        )

    return confirm


def _require_stage_readbacks(
    installed: MixedEdgeExecutionBinding,
    report: MixedBridgeExecutionEvidence,
    edge: object,
    request: ParticipantActionAdmissionRequest,
    operation_id: str,
    snapshot: RuntimeSnapshot,
    capture: MixedEdgeExecutionCapture,
) -> None:
    if report.delivery_evidence_refs:
        _require_delivery_readback(installed, report, edge, operation_id, snapshot)
        capture.delivery_confirmed = True
    if report.observation_evidence_refs:
        _require_observation_readback(installed, report, edge, request, operation_id, snapshot)
        capture.observation_confirmed = True


def _require_delivery_readback(
    installed: MixedEdgeExecutionBinding,
    report: MixedBridgeExecutionEvidence,
    edge: object,
    operation_id: str,
    snapshot: RuntimeSnapshot,
) -> None:
    if installed.delivery_readback is None:
        raise ValueError("mixed delivery requires destination readback")
    delivery = MixedDeliveryReadback.model_validate(installed.delivery_readback(operation_id, deepcopy(snapshot)))
    if (delivery.operation_id, delivery.destination_component_id) != (operation_id, edge.target_component_id):
        raise ValueError("mixed destination receipt differs from the admitted edge")
    if not set(report.delivery_evidence_refs).issubset(delivery.evidence_refs):
        raise ValueError("mixed destination receipt differs from the admitted edge")


def _require_observation_readback(
    installed: MixedEdgeExecutionBinding,
    report: MixedBridgeExecutionEvidence,
    edge: object,
    request: ParticipantActionAdmissionRequest,
    operation_id: str,
    snapshot: RuntimeSnapshot,
) -> None:
    if installed.observation_readback is None:
        raise ValueError("mixed observation requires participant readback")
    observation = MixedObservationReadback.model_validate(
        installed.observation_readback(operation_id, deepcopy(snapshot))
    )
    if (observation.operation_id, observation.participant_address, observation.audience_ref) != (
        operation_id,
        request.participant_address,
        edge.audience_scope_ref,
    ):
        raise ValueError("mixed participant observation differs from the authorized audience")
    if not set(report.observation_evidence_refs).issubset(observation.evidence_refs):
        raise ValueError("mixed participant observation differs from the authorized audience")


def _require_time_grant(
    grant: MixedTimeCoordinationEvidence,
    operation_id: str,
    edge: object,
    mapping: object,
    state: TimeRuntimeStateModel,
) -> None:
    source = state.clocks[edge.time_binding.source_clock_address].coordinate
    destination = state.clocks[edge.time_binding.target_clock_address].coordinate
    required = {item.evidence_ref for item in edge.evidence_bindings}
    provided = set(grant.mapping_evidence_refs) | set(grant.timing_evidence_refs)
    mapped_tick = Fraction(source.tick * mapping.scale.numerator, mapping.scale.denominator) + mapping.offset_ticks
    granted_identity = (grant.operation_id, grant.mapping_ref, grant.ordering_basis, grant.comparison)
    required_identity = (operation_id, edge.time_binding.mapping_address, edge.time_binding.ordering_basis, "ordered")
    if granted_identity != required_identity or edge.time_binding.ordering_basis in {
        "wall_clock_only",
        "unknown",
        "unsupported",
    }:
        raise ValueError("executable edge time mapping or governed order is unsupported")
    if (grant.source_coordinate, grant.destination_coordinate, source.segment) != (
        source,
        destination,
        destination.segment,
    ):
        raise ValueError("executable edge time mapping or governed order is unsupported")
    if (mapped_tick, source.microstep) > (destination.tick, destination.microstep) or not required.issubset(provided):
        raise ValueError("executable edge time mapping or governed order is unsupported")


def _require_bridge_report(
    report: MixedBridgeExecutionEvidence,
    operation_id: str,
    installed: MixedEdgeExecutionBinding,
    result: ApplyResult,
) -> None:
    report_identity = (
        report.operation_id,
        report.bridge_ref,
        report.bridge_version,
        report.bridge_digest,
        report.source_action_address,
        report.destination_action_address,
    )
    installed_identity = (
        operation_id,
        installed.bridge_ref,
        installed.bridge_version,
        installed.bridge_digest,
        installed.source_action_address,
        installed.destination_action_address,
    )
    if report_identity != installed_identity or set(report.mapping_loss_refs) != {installed.mapping_loss_ref}:
        raise ValueError("executable edge report differs from the admitted bridge or provider result")
    if (report.execution_status == "succeeded" and not result.success) or (
        report.execution_status == "failed" and result.success
    ):
        raise ValueError("executable edge report differs from the admitted bridge or provider result")


__all__ = ("_mapped_edge_method", "_stage_readback_method")
