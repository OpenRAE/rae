"""Exact binding and live-cut crossing checks for delivery tool actions."""

from copy import deepcopy
from dataclasses import replace

from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.errors import ConflictError
from raes_contracts.participant_tool_actions import ParticipantToolActionRefusal

from .participant_control_orchestration import admit_ingress_sinks
from .participant_control_runtime import ParticipantControlLiveCut
from .participant_crossing_intents import action_crossing_intent, action_subject
from .participant_crossing_mediation import ParticipantCrossingEvidence, prepare_participant_crossing
from .participant_crossing_transform import _governed_action_request, _require_governed_subject
from .participant_delivery_driver import matching_delivery_tool_offers
from .participant_flow_sink import ParticipantFlowSinkKind
from .participant_inject_control import require_delivery_control
from .participant_temporal_binding import bind_shared_time_context


def tool_binding(port, request):
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
    if actual != expected:
        return None, ParticipantToolActionRefusal.INVOCATION_MISMATCH
    matches = [
        binding
        for binding in port._bindings
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
    if not set(request.target_addresses) <= set(binding.target_addresses):
        return None, ParticipantToolActionRefusal.TARGET_UNBOUND
    offers = execution_offers(port, request)
    if len(offers) != 1:
        return (
            None,
            ParticipantToolActionRefusal.EXECUTION_OFFER_MISSING
            if not offers
            else ParticipantToolActionRefusal.EXECUTION_OFFER_AMBIGUOUS,
        )
    return binding, None


def execution_offers(port, request):
    return matching_delivery_tool_offers(
        port._capability,
        action_contract_address=request.action_contract_address,
        implementation_ref=port.participant_implementation_ref,
        target_addresses=request.target_addresses,
        temporal_bindings=port._temporal,
    )


def action_admission(port, request, binding, action_instance_id):
    contexts = []
    for temporal in port._temporal:
        if temporal.action_contract_address != request.action_contract_address:
            continue
        clocks = getattr(port._plane._snapshot.time_model_state, "clocks", {})
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


def require_live_invocation(port):
    plane = port._plane
    plane._require_state_writer()
    plane._reload_derived_state()
    live = plane._snapshot.participant_episode_results.get(port.participant_address, {})
    if (live.get("episode_id"), live.get("status")) != (port.episode_id, "running"):
        raise ConflictError("tool invocation episode is no longer live")
    if plane._execution_generation != port.execution_generation:
        raise ConflictError("tool invocation execution generation changed")
    if port._ledger.effect_admission_refusal() is not None:
        raise ConflictError("tool invocation effect admission is closed")


def prepare_tool_crossing(port, admission, evidence, *, stage):
    plane = port._plane
    require_live_invocation(port)
    if not isinstance(evidence, ParticipantCrossingEvidence):
        raise ConflictError("tool action crossing evidence is required")
    evidence = ParticipantCrossingEvidence.model_validate(evidence.model_dump(mode="json"))
    revision = plane._snapshot_state.revision
    with plane._mutation_authority.external_call():
        raw = plane._execution_adapter.call(
            "control",
            plane._inject_delivery.resolver.resolve_invocation_cut,
            port.invocation.model_copy(deep=True),
            deepcopy(admission),
            deepcopy(plane._snapshot),
            timeout_ms=plane._supervision.admission_ms,
        )
    port._scope.require_live()
    plane._reload_derived_state()
    if plane._snapshot_state.revision != revision:
        raise ConflictError("tool action authority cut changed")
    if not isinstance(raw, ParticipantControlLiveCut):
        raise ConflictError("tool action live cut is unavailable")
    cut = ParticipantControlLiveCut.model_validate(raw.model_dump(mode="json"))
    delivery = plane._inject_delivery.model.participant_inject_deliveries[
        port.invocation.delivery.application.delivery_address
    ]
    require_delivery_control(
        plane,
        port.invocation.delivery.application,
        delivery,
        cut.effective_order,
        port._identity,
        live_cut=cut,
        request_ref=admission.action_instance_id,
    )
    behavior = plane._inject_delivery.model.participant_behaviors[port.participant_address]
    anchors = set(behavior.authority_anchor_addresses or behavior.authority_anchor_refs)
    if (
        cut.request_ref != admission.action_instance_id
        or not anchors
        or not anchors <= set(cut.active_authority_basis_refs)
        or not set(admission.target_addresses) <= set(cut.authorized_scope_refs)
    ):
        raise ConflictError("tool action authority is unavailable")
    intent = action_crossing_intent(
        plane, behavior, admission, evidence, port._identity, effective_order=cut.effective_order
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
    crossing = prepare_participant_crossing(
        plane,
        intent.model_copy(deep=True),
        identity=port._identity,
        idempotency_key=f"{admission.action_instance_id}:{stage}",
        incumbent_carrier=deepcopy(admission),
    )
    if crossing.intent != intent:
        raise ConflictError("tool action crossing intent was changed")
    crossing, _, refused = admit_ingress_sinks(
        plane,
        crossing,
        sink_kind=ParticipantFlowSinkKind.ACTION_ARGUMENT,
        action="admit_participant_tool_action",
    )
    if refused is not None:
        return None, None
    governed = replace(deepcopy(_governed_action_request(plane, crossing, deepcopy(admission))))
    # The policy owns a transformed carrier's reference. Its exact digest, kind,
    # contract, participant and episode must still describe the returned carrier.
    actual_subject = action_subject(plane, governed).model_copy(
        update={
            "subject_ref": crossing.governed_subject.subject_ref,
        }
    )
    _require_governed_subject(crossing, actual_subject)
    transformed = replace(
        port._current_request,
        action_contract_address=governed.action_contract_address,
        observation_boundary_address=governed.observation_boundary_address,
        target_addresses=governed.target_addresses,
    )
    _, refusal = tool_binding(port, transformed)
    if refusal is not None or (
        governed.action_instance_id != admission.action_instance_id
        or governed.participant_address != admission.participant_address
        or governed.execution_scope_ref != admission.execution_scope_ref
        or governed.execution_generation != admission.execution_generation
        or governed.implementation_manifest != admission.implementation_manifest
        or governed.implementation_selection != admission.implementation_selection
        or governed.temporal_contexts != admission.temporal_contexts
        or governed.temporal_evidence != admission.temporal_evidence
    ):
        raise ConflictError("governed tool action binding differs")
    port._scope.require_live()
    if crossing.intent != intent:
        raise ConflictError("tool action crossing intent was changed")
    if plane._snapshot_state.revision != revision:
        raise ConflictError("tool action policy cut changed")
    return crossing, governed
