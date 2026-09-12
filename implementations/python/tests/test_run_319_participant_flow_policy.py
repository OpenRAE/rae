"""RUN-319 operation-bound participant information-flow enforcement tests."""

from __future__ import annotations

from pathlib import Path
from threading import Barrier, Thread

import pytest
from participant_crossing_fixtures import (
    PARTICIPANT,
    TRANSFORMED_ACTION,
    StaticCrossingResolver,
    TransformedActionResolver,
    TransformedEgressResolver,
    action_plane,
    admission_request,
    admit,
    behavior,
    control_specification,
    crossing_request,
    evidence,
    identity,
    policy_capable_target,
)
from pydantic import ValidationError
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingGateDisposition,
    ParticipantCrossingSubjectKind,
)
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot, RuntimeSnapshotEnvelope
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_api_models import _snapshot_model
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
)
from raes_runtime.control_plane_store import (
    InMemoryControlPlaneStore,
    LocalControlPlaneStore,
)
from raes_runtime.control_plane_store_snapshots import _snapshot_from_payload, _snapshot_payload
from raes_runtime.operational_apparatus import operational_apparatus_summary
from raes_runtime.participant_control_intents import ParticipantHandoffControlIntent
from raes_runtime.participant_crossing_boundary import _action_subject
from raes_runtime.participant_crossing_egress import _view_subject
from raes_runtime.participant_crossing_mediation import (
    ParticipantCrossingEvidence,
    ParticipantCrossingIntent,
    ParticipantCrossingPolicyResolution,
)
from raes_runtime.participant_result_contracts import (
    participant_runtime_history_transition_diagnostics,
    participant_runtime_state_contract_diagnostics,
)
from raes_runtime.participant_retrieval import _context_revision_paths, _ContextViewOptions


def test_crossing_history_is_first_class_serialized_and_operational_state() -> None:
    request = crossing_request()
    snapshot = RuntimeSnapshot(participant_crossing_history={PARTICIPANT: [request]})

    restored = _snapshot_from_payload(_snapshot_payload(snapshot))
    published = _snapshot_model(RuntimeSnapshotEnvelope(snapshot=snapshot))
    summary = operational_apparatus_summary(
        target_name="reference",
        snapshot=snapshot,
        operation_records=[],
        audit_events=[],
    )

    assert restored.participant_crossing_history == {PARTICIPANT: [request]}
    assert published.participant_crossing_history[PARTICIPANT][0].event_id == request["event_id"]
    assert summary["runtime_surfaces"]["participant_crossing_history"] == 1


def test_crossing_history_is_preserved_and_append_only() -> None:
    request = crossing_request()
    snapshot = RuntimeSnapshot(participant_crossing_history={PARTICIPANT: [request]})
    rewritten = RuntimeSnapshot(
        participant_crossing_history={
            PARTICIPANT: [{**request, "event_id": "crossing-occurrence.requested.rewritten"}]
        },
    )

    assert snapshot.with_entries({}).participant_crossing_history == snapshot.participant_crossing_history
    assert any(
        "append-only" in diagnostic.message
        for diagnostic in participant_runtime_history_transition_diagnostics(snapshot, rewritten)
    )
    invalid = RuntimeSnapshot(participant_crossing_history={"participants.other": [request]})
    assert any(
        "map key" in diagnostic.message for diagnostic in participant_runtime_state_contract_diagnostics(invalid)
    )


def test_caller_evidence_cannot_describe_the_protected_operation() -> None:
    payload = {
        **evidence().model_dump(mode="json"),
        "interaction_kind": "denial",
        "participant_address": "participant.attacker",
    }
    with pytest.raises(ValidationError, match="interaction_kind"):
        ParticipantCrossingEvidence.model_validate(payload)


def test_action_boundary_authorizes_and_finalizes_one_operation() -> None:
    resolver = StaticCrossingResolver()
    plane = action_plane(resolver)

    receipt = admit(plane)

    assert receipt.accepted is True
    assert len(plane.snapshot.participant_behavior_history[PARTICIPANT]) >= 2
    crossing = plane.snapshot.participant_crossing_history[PARTICIPANT]
    assert [item["occurrence"]["stage"] for item in crossing] == ["requested", "decided"]
    assert len(plane._operations) == 2  # episode initialization plus the combined action
    audit = plane.audit_log()[-1]
    assert audit.action == "admit_participant_action"
    assert audit.operation_id == receipt.operation_id
    assert audit.details["crossing_decision_id"] == crossing[-1]["occurrence"]["decision_id"]


def test_action_boundary_derives_exact_subject_and_semantics_from_request() -> None:
    resolver = StaticCrossingResolver()
    plane = action_plane(resolver)
    request = admission_request()

    admit(plane, request=request)

    resolved = resolver.seen_intents[0]
    assert resolved.interaction_kind.value == "action-proposal"
    assert resolved.action_or_projection_ref == request.action_contract_address
    assert resolved.subject == _action_subject(plane, request)
    assert resolved.participant_address == request.participant_address
    assert resolved.episode_id == "episode-1"


def test_configured_action_ingress_cannot_bypass_crossing_mediation() -> None:
    plane = action_plane(StaticCrossingResolver())
    participant_behavior = behavior()
    request = admission_request()
    caller = identity()

    with pytest.raises(ValueError, match="requires crossing evidence"):
        plane.admit_participant_action(
            participant_behavior,
            request,
            identity=caller,
        )

    assert plane.snapshot.participant_behavior_history == {}
    assert plane.snapshot.participant_crossing_history == {}


def test_policy_capable_target_requires_crossing_resolver_at_startup() -> None:
    target = policy_capable_target()
    with pytest.raises(ValueError, match="policy capabilities require a crossing policy resolver"):
        RuntimeControlPlane(target)


def test_unsupported_backend_never_executes_the_incumbent_action() -> None:
    resolver = StaticCrossingResolver()
    plane = action_plane(resolver, target=create_stub_target())

    receipt = admit(plane)

    assert receipt.accepted is True
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    assert plane.snapshot.participant_behavior_history == {}
    decision = plane.snapshot.participant_crossing_history[PARTICIPANT][-1]["occurrence"]
    assert decision["disposition"] == "unsupported"
    assert decision["gates"]["backend_support"] == "unsupported"


@pytest.mark.parametrize(
    "gate",
    ["participant_authority", "action_admission", "marking_authorization"],
)
def test_independent_ingress_gate_denials_do_not_execute_action(gate: str) -> None:
    resolver = StaticCrossingResolver(gate_overrides={gate: ParticipantCrossingGateDisposition.DENY})
    plane = action_plane(resolver)

    receipt = admit(plane, idempotency_key=f"denied-{gate}")

    assert receipt.accepted is True
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    assert plane.snapshot.participant_behavior_history == {}
    decision = plane.snapshot.participant_crossing_history[PARTICIPANT][-1]["occurrence"]
    assert decision["gates"][gate] == "deny"


def test_identity_denials_are_security_audited_without_participant_facts() -> None:
    plane = action_plane(StaticCrossingResolver())
    unbound = identity(bound=False)

    with pytest.raises(PermissionError, match="subject"):
        admit(plane, control_identity=unbound)

    assert plane.snapshot.participant_crossing_history == {}
    assert plane.snapshot.participant_behavior_history == {}
    assert plane.audit_log()[-1].reason == "subject-forbidden"
    assert plane.audit_log()[-1].details == {}


def test_operation_bound_idempotency_replays_neither_decision_nor_action() -> None:
    plane = action_plane(StaticCrossingResolver())

    first = admit(plane, idempotency_key="same-operation")
    retry = admit(plane, idempotency_key="same-operation")

    assert retry.operation_id == first.operation_id
    assert len(plane.snapshot.participant_crossing_history[PARTICIPANT]) == 2
    behavior_count = len(plane.snapshot.participant_behavior_history[PARTICIPANT])
    assert behavior_count >= 2
    different_request = admission_request(action_instance_id="different")
    with pytest.raises(ValueError, match="different semantics"):
        admit(
            plane,
            request=different_request,
            idempotency_key="same-operation",
        )
    assert len(plane.snapshot.participant_behavior_history[PARTICIPANT]) == behavior_count


def test_operation_bound_idempotency_rejects_replay_after_state_cut_advances() -> None:
    plane = action_plane(StaticCrossingResolver())

    admit(plane, idempotency_key="state-cut-bound")
    admit(
        plane,
        request=admission_request(action_instance_id="later-action"),
        idempotency_key="later-operation",
    )

    with pytest.raises(ValueError, match="state cut advanced"):
        admit(plane, idempotency_key="state-cut-bound")


def test_transformed_action_is_revalidated_and_the_governed_carrier_executes() -> None:
    resolver = TransformedActionResolver()
    plane = action_plane(
        resolver,
        target=policy_capable_target(
            "participant_ingress_admission",
            "participant_transformation",
        ),
    )

    receipt = admit(plane)

    assert receipt.accepted is True
    history = plane.snapshot.participant_crossing_history[PARTICIPANT]
    assert [item["occurrence"]["stage"] for item in history] == [
        "requested",
        "decided",
        "transformed",
        "requested",
        "decided",
    ]
    behavior = plane.snapshot.participant_behavior_history[PARTICIPANT]
    assert all(
        item.get("action_contract_address") == TRANSFORMED_ACTION
        for item in behavior
        if "action_contract_address" in item
    )


def test_fresh_denial_of_transformed_action_prevents_backend_execution() -> None:
    resolver = TransformedActionResolver(deny_fresh=True)
    plane = action_plane(
        resolver,
        target=policy_capable_target(
            "participant_ingress_admission",
            "participant_transformation",
        ),
    )

    receipt = admit(plane)

    assert receipt.accepted is True
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    assert plane.snapshot.participant_behavior_history == {}
    assert plane.snapshot.participant_crossing_history[PARTICIPANT][-1]["occurrence"]["disposition"] == "deny"


def _status_evidence_call(
    plane: RuntimeControlPlane,
    *,
    identity: ControlPlaneIdentity,
    idempotency_key: str,
):
    return plane.get_participant_status_view(
        PARTICIPANT,
        identity=identity,
        crossing_evidence=evidence(),
        idempotency_key=idempotency_key,
    )


def test_egress_requires_separate_audience_authority_and_commits_before_return() -> None:
    resolver = StaticCrossingResolver()
    plane = action_plane(
        resolver,
        target=policy_capable_target(
            "participant_egress_projection",
            "participant_transformation",
        ),
    )
    unbound_identity = identity()

    with pytest.raises(PermissionError, match="audience"):
        _status_evidence_call(plane, identity=unbound_identity, idempotency_key="egress-unbound")
    assert plane.snapshot.participant_crossing_history == {}

    view = _status_evidence_call(
        plane,
        identity=identity(audience_bound=True),
        idempotency_key="egress-bound",
    )

    assert view is not None
    assert view.participant_address == PARTICIPANT
    assert plane.snapshot.participant_crossing_history[PARTICIPANT][-1]["occurrence"]["disposition"] == "permit"
    assert plane.audit_log()[-1].operation_id in plane._operations


def test_egress_transformation_returns_only_the_committed_governed_view() -> None:
    resolver = TransformedEgressResolver()
    plane = action_plane(
        resolver,
        target=policy_capable_target(
            "participant_egress_projection",
            "participant_transformation",
        ),
    )

    view = _status_evidence_call(
        plane,
        identity=identity(audience_bound=True),
        idempotency_key="egress-redacted",
    )
    retry = _status_evidence_call(
        plane,
        identity=identity(audience_bound=True),
        idempotency_key="egress-redacted",
    )

    assert view is not None
    assert view.redaction_policy_ref == "policy:redacted-status"
    assert view.marking_definition_refs == ["marking:participant-control", "marking:redacted"]
    assert retry == view
    history = plane.snapshot.participant_crossing_history[PARTICIPANT]
    assert [item["occurrence"]["stage"] for item in history] == [
        "requested",
        "decided",
        "transformed",
    ]


@pytest.mark.parametrize("field", ["payload_ref", "derivation_basis_ref"])
def test_runtime_revision_normalization_preserves_caller_controlled_context_identity(field: str) -> None:
    resolver = StaticCrossingResolver()
    plane = action_plane(resolver)
    plane._crossing_policy_resolver = None

    first = plane.get_participant_context_view(
        PARTICIPANT,
        view_ref="context.network-posture",
        **{field: "runtime.snapshot.revision.7"},
    )
    second = plane.get_participant_context_view(
        PARTICIPANT,
        view_ref="context.network-posture",
        **{field: "runtime.snapshot.revision.8"},
    )
    assert first is not None
    assert second is not None
    revision_paths = _context_revision_paths(_ContextViewOptions())
    first_subject = _view_subject(
        first,
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        subject_kind=ParticipantCrossingSubjectKind.PARTICIPANT_CONTEXT_VIEW,
        runtime_owned_revision_paths=revision_paths,
    )
    second_subject = _view_subject(
        second,
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        subject_kind=ParticipantCrossingSubjectKind.PARTICIPANT_CONTEXT_VIEW,
        runtime_owned_revision_paths=revision_paths,
    )

    assert first_subject.subject_digest != second_subject.subject_digest


def test_missing_visibility_gate_fails_closed_without_serializing_output() -> None:
    resolver = StaticCrossingResolver(gate_overrides={"visibility": ParticipantCrossingGateDisposition.NOT_APPLICABLE})
    plane = action_plane(
        resolver,
        target=policy_capable_target(
            "participant_egress_projection",
            "participant_transformation",
        ),
    )
    audience_identity = identity(audience_bound=True)

    with pytest.raises(PermissionError, match="not permitted"):
        _status_evidence_call(
            plane,
            identity=audience_identity,
            idempotency_key="egress-no-visibility",
        )

    decision = plane.snapshot.participant_crossing_history[PARTICIPANT][-1]["occurrence"]
    assert decision["gates"]["visibility"] == "unknown"


def test_authorized_downgrade_records_only_effective_backend_strength() -> None:
    feature = "participant_ingress_admission"
    resolver = StaticCrossingResolver(allowed_downgrades={feature: ParticipantFeatureSupportLevel.BOUNDED})
    plane = action_plane(
        resolver,
        target=policy_capable_target(
            feature,
            support_level=ParticipantFeatureSupportLevel.BOUNDED,
        ),
    )

    receipt = admit(plane)

    assert receipt.accepted is True
    history = plane.snapshot.participant_crossing_history[PARTICIPANT]
    assert all(item["occurrence"]["backend_posture"] == "bounded" for item in history)


def test_supervisory_control_derives_handoff_semantics_and_commits_one_transition() -> None:
    resolver = StaticCrossingResolver()
    specification = control_specification()
    plane = RuntimeControlPlane(
        policy_capable_target(
            "participant_ingress_admission",
            "participant_intervention",
        ),
        behavior_specifications={specification.address: specification},
        crossing_policy_resolver=resolver,
        enforce_final_sink_flow_control=False,
    )
    intent = ParticipantHandoffControlIntent(
        declaration_ref=specification.control_transitions[0].address,
        episode_id="episode-1",
        client_correlation_id="handoff-1",
        policy_revision="1.0.0",
        expected_state_revision=0,
        provenance_refs=["provenance:handoff"],
        evidence_refs=["evidence:handoff"],
        object_marking_refs=["marking:participant-control"],
        limitation_refs=["limitation:none"],
        completion_evidence_ref="evidence:handoff",
    )

    receipt = plane.record_participant_control(
        PARTICIPANT,
        intent,
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="handoff",
    )

    assert receipt.accepted is True
    assert resolver.seen_intents[0].interaction_kind.value == "handoff"
    assert len(plane.snapshot.participant_control_history[PARTICIPANT]) == 1
    assert len(plane.snapshot.participant_crossing_history[PARTICIPANT]) == 2
    assert len(plane._operations) == 1

    stale = intent.model_copy(update={"client_correlation_id": "handoff-stale"})
    rejected = plane.record_participant_control(
        PARTICIPANT,
        stale,
        identity=identity(),
        crossing_evidence=evidence(),
        idempotency_key="handoff-stale",
    )

    assert rejected.accepted is True
    assert plane.get_operation(rejected.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    assert plane.audit_log()[-1].allowed is False
    assert plane.audit_log()[-1].reason == "stale-state"


def test_crossing_history_restarts_and_operation_replays_idempotently(tmp_path: Path) -> None:
    resolver = StaticCrossingResolver()
    store_path = tmp_path / "control-plane"
    first = action_plane(resolver, store=LocalControlPlaneStore(store_path))
    receipt = admit(first, idempotency_key="restart-crossing")
    first.close()

    restarted_resolver = StaticCrossingResolver()
    restarted_resolver.subjects = list(resolver.subjects)
    restarted_resolver.evidence_refs = set(resolver.evidence_refs)
    restarted = RuntimeControlPlane(
        policy_capable_target(),
        store=LocalControlPlaneStore(store_path),
        crossing_policy_resolver=restarted_resolver,
        enforce_final_sink_flow_control=False,
    )
    retry = admit(restarted, idempotency_key="restart-crossing")

    assert retry.operation_id == receipt.operation_id
    assert len(restarted.snapshot.participant_crossing_history[PARTICIPANT]) == 2
    restarted.close()


class _FailingCommitStore(InMemoryControlPlaneStore):
    def commit_participant_transition(self, **kwargs: object) -> None:
        del kwargs
        raise RuntimeError("injected atomic write failure")


def test_atomic_write_failure_leaves_backend_and_histories_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = StaticCrossingResolver()
    store = _FailingCommitStore()
    target = policy_capable_target()
    runtime = target.participant_runtime
    assert runtime is not None
    original = runtime.admit_action
    calls = 0

    def tracked_admit_action(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime, "admit_action", tracked_admit_action)
    plane = action_plane(resolver, store=store, target=target)

    with pytest.raises(RuntimeError, match="atomic write failure"):
        admit(plane)

    assert calls == 0
    assert plane.snapshot.participant_crossing_history == {}
    assert plane.snapshot.participant_behavior_history == {}
    assert store.load_snapshot().participant_crossing_history == {}
    assert store.load_snapshot().participant_behavior_history == {}


class _BarrierResolver(StaticCrossingResolver):
    def __init__(self, barrier: Barrier) -> None:
        super().__init__()
        self.barrier = barrier

    def resolve(
        self,
        intent: ParticipantCrossingIntent,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantCrossingPolicyResolution:
        resolution = super().resolve(intent, snapshot)
        # The full verification suite runs this test under xdist on a
        # CPU-constrained runner. Give the peer operation enough time to reach
        # the rendezvous even when its worker is temporarily descheduled.
        self.barrier.wait(timeout=30)
        return resolution


def test_concurrent_operation_cannot_commit_against_a_stale_history_cut() -> None:
    base = RuntimeControlPlane(
        policy_capable_target(),
        crossing_policy_resolver=StaticCrossingResolver(),
        enforce_final_sink_flow_control=False,
    )
    base.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
    store = base._store
    barrier = Barrier(2)
    planes = [
        RuntimeControlPlane(
            policy_capable_target(),
            store=store,
            crossing_policy_resolver=_BarrierResolver(barrier),
            enforce_final_sink_flow_control=False,
        )
        for _ in range(2)
    ]
    results: list[object] = []

    def run(index: int) -> None:
        try:
            results.append(
                admit(
                    planes[index],
                    request=admission_request(action_instance_id=f"concurrent-{index}"),
                    idempotency_key=f"concurrent-{index}",
                )
            )
        except Exception as exc:  # noqa: BLE001 - concurrency outcome is the assertion surface
            results.append(exc)

    threads = [Thread(target=run, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=40)

    assert sum(not isinstance(result, Exception) for result in results) == 1, [repr(result) for result in results]
    assert any("snapshot revision conflict" in str(result) for result in results if isinstance(result, Exception))
    durable = store.load_snapshot()
    assert len(durable.participant_crossing_history[PARTICIPANT]) == 2


class _MissingPolicyResolver(StaticCrossingResolver):
    def resolve(
        self,
        intent: ParticipantCrossingIntent,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantCrossingPolicyResolution:
        del intent, snapshot
        raise ValueError("secret policy lookup detail")


def test_missing_policy_fails_closed_with_safe_diagnostic_and_audit() -> None:
    plane = action_plane(_MissingPolicyResolver())

    receipt = admit(plane, idempotency_key="missing-policy")

    assert receipt.accepted is True
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    assert plane.snapshot.participant_behavior_history == {}
    assert plane.snapshot.participant_crossing_history == {}
    assert receipt.diagnostics[0].code == "runtime.participant-crossing-policy-unresolved"
    assert "secret" not in receipt.diagnostics[0].message
    assert plane.audit_log()[-1].reason == "policy-unresolved"


def test_runtime_exposes_no_detached_crossing_recorder() -> None:
    plane = action_plane(StaticCrossingResolver())

    assert not hasattr(plane, "record_participant_crossing")
