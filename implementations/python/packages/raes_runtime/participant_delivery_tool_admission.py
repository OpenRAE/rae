"""Exact binding and live-cut crossing checks for delivery tool actions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.contracts.participant_crossing_evidence import ParticipantCrossingEvidence
from raes_contracts.errors import ConflictError
from raes_contracts.participant_tool_actions import ParticipantToolActionRefusal

from .participant_delivery_driver import matching_delivery_tool_offers
from .participant_temporal_binding import bind_shared_time_context


def tool_binding(port: object, request: object) -> tuple[object, ParticipantToolActionRefusal | None]:
    if not _invocation_matches(port, request):
        return None, ParticipantToolActionRefusal.INVOCATION_MISMATCH
    binding, refusal = _bound_relation(port, request)
    if refusal is not None:
        return None, refusal
    offers = execution_offers(port, request)
    if len(offers) != 1:
        refusal = (
            ParticipantToolActionRefusal.EXECUTION_OFFER_MISSING
            if not offers
            else ParticipantToolActionRefusal.EXECUTION_OFFER_AMBIGUOUS
        )
    return (binding, None) if refusal is None else (None, refusal)


def _invocation_matches(port: object, request: object) -> bool:
    expected = (
        port.invocation_action_instance_id,
        port.participant_address,
        port.episode_id,
        port.participant_implementation_ref,
        port.execution_scope_ref,
        port.execution_generation,
    )
    actual = (
        request.invocation_action_instance_id,
        request.participant_address,
        request.episode_id,
        request.participant_implementation_ref,
        request.execution_scope_ref,
        request.execution_generation,
    )
    return actual == expected


def _bound_relation(port: object, request: object) -> tuple[object, ParticipantToolActionRefusal | None]:
    matches = [
        binding
        for binding in port.delivery_tools_context().bindings
        if (
            binding.tool_affordance_address == request.tool_affordance_address
            and binding.action_contract_address == request.action_contract_address
            and request.participant_address in binding.participant_addresses
        )
    ]
    if len(matches) != 1:
        return (
            None,
            ParticipantToolActionRefusal.BINDING_UNKNOWN
            if not matches
            else ParticipantToolActionRefusal.BINDING_AMBIGUOUS,
        )
    binding = matches[0]
    if request.observation_boundary_address not in binding.observation_boundary_addresses:
        return None, ParticipantToolActionRefusal.OBSERVATION_BOUNDARY_UNBOUND
    refusal = (
        None
        if set(request.target_addresses) <= set(binding.target_addresses)
        else ParticipantToolActionRefusal.TARGET_UNBOUND
    )
    return binding, refusal


def execution_offers(port: object, request: object) -> list[object]:
    return matching_delivery_tool_offers(
        port.delivery_tools_context().capability,
        action_contract_address=request.action_contract_address,
        implementation_ref=port.participant_implementation_ref,
        target_addresses=request.target_addresses,
        temporal_bindings=port.delivery_tools_context().temporal,
    )


def action_admission(
    port: object, request: object, binding: object, action_instance_id: str
) -> ParticipantActionAdmissionRequest:
    contexts = []
    for temporal in port.delivery_tools_context().temporal:
        if temporal.action_contract_address != request.action_contract_address:
            continue
        clocks = getattr(port.delivery_tools_context().plane.delivery_snapshot.time_model_state, "clocks", {})
        clock = clocks.get(temporal.clock_address)
        if clock is None:
            raise ConflictError("tool action shared clock is unavailable")
        contexts.append(
            bind_shared_time_context(
                temporal,
                participant_address=port.participant_address,
                episode_id=port.episode_id,
                action_instance_id=action_instance_id,
                execution_scope_ref=port.execution_scope_ref,
                execution_generation=port.execution_generation,
                clock=clock,
            )
        )
    return ParticipantActionAdmissionRequest(
        participant_address=request.participant_address,
        action_contract_address=request.action_contract_address,
        observation_boundary_address=request.observation_boundary_address,
        action_instance_id=action_instance_id,
        implementation_manifest=port.invocation.implementation_manifest,
        implementation_selection=port.invocation.implementation_selection,
        observation_boundary_evidence_refs=dict(binding.observation_boundary_evidence_refs).get(
            request.observation_boundary_address, ()
        ),
        requires_terminal_outcome=True,
        target_addresses=request.target_addresses,
        execution_scope_ref=port.execution_scope_ref,
        execution_generation=port.execution_generation,
        temporal_contexts=tuple(contexts),
    )


def require_live_invocation(port: object) -> None:
    plane = port.delivery_tools_context().plane
    plane.delivery_require_state_writer()
    plane.delivery_reload_derived_state()
    live = plane.delivery_snapshot.participant_episode_results.get(port.participant_address, {})
    if (live.get("episode_id"), live.get("status")) != (port.episode_id, "running"):
        raise ConflictError("tool invocation episode is no longer live")
    if plane.delivery_execution_generation != port.execution_generation:
        raise ConflictError("tool invocation execution generation changed")
    if port.delivery_tools_context().ledger.effect_admission_refusal() is not None:
        raise ConflictError("tool invocation effect admission is closed")


def prepare_tool_crossing(
    port: object, admission: object, evidence: ParticipantCrossingEvidence | None, *, stage: str
) -> tuple[object, object]:
    plane = port.delivery_tools_context().plane
    if not isinstance(evidence, ParticipantCrossingEvidence):
        raise ConflictError("tool action crossing evidence is required")
    evidence = ParticipantCrossingEvidence.model_validate(evidence.model_dump(mode="json"))
    cut, behavior, revision = _live_tool_cut(port, admission)
    intent = plane.delivery_action_crossing_intent(
        behavior,
        admission,
        evidence,
        port.delivery_tools_context().identity,
        effective_order=cut.effective_order,
    )
    # Admission and dispatch authorize immutable carrier values, not a mutable
    # action-id alias. In particular, dispatch includes newly supplied dwell proof.
    subject = intent.subject
    intent = intent.model_copy(
        update={
            "subject": subject.model_copy(
                update={
                    "subject_ref": f"{subject.subject_ref}:{stage}:{subject.subject_digest}",
                }
            )
        }
    )
    crossing = plane.delivery_prepare_participant_crossing(
        intent.model_copy(deep=True),
        identity=port.delivery_tools_context().identity,
        idempotency_key=f"{admission.action_instance_id}:{stage}",
        incumbent_carrier=deepcopy(admission),
    )
    if crossing.intent != intent:
        raise ConflictError("tool action crossing intent was changed")
    crossing, _, refused = plane.delivery_admit_ingress_sinks(
        crossing,
        sink_kind=plane.delivery_action_sink_kind,
        action="admit_participant_tool_action",
    )
    if refused is not None:
        return None, None
    governed = replace(deepcopy(plane.delivery_governed_action_request(crossing, deepcopy(admission))))
    # The policy owns a transformed carrier's reference. Its exact digest, kind,
    # contract, participant and episode must still describe the returned carrier.
    actual_subject = plane.delivery_action_subject(governed).model_copy(
        update={
            "subject_ref": crossing.governed_subject.subject_ref,
        }
    )
    plane.delivery_require_governed_subject(crossing, actual_subject)
    transformed = replace(
        port.delivery_tools_context().current_request,
        action_contract_address=governed.action_contract_address,
        observation_boundary_address=governed.observation_boundary_address,
        target_addresses=governed.target_addresses,
    )
    _, refusal = tool_binding(port, transformed)
    _require_same_governed_binding(admission, governed, refusal)
    port.delivery_tools_context().scope.require_live()
    if crossing.intent != intent:
        raise ConflictError("tool action crossing intent was changed")
    if plane.delivery_snapshot_state.revision != revision:
        raise ConflictError("tool action policy cut changed")
    return crossing, governed


def _live_tool_cut(port: object, admission: ParticipantActionAdmissionRequest) -> tuple[object, object, int]:
    plane = port.delivery_tools_context().plane
    require_live_invocation(port)
    revision = plane.delivery_snapshot_state.revision
    with plane.delivery_mutation_authority.external_call():
        raw = plane.delivery_execution_adapter.call(
            "control",
            plane.delivery_inject_delivery.resolver.resolve_invocation_cut,
            port.invocation.model_copy(deep=True),
            deepcopy(admission),
            deepcopy(plane.delivery_snapshot),
            timeout_ms=plane.delivery_supervision.admission_ms,
        )
    port.delivery_tools_context().scope.require_live()
    plane.delivery_reload_derived_state()
    if plane.delivery_snapshot_state.revision != revision:
        raise ConflictError("tool action authority cut changed")
    cut = plane.delivery_live_cut(raw)
    delivery = plane.delivery_inject_delivery.model.participant_inject_deliveries[
        port.invocation.delivery.application.delivery_address
    ]
    plane.delivery_require_delivery_control(
        port.invocation.delivery.application,
        delivery,
        cut.effective_order,
        port.delivery_tools_context().identity,
        live_cut=cut,
        request_ref=admission.action_instance_id,
    )
    behavior = plane.delivery_inject_delivery.model.participant_behaviors[port.participant_address]
    anchors = set(behavior.authority_anchor_addresses or behavior.authority_anchor_refs)
    if (
        cut.request_ref != admission.action_instance_id
        or not anchors
        or not anchors <= set(cut.active_authority_basis_refs)
        or not set(admission.target_addresses) <= set(cut.authorized_scope_refs)
    ):
        raise ConflictError("tool action authority is unavailable")
    return cut, behavior, revision


def _require_same_governed_binding(
    admission: ParticipantActionAdmissionRequest,
    governed: ParticipantActionAdmissionRequest,
    refusal: ParticipantToolActionRefusal | None,
) -> None:
    coordinates = (
        "action_instance_id",
        "participant_address",
        "execution_scope_ref",
        "execution_generation",
        "implementation_manifest",
        "implementation_selection",
        "temporal_contexts",
        "temporal_evidence",
    )
    original = tuple(getattr(admission, name) for name in coordinates)
    updated = tuple(getattr(governed, name) for name in coordinates)
    if refusal is not None or original != updated:
        raise ConflictError("governed tool action binding differs")
