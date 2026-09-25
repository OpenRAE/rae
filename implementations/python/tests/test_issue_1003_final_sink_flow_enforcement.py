"""Issue #1003 SEM-233 final-sink runtime enforcement at the RUN-319 boundary.

These tests drive the real ``RuntimeControlPlane`` to the ``RuntimeTarget``
boundary with an instrumented backend and assert that the published SEM-233
final-sink permit is resolved, validated, bound to the live state cut, and
committed atomically before any effect. Every non-permit class produces zero
backend dispatch and zero serialization with bounded, value-independent
evidence; permitted operations fold safe SEM-233 references into the audit.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from participant_crossing_fixtures import (
    PARTICIPANT,
    StaticCrossingResolver,
    action_plane,
    admission_request,
    admit,
    control_specification,
    evidence,
    identity,
    policy_capable_target,
)
from raes_contracts.contracts import ParticipantFlowFinalDisposition as Disposition
from raes_contracts.contracts import ParticipantFlowSinkKind
from raes_contracts.runtime_state import OperationState, OperationStatus
from raes_runtime import participant_crossing_egress
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore, LocalControlPlaneStore
from raes_runtime.participant_control_intents import ParticipantHandoffControlIntent
from sem233_flow_sink_fixtures import (
    FlowSinkToggles,
    Sem233FlowSinkResolver,
    deny_resolver,
    permit_resolver,
    sem233_plane,
)

_SECRET = "secret flow-sink policy detail must not leak"

_NON_PERMIT_TOGGLES = [
    pytest.param(FlowSinkToggles(capability_disposition=Disposition.DENY), id="final-deny"),
    pytest.param(FlowSinkToggles(capability_disposition=Disposition.UNSUPPORTED), id="capability-unsupported"),
    pytest.param(FlowSinkToggles(history_disposition=Disposition.STALE), id="history-stale-cut"),
    pytest.param(FlowSinkToggles(history_disposition=Disposition.UNRESOLVED), id="final-unresolved"),
    pytest.param(FlowSinkToggles(relation_head_refs=("history-head:stale.1",)), id="history-head-mismatch"),
    pytest.param(FlowSinkToggles(raise_exception=True), id="resolver-raises"),
    pytest.param(FlowSinkToggles(return_non_resolution=True), id="resolver-returns-non-resolution"),
    pytest.param(FlowSinkToggles(api_423_ref="crossing-decision.mismatch"), id="api-423-mismatch"),
    pytest.param(FlowSinkToggles(relation_audience="audience:wrong-sink"), id="binding-mismatch-audience"),
]


def _operation_status(plane: RuntimeControlPlane, operation_id: str) -> OperationStatus:
    status = plane.get_operation(operation_id)
    assert status is not None
    return status


def _instrument_backend(target: object) -> dict[str, int]:
    """Wrap the backend admit method to count real target invocations."""

    runtime = target.participant_runtime
    assert runtime is not None
    original = runtime.admit_action
    counter = {"calls": 0}

    def tracked(*args: object, **kwargs: object):
        counter["calls"] += 1
        return original(*args, **kwargs)

    runtime.admit_action = tracked  # type: ignore[method-assign]
    return counter


def _egress_target() -> object:
    return policy_capable_target("participant_egress_projection", "participant_transformation")


def _status_view(plane: RuntimeControlPlane, *, idempotency_key: str):
    return plane.get_participant_status_view(
        PARTICIPANT,
        identity=identity(audience_bound=True),
        crossing_evidence=evidence(),
        idempotency_key=idempotency_key,
    )


def _flow_details(plane: RuntimeControlPlane) -> dict[str, object]:
    details = plane.audit_log()[-1].details
    return {key: value for key, value in details.items() if key.startswith("flow")}


def _no_secret_leak(plane: RuntimeControlPlane, receipt: object) -> bool:
    audit = plane.audit_log()[-1]
    surfaces = [str(audit.details), audit.reason]
    surfaces.extend(diagnostic.message for diagnostic in getattr(receipt, "diagnostics", ()))
    return all(_SECRET not in surface for surface in surfaces)


# --- Permitted paths ------------------------------------------------------


def test_permitted_ingress_calls_backend_once_and_records_sem233() -> None:
    target = policy_capable_target()
    counter = _instrument_backend(target)
    plane = sem233_plane(permit_resolver(), target=target)

    receipt = admit(plane, idempotency_key="permit-ingress")

    assert receipt.accepted is True
    assert counter["calls"] == 1
    crossing = plane.snapshot.participant_crossing_history[PARTICIPANT]
    assert crossing[-1]["occurrence"]["decision_id"]
    details = _flow_details(plane)
    assert details["flow_sink_decision_id"] == "sink-decision.1"
    assert details["flow_final_disposition"] == "permit"
    assert details["flow_relation_document_id"] == "participant-flow-control-relation:red:episode-1"


def test_permitted_egress_returns_view_with_sem233_reference() -> None:
    plane = sem233_plane(permit_resolver(), target=_egress_target())

    view = _status_view(plane, idempotency_key="permit-egress")

    assert view is not None
    assert view.participant_address == PARTICIPANT
    assert plane.snapshot.participant_crossing_history[PARTICIPANT][-1]["occurrence"]["disposition"] == "permit"
    details = _flow_details(plane)
    assert details["flow_sink_decision_id"] == "sink-decision.1"
    assert details["flow_final_disposition"] == "permit"


def test_permitted_control_ingress_applies_transition_with_sem233_reference() -> None:
    specification = control_specification()
    plane = RuntimeControlPlane(
        policy_capable_target("participant_ingress_admission", "participant_intervention"),
        behavior_specifications={specification.address: specification},
        crossing_policy_resolver=permit_resolver(),
    )
    intent = _handoff_intent(specification)

    receipt = plane.record_participant_control(
        PARTICIPANT,
        intent,
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="permit-control",
    )

    assert receipt.accepted is True
    assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1
    assert _flow_details(plane)["flow_final_disposition"] == "permit"


# --- Zero-effect non-permit classes --------------------------------------


@pytest.mark.parametrize("toggles", _NON_PERMIT_TOGGLES)
def test_non_permit_ingress_never_dispatches_backend(toggles: FlowSinkToggles) -> None:
    target = policy_capable_target()
    counter = _instrument_backend(target)
    plane = sem233_plane(deny_resolver(toggles), target=target)

    receipt = admit(plane, idempotency_key="deny-ingress")

    assert receipt.accepted is True
    status = _operation_status(plane, receipt.operation_id)
    assert status.state is OperationState.FAILED
    assert counter["calls"] == 0
    assert plane.snapshot.participant_behavior_history == {}
    assert status.diagnostics[0].code == "runtime.participant-flow-sink-denied"
    assert plane.audit_log()[-1].reason == "flow-sink-denied"
    assert _no_secret_leak(plane, receipt)


@pytest.mark.parametrize("toggles", _NON_PERMIT_TOGGLES)
def test_non_permit_egress_raises_and_serializes_nothing(toggles: FlowSinkToggles) -> None:
    plane = sem233_plane(deny_resolver(toggles), target=_egress_target())

    with pytest.raises(PermissionError, match="not permitted"):
        _status_view(plane, idempotency_key="deny-egress")

    history = plane.snapshot.participant_crossing_history[PARTICIPANT]
    stages = [item["occurrence"]["stage"] for item in history]
    assert "decided" in stages
    assert "delivered" not in stages
    assert "observed" not in stages
    audit = plane.audit_log()[-1]
    assert audit.reason == "flow-sink-denied"
    assert audit.allowed is False
    status = _operation_status(plane, audit.operation_id)
    assert status.state is OperationState.FAILED
    assert {item.code for item in status.diagnostics} == {
        "runtime.participant-flow-sink-denied",
        "runtime.control-plane.operation-failed",
    }
    assert plane._store.load_records()[audit.operation_id].result_payload is None
    assert _no_secret_leak(plane, audit)


def test_denied_egress_replay_keeps_the_same_failed_operation() -> None:
    plane = sem233_plane(
        deny_resolver(FlowSinkToggles(capability_disposition=Disposition.DENY)),
        target=_egress_target(),
    )

    with pytest.raises(PermissionError, match="not permitted"):
        _status_view(plane, idempotency_key="deny-egress-replay")
    audit = plane.audit_log()[-1]
    audits = plane.audit_log()
    history = plane.snapshot.participant_crossing_history[PARTICIPANT]

    with pytest.raises(PermissionError, match="not permitted"):
        _status_view(plane, idempotency_key="deny-egress-replay")

    assert plane.audit_log() == audits
    assert plane.snapshot.participant_crossing_history[PARTICIPANT] == history
    assert _operation_status(plane, audit.operation_id).state is OperationState.FAILED


def test_claim_race_cannot_release_payload_from_denied_incumbent(monkeypatch: pytest.MonkeyPatch) -> None:
    permitted = sem233_plane(permit_resolver(), target=_egress_target())
    payload = _status_view(permitted, idempotency_key="permitted-source").model_dump(mode="json")
    resolver = deny_resolver(FlowSinkToggles(capability_disposition=Disposition.DENY))
    plane = sem233_plane(resolver, target=_egress_target())
    with pytest.raises(PermissionError, match="not permitted"):
        _status_view(plane, idempotency_key="racing-egress")
    operation_id = plane.audit_log()[-1].operation_id
    incumbent = plane._store.load_records()[operation_id]
    resolver.toggles = FlowSinkToggles()

    # Model another writer winning the claim after this call prepared a permit.
    # Even an incumbent with a stray legacy payload cannot authorize release.
    monkeypatch.setattr(participant_crossing_egress, "commit_prepared_crossing", lambda *_args: incumbent.receipt)
    original_load = plane._store.load_records
    monkeypatch.setattr(
        plane._store,
        "load_records",
        lambda: {**original_load(), operation_id: replace(incumbent, result_payload=payload)},
    )

    with pytest.raises(PermissionError, match="not permitted"):
        _status_view(plane, idempotency_key="racing-egress")


def test_denied_egress_remains_failed_after_local_store_reopen(tmp_path: Path) -> None:
    store_path = tmp_path / "denied-egress"
    resolver = deny_resolver(FlowSinkToggles(capability_disposition=Disposition.DENY))
    first = sem233_plane(
        resolver,
        target=_egress_target(),
        store=LocalControlPlaneStore(store_path),
    )
    with pytest.raises(PermissionError, match="not permitted"):
        _status_view(first, idempotency_key="denied-egress-reopen")
    audit = first.audit_log()[-1]
    audits = first.audit_log()
    history = first.snapshot.participant_crossing_history[PARTICIPANT]
    first.close()

    reopened_resolver = deny_resolver(FlowSinkToggles(capability_disposition=Disposition.DENY))
    reopened_resolver.subjects = list(resolver.subjects)
    reopened_resolver.evidence_refs = set(resolver.evidence_refs)
    reopened = RuntimeControlPlane(
        _egress_target(),
        store=LocalControlPlaneStore(store_path),
        crossing_policy_resolver=reopened_resolver,
    )
    try:
        with pytest.raises(PermissionError, match="not permitted"):
            _status_view(reopened, idempotency_key="denied-egress-reopen")
        assert _operation_status(reopened, audit.operation_id).state is OperationState.FAILED
        assert reopened.audit_log() == audits
        assert reopened.snapshot.participant_crossing_history[PARTICIPANT] == history
        assert reopened._store.load_records()[audit.operation_id].result_payload is None
    finally:
        reopened.close()


@pytest.mark.parametrize("toggles", _NON_PERMIT_TOGGLES)
def test_non_permit_control_ingress_applies_no_transition(toggles: FlowSinkToggles) -> None:
    specification = control_specification()
    plane = RuntimeControlPlane(
        policy_capable_target("participant_ingress_admission", "participant_intervention"),
        behavior_specifications={specification.address: specification},
        crossing_policy_resolver=deny_resolver(toggles),
    )

    receipt = plane.record_participant_control(
        PARTICIPANT,
        _handoff_intent(specification),
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="deny-control",
    )

    assert receipt.accepted is True
    assert _operation_status(plane, receipt.operation_id).state is OperationState.FAILED
    assert plane.snapshot.participant_control_history == {}
    assert len(plane.snapshot.participant_crossing_history[PARTICIPANT]) == 2
    assert _no_secret_leak(plane, receipt)


# --- Sink-kind binding and enforcement configuration ---------------------


def test_permit_bound_to_a_different_sink_kind_is_denied() -> None:
    # A resolver can return a validator-valid permit whose sink coordinate names
    # another sink kind (here PARTICIPANT_OUTPUT) than the ACTION_ARGUMENT sink
    # actually being admitted. Passing sink_kind into the resolver is not an
    # enforcement boundary; the runtime must reject the effect unless the
    # decision's own sink kind matches the concrete sink being invoked.
    target = policy_capable_target()
    counter = _instrument_backend(target)
    resolver = deny_resolver(FlowSinkToggles(relation_sink_kind=ParticipantFlowSinkKind.PARTICIPANT_OUTPUT))
    plane = sem233_plane(resolver, target=target)

    receipt = admit(plane, idempotency_key="wrong-sink-kind")

    assert receipt.accepted is True
    status = _operation_status(plane, receipt.operation_id)
    assert status.state is OperationState.FAILED
    assert counter["calls"] == 0
    assert status.diagnostics[0].code == "runtime.participant-flow-sink-denied"


def test_secure_default_requires_flow_sink_resolver_capability() -> None:
    # Final-sink enforcement is fail-closed by default: a policy-governing control
    # plane refuses to construct with a resolver that cannot resolve the SEM-233
    # permit, rather than silently admitting effects with no final-sink decision.
    target = policy_capable_target("participant_ingress_admission")
    resolver = StaticCrossingResolver()
    with pytest.raises(ValueError, match="resolve_flow_sink_decision"):
        RuntimeControlPlane(target, crossing_policy_resolver=resolver)


# --- Idempotency and replay ----------------------------------------------


def test_idempotent_replay_returns_stored_receipt_without_second_backend_call() -> None:
    target = policy_capable_target()
    counter = _instrument_backend(target)
    plane = sem233_plane(permit_resolver(), target=target)

    first = admit(plane, idempotency_key="replay")
    retry = admit(plane, idempotency_key="replay")

    assert retry.operation_id == first.operation_id
    assert counter["calls"] == 1
    assert len(plane.snapshot.participant_crossing_history[PARTICIPANT]) == 2


def test_replay_after_state_cut_advance_is_rejected() -> None:
    plane = sem233_plane(permit_resolver())

    admit(plane, idempotency_key="cut-bound")
    admit(
        plane,
        request=admission_request(action_instance_id="later"),
        idempotency_key="later",
    )

    with pytest.raises(ValueError, match="idempotency claim conflicts with the original request"):
        admit(plane, idempotency_key="cut-bound")


# --- Both stores and restart ---------------------------------------------


@pytest.mark.parametrize(
    "make_store", [lambda _p: InMemoryControlPlaneStore(), lambda p: LocalControlPlaneStore(p / "cp")]
)
def test_permit_and_denial_hold_across_both_stores(make_store, tmp_path: Path) -> None:
    permit_plane = sem233_plane(permit_resolver(), store=make_store(tmp_path / "permit"))
    assert admit(permit_plane, idempotency_key="store-permit").accepted is True

    deny_plane = sem233_plane(
        deny_resolver(FlowSinkToggles(capability_disposition=Disposition.DENY)),
        store=make_store(tmp_path / "deny"),
    )
    denied = admit(deny_plane, idempotency_key="store-deny")
    assert denied.accepted is True
    assert _operation_status(deny_plane, denied.operation_id).state is OperationState.FAILED
    assert deny_plane.snapshot.participant_behavior_history == {}


def test_local_store_restart_revalidates_and_replays_idempotently(tmp_path: Path) -> None:
    store_path = tmp_path / "control-plane"
    resolver = permit_resolver()
    first = sem233_plane(resolver, store=LocalControlPlaneStore(store_path))
    receipt = admit(first, idempotency_key="restart")
    first.close()

    restarted_resolver = Sem233FlowSinkResolver()
    restarted_resolver.subjects = list(resolver.subjects)
    restarted_resolver.evidence_refs = set(resolver.evidence_refs)
    restarted = RuntimeControlPlane(
        policy_capable_target(),
        store=LocalControlPlaneStore(store_path),
        crossing_policy_resolver=restarted_resolver,
    )

    retry = admit(restarted, idempotency_key="restart")

    assert retry.operation_id == receipt.operation_id
    assert len(restarted.snapshot.participant_crossing_history[PARTICIPANT]) == 2
    restarted.close()


# --- Legacy path and commit-before-effect --------------------------------


def test_legacy_resolver_without_flow_sink_hook_admits_normally() -> None:
    target = policy_capable_target()
    counter = _instrument_backend(target)
    plane = action_plane(StaticCrossingResolver(), target=target)

    receipt = admit(plane, idempotency_key="legacy")

    assert receipt.accepted is True
    assert counter["calls"] == 1
    assert not any(key.startswith("flow_sink") for key in plane.audit_log()[-1].details)


class _FailingCommitStore(InMemoryControlPlaneStore):
    def commit_participant_transition(self, **kwargs: object) -> None:
        del kwargs
        raise RuntimeError("injected atomic write failure")


def test_denied_egress_commit_failure_writes_no_terminal_audit_or_history() -> None:
    plane = sem233_plane(
        deny_resolver(FlowSinkToggles(capability_disposition=Disposition.DENY)),
        target=_egress_target(),
        store=_FailingCommitStore(),
    )
    prior_audits = plane.audit_log()

    with pytest.raises(RuntimeError, match="atomic write failure"):
        _status_view(plane, idempotency_key="denied-egress-atomic")

    assert plane._store.read_audit() == prior_audits
    assert plane._store.load_snapshot().participant_crossing_history == {}


def test_commit_before_effect_failing_store_never_dispatches_backend() -> None:
    target = policy_capable_target()
    counter = _instrument_backend(target)
    plane = sem233_plane(permit_resolver(), store=_FailingCommitStore(), target=target)

    with pytest.raises(RuntimeError, match="atomic write failure"):
        admit(plane, idempotency_key="failing")

    assert counter["calls"] == 0
    assert plane.snapshot.participant_crossing_history == {}
    assert plane.snapshot.participant_behavior_history == {}


def _handoff_intent(specification: object) -> ParticipantHandoffControlIntent:
    return ParticipantHandoffControlIntent(
        declaration_ref=specification.control_transitions[0].address,
        episode_id="episode-1",
        client_correlation_id="handoff-1003",
        policy_revision="1.0.0",
        expected_state_revision=0,
        provenance_refs=["provenance:handoff"],
        evidence_refs=["evidence:handoff"],
        object_marking_refs=["marking:participant-control"],
        limitation_refs=["limitation:none"],
        completion_evidence_ref="evidence:handoff",
    )
