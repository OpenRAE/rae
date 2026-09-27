"""Executable native handoff and correlated time readback for mixed phases."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction

from raes_contracts.contracts.mixed_composition import MixedCompositionTransitionModel
from raes_contracts.contracts.mixed_runtime import MixedCompositionRuntimeStateModel
from raes_contracts.contracts.time_model import TimeRuntimeStateModel, validate_time_runtime_state
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot

from .control_plane_mutation import external_control_plane_call
from .mixed_runtime import MixedRuntimeBinding
from .mixed_runtime_edge import MixedTimeCoordinationEvidence
from .mixed_runtime_handoff import MixedHandoffBinding, MixedHandoffEvidence, MixedHandoffReadback


@dataclass(frozen=True)
class _HandoffResolution:
    state: OperationState
    order_ref: str
    evidence_refs: tuple[str, ...] = ()
    destination_component_id: str | None = None


@dataclass
class _HandoffProgress:
    confirmed_refs: tuple[str, ...]
    correlated: bool = False
    evidence: MixedHandoffEvidence | None = None
    readback: MixedHandoffReadback | None = None


def _perform_handoff(
    control_plane: object,
    binding: MixedRuntimeBinding,
    transition: MixedCompositionTransitionModel,
    state: MixedCompositionRuntimeStateModel,
    operation_id: str,
) -> _HandoffResolution | None:
    target = binding.profile.phases[transition.target_phase_id]
    if set(state.active_component_ids) == set(target.active_component_ids):
        return None
    return _resolve_required_handoff(control_plane, binding, transition, state, operation_id)


def _resolve_required_handoff(
    control_plane: object,
    binding: MixedRuntimeBinding,
    transition: MixedCompositionTransitionModel,
    state: MixedCompositionRuntimeStateModel,
    operation_id: str,
) -> _HandoffResolution:
    installed = binding.handoff_bindings.get(transition.transition_id)
    resolution = _HandoffResolution(OperationState.FAILED, "order:handoff-unbound")
    if installed is not None:
        declaration = binding.context.time_models[installed.time_model_ref]
        baseline_snapshot = deepcopy(control_plane._snapshot)
        try:
            time_state, grant = _request_handoff_grant(
                control_plane, installed, declaration, transition, operation_id, baseline_snapshot
            )
        except Exception:
            resolution = _HandoffResolution(OperationState.FAILED, "order:handoff-time-refused")
        else:
            progress = _HandoffProgress(
                tuple(dict.fromkeys([*grant.mapping_evidence_refs, *grant.timing_evidence_refs]))
            )
            try:
                _invoke_handoff_stage(
                    control_plane,
                    installed,
                    declaration,
                    transition,
                    state,
                    operation_id,
                    baseline_snapshot,
                    time_state,
                    grant,
                    progress,
                )
            except Exception:
                resolution = _HandoffResolution(OperationState.INDETERMINATE, grant.order_ref, progress.confirmed_refs)
            else:
                resolution = _handoff_stage_outcome(installed, state, operation_id, grant, progress)
    return resolution


def _request_handoff_grant(
    control_plane: object,
    installed: MixedHandoffBinding,
    declaration: object,
    transition: MixedCompositionTransitionModel,
    operation_id: str,
    baseline_snapshot: RuntimeSnapshot,
) -> tuple[TimeRuntimeStateModel, MixedTimeCoordinationEvidence]:
    with external_control_plane_call(control_plane):
        time_state = installed.time_runtime.state(deepcopy(baseline_snapshot))
        if not isinstance(time_state, TimeRuntimeStateModel):
            raise TypeError("handoff time readback must be typed")
        validate_time_runtime_state(declaration, time_state)
        if time_state != baseline_snapshot.time_model_state:
            raise ValueError("handoff time readback differs from the committed snapshot")
        grant = MixedTimeCoordinationEvidence.model_validate(
            installed.coordinate(operation_id, deepcopy(transition), deepcopy(time_state))
        )
    _require_handoff_time_grant(installed, grant, operation_id, declaration, time_state, transition)
    return time_state, grant


def _invoke_handoff_stage(
    control_plane: object,
    installed: MixedHandoffBinding,
    declaration: object,
    transition: MixedCompositionTransitionModel,
    state: MixedCompositionRuntimeStateModel,
    operation_id: str,
    baseline_snapshot: RuntimeSnapshot,
    time_state: TimeRuntimeStateModel,
    grant: MixedTimeCoordinationEvidence,
    progress: _HandoffProgress,
) -> None:
    with external_control_plane_call(control_plane):
        evidence = MixedHandoffEvidence.model_validate(
            installed.invoke(operation_id, deepcopy(transition), deepcopy(state), deepcopy(baseline_snapshot))
        )
        required = {item.evidence_ref for item in transition.evidence_bindings}
        progress.correlated = _handoff_evidence_correlated(
            evidence, installed, transition, state, operation_id, grant, required
        )
        progress.evidence = evidence
        if progress.correlated:
            progress.confirmed_refs = tuple(dict.fromkeys([*progress.confirmed_refs, *evidence.evidence_refs]))
        readback = MixedHandoffReadback.model_validate(installed.readback(operation_id, deepcopy(baseline_snapshot)))
        progress.readback = readback
        if progress.correlated and readback.operation_id == operation_id:
            progress.confirmed_refs = tuple(dict.fromkeys([*progress.confirmed_refs, *readback.evidence_refs]))
        _validate_handoff_time_readback(installed, declaration, baseline_snapshot, time_state)


def _handoff_evidence_correlated(
    evidence: MixedHandoffEvidence,
    installed: MixedHandoffBinding,
    transition: MixedCompositionTransitionModel,
    state: MixedCompositionRuntimeStateModel,
    operation_id: str,
    grant: MixedTimeCoordinationEvidence,
    required: set[str],
) -> bool:
    observed = (
        evidence.operation_id,
        evidence.transition_id,
        evidence.source_component_id,
        evidence.destination_component_id,
        evidence.predecessor_history_head,
        evidence.phase_revision,
        evidence.order_ref,
    )
    expected = (
        operation_id,
        transition.transition_id,
        installed.source_component_id,
        installed.destination_component_id,
        state.history_head,
        state.phase_revision,
        grant.order_ref,
    )
    return observed == expected and required.issubset(evidence.evidence_refs)


def _validate_handoff_time_readback(
    installed: MixedHandoffBinding,
    declaration: object,
    baseline_snapshot: RuntimeSnapshot,
    time_state: TimeRuntimeStateModel,
) -> None:
    final_time = installed.time_runtime.state(deepcopy(baseline_snapshot))
    if not isinstance(final_time, TimeRuntimeStateModel):
        raise TypeError("handoff post-transfer time readback must be typed")
    validate_time_runtime_state(declaration, final_time)
    if final_time != baseline_snapshot.time_model_state:
        raise ValueError("handoff post-transfer time readback differs from the committed snapshot")
    for clock_address in (installed.source_clock_address, installed.destination_clock_address):
        previous = time_state.clocks[clock_address].coordinate
        current = final_time.clocks[clock_address].coordinate
        if (current.segment, current.tick, current.microstep) < (previous.segment, previous.tick, previous.microstep):
            raise ValueError("handoff time readback regressed")


def _handoff_stage_outcome(
    installed: MixedHandoffBinding,
    state: MixedCompositionRuntimeStateModel,
    operation_id: str,
    grant: MixedTimeCoordinationEvidence,
    progress: _HandoffProgress,
) -> _HandoffResolution:
    evidence = progress.evidence
    readback = progress.readback
    resolution = _HandoffResolution(OperationState.INDETERMINATE, grant.order_ref, progress.confirmed_refs)
    if progress.correlated and evidence is not None and readback is not None and readback.operation_id == operation_id:
        if evidence.status == "committed":
            committed = (readback.owner_component_id, readback.owner_ref, readback.phase_revision) == (
                installed.destination_component_id,
                installed.destination_owner_ref,
                state.phase_revision + 1,
            )
            resolution = _HandoffResolution(
                OperationState.SUCCEEDED if committed else OperationState.INDETERMINATE,
                evidence.order_ref,
                progress.confirmed_refs,
                installed.destination_component_id if committed else None,
            )
        elif evidence.status in {"failed", "stale"}:
            retained = (readback.owner_component_id, readback.owner_ref, readback.phase_revision) == (
                installed.source_component_id,
                installed.source_owner_ref,
                state.phase_revision,
            )
            resolution = _HandoffResolution(
                OperationState.FAILED if retained else OperationState.INDETERMINATE,
                evidence.order_ref,
                progress.confirmed_refs,
            )
        else:
            resolution = _HandoffResolution(OperationState.INDETERMINATE, evidence.order_ref, progress.confirmed_refs)
    return resolution


def _require_handoff_time_grant(
    installed: MixedHandoffBinding,
    grant: MixedTimeCoordinationEvidence,
    operation_id: str,
    declaration: object,
    state: TimeRuntimeStateModel,
    transition: MixedCompositionTransitionModel,
) -> None:
    source = state.clocks[installed.source_clock_address].coordinate
    destination = state.clocks[installed.destination_clock_address].coordinate
    mapping = declaration.mappings[installed.mapping_ref]
    mapped_tick = Fraction(source.tick * mapping.scale.numerator, mapping.scale.denominator) + mapping.offset_ticks
    required = {item.evidence_ref for item in transition.evidence_bindings}
    granted = (
        grant.operation_id,
        grant.mapping_ref,
        grant.ordering_basis,
        grant.comparison,
        grant.source_coordinate,
        grant.destination_coordinate,
        source.segment,
    )
    expected = (
        operation_id,
        installed.mapping_ref,
        installed.ordering_basis,
        "ordered",
        source,
        destination,
        destination.segment,
    )
    if granted != expected:
        raise ValueError("handoff time coordination is unsupported")
    if (mapped_tick, source.microstep) > (destination.tick, destination.microstep):
        raise ValueError("handoff time coordination is unsupported")
    if not required.issubset(set(grant.mapping_evidence_refs) | set(grant.timing_evidence_refs)):
        raise ValueError("handoff time coordination is unsupported")
