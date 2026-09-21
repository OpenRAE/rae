"""Issue #1069 RUN-320 modular participant-control orchestration at real sinks.

These tests drive the real ``RuntimeControlPlane`` to the ``RuntimeTarget``
boundary with an instrumented backend. Providers are invoked only through the
published ``participant-control-provider/v1`` protocol, the composed evaluation
is committed before any effect or disclosure, and every non-eligible class
produces zero backend dispatch and zero serialization with bounded evidence.
"""

from __future__ import annotations

import pytest
from participant_control_contract_fixtures import evaluation_payload
from participant_control_runtime_fixtures import (
    INSTANCE,
    MONITOR,
    DuplicateSlotProvider,
    SyntheticControlProvider,
    SyntheticControlResolver,
    admitted_payload,
    advisory_monitor_payload,
    conflicting_effect_payload,
    control_binding,
    with_status,
)
from participant_crossing_fixtures import (
    AUDIENCE,
    PARTICIPANT,
    StaticCrossingResolver,
    action_plane,
    admit,
    control_specification,
    evidence,
    identity,
    policy_capable_target,
)
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane

_SECRET = "provider failure detail must never reach a caller"


def _instrument_backend(target: object) -> dict[str, int]:
    runtime = target.participant_runtime
    assert runtime is not None
    original = runtime.admit_action
    counter = {"calls": 0}

    def tracked(*args: object, **kwargs: object):
        counter["calls"] += 1
        return original(*args, **kwargs)

    runtime.admit_action = tracked  # type: ignore[method-assign]
    return counter


def control_target(*features: str):
    """A target declaring API-407 modular-control support for this runtime."""

    return policy_capable_target("participant_ingress_admission", "participant_modular_control", *features)


def _plane(binding, *, target=None, store=None):
    return action_plane(
        StaticCrossingResolver(),
        target=target or control_target(),
        store=store,
        participant_control=binding,
    )


def _evaluations(plane) -> list[dict]:
    return list(plane.snapshot.participant_control_evaluation_history.get(PARTICIPANT, ()))


def _audit_details(plane) -> dict[str, str]:
    return dict(plane.audit_log()[-1].details)


def _status(plane, operation_id):
    status = plane.get_operation(operation_id)
    assert status is not None
    return status


# --- Eligible composition -------------------------------------------------


def test_eligible_composition_commits_before_the_backend_effect():
    target = control_target()
    counter = _instrument_backend(target)
    binding = control_binding()
    plane = _plane(binding, target=target)

    receipt = admit(plane, idempotency_key="control-eligible")

    assert receipt.accepted is True
    assert counter["calls"] == 1
    evaluations = _evaluations(plane)
    assert len(evaluations) == 1
    assert evaluations[0]["composition"]["disposition"] == "eligible"
    assert _audit_details(plane)["control_disposition"] == "eligible"


def test_providers_are_invoked_through_the_published_protocol_for_the_live_cut():
    binding = control_binding()
    plane = _plane(binding)

    admit(plane, idempotency_key="control-protocol")

    provider = binding.providers[INSTANCE]
    assert len(provider.calls) == 1
    context = provider.calls[0].context
    assert context.participant_address == PARTICIPANT
    assert context.expected_history_heads  # bound to the live state cut


def test_two_mechanisms_and_profiles_compose_without_backend_name_branches():
    binding = control_binding(advisory_monitor_payload())
    plane = _plane(binding)

    admit(plane, idempotency_key="control-two-mechanisms")

    evaluation = _evaluations(plane)[0]
    assert {result["instance_id"] for result in evaluation["results"]} == {INSTANCE, MONITOR}
    assert evaluation["composition"]["disposition"] == "eligible"


@pytest.mark.parametrize("reverse", [False, True])
def test_permuted_provider_return_order_composes_identically(reverse: bool):
    payload = advisory_monitor_payload()
    providers = {
        instance: SyntheticControlProvider(instance_id=instance, reverse=reverse) for instance in (INSTANCE, MONITOR)
    }
    plane = _plane(control_binding(payload, providers=providers))

    admit(plane, idempotency_key="control-order")

    evaluation = _evaluations(plane)[0]
    assert evaluation["composition"]["contributing_result_ids"] == ["result-fact", "result-rule", "result-advice"]
    assert evaluation["composition"]["disposition"] == "eligible"


def test_advisory_negative_assessment_alone_never_blocks_release():
    target = control_target()
    counter = _instrument_backend(target)
    plane = _plane(control_binding(advisory_monitor_payload()), target=target)

    admit(plane, idempotency_key="control-advisory")

    assert counter["calls"] == 1
    assert _evaluations(plane)[0]["composition"]["blockers"] == []


def test_observation_only_selection_keeps_the_incumbent_gates():
    """A permissive profile with no denial slot still passes ordinary admission."""

    payload = evaluation_payload()
    payload["request"]["selection"]["slots"] = [payload["request"]["selection"]["slots"][0]]
    payload["results"] = [payload["results"][0]]
    plane = _plane(control_binding(payload))

    receipt = admit(plane, idempotency_key="control-observe-only")

    assert receipt.accepted is True
    assert _evaluations(plane)[0]["composition"]["disposition"] == "eligible"


# --- Zero-effect non-eligible classes -------------------------------------


@pytest.mark.parametrize(
    "status,disposition",
    [("missing", "failed"), ("stale", "stale"), ("unsupported", "unsupported"), ("failed", "failed")],
)
def test_unsatisfied_mandatory_slot_never_dispatches(status: str, disposition: str):
    target = control_target()
    counter = _instrument_backend(target)
    payload = with_status(evaluation_payload(), "fact", status)
    plane = _plane(control_binding(payload), target=target)

    receipt = admit(plane, idempotency_key="control-unsatisfied")

    assert counter["calls"] == 0
    assert _status(plane, receipt.operation_id).state is OperationState.FAILED
    assert plane.snapshot.participant_behavior_history == {}
    assert _evaluations(plane)[0]["composition"]["disposition"] == disposition


def test_conflicting_effect_requests_deny_the_parent():
    target = control_target()
    counter = _instrument_backend(target)
    plane = _plane(control_binding(conflicting_effect_payload()), target=target)

    receipt = admit(plane, idempotency_key="control-conflict")

    assert counter["calls"] == 0
    assert _status(plane, receipt.operation_id).state is OperationState.FAILED
    evaluation = _evaluations(plane)[0]
    assert evaluation["composition"]["disposition"] == "conflict"
    assert "effect-conflict" in evaluation["composition"]["blockers"]


def test_weakened_support_blocks_under_the_requested_binding():
    payload = evaluation_payload()
    payload["support"][0]["effective_level"] = "bounded"
    payload["support"][0]["constraints"] = [
        {"kind": "constraint", "ref": "bounded-explicit-flows", "revision": "rev1", "digest": "sha256:" + "a" * 64}
    ]
    target = control_target()
    counter = _instrument_backend(target)
    plane = _plane(control_binding(payload), target=target)

    admit(plane, idempotency_key="control-weakened")

    assert counter["calls"] == 0
    assert _evaluations(plane)[0]["composition"]["disposition"] == "weakened"


def test_provider_exception_fails_closed_without_leaking_its_detail():
    target = control_target()
    counter = _instrument_backend(target)
    providers = {INSTANCE: SyntheticControlProvider(raises=True)}
    plane = _plane(control_binding(providers=providers), target=target)

    receipt = admit(plane, idempotency_key="control-provider-raises")

    assert counter["calls"] == 0
    status = _status(plane, receipt.operation_id)
    assert status.state is OperationState.FAILED
    assert _SECRET not in repr(status.diagnostics)
    assert _SECRET not in repr(plane.audit_log()[-1])
    assert _evaluations(plane)[0]["composition"]["disposition"] == "failed"


def test_malformed_provider_return_is_recorded_as_failed_not_omitted():
    providers = {INSTANCE: SyntheticControlProvider(returns_invalid=True)}
    plane = _plane(control_binding(providers=providers))

    admit(plane, idempotency_key="control-provider-malformed")

    evaluation = _evaluations(plane)[0]
    assert {result["slot_id"] for result in evaluation["results"]} == {"fact", "rule"}
    assert all(result["status"] == "failed" for result in evaluation["results"])


def test_an_omitted_slot_is_recorded_missing_rather_than_dropped():
    providers = {INSTANCE: SyntheticControlProvider(omits_slot="rule")}
    plane = _plane(control_binding(providers=providers))

    admit(plane, idempotency_key="control-provider-omits")

    evaluation = _evaluations(plane)[0]
    statuses = {result["slot_id"]: result["status"] for result in evaluation["results"]}
    assert statuses == {"fact": "resolved", "rule": "missing"}


def test_stale_state_cut_refuses_without_reusing_an_old_permit():
    target = control_target()
    counter = _instrument_backend(target)
    plane = _plane(control_binding(stale_heads=True), target=target)

    receipt = admit(plane, idempotency_key="control-stale")

    assert counter["calls"] == 0
    assert _status(plane, receipt.operation_id).state is OperationState.FAILED
    assert _audit_details(plane)["control_disposition"] == "stale"


def test_resolver_failure_fails_closed_without_leaking_its_detail():
    target = control_target()
    counter = _instrument_backend(target)
    plane = _plane(control_binding(raises=True), target=target)

    receipt = admit(plane, idempotency_key="control-resolver-raises")

    assert counter["calls"] == 0
    status = _status(plane, receipt.operation_id)
    assert status.state is OperationState.FAILED
    assert "resolver failure detail" not in repr(status.diagnostics)


def test_non_permit_incumbent_gate_blocks_even_with_resolved_mechanisms():
    target = control_target()
    counter = _instrument_backend(target)
    plane = _plane(control_binding(incumbent_gate_disposition="deny"), target=target)

    admit(plane, idempotency_key="control-gate-deny")

    assert counter["calls"] == 0
    assert _evaluations(plane)[0]["composition"]["disposition"] == "deny"


# --- Governed egress ------------------------------------------------------


def _egress_target():
    return control_target("participant_egress_projection", "participant_transformation")


def _status_view(plane, *, idempotency_key: str):
    return plane.get_participant_status_view(
        PARTICIPANT,
        identity=identity(audience_bound=True),
        crossing_evidence=evidence(),
        idempotency_key=idempotency_key,
    )


def test_eligible_composition_permits_the_governed_egress_projection():
    plane = _plane(control_binding(), target=_egress_target())

    view = _status_view(plane, idempotency_key="control-egress-permit")

    assert view is not None
    assert view.participant_address == PARTICIPANT
    assert _evaluations(plane)[0]["composition"]["disposition"] == "eligible"


def test_non_eligible_composition_refuses_egress_and_serializes_nothing():
    providers = {INSTANCE: SyntheticControlProvider(omits_slot="fact")}
    plane = _plane(control_binding(providers=providers), target=_egress_target())

    with pytest.raises(PermissionError, match="not permitted"):
        _status_view(plane, idempotency_key="control-egress-deny")

    stages = [item["occurrence"]["stage"] for item in plane.snapshot.participant_crossing_history[PARTICIPANT]]
    assert "delivered" not in stages
    assert _evaluations(plane)[0]["composition"]["disposition"] == "failed"


def test_a_resolver_cannot_substitute_a_selection_the_apparatus_never_admitted():
    """PC-01: changing the selection requires a new admitted binding, not a cut."""

    target = control_target()
    counter = _instrument_backend(target)
    binding = control_binding()
    rival = SyntheticControlResolver(
        payload=admitted_payload(advisory_monitor_payload(), participant=PARTICIPANT, audience=AUDIENCE)
    )
    rival.providers = tuple(binding.providers.values())
    object.__setattr__(binding, "resolver", rival)
    plane = _plane(binding, target=target)

    receipt = admit(plane, idempotency_key="control-unadmitted-selection")

    assert counter["calls"] == 0
    assert _status(plane, receipt.operation_id).state is OperationState.FAILED
    assert _audit_details(plane)["control_disposition"] == "unresolved"
    assert _evaluations(plane) == []


def test_duplicate_provider_slots_are_refused_rather_than_collapsed():
    """Order must not decide which contribution survives; the response is malformed."""

    target = control_target()
    counter = _instrument_backend(target)
    providers = {INSTANCE: DuplicateSlotProvider()}
    plane = _plane(control_binding(providers=providers), target=target)

    admit(plane, idempotency_key="control-duplicate-slot")

    assert counter["calls"] == 0
    evaluation = _evaluations(plane)[0]
    assert {result["status"] for result in evaluation["results"]} == {"failed"}


def test_permitted_control_ingress_commits_its_evaluation():
    """The supervisory transition carries the composition it was admitted under."""

    specification = control_specification()
    plane = RuntimeControlPlane(
        control_target("participant_intervention"),
        crossing_policy_resolver=StaticCrossingResolver(),
        behavior_specifications={specification.address: specification},
        participant_control=control_binding(),
        enforce_final_sink_flow_control=False,
    )
    plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")

    receipt = plane.record_participant_control(
        PARTICIPANT,
        _handoff_intent(specification),
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="control-ingress-evaluation",
    )

    assert receipt.accepted is True
    assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1
    evaluations = _evaluations(plane)
    assert len(evaluations) == 1
    assert evaluations[0]["composition"]["disposition"] == "eligible"
    assert any(result["slot_id"] == "rule" for result in evaluations[0]["results"])
    # The committed supervisory operation is provably the one that appended the
    # evaluation, so its effects have a principal to act for at this sink too.
    from raes_runtime.participant_control_receipts import originating_operations

    origin = originating_operations(plane, PARTICIPANT)[evaluations[0]["evaluation_id"]]
    assert origin.receipt.operation_id == receipt.operation_id
    assert origin.status.context.actor_id == identity().identity


def _handoff_intent(specification):
    from raes_runtime.participant_control_intents import ParticipantHandoffControlIntent

    return ParticipantHandoffControlIntent(
        declaration_ref=specification.control_transitions[0].address,
        episode_id="episode-1",
        client_correlation_id="control-ingress-1069",
        policy_revision="1.0.0",
        expected_state_revision=0,
        provenance_refs=["provenance:handoff"],
        evidence_refs=["evidence:handoff"],
        object_marking_refs=["marking:participant-control"],
        limitation_refs=["limitation:none"],
        completion_evidence_ref="evidence:handoff",
    )


def test_an_unconfigured_control_plane_runs_the_incumbent_path_unchanged():
    target = control_target()
    counter = _instrument_backend(target)
    plane = action_plane(StaticCrossingResolver(), target=target)

    receipt = admit(plane, idempotency_key="control-unconfigured")

    assert receipt.accepted is True
    assert counter["calls"] == 1
    assert plane.snapshot.participant_control_evaluation_history == {}


def test_a_reconstructed_crossing_identity_is_refused_as_a_stale_cut():
    """API-424 names the crossing occurrence event, not the decision id.

    A resolver that reconstructs the occurrence — rather than naming the
    committed RUN-319 record — cannot satisfy both the runtime binding and the
    portable validator, and the runtime refuses it instead of composing.
    """

    target = control_target()
    counter = _instrument_backend(target)
    plane = _plane(control_binding(replacement_crossing=True), target=target)

    receipt = admit(plane, idempotency_key="control-reconstructed-crossing")

    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
    assert plane.snapshot.participant_control_evaluation_history == {}
    assert counter["calls"] == 0
    assert plane.audit_log()[-1].details["control_disposition"] == "stale"


def test_the_committed_crossing_record_is_what_the_admitted_cut_names():
    """The bound digest is reproducible from committed state, not from memory."""

    from participant_control_runtime_fixtures import committed_crossing_record, live_crossing_digest

    plane = _plane(control_binding())
    admit(plane, idempotency_key="control-committed-crossing")

    resolver = plane._participant_control.resolver
    context = resolver.live["request"]["context"]
    committed = committed_crossing_record(
        type("_Prepared", (), {"decision": resolver.live_crossing, "next_snapshot": plane.snapshot})
    )
    assert context["crossing"]["ref"] == committed.event_id
    assert context["crossing"]["digest"] == live_crossing_digest(committed)
    assert committed.event_id != committed.occurrence.decision_id


def test_a_trusted_context_callback_cannot_mutate_the_runtime_re_entrantly():
    """Operator resolver code runs under the external-call re-entry fence."""

    from participant_control_runtime_fixtures import ReentrantValidationResolver

    template = control_binding()
    resolver = ReentrantValidationResolver(payload=template.resolver.payload)
    binding = control_binding(resolver=resolver)
    target = control_target()
    counter = _instrument_backend(target)
    plane = _plane(binding, target=target)
    resolver.plane = plane

    receipt = admit(plane, idempotency_key="control-reentrant-validation")

    # The re-entrant mutation was refused by the fence, not committed.
    assert resolver.reentry_errors == ["backend callback cannot start a control-plane mutation"]
    assert "participants.reentrant" not in plane.snapshot.participant_episode_results
    # The missing trusted context fails closed: nothing composed, nothing dispatched.
    assert plane.snapshot.participant_control_evaluation_history == {}
    assert counter["calls"] == 0
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED
