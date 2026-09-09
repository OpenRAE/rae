"""RUN-310 observable supervisory lifecycle tests."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from raes.participant_behavior_specification import MixedControlTransitionKind
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.planning import RuntimeDomain
from raes_contracts.runtime_state import (
    OperationAdmissionContext,
    OperationKind,
    OperationReceipt,
    OperationState,
    OperationStatus,
    RuntimeSnapshot,
)
from raes_processor.models import (
    MixedControlControllerStateRuntime,
    MixedControlDispositionRulesRuntime,
    MixedControlTransitionRuntime,
    ParticipantBehaviorSpecificationRuntime,
)
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api import create_control_plane_app
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ControlPlaneSecurityConfig,
    ParticipantControlSubjectBinding,
)
from raes_runtime.control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    InMemoryControlPlaneStore,
    LocalControlPlaneStore,
)
from raes_runtime.participant_control import (
    ParticipantApprovalControlIntent,
    ParticipantCancellationControlIntent,
    ParticipantDenialControlIntent,
    ParticipantExternalDirectionControlIntent,
    ParticipantHandoffControlIntent,
    ParticipantInterventionControlIntent,
    ParticipantOverrideControlIntent,
    ParticipantProposalControlIntent,
)
from raes_runtime.participant_result_contracts import (
    participant_runtime_history_transition_diagnostics,
    participant_runtime_state_contract_diagnostics,
)
from starlette.testclient import TestClient


def _control_event(event_id: str, *, revision: int = 1) -> dict[str, object]:
    return {
        "event_id": event_id,
        "schema_name": "participant-control-occurrence",
        "schema_version": "1.0.0",
        "event_type": "participant-control-occurrence",
        "extension_policy": "closed",
        "participant_address": "participant.behavior.red-agent",
        "episode_id": "episode-1",
        "occurred_at": "2026-07-26T10:00:00Z",
        "recorded_at": "2026-07-26T10:00:00Z",
        "ingested_at": "2026-07-26T10:00:00Z",
        "clock_authority": "runtime.control-plane.clock",
        "ordering_basis": "logical_clock",
        "logical_order_ref": f"order:{revision}",
        "actor_ref": "participant.behavior.supervisor",
        "producer_ref": "runtime.control-plane.test",
        "provenance_refs": ["provenance:test"],
        "evidence_refs": ["evidence:test"],
        "object_marking_refs": ["marking:test"],
        "authorization_scope": "nodes.web",
        "occurrence": {
            "kind": "handoff",
            "declaration_ref": "participant.behavior-specification.controlled.control-transition.handoff",
            "controller_ref": "participant.behavior.supervisor",
            "controller_state_ref": "participant.behavior-specification.controlled.controller-state.autonomous",
            "authority_basis_refs": ["entities.red-team"],
            "controlled_scope_refs": ["nodes.web"],
            "behavior_specification_ref": "participant.behavior-specification.controlled",
            "mixed_control_policy_ref": "participant.behavior-specification.controlled",
            "policy_revision": "1.0.0",
            "expected_state_revision": 0,
            "effective_order": 1,
            "valid_from_order": 0,
            "valid_until_order": 10,
            "occurrence_revision": revision,
            "disposition": "accepted",
            "limitation_refs": ["limitation:none"],
            "prior_controller_state_ref": ("participant.behavior-specification.controlled.controller-state.autonomous"),
            "resulting_controller_state_ref": (
                "participant.behavior-specification.controlled.controller-state.supervised"
            ),
            "resulting_state_revision": 1,
            "completion_evidence_ref": "evidence:handoff",
        },
    }


def _operation_record(operation_id: str = "operation-1") -> ControlPlaneOperationRecord:
    context = OperationAdmissionContext(
        actor_id="operator",
        authorization_scope=("role:operator",),
        target_scope="target:stub",
        run_scope="run:test",
        operation_kind=OperationKind.PARTICIPANT_CONTROL,
        request_commitment=f"sha256:{'a' * 64}",
    )
    return ControlPlaneOperationRecord(
        receipt=OperationReceipt(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            submitted_at="2026-07-26T10:00:00Z",
            accepted=True,
            context=context,
        ),
        status=OperationStatus(
            operation_id=operation_id,
            domain=RuntimeDomain.PARTICIPANT,
            state=OperationState.SUCCEEDED,
            submitted_at="2026-07-26T10:00:00Z",
            updated_at="2026-07-26T10:00:00Z",
            context=context,
            changed_addresses=["participant.behavior.red-agent"],
        ),
        request_fingerprint="fingerprint-1",
        idempotency_key="scope-key-1",
    )


def _audit_event(operation_id: str = "operation-1") -> AuditEvent:
    return AuditEvent(
        timestamp="2026-07-26T10:00:00Z",
        action="record_participant_control",
        identity="operator",
        allowed=True,
        target="participant.behavior.red-agent",
        operation_id=operation_id,
        reason="accepted",
    )


_PARTICIPANT = "participant.behavior.red-agent"
_SPEC_ADDRESS = "participant.behavior-specification.controlled"
_AUTONOMOUS = f"{_SPEC_ADDRESS}.controller-state.autonomous"
_SUPERVISED = f"{_SPEC_ADDRESS}.controller-state.supervised"
_CONTROLLER = "participant.behavior.supervisor"


def _compiled_specification() -> ParticipantBehaviorSpecificationRuntime:
    autonomous = MixedControlControllerStateRuntime(
        address=_AUTONOMOUS,
        name="autonomous",
        spec={},
        state_id="autonomous",
        controller_ref="supervisor",
        controller_address=_CONTROLLER,
        authority_basis_refs=("red-team",),
        authority_basis_addresses=("entities.red-team",),
        scope_refs=("web",),
        scope_addresses=("nodes.web",),
        policy_revision="1.0.0",
        valid_from_order=0,
        valid_until_order=20,
        authority_status="active",
        evidence_refs=("authority-evidence",),
        evidence_addresses=("evidence.authority",),
    )
    supervised = replace(
        autonomous,
        address=_SUPERVISED,
        name="supervised",
        state_id="supervised",
    )
    kinds = [
        MixedControlTransitionKind.PROPOSAL,
        MixedControlTransitionKind.APPROVAL,
        MixedControlTransitionKind.DENIAL,
        MixedControlTransitionKind.EXTERNAL_DIRECTION,
        MixedControlTransitionKind.INTERVENTION,
        MixedControlTransitionKind.HANDOFF,
        MixedControlTransitionKind.OVERRIDE,
        MixedControlTransitionKind.CANCELLATION,
    ]
    transitions = tuple(
        MixedControlTransitionRuntime(
            address=f"{_SPEC_ADDRESS}.control-transition.{kind.value}",
            name=kind.value,
            spec={},
            transition_id=kind.value,
            transition_kind=kind.value,
            from_state_address=_SUPERVISED if index > 5 else _AUTONOMOUS,
            to_state_address=_SUPERVISED if index >= 5 else _AUTONOMOUS,
            policy_revision="1.0.0",
            expected_state_revision=index,
            resulting_state_revision=index + 1,
            effective_order=index + 1,
            valid_from_order=0,
            valid_until_order=20,
            proposal_address=f"{_SPEC_ADDRESS}.control-transition.proposal" if index else "",
            proposal_revision=1 if index else None,
            evidence_refs=("transition-evidence",),
            evidence_addresses=("evidence.transition",),
            completion_evidence_refs=("handoff-evidence",) if kind is MixedControlTransitionKind.HANDOFF else (),
            completion_evidence_addresses=("evidence.handoff",) if kind is MixedControlTransitionKind.HANDOFF else (),
        )
        for index, kind in enumerate(kinds)
    )
    return ParticipantBehaviorSpecificationRuntime(
        address=_SPEC_ADDRESS,
        name="controlled",
        spec={},
        spec_name="controlled",
        participant_addresses=(_PARTICIPANT,),
        behavior_mode="mixed-control",
        mixed_control_participant_address=_PARTICIPANT,
        mixed_control_policy_revision="1.0.0",
        mixed_control_order_strategy="total-effective-order",
        mixed_control_initial_state_address=_AUTONOMOUS,
        mixed_control_dispositions=MixedControlDispositionRulesRuntime(
            duplicate="idempotent",
            stale="reject",
            revoked="reject",
            late="reject",
            concurrent="reject",
            conflict="reject",
        ),
        controller_states=(autonomous, supervised),
        control_transitions=transitions,
    )


def _single_transition_specification(kind: MixedControlTransitionKind) -> ParticipantBehaviorSpecificationRuntime:
    specification = _compiled_specification()
    transition = next(
        candidate for candidate in specification.control_transitions if candidate.transition_kind == kind.value
    )
    return replace(
        specification,
        control_transitions=(
            replace(
                transition,
                from_state_address=_AUTONOMOUS,
                to_state_address=_AUTONOMOUS,
                expected_state_revision=0,
                resulting_state_revision=1,
                effective_order=1,
            ),
        ),
    )


def _identity(*, bound: bool = True) -> ControlPlaneIdentity:
    return ControlPlaneIdentity(
        identity="operator",
        roles=frozenset({ControlPlaneRole.OPERATOR}),
        target_name="stub",
        participant_control_subjects=(
            ParticipantControlSubjectBinding(
                participant_address=_PARTICIPANT,
                controller_ref=_CONTROLLER,
            ),
        )
        if bound
        else (),
    )


def _base_intent_fields(kind: str, expected_revision: int) -> dict[str, object]:
    return {
        "declaration_ref": f"{_SPEC_ADDRESS}.control-transition.{kind}",
        "episode_id": "episode-1",
        "client_correlation_id": f"correlation-{kind}",
        "policy_revision": "1.0.0",
        "expected_state_revision": expected_revision,
        "provenance_refs": ["provenance:test"],
        "evidence_refs": ["evidence:test"],
        "object_marking_refs": ["marking:test"],
        "limitation_refs": ["limitation:none"],
    }


def test_runtime_snapshot_preserves_first_class_control_history() -> None:
    event = _control_event("control-event-1")
    snapshot = RuntimeSnapshot(participant_control_history={"participant.behavior.red-agent": [event]})

    updated = snapshot.with_entries(dict(snapshot.entries))

    assert updated.participant_control_history == {"participant.behavior.red-agent": [event]}


@pytest.mark.parametrize("store_kind", ["memory", "local"])
def test_control_history_round_trips_through_control_plane_store(
    store_kind: str,
    tmp_path: Path,
) -> None:
    store = (
        InMemoryControlPlaneStore() if store_kind == "memory" else LocalControlPlaneStore(tmp_path / "control-plane")
    )
    snapshot = RuntimeSnapshot(
        participant_control_history={"participant.behavior.red-agent": [_control_event("control-event-1")]}
    )

    store.save_snapshot(snapshot, expected_revision=store.load_snapshot_state().revision)

    assert store.load_snapshot().participant_control_history == snapshot.participant_control_history


def test_control_history_snapshot_rejects_cross_participant_and_revision_gaps() -> None:
    event = _control_event("control-event-1", revision=2)
    snapshot = RuntimeSnapshot(participant_control_history={"participant.behavior.other-agent": [event]})

    diagnostics = participant_runtime_state_contract_diagnostics(snapshot)

    assert diagnostics
    assert all(diagnostic.code == "runtime.backend-contract-invalid" for diagnostic in diagnostics)
    assert any("map key" in diagnostic.message for diagnostic in diagnostics)
    assert any("occurrence_revision" in diagnostic.message for diagnostic in diagnostics)


def test_control_history_transition_rejects_rewrite_of_prior_occurrence() -> None:
    original = _control_event("control-event-1")
    rewritten = _control_event("control-event-rewritten")
    previous = RuntimeSnapshot(participant_control_history={"participant.behavior.red-agent": [original]})
    next_snapshot = RuntimeSnapshot(participant_control_history={"participant.behavior.red-agent": [rewritten]})

    diagnostics = participant_runtime_history_transition_diagnostics(previous, next_snapshot)

    assert diagnostics
    assert any("append-only prefix" in diagnostic.message for diagnostic in diagnostics)


@pytest.mark.parametrize("store_kind", ["memory", "local"])
def test_atomic_control_transition_commit_checks_head_and_persists_all_outputs(
    store_kind: str,
    tmp_path: Path,
) -> None:
    store = (
        InMemoryControlPlaneStore() if store_kind == "memory" else LocalControlPlaneStore(tmp_path / "control-plane")
    )
    event = _control_event("control-event-1")
    snapshot = RuntimeSnapshot(participant_control_history={"participant.behavior.red-agent": [event]})
    record = _operation_record()
    audit = _audit_event()

    store.claim_record(
        replace(
            record,
            status=replace(record.status, state=OperationState.RUNNING, changed_addresses=[]),
        )
    )
    store.commit_control_transition(
        participant_address="participant.behavior.red-agent",
        expected_head=None,
        snapshot=snapshot,
        record=record,
        audit_event=audit,
        expected_revision=store.load_snapshot_state().revision,
    )

    restarted = store if store_kind == "memory" else LocalControlPlaneStore(tmp_path / "control-plane")
    assert restarted.load_snapshot().participant_control_history == snapshot.participant_control_history
    assert restarted.load_records()[record.receipt.operation_id] == record
    assert restarted.find_by_idempotency(record.idempotency_key) == record
    assert restarted.read_audit() == [audit]

    conflicting = RuntimeSnapshot(
        participant_control_history={
            "participant.behavior.red-agent": [
                event,
                _control_event("control-event-2", revision=2),
            ]
        }
    )
    conflicting_record = replace(record, idempotency_key="scope-key-2")
    conflicting_audit = replace(audit, operation_id="operation-2")
    revision = restarted.load_snapshot_state().revision
    with pytest.raises(ValueError, match="expected control history head"):
        restarted.commit_control_transition(
            participant_address="participant.behavior.red-agent",
            expected_head=None,
            snapshot=conflicting,
            record=conflicting_record,
            audit_event=conflicting_audit,
            expected_revision=revision,
        )

    assert restarted.load_snapshot().participant_control_history == snapshot.participant_control_history


def test_supervisory_lifecycle_records_every_control_kind_without_dispatch() -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        behavior_specifications={_SPEC_ADDRESS: _compiled_specification()},
    )
    intents = [
        ParticipantProposalControlIntent(
            **_base_intent_fields("proposal", 0),
            proposal_id="proposal-1",
            proposal_revision=1,
            action_contract_ref="action-contract:contain-host",
            payload_ref="payload:proposal-1",
        ),
        ParticipantApprovalControlIntent(
            **_base_intent_fields("approval", 1),
            proposal_ref="proposal-1",
            proposal_revision=1,
            decision_ref="decision-approval-1",
            decision_revision=1,
        ),
        ParticipantDenialControlIntent(
            **_base_intent_fields("denial", 2),
            proposal_ref="proposal-1",
            proposal_revision=1,
            decision_ref="decision-denial-1",
            decision_revision=1,
        ),
        ParticipantExternalDirectionControlIntent(
            **_base_intent_fields("external-direction", 3),
            target_kind="control",
            target_ref="pending-control-target",
            target_revision=1,
        ),
        ParticipantInterventionControlIntent(
            **_base_intent_fields("intervention", 4),
            affected_target_kind="control",
            affected_occurrence_ref="pending-control-target",
            affected_revision=1,
            intervention_ref="intervention-1",
        ),
        ParticipantHandoffControlIntent(
            **_base_intent_fields("handoff", 5),
            completion_evidence_ref="evidence:handoff",
        ),
        ParticipantOverrideControlIntent(
            **_base_intent_fields("override", 6),
            superseded_target_kind="decision",
            superseded_occurrence_ref="decision-approval-1",
            superseded_revision=1,
            replacement_ref="decision-override-1",
        ),
        ParticipantCancellationControlIntent(
            **_base_intent_fields("cancellation", 7),
            target_kind="decision",
            target_ref="decision-denial-1",
            target_revision=1,
        ),
    ]

    receipts = []
    for index, intent in enumerate(intents):
        history = control_plane.snapshot.participant_control_history.get(_PARTICIPANT, [])
        if isinstance(intent, ParticipantExternalDirectionControlIntent):
            intent = intent.model_copy(update={"target_ref": history[0]["event_id"]})
        elif isinstance(intent, ParticipantInterventionControlIntent):
            intent = intent.model_copy(
                update={
                    "affected_occurrence_ref": history[-1]["event_id"],
                    "affected_revision": history[-1]["occurrence"]["occurrence_revision"],
                }
            )
        receipts.append(
            control_plane.record_participant_control(
                _PARTICIPANT,
                intent,
                identity=_identity(),
                idempotency_key=f"key-{index}",
            )
        )

    history = control_plane.snapshot.participant_control_history[_PARTICIPANT]
    assert [receipt.accepted for receipt in receipts] == [True] * len(receipts)
    assert [event["occurrence"]["kind"] for event in history] == [
        kind.value
        for kind in (
            MixedControlTransitionKind.PROPOSAL,
            MixedControlTransitionKind.APPROVAL,
            MixedControlTransitionKind.DENIAL,
            MixedControlTransitionKind.EXTERNAL_DIRECTION,
            MixedControlTransitionKind.INTERVENTION,
            MixedControlTransitionKind.HANDOFF,
            MixedControlTransitionKind.OVERRIDE,
            MixedControlTransitionKind.CANCELLATION,
        )
    ]
    assert all(event["occurrence"]["disposition"] == "accepted" for event in history)


def test_supervisory_control_is_subject_bound_idempotent_and_state_revision_bound() -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        behavior_specifications={_SPEC_ADDRESS: _compiled_specification()},
    )
    intent = ParticipantProposalControlIntent(
        **_base_intent_fields("proposal", 0),
        proposal_id="proposal-1",
        proposal_revision=1,
        action_contract_ref="action-contract:contain-host",
        payload_ref="payload:proposal-1",
    )

    unbound_identity = _identity(bound=False)
    with pytest.raises(PermissionError, match="subject"):
        control_plane.record_participant_control(
            _PARTICIPANT,
            intent,
            identity=unbound_identity,
            idempotency_key="key-1",
        )
    assert not control_plane.snapshot.participant_control_history
    other_target_identity = replace(_identity(), target_name="other-target")
    with pytest.raises(PermissionError, match="target"):
        control_plane.record_participant_control(
            _PARTICIPANT,
            intent,
            identity=other_target_identity,
            idempotency_key="key-target",
        )
    assert not control_plane.snapshot.participant_control_history

    first = control_plane.record_participant_control(
        _PARTICIPANT,
        intent,
        identity=_identity(),
        idempotency_key="key-1",
    )
    retry = control_plane.record_participant_control(
        _PARTICIPANT,
        intent,
        identity=_identity(),
        idempotency_key="key-1",
    )
    assert retry.operation_id == first.operation_id
    assert len(control_plane.snapshot.participant_control_history[_PARTICIPANT]) == 1

    changed = intent.model_copy(update={"proposal_id": "proposal-2"})
    changed_identity = _identity()
    with pytest.raises(ValueError, match="different semantics"):
        control_plane.record_participant_control(
            _PARTICIPANT,
            changed,
            identity=changed_identity,
            idempotency_key="key-1",
        )

    stale = ParticipantApprovalControlIntent(
        **_base_intent_fields("approval", 0),
        proposal_ref="proposal-1",
        proposal_revision=1,
        decision_ref="decision-stale-1",
        decision_revision=1,
    )
    rejected = control_plane.record_participant_control(
        _PARTICIPANT,
        stale,
        identity=_identity(),
        idempotency_key="key-stale",
    )
    assert rejected.accepted is True
    assert control_plane.get_operation(rejected.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    assert (
        control_plane.snapshot.participant_control_history[_PARTICIPANT][-1]["occurrence"]["reason_code"]
        == "stale-state"
    )


@pytest.mark.parametrize(
    ("failure", "reason_code"),
    [
        ("stale-policy", "stale-policy"),
        ("revoked-authority", "revoked-authority"),
        ("late-authority", "late-authority"),
        ("unsupported-order", "unsupported-order-strategy"),
    ],
)
def test_supervisory_control_records_bounded_policy_and_authority_rejections(
    failure: str,
    reason_code: str,
) -> None:
    specification = _compiled_specification()
    intent_fields = _base_intent_fields("proposal", 0)
    if failure == "stale-policy":
        intent_fields["policy_revision"] = "2.0.0"
    elif failure == "revoked-authority":
        state = replace(specification.controller_states[0], authority_status="revoked")
        specification = replace(
            specification,
            controller_states=(state, *specification.controller_states[1:]),
        )
    elif failure == "late-authority":
        state = replace(specification.controller_states[0], valid_until_order=0)
        specification = replace(
            specification,
            controller_states=(state, *specification.controller_states[1:]),
        )
    else:
        specification = replace(
            specification,
            mixed_control_order_strategy="causal-partial-order",
        )
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        behavior_specifications={_SPEC_ADDRESS: specification},
    )
    intent = ParticipantProposalControlIntent(
        **intent_fields,
        proposal_id="proposal-1",
        proposal_revision=1,
        action_contract_ref="action-contract:contain-host",
        payload_ref="payload:proposal-1",
    )

    receipt = control_plane.record_participant_control(
        _PARTICIPANT,
        intent,
        identity=_identity(),
        idempotency_key=f"key-{failure}",
    )

    assert receipt.accepted is True
    assert control_plane.get_operation(receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    event = control_plane.snapshot.participant_control_history[_PARTICIPANT][-1]
    assert event["occurrence"]["reason_code"] == reason_code
    assert "2.0.0" not in str(receipt.diagnostics)


def test_supervisory_control_restarts_and_replays_before_the_next_transition(
    tmp_path: Path,
) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    specification = _compiled_specification()
    first = RuntimeControlPlane(
        create_stub_target(),
        store=store,
        behavior_specifications={_SPEC_ADDRESS: specification},
    )
    proposal = ParticipantProposalControlIntent(
        **_base_intent_fields("proposal", 0),
        proposal_id="proposal-1",
        proposal_revision=1,
        action_contract_ref="action-contract:contain-host",
        payload_ref="payload:proposal-1",
    )
    assert first.record_participant_control(
        _PARTICIPANT,
        proposal,
        identity=_identity(),
        idempotency_key="key-proposal",
    ).accepted
    first.close()

    restarted = RuntimeControlPlane(
        create_stub_target(),
        store=LocalControlPlaneStore(tmp_path / "control-plane"),
        behavior_specifications={_SPEC_ADDRESS: specification},
    )
    approval = ParticipantApprovalControlIntent(
        **_base_intent_fields("approval", 1),
        proposal_ref="proposal-1",
        proposal_revision=1,
        decision_ref="decision-approval-1",
        decision_revision=1,
    )

    assert restarted.record_participant_control(
        _PARTICIPANT,
        approval,
        identity=_identity(),
        idempotency_key="key-approval",
    ).accepted
    assert len(restarted.snapshot.participant_control_history[_PARTICIPANT]) == 2
    restarted.close()


def test_controller_state_replay_is_scoped_to_one_episode() -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        behavior_specifications={_SPEC_ADDRESS: _single_transition_specification(MixedControlTransitionKind.PROPOSAL)},
    )
    first = ParticipantProposalControlIntent(
        **_base_intent_fields("proposal", 0),
        proposal_id="proposal-episode-1",
        proposal_revision=1,
        action_contract_ref="action-contract:contain-host",
        payload_ref="payload:proposal-episode-1",
    )
    second = first.model_copy(
        update={
            "episode_id": "episode-2",
            "proposal_id": "proposal-episode-2",
            "payload_ref": "payload:proposal-episode-2",
        }
    )

    assert control_plane.record_participant_control(
        _PARTICIPANT,
        first,
        identity=_identity(),
        idempotency_key="key-episode-1",
    ).accepted
    assert control_plane.record_participant_control(
        _PARTICIPANT,
        second,
        identity=_identity(),
        idempotency_key="key-episode-2",
    ).accepted


def _behavior_target_snapshot() -> RuntimeSnapshot:
    common = {
        "event_type": "action_attempted",
        "timestamp": "2026-07-26T10:00:00Z",
        "participant_address": _PARTICIPANT,
        "episode_id": "episode-1",
        "action_instance_id": "action-1",
        "action_contract_address": "participant.action-contract.contain-host",
        "actor_provenance": "participant:red-agent",
        "details": {},
    }
    return RuntimeSnapshot(
        participant_behavior_history={
            _PARTICIPANT: [
                {
                    **common,
                    "lifecycle_phase": "intent_or_proposal",
                    "phase_realization": "runtime_mediated",
                },
                {
                    **common,
                    "lifecycle_phase": "selection_or_admission",
                    "phase_realization": "runtime_mediated",
                    "admission_disposition": "admitted",
                },
                {
                    **common,
                    "lifecycle_phase": "execution_attempt",
                    "phase_realization": "runtime_mediated",
                    "operation_ref": "attempt-1",
                    "operation_state": "running",
                },
            ]
        }
    )


@pytest.mark.parametrize(
    ("kind", "target_kind", "target_ref"),
    [
        (MixedControlTransitionKind.EXTERNAL_DIRECTION, "action", "action-1"),
        (MixedControlTransitionKind.INTERVENTION, "attempt", "attempt-1"),
        (MixedControlTransitionKind.CANCELLATION, "admitted-action", "action-1"),
    ],
)
def test_typed_targets_resolve_authoritative_behavior_lifecycle_stages(
    kind: MixedControlTransitionKind,
    target_kind: str,
    target_ref: str,
) -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        initial_snapshot=_behavior_target_snapshot(),
        behavior_specifications={_SPEC_ADDRESS: _single_transition_specification(kind)},
    )
    fields = _base_intent_fields(kind.value, 0)
    if kind is MixedControlTransitionKind.EXTERNAL_DIRECTION:
        intent = ParticipantExternalDirectionControlIntent(
            **fields,
            target_kind=target_kind,
            target_ref=target_ref,
            target_revision=1,
        )
    elif kind is MixedControlTransitionKind.INTERVENTION:
        intent = ParticipantInterventionControlIntent(
            **fields,
            affected_target_kind=target_kind,
            affected_occurrence_ref=target_ref,
            affected_revision=1,
            intervention_ref="intervention-1",
        )
    else:
        intent = ParticipantCancellationControlIntent(
            **fields,
            target_kind=target_kind,
            target_ref=target_ref,
            target_revision=1,
        )

    receipt = control_plane.record_participant_control(
        _PARTICIPANT,
        intent,
        identity=_identity(),
        idempotency_key=f"key-{kind.value}",
    )

    assert receipt.accepted
    event = control_plane.snapshot.participant_control_history[_PARTICIPANT][-1]
    assert event["predecessor_event_refs"] == [target_ref]


def test_unresolved_typed_target_appends_a_bounded_rejection_without_fallback() -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        behavior_specifications={
            _SPEC_ADDRESS: _single_transition_specification(MixedControlTransitionKind.EXTERNAL_DIRECTION)
        },
    )
    intent = ParticipantExternalDirectionControlIntent(
        **_base_intent_fields("external-direction", 0),
        target_kind="action",
        target_ref="action-missing",
        target_revision=1,
    )

    receipt = control_plane.record_participant_control(
        _PARTICIPANT,
        intent,
        identity=_identity(),
        idempotency_key="key-missing-target",
    )

    assert receipt.accepted is True
    assert control_plane.get_operation(receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    event = control_plane.snapshot.participant_control_history[_PARTICIPANT][-1]
    assert event["occurrence"]["reason_code"] == "invalid-target"
    assert event["predecessor_event_refs"] == []


def test_failed_atomic_control_commit_exposes_no_partial_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalControlPlaneStore(tmp_path / "control-plane")
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        store=store,
        behavior_specifications={_SPEC_ADDRESS: _compiled_specification()},
    )
    intent = ParticipantProposalControlIntent(
        **_base_intent_fields("proposal", 0),
        proposal_id="proposal-1",
        proposal_revision=1,
        action_contract_ref="action-contract:contain-host",
        payload_ref="payload:proposal-1",
    )

    real_upsert = store._upsert_record

    def fail_record_upsert(
        connection: sqlite3.Connection,
        record: ControlPlaneOperationRecord,
    ) -> None:
        real_upsert(connection, record)
        raise OSError("commit failed")

    monkeypatch.setattr(store, "_upsert_record", fail_record_upsert)
    identity = _identity()
    with pytest.raises(OSError, match="commit failed"):
        control_plane.record_participant_control(
            _PARTICIPANT,
            intent,
            identity=identity,
            idempotency_key="key-1",
        )

    assert not control_plane.snapshot.participant_control_history
    restarted = LocalControlPlaneStore(tmp_path / "control-plane")
    assert not restarted.load_snapshot().participant_control_history
    assert not restarted.load_records()
    assert not restarted.read_audit()


def _api_security(*, bound: bool = True) -> ControlPlaneSecurityConfig:
    return ControlPlaneSecurityConfig(
        bearer_tokens={
            "operator-token": _identity(bound=bound),
        }
    )


def _proposal_body() -> dict[str, object]:
    return {
        "kind": "proposal",
        **_base_intent_fields("proposal", 0),
        "proposal_id": "proposal-1",
        "proposal_revision": 1,
        "action_contract_ref": "action-contract:contain-host",
        "payload_ref": "payload:proposal-1",
    }


def test_supervisory_http_route_is_closed_subject_bound_and_idempotent() -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        behavior_specifications={_SPEC_ADDRESS: _compiled_specification()},
    )
    app = create_control_plane_app(control_plane, security=_api_security())
    headers = {
        "authorization": "Bearer operator-token",
        "idempotency-key": "key-1",
    }

    with TestClient(app) as client:
        first = client.post(
            f"/participants/{_PARTICIPANT}/control-occurrences",
            json=_proposal_body(),
            headers=headers,
        )
        retry = client.post(
            f"/participants/{_PARTICIPANT}/control-occurrences",
            json=_proposal_body(),
            headers=headers,
        )
        smuggled = client.post(
            f"/participants/{_PARTICIPANT}/control-occurrences",
            json={**_proposal_body(), "disposition": "accepted"},
            headers={**headers, "idempotency-key": "key-2"},
        )
        invalid_target = client.post(
            f"/participants/{_PARTICIPANT}/control-occurrences",
            json={
                "kind": "external-direction",
                **_base_intent_fields("external-direction", 1),
                "target_kind": "decision",
                "target_ref": "decision-1",
                "target_revision": 1,
            },
            headers={**headers, "idempotency-key": "key-3"},
        )

    assert first.status_code == 200
    assert retry.status_code == 200
    assert retry.json()["operation_id"] == first.json()["operation_id"]
    assert smuggled.status_code == 422
    assert invalid_target.status_code == 422
    assert len(control_plane.snapshot.participant_control_history[_PARTICIPANT]) == 1


def test_supervisory_http_route_rejects_unbound_subject_without_occurrence() -> None:
    control_plane = RuntimeControlPlane(
        create_stub_target(),
        behavior_specifications={_SPEC_ADDRESS: _compiled_specification()},
    )
    app = create_control_plane_app(control_plane, security=_api_security(bound=False))

    with TestClient(app) as client:
        known = client.post(
            f"/participants/{_PARTICIPANT}/control-occurrences",
            json=_proposal_body(),
            headers={"authorization": "Bearer operator-token"},
        )
        unknown = client.post(
            "/participants/participant.behavior.unknown/control-occurrences",
            json=_proposal_body(),
            headers={"authorization": "Bearer operator-token"},
        )

    assert known.status_code == 403
    assert unknown.status_code == 403
    assert known.json() == unknown.json() == {"detail": "forbidden"}
    assert not control_plane.snapshot.participant_control_history
