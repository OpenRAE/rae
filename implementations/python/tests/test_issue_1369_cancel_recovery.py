"""Cancellation acceptance and safe resumable delivery are separate writes."""

import pytest
from participant_crossing_fixtures import PARTICIPANT
from raes_contracts.errors import ConflictError
from reusable_control_runtime_fixtures import identity
from test_issue_1369_cancellation_effects import cancellation_race_plane


@pytest.mark.parametrize("interruption", ["owner-dispatch", "control-delivery"])
def test_cancellation_resumes_after_owner_acceptance_before_delivery(monkeypatch, interruption):
    plane, provider, target = cancellation_race_plane()
    from raes_runtime import operation_provider_control

    interrupted_owner = plane if interruption == "owner-dispatch" else operation_provider_control
    method = "dispatch_participant_cancellation" if interruption == "owner-dispatch" else "deliver_control"
    dispatch = getattr(interrupted_owner, method)

    def interrupted(*args, **kwargs):
        raise OSError("synthetic interruption after cancellation acceptance")

    with plane:
        monkeypatch.setattr(interrupted_owner, method, interrupted)
        first = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        assert [item.disposition for item in first] == ["indeterminate"]
        assert provider.cancels == 0
        owner = plane._store.load_records()[first[0].receipt_ref]
        control_id = owner.result_payload["participant_control_cancellation"]["control_id"]
        original_history = plane.snapshot.participant_control_history[PARTICIPANT]
        monkeypatch.setattr(interrupted_owner, method, dispatch)
        second = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        assert second == first
        assert provider.cancels == 1
        assert plane.snapshot.participant_control_history[PARTICIPANT] == original_history
        controls = plane._store.load_records()[target.receipt.operation_id].invocation.controls
        assert [item.control_id for item in controls] == [control_id]
        assert plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity()) == second
        assert provider.cancels == 1


@pytest.mark.parametrize("pending_native", [True, False])
def test_cancellation_resumes_after_restart_and_recovery(tmp_path, monkeypatch, pending_native):
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane_recovery import IndeterminateResolutionDisposition
    from raes_runtime.control_plane_store import LocalControlPlaneStore
    from reusable_control_runtime_fixtures import configured_plane

    directory = tmp_path / "cancel-recovery"
    plane, provider, target = cancellation_race_plane(
        store=LocalControlPlaneStore(directory), pending_native=pending_native
    )

    def interrupted(*args, **kwargs):
        raise OSError("synthetic interruption before control delivery")

    with plane:
        monkeypatch.setattr(plane, "dispatch_participant_cancellation", interrupted)
        first = plane.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        assert [item.disposition for item in first] == ["indeterminate"]
        claim = next(r for r in plane._store.load_records().values() if r.idempotency_key.startswith("control-effect:"))
        owner_id = first[0].receipt_ref
        assert provider.cancels == 0
    reopened, _ = configured_plane(
        target=plane._target,
        operation_evidence=plane._operation_evidence,
        participant_control=plane._participant_control,
        crossing_policy_resolver=plane._crossing_policy_resolver,
        enforce_final_sink_flow_control=False,
        store=LocalControlPlaneStore(directory),
        owner=plane._mixed_control.resolver,
    )
    with reopened:
        if pending_native:
            caller = identity()
            with pytest.raises(ConflictError, match="indeterminate operation requires resolution"):
                reopened.dispatch_participant_control_effects(PARTICIPANT, identity=caller)
        else:
            # Cancellation may supervise unknown running work; its unsettled
            # claim remains immutable until explicit recovery resolution.
            early = reopened.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
            assert [item.disposition for item in early] == ["indeterminate"]
            assert reopened.get_operation(claim.receipt.operation_id).state is OperationState.INDETERMINATE
        for operation_id in (target.receipt.operation_id, claim.receipt.operation_id):
            if reopened.get_operation(operation_id).state is OperationState.INDETERMINATE:
                reopened.resolve_indeterminate_operation(
                    operation_id,
                    disposition=IndeterminateResolutionDisposition.ACCEPT_CURRENT_SNAPSHOT,
                    idempotency_key="resolve-" + operation_id,
                    identity=identity(),
                )
        outcomes = reopened.dispatch_participant_control_effects(PARTICIPANT, identity=identity())
        assert [item.disposition for item in outcomes] == ["applied" if pending_native else "indeterminate"]
        assert outcomes[0].receipt_ref == owner_id
        assert provider.cancels == (0 if pending_native else 1)
        assert reopened.dispatch_participant_control_effects(PARTICIPANT, identity=identity()) == outcomes
        assert provider.cancels == (0 if pending_native else 1)
