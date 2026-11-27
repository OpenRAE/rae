"""Observed public crossings are compared with the unchanged finite kernel."""

from dataclasses import replace

import pytest
from crossing_runtime_observer import capture_call, crossing_binding
from implementations.formal.participant_crossing.runtime_mapping import assess
from participant_crossing_fixtures import StaticCrossingResolver, action_plane, admit
from raes_contracts.contracts.participant_crossing import ParticipantCrossingGateDisposition as Gate


@pytest.mark.parametrize("cut", ["p0", "p1"])
@pytest.mark.parametrize("input_class", ["plain", "transform", "declassify", "unsupported", "forbidden"])
def test_all_declared_inputs_run_through_public_admission(input_class, cut):
    from crossing_runtime_cases import ingress_case

    observed = ingress_case(input_class, cut)
    report = assess(observed)
    assert report["classification"] != "invalid-evidence", report
    assert report["crossing_rows_added"] >= 2
    if input_class in {"forbidden", "unsupported"} or (input_class == "declassify" and cut == "p0"):
        assert report["classification"] == "match", report
    else:
        assert report["classification"] == "incompatible"
    if input_class == "transform" or (input_class == "declassify" and cut == "p1"):
        assert report["crossing_rows_added"] == 5
        assert "transition-mismatch" in report["issues"]


@pytest.mark.parametrize("mode", ["same-cut", "later-cut", "changed-input"])
def test_public_retry_preserves_the_original_result_without_another_commit(mode):
    from crossing_runtime_cases import replay_case

    first, retry = replay_case(mode)
    assert retry.after == first.after
    assert retry.records_after == first.records_after
    assert retry.audit == first.audit
    assert retry.backend_calls == 0
    if mode == "same-cut":
        assert retry.result.operation_id == first.result.operation_id
    else:
        assert retry.error_type is not None
    assert assess(retry)["classification"] != "match"


@pytest.mark.parametrize("permitted", [False, True])
def test_final_sink_outcome_is_not_replaced_with_an_earlier_permit(permitted):
    from crossing_runtime_cases import egress_case
    from raes_contracts.runtime_state import OperationState

    observed = egress_case(permitted)
    report = assess(observed)
    assert report["classification"] in {"incompatible", "observation-gap"}, report
    assert report["final_sink_enforced"] is True
    assert report["visible_events"][:2] == ["crossing.request", "crossing.decision.permit"]
    changed = [record for key, record in observed.records_after.items() if key not in observed.records_before]
    assert len(changed) == 1
    assert changed[0].status.state is (OperationState.SUCCEEDED if permitted else OperationState.FAILED)
    if not permitted:
        assert observed.result is None
        assert changed[0].result_payload is None
        assert "unmodeled-error" in report["issues"]
        assert "final-outcome-mismatch" in report["issues"]


def test_installed_provider_effect_is_executed_and_reported_outside_the_single_operation_carrier():
    from crossing_runtime_cases import effect_case

    parent, effect, owner = effect_case()
    assert "effect" in owner.calls
    assert effect.result[0].disposition == "applied"
    assert effect.after.participant_control_history
    assert len(effect.records_after) > len(parent.records_after)
    assert assess(effect)["classification"] != "match"


@pytest.mark.parametrize("context", ["valid", "missing-identity", "wrong-participant", "stale-epoch"])
def test_v2_uses_the_public_delivered_surface_and_original_context(context):
    from crossing_runtime_cases import v2_case

    observed = v2_case(context)
    report = assess(observed)
    assert report["classification"] != "match"
    if context == "valid":
        assert observed.result.accepted
        assert report["crossing_rows_added"] == 2
    else:
        assert report["crossing_rows_added"] == 0
        assert not observed.after.participant_behavior_history.get(observed.binding.participant)


def test_observed_public_refusal_matches_the_concrete_transitions():
    plane = action_plane(StaticCrossingResolver(gate_overrides={"action_admission": Gate.DENY}))
    with plane:
        observed = capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="forbidden")
    report = assess(observed)
    assert report["classification"] == "match"
    assert report["states"][-1]["phase"] == "terminal"
    assert report["states"][-1]["head"] == "h1"
    assert report["backend_calls"] == 0
    assert report["visible_events"] == ["crossing.request", "crossing.decision.deny"]


def test_support_and_transaction_evidence_retains_the_observed_runtime_values():
    from crossing_runtime_cases import ingress_case

    report = assess(ingress_case("unsupported"))
    support = next(event for event in report["events"] if event["label"] == "internal.resolve-capability")
    assert support["facts"]["gates"]["backend_support"] == "unsupported"
    assert support["facts"]["effective_levels"] == [["participant_ingress_admission", "unsupported"]]
    commit = next(event for event in report["events"] if event["label"] == "internal.atomic-commit")
    assert commit["facts"]["operation_state"] == "failed"
    assert commit["facts"]["crossing_rows"] == 2


def test_missing_phase_evidence_is_not_filled_from_the_model():
    plane = action_plane(StaticCrossingResolver(gate_overrides={"action_admission": Gate.DENY}))
    with plane:
        observed = capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="forbidden")
    missing = replace(observed, events=tuple(event for event in observed.events if event.label != "internal.validate"))
    report = assess(missing)
    assert report["classification"] == "observation-gap"
    assert "missing-witness" in report["issues"]
    assert "transition-mismatch" not in report["issues"]
    assert all(state["phase"] != "resolving-cut" for state in report["states"])


def test_timing_is_rejected_without_changing_the_carrier():
    plane = action_plane(StaticCrossingResolver(gate_overrides={"action_admission": Gate.DENY}))
    with plane:
        observed = capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="forbidden")
    assert "timing-excluded" in assess(replace(observed, timed=True))["issues"]


@pytest.mark.parametrize("fault", ["audit", "operation", "protected-state", "identity"])
def test_corrupted_observations_cannot_claim_a_matching_execution(fault):
    plane = action_plane(StaticCrossingResolver(gate_overrides={"action_admission": Gate.DENY}))
    with plane:
        observed = capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="forbidden")
    if fault == "audit":
        observed = replace(observed, audit=())
    elif fault == "operation":
        observed = replace(observed, records_after=observed.records_before)
    elif fault == "protected-state":
        observed = replace(observed, after=observed.after.with_entries({}, metadata={"unexpected": True}))
    else:
        observed = replace(observed, binding=replace(observed.binding, episode="other-episode"))
    assert assess(observed)["classification"] == ("incompatible" if fault == "identity" else "invalid-evidence")


def test_v2_callback_result_failure_does_not_disclose_private_text():
    import test_sem_220_participant_decision_surface_v2_runtime as cases
    from participant_crossing_fixtures import evidence, identity
    from raes_contracts.participant_binding_v2 import ParticipantDecisionSurfaceBindingResolversV2

    plane, delivered, implementation_selection, delivery = cases._governed_selection_case()
    private_detail = "synthetic-private-callback-detail"

    class InvalidApparatusResult:
        def model_dump(self, **kwargs):
            raise ValueError(private_detail)

    resolvers = ParticipantDecisionSurfaceBindingResolversV2(
        argument_shape=cases._resolved_selection,
        apparatus=lambda **_: InvalidApparatusResult(),
        delivery=lambda **_: delivery,
    )
    with plane:
        receipt = plane.admit_participant_decision_surface_selection_v2(
            cases._compiled_participant_behavior(),
            surface=delivered,
            selection=cases._selection_for(delivered),
            admission_request=replace(cases._admission_request(), implementation_selection=implementation_selection),
            resolvers=resolvers,
            identity=identity(participant_address=cases.PARTICIPANT),
            crossing_evidence=evidence(),
            idempotency_key="invalid-callback",
        )
        assert receipt.accepted is False
        assert private_detail not in str(receipt)
        assert private_detail not in str(plane._store.load_records())
        assert private_detail not in str(plane.audit_log())
        assert not plane.snapshot.participant_crossing_history


def test_unresolved_required_gate_is_not_projected_to_supported_execution():
    plane = action_plane(StaticCrossingResolver(gate_overrides={"action_admission": Gate.UNKNOWN}))
    with plane:
        observed = capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="unsupported")
    report = assess(observed)
    assert report["classification"] == "incompatible"
    assert "transition-mismatch" in report["issues"]
    assert observed.backend_calls == 0
    assert not observed.after.participant_behavior_history


def test_lost_commit_acknowledgement_uses_readback_without_a_second_result():
    from raes_runtime.control_plane_store import InMemoryControlPlaneStore

    class LostAcknowledgement(InMemoryControlPlaneStore):
        lose_once = True

        def commit_participant_transition(self, **kwargs):
            result = super().commit_participant_transition(**kwargs)
            if self.lose_once:
                self.lose_once = False
                raise OSError("synthetic lost acknowledgement")
            return result

    plane = action_plane(
        StaticCrossingResolver(gate_overrides={"action_admission": Gate.DENY}), store=LostAcknowledgement()
    )
    with plane:
        first = capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="forbidden")
        retry = capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="forbidden")
    assert len(first.after.participant_crossing_history[first.binding.participant]) == 2
    assert retry.after == first.after
    assert retry.records_after == first.records_after
    assert retry.backend_calls == 0
    assert assess(first)["classification"] == "incompatible"
    assert "unmodeled-error" in assess(first)["issues"]


def test_callback_time_state_change_is_not_reordered_into_an_idle_policy_advance():
    from raes_runtime.control_plane_store import InMemoryControlPlaneStore

    store = InMemoryControlPlaneStore()

    class StaleResolver(StaticCrossingResolver):
        def resolve(self, intent, snapshot):
            result = super().resolve(intent, snapshot)
            current = store.load_snapshot_state()
            store.save_snapshot(
                current.snapshot.with_entries({}, metadata={"external-cut": "advanced"}),
                expected_revision=current.revision,
            )
            return result

    plane = action_plane(StaleResolver(), store=store)
    with plane:
        observed = capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="plain")
    report = assess(observed)
    assert observed.backend_calls == 0
    assert "runtime.state-cut.changed" in report["visible_events"]
    assert "policy.cut.advance" not in report["visible_events"]
    assert report["classification"] != "match"
    assert "protected-state-changed-after-refusal" in report["runtime_safety_issues"]


def test_wrong_audit_contents_fail_even_when_the_model_path_is_also_incompatible():
    from crossing_runtime_cases import egress_case

    observed = egress_case(False)
    changed = tuple(replace(event, allowed=True, reason="wrong") for event in observed.audit)
    commits = tuple(replace(commit, audit=changed) for commit in observed.commits)
    report = assess(replace(observed, audit=changed, commits=commits))
    assert report["runtime_safety_issues"]
    assert report["classification"] == "invalid-evidence"


def test_refusal_cannot_rewrite_previously_retained_evaluation_history():
    from crossing_runtime_cases import effect_case

    _, effect, _ = effect_case()
    observed = replace(effect, after=replace(effect.after, participant_control_evaluation_history={}))
    report = assess(observed)
    assert "history-integrity-invalid" in report["runtime_safety_issues"]
    assert report["classification"] == "invalid-evidence"


def test_legacy_fixture_cannot_infer_an_operating_profile_from_its_store_class():
    from crossing_runtime_cases import ingress_case

    report = assess(ingress_case("forbidden"))
    assert report["configuration"]["operating_profile"] is None
    assert "store.atomic-terminal" in report["configuration"]["store_capabilities"]


def test_durable_record_cannot_disagree_with_the_last_witnessed_commit():
    from crossing_runtime_cases import ingress_case
    from raes_contracts.runtime_state import OperationState

    observed = ingress_case("forbidden")
    record_id = observed.result.operation_id
    record = observed.records_after[record_id]
    record = replace(record, status=replace(record.status, state=OperationState.SUCCEEDED, diagnostics=[]))
    observed = replace(observed, records_after={**observed.records_after, record_id: record})
    report = assess(observed)
    assert report["runtime_safety_issues"]
    assert report["classification"] == "invalid-evidence"


def test_refusal_cannot_hide_changes_to_another_participant_history():
    from crossing_runtime_cases import ingress_case

    observed = ingress_case("forbidden")
    histories = dict(observed.after.participant_crossing_history)
    histories["participant.other"] = list(histories[observed.binding.participant])
    observed = replace(observed, after=replace(observed.after, participant_crossing_history=histories))
    assert "unrelated-refusal-state-change" in assess(observed)["runtime_safety_issues"]


def test_stale_cut_marker_cannot_hide_real_backend_execution_before_failure():
    from crossing_runtime_cases import ingress_case
    from implementations.formal.participant_crossing.runtime_mapping import Event

    observed = ingress_case("plain")
    assert observed.backend_calls == 1
    failed = replace(
        observed,
        result=None,
        error_type="OSError",
        events=(Event("runtime.state-cut.changed"), *observed.events),
    )
    report = assess(failed)
    assert "backend-executed-during-refusal" in report["runtime_safety_issues"]
    assert report["classification"] == "invalid-evidence"


@pytest.mark.parametrize("mode", ["same-cut", "later-cut", "changed-input"])
def test_retry_mapping_starts_from_the_retained_result(mode):
    from crossing_runtime_cases import replay_case

    first, retry = replay_case(mode)
    original, continued = assess(first), assess(retry)
    assert continued["states"][0] == original["states"][-1]
    assert continued["states"][0]["head"] == "h1"
    if mode == "same-cut":
        assert continued["states"][1]["intent"][3] == "same-cut"
    elif mode == "later-cut":
        assert continued["states"][1]["cut"] == "p1"
        assert continued["states"][1]["last"][1] == "p0"
        assert continued["states"][2]["intent"][2:] == ("p0", "later-cut")


def test_witnessed_contradiction_is_not_a_missing_observation():
    from crossing_runtime_cases import ingress_case

    observed = ingress_case("forbidden")
    events = tuple(
        replace(event, label="crossing.delivery") if event.label == "internal.validate" else event
        for event in observed.events
    )
    report = assess(replace(observed, events=events))
    assert report["classification"] == "incompatible"
    assert "transition-mismatch" in report["issues"]


def test_lost_acknowledgement_after_a_proven_success_is_not_a_refusal():
    from crossing_runtime_cases import ingress_case

    observed = ingress_case("plain")
    report = assess(replace(observed, result=None, error_type="OSError"))
    assert report["runtime_safety_issues"] == []
    assert report["classification"] == "incompatible"
    assert "unmodeled-error" in report["issues"]


def test_retry_cannot_use_a_late_audit_to_certify_its_starting_state():
    from crossing_runtime_cases import replay_case

    _, retry = replay_case("same-cut")
    report = assess(replace(retry, audit_before=()))
    assert report["classification"] == "observation-gap"
    assert "initial-state-unmapped" in report["issues"]
    assert report["states"] == []


@pytest.mark.parametrize("where", ["commit", "readback", "store"])
@pytest.mark.parametrize("fault", ["record", "audit"])
def test_refusal_preserves_prior_operation_records_and_audit(fault, where):
    from raes_runtime.control_plane_store import InMemoryControlPlaneStore

    prior_plane = action_plane(StaticCrossingResolver(gate_overrides={"action_admission": Gate.DENY}))
    with prior_plane:
        prior = capture_call(
            prior_plane,
            lambda: admit(prior_plane, idempotency_key="prior-evidence"),
            crossing_binding(),
            input_class="forbidden",
        )

    class EvidenceLosingStore(InMemoryControlPlaneStore):
        def _publish(self, *args, **kwargs):
            super()._publish(*args, **kwargs)
            if where == "store":
                if fault == "record":
                    for key in prior.records_after:
                        self._records.pop(key, None)
                else:
                    self._audit = self._audit[len(prior.audit) :]

    store = EvidenceLosingStore()
    plane = action_plane(StaticCrossingResolver(gate_overrides={"action_admission": Gate.DENY}), store=store)
    # Seed already validated evidence from a distinct real public operation.
    store._records.update(prior.records_after)
    store._audit.extend(prior.audit)
    with plane:
        observed = capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="forbidden")
    if where != "store":
        assert assess(observed)["runtime_safety_issues"] == []
    if where == "commit":
        commit = observed.commits[0]
        damaged = (
            replace(
                commit, records={key: value for key, value in commit.records.items() if key not in prior.records_after}
            )
            if fault == "record"
            else replace(commit, audit=commit.audit[len(prior.audit) :])
        )
        observed = replace(observed, commits=(damaged, *observed.commits[1:]))
    elif where == "readback" and fault == "record":
        observed = replace(
            observed,
            records_after={
                key: value for key, value in observed.records_after.items() if key not in prior.records_after
            },
        )
    elif where == "readback":
        observed = replace(observed, audit=observed.audit[len(prior.audit) :])
    report = assess(observed)
    assert report["classification"] == "invalid-evidence"
    assert ("operation-records-not-preserved" if fault == "record" else "audit-prefix-changed") in report[
        "runtime_safety_issues"
    ]


def test_authorized_backend_failure_remains_a_model_incompatibility():
    from crossing_runtime_cases import backend_failure_case
    from raes_contracts.runtime_state import OperationState

    observed = backend_failure_case()
    assert observed.backend_calls == 1
    assert observed.error_type is None
    assert observed.result.accepted
    assert observed.records_after[observed.result.operation_id].status.state is OperationState.FAILED
    report = assess(observed)
    assert report["runtime_safety_issues"] == []
    assert report["classification"] == "incompatible"
    assert "external-application-outside-crossing-model" in report["issues"]
    assert report["operation_outcomes"] == ["failed"]
