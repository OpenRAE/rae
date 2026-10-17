"""Only validated execution-owner evidence establishes a cancellation outcome."""

from dataclasses import replace

import pytest
from raes_contracts.runtime_state import OperationState
from raes_runtime.operation_provider_execution import accept_response
from reusable_control_runtime_fixtures import PARTICIPANT, configured_plane, identity
from test_issue_1362_provider_execution import Provider, target
from test_issue_1364_cancellation import admitted_attempt, cancellation


class ScopedEvidence:
    expected_digest = None

    def validate_effects(self, request, response):
        refs = response.message.effects.evidence_refs
        return (
            response.binding == request.binding
            and len(refs) == 1
            and refs[0].contract_id == "runtime-snapshot-v1"
            and refs[0].artifact_id == "scoped-cessation"
            and refs[0].digest == self.expected_digest
        )

    def resolve_result(self, request, response, predecessor):
        from raes_contracts.runtime_state import ApplyResult

        return ApplyResult(response.message.proposed_state is OperationState.SUCCEEDED, predecessor)


def settle_evidence(plane, parent, provider, *, effect, state):
    from raes_contracts.canonical import canonical_json_digest
    from raes_contracts.planning import ProvisioningPlan, RuntimeDomain
    from raes_runtime.control_plane_execution import OperationExecutionRequest
    from raes_runtime.control_plane_store_snapshots import _snapshot_payload
    from raes_runtime.control_plane_supervised_execution import settle
    from raes_runtime.operation_provider_execution import validate_outcome

    digest = canonical_json_digest(_snapshot_payload(plane.snapshot))
    plane._operation_evidence.expected_digest = digest
    evidence = {"contract_id": "runtime-snapshot-v1", "artifact_id": "scoped-cessation", "digest": digest}
    effects = {"effect": effect, "cessation_established": True, "evidence_refs": [evidence]}
    if effect == "partial":
        effects.update(residual_scope=["provision.node.web"], residual_state=evidence)
    message = {
        "kind": "outcome",
        "proposed_state": state.value,
        "effects": effects,
        "satisfaction": "satisfied" if state is OperationState.SUCCEEDED else "unsatisfied",
        "release_gates_satisfied": state is OperationState.SUCCEEDED,
        "cancellation_established": state is OperationState.CANCELLED,
    }
    if state is OperationState.SUCCEEDED:
        message["result"] = evidence
    response = provider.report(parent.invocation.request, message)
    request = OperationExecutionRequest(
        domain=RuntimeDomain.PARTICIPANT,
        method=lambda: None,
        plan=ProvisioningPlan(),
        address=PARTICIPANT,
        context=parent.receipt.context,
        diagnostics=[],
        base_snapshot=None,
        idempotency_key="action-1",
        request_fingerprint=parent.receipt.context.request_commitment,
    )
    with plane._mutation_authority.supervision():
        parent = accept_response(plane, parent, response)
        result, release, payload = validate_outcome(plane, parent, response, request, plane._snapshot)
        settle(plane, parent, state, result=result, release_commitment=release, result_payload=payload)


@pytest.mark.parametrize(
    ("effect", "state", "expected"),
    [("absent", OperationState.SUCCEEDED, "too-late"), ("partial", OperationState.CANCELLED, "partial-limitation")],
)
def test_settled_target_outcomes_require_validated_cessation_and_residual_evidence(effect, state, expected):
    provider = Provider()
    with configured_plane(target=target(provider), operation_evidence=ScopedEvidence())[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        parent = consume(plane, admitted_attempt(plane, native=False), provider)
        settle_evidence(plane, parent, provider, effect=effect, state=state)
        intent = cancellation(
            plane, owner, parent.receipt.operation_id, target_kind="attempt", revision=0, head=0, order=1
        )
        receipt = plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="cancel")

        status = plane.participant_cancellation_status(receipt.operation_id, identity=identity())

        assert status.cancellation_effect.value == expected
        assert status.evidence_refs == ["scoped-cessation"]


def consume(plane, record, provider):
    provider.request = record.invocation.request
    with plane._mutation_authority.supervision():
        record = accept_response(plane, record, provider.check_operation(provider.request))
        running = replace(
            record,
            status=replace(record.status, state=OperationState.RUNNING),
            invocation=record.invocation.model_copy(update={"consumed": True}),
        )
        plane._store.save_record(running)
        plane._reload_derived_state()
        return accept_response(
            plane, running, provider.report(provider.request, {"kind": "acknowledgement", "disposition": "accepted"})
        )


@pytest.mark.parametrize("ack", ["accepted", "refused", "missing"])
def test_backend_control_disposition_alone_never_proves_a_cancellation_effect(ack):
    provider = Provider()
    if ack == "missing":

        def missing(control):
            provider.cancels += 1
            raise TimeoutError("synthetic lost acknowledgement")

        provider.cancel_operation = missing
    elif ack == "refused":
        from raes_contracts.contracts import backend_operation_control_digest

        provider.cancel_operation = lambda control: provider.report(
            provider.request,
            {
                "kind": "control",
                "control_id": control.control_id,
                "control_digest": backend_operation_control_digest(control),
                "disposition": "refused",
            },
        )
    with configured_plane(target=target(provider))[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        parent = consume(plane, admitted_attempt(plane, native=False), provider)
        intent = cancellation(
            plane, owner, parent.receipt.operation_id, target_kind="attempt", revision=0, head=0, order=1
        )
        receipt = plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="cancel")

        status = plane.dispatch_participant_cancellation(receipt.operation_id, identity=identity())

        assert status.cancellation_effect is None
        assert status.backend_disposition == (None if ack == "missing" else ack)
        assert plane.get_operation(parent.receipt.operation_id).state is OperationState.RUNNING
        assert plane._operations[parent.receipt.operation_id].invocation.reserved
        plane.dispatch_participant_cancellation(receipt.operation_id, identity=identity())
        assert provider.cancels == (0 if ack == "refused" else 1)


def test_retry_resumes_a_retained_control_only_if_its_delivery_was_never_claimed(monkeypatch):
    import raes_runtime.operation_provider_control as controls

    provider = Provider()
    with configured_plane(target=target(provider))[0] as plane:
        owner = plane._mixed_control.resolver
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=identity())
        parent = consume(plane, admitted_attempt(plane, native=False), provider)
        intent = cancellation(
            plane, owner, parent.receipt.operation_id, target_kind="attempt", revision=0, head=0, order=1
        )
        receipt = plane.record_participant_control(PARTICIPANT, intent, identity=identity(), idempotency_key="cancel")
        with monkeypatch.context() as patch:

            def interrupted(*args):
                raise RuntimeError("interrupted before delivery claim")

            patch.setattr(controls, "deliver_control", interrupted)
            with pytest.raises(RuntimeError, match="interrupted"):
                plane.dispatch_participant_cancellation(receipt.operation_id, identity=identity())

        status = plane.dispatch_participant_cancellation(receipt.operation_id, identity=identity())

        assert status.backend_disposition == "accepted"
        assert provider.cancels == 1
