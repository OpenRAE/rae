"""Independent timing, policy and ownership gates of delivery tool actions."""

from dataclasses import replace

import pytest
from delivery_invocation_fixtures import (
    PARTICIPANT,
    caller,
    delivery_plane,
    invocation_request,
    temporal_payload,
    tool_evidence,
    tool_outcome,
    tool_request,
)
from raes_contracts.participant_tool_actions import ParticipantToolActionRefusal


def dwell_payload(payload):
    temporal_payload(payload)
    constraint = payload["temporal_constraints"]["finish-by-five"]
    constraint.update(constraint_kind="window", start={"tick": 0})
    action = payload["action_contracts"]["probe"]
    temporal = action["temporal_contracts"][0]
    temporal.update(temporal_kind="dwell", event_points=["start", "end"], window_ref="finish-by-five")
    temporal["shared_time_binding"].update(
        evidence_mode="continuous",
        event_point="start",
        condition_precondition_id="present",
        observation_boundary_ref="red-view",
    )
    boundary = payload["observation_boundaries"]["red-view"]
    boundary["observable_refs"].append("nodes.web")
    boundary["view_rules"].append(
        {
            "information_ref": "nodes.web",
            "boundary_class": "observable_resource",
            "disposition": "observable",
            "visibility_basis": "Declared condition coverage.",
        }
    )


@pytest.mark.parametrize("mode", ["valid", "missing", "gap", "false", "sampled"])
def test_dwell_requires_exact_continuous_coverage_before_dispatch(tmp_path, mode):
    from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel
    from raes_contracts.contracts.participant_temporal_history import require_participant_temporal_history

    calls = []

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        assert decision.admitted
        context = decision.binding.temporal_contexts[0].shared_time
        coverage = [{"start": context.bound_start, "end": context.bound_end, "condition_holds": mode != "false"}]
        if mode == "gap":
            coverage[0]["start"] = context.bound_start.model_copy(update={"tick": 1})
        proofs = (
            ()
            if mode == "missing"
            else (
                ParticipantTemporalEvidenceModel(
                    context=context,
                    observation_boundary_address=decision.binding.observation_boundary_address,
                    evidence_mode="sampled" if mode == "sampled" else "continuous",
                    condition_precondition_id="present",
                    coverage=coverage,
                    evidence_refs=(decision.binding.observation_boundary_evidence_refs[0],),
                ),
            )
        )
        receipt = port.dispatch(decision.action_instance_id, temporal_evidence=proofs)
        assert receipt.accepted is (mode == "valid")
        assert port.admit(tool_request(port), crossing_evidence=tool_evidence()) == decision
        if receipt.accepted:
            calls.append(receipt.action_instance_id)
            assert port.complete(receipt.action_instance_id, tool_outcome(port, receipt.binding)).accepted

    plane, runtime, owner, delivered, _ = delivery_plane(tmp_path, script, payload_transform=dwell_payload)
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        assert len(calls) == (mode == "valid")
        if mode == "valid":
            assert owner.invocation_requests[-1].temporal_evidence
        require_participant_temporal_history(plane.snapshot)
        assessment = plane.snapshot.participant_behavior_history[PARTICIPANT][-1]["temporal_assessments"][0]
        assert (assessment["status"] == "met") is (mode == "valid")


def test_expired_deadline_yields_no_dispatch_grant(tmp_path):
    def expired(payload):
        temporal_payload(payload)
        payload["temporal_constraints"]["finish-by-five"]["end"] = {"tick": 4}

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        assert decision.admitted
        assert (
            port.dispatch(decision.action_instance_id).refusal
            is ParticipantToolActionRefusal.TEMPORAL_GUARANTEE_UNSATISFIED
        )

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path, script, payload_transform=expired)
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        terminal = plane.snapshot.participant_behavior_history[PARTICIPANT][-1]
        assert terminal["invocation_tool_context"]["settlement"] == "withheld"
        assert terminal["temporal_assessments"][0]["status"] != "met"


@pytest.mark.parametrize("gate", ["crossing", "sink"])
@pytest.mark.parametrize("stage", ["admit", "dispatch"])
def test_each_tool_gate_refuses_before_dispatch(tmp_path, gate, stage):
    from raes_contracts.contracts.participant_crossing import ParticipantCrossingGateDisposition
    from raes_contracts.contracts.participant_flow_control import ParticipantFlowFinalDisposition

    owners = {}

    def deny():
        resolver = owners["plane"]._crossing_policy_resolver
        if gate == "crossing":
            resolver.gate_overrides["action_admission"] = ParticipantCrossingGateDisposition.DENY
        else:
            resolver.toggles = replace(resolver.toggles, capability_disposition=ParticipantFlowFinalDisposition.DENY)

    def script(invocation, port):
        if stage == "admit":
            deny()
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        if stage == "admit":
            assert not decision.admitted
        else:
            assert decision.admitted
            deny()
            assert not port.dispatch(decision.action_instance_id).accepted

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path, script)
    owners["plane"] = plane
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        assert all(
            event.get("action_result", {}).get("status") != "succeeded"
            for event in plane.snapshot.participant_behavior_history.get(PARTICIPANT, ())
        )


@pytest.mark.parametrize("replace_identity", [False, True])
def test_transformation_preserves_child_identity_and_returns_exact_binding(tmp_path, replace_identity):
    from types import SimpleNamespace

    from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
    from raes_contracts.contracts.participant_crossing import ParticipantCrossingOperation
    from raes_runtime.participant_crossing_intents import action_subject
    from raes_runtime.participant_crossing_mediation import ParticipantCrossingTransformationResolution
    from sem233_flow_sink_fixtures import Sem233FlowSinkResolver

    class Resolver(Sem233FlowSinkResolver):
        def resolve_operation(self, intent, snapshot, carrier):
            base = self.resolve(intent, snapshot)
            if not isinstance(carrier, ParticipantActionAdmissionRequest) or carrier.evidence_refs:
                return base
            governed = replace(
                carrier,
                evidence_refs=("content.participant-observation",),
                action_instance_id=carrier.action_instance_id + "-derived"
                if replace_identity
                else carrier.action_instance_id,
            )
            subject = action_subject(SimpleNamespace(_snapshot=snapshot), governed)
            self.subjects.append(subject)
            return replace(
                base,
                required_operation=ParticipantCrossingOperation.TRANSFORMATION,
                transformation=ParticipantCrossingTransformationResolution(
                    result_subject=subject,
                    rule_ref="rule:tool-evidence",
                    rule_revision="1",
                    result_marking_refs=("marking:participant-control",),
                ),
            )

        def transform_ingress(self, intent, subject, carrier):
            return replace(
                carrier,
                evidence_refs=("content.participant-observation",),
                action_instance_id=carrier.action_instance_id + "-derived"
                if replace_identity
                else carrier.action_instance_id,
            )

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        if replace_identity:
            assert decision.refusal is ParticipantToolActionRefusal.AUTHORITY_DENIED
            return
        assert decision.admitted
        assert decision.binding.evidence_refs == ("content.participant-observation",)
        grant = port.dispatch(decision.action_instance_id)
        assert grant.accepted
        assert grant.binding == decision.binding
        assert port.complete(grant.action_instance_id, tool_outcome(port, grant.binding)).accepted

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path, script, resolver=Resolver())
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        assert bool(plane.snapshot.participant_behavior_history.get(PARTICIPANT)) is not replace_identity


@pytest.mark.parametrize("revoke", [False, True])
def test_originating_control_is_checked_without_a_validated_selection(tmp_path, revoke):
    owners, effects = {}, []

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        assert decision.admitted
        assert decision.binding.validated_selection is None
        owners["owner"].revoked_control_evidence = revoke
        grant = port.dispatch(decision.action_instance_id)
        assert grant.accepted is not revoke
        if grant.accepted:
            effects.append(grant.action_instance_id)
            assert port.complete(grant.action_instance_id, tool_outcome(port, grant.binding)).accepted

    plane, runtime, owner, delivered, _ = delivery_plane(tmp_path, script, controlled=True)
    owners["owner"] = owner
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller(supervisor=True))
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        assert len(effects) == (not revoke)


def test_shared_time_plan_requires_the_installed_exact_delivery_driver(tmp_path):
    from raes_runtime.manager_plan_admission import reference_participant_driver_diagnostics
    from raes_runtime.participant_delivery_driver import delivery_tool_driver_actions

    plane, _, _, _, model = delivery_plane(tmp_path, payload_transform=temporal_payload)
    with plane:
        assert any(
            item.code == "runtime.participant-temporal-driver-unsupported"
            for item in reference_participant_driver_diagnostics(model)
        )
        actions = delivery_tool_driver_actions(plane, model)
        assert actions
        assert not any(
            item.code == "runtime.participant-temporal-driver-unsupported"
            for item in reference_participant_driver_diagnostics(model, delivery_actions=actions)
        )
        planned = plane.plan(model.realization_instance)
        assert not any(item.code == "runtime.participant-temporal-driver-unsupported" for item in planned.diagnostics)


def test_lost_completion_ack_reconciles_once_without_duplicate_history(tmp_path):
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    class Store(LocalControlPlaneStore):
        fail_once = True

        def commit_participant_transition(self, **kwargs):
            result = super().commit_participant_transition(**kwargs)
            record = kwargs["record"]
            if (
                self.fail_once
                and record.result_payload
                and "delivery_tool" in record.result_payload
                and record.status.state is OperationState.SUCCEEDED
            ):
                self.fail_once = False
                raise OSError("synthetic lost completion acknowledgement")
            return result

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        grant = port.dispatch(decision.action_instance_id)
        assert grant.accepted
        outcome = tool_outcome(port, grant.binding)
        assert port.complete(grant.action_instance_id, outcome).accepted
        assert port.complete(grant.action_instance_id, outcome).accepted

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path, script, store=Store(tmp_path / "durable"))
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        assert len(plane.snapshot.participant_behavior_history[PARTICIPANT]) == 3


def test_timeout_revokes_a_child_waiting_on_foreign_authority(tmp_path):
    from threading import Event

    entered, release, finished = Event(), Event(), Event()
    answers = []

    def script(invocation, port):
        try:
            answers.append(port.admit(tool_request(port), crossing_evidence=tool_evidence()))
        finally:
            finished.set()

    plane, runtime, owner, delivered, _ = delivery_plane(tmp_path, script)
    original = owner.resolve_invocation_cut

    def blocked(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    owner.resolve_invocation_cut = blocked
    plane._supervision = replace(plane._supervision, execution_ms=150)
    with plane:
        try:
            receipt = plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
            assert entered.is_set()
            assert plane.get_operation(receipt.operation_id).state.value == "indeterminate"
            assert runtime.port.closed
        finally:
            release.set()
            assert finished.wait(3)
        assert len(answers) == 1
        assert not answers[0].admitted
        assert not plane.snapshot.participant_behavior_history.get(PARTICIPANT)
        assert not plane._mutation_authority.owns_current_thread()


@pytest.mark.parametrize("uncertain", [False, True])
def test_conflicting_effects_reserve_capacity_until_known_settlement(tmp_path, uncertain):
    from delivery_invocation_fixtures import tool_payload

    def conflicting(payload):
        tool_payload(payload)
        payload["action_contracts"]["probe"]["interactions"] = [
            {
                "interaction_class": "shared_state_change",
                "target": "nodes.web",
                "rationale": "Both tools update the same declared node state.",
                "shared_state_refs": ["nodes.web"],
            }
        ]

    def script(invocation, port):
        first = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        second = port.admit(tool_request(port, tool_call_id="second"), crossing_evidence=tool_evidence())
        grant = port.dispatch(first.action_instance_id)
        assert grant.accepted
        assert port.dispatch(second.action_instance_id).refusal is ParticipantToolActionRefusal.SEMANTIC_CONFLICT
        if uncertain:
            assert port.report_unknown(grant.action_instance_id, "timeout").accepted
            assert port.dispatch(second.action_instance_id).refusal is ParticipantToolActionRefusal.UNRESOLVED_EFFECTS
        else:
            assert port.complete(grant.action_instance_id, tool_outcome(port, grant.binding)).accepted
            next_grant = port.dispatch(second.action_instance_id)
            assert next_grant.accepted
            assert port.complete(next_grant.action_instance_id, tool_outcome(port, next_grant.binding)).accepted

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path, script, payload_transform=conflicting)
    with plane:
        receipt = plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        assert len(plane.snapshot.participant_behavior_history[PARTICIPANT]) == 6
        assert plane.get_operation(receipt.operation_id).state.value == ("indeterminate" if uncertain else "succeeded")


@pytest.mark.parametrize("after_commit", [False, True])
def test_admission_store_failure_never_leaves_an_untracked_live_child(tmp_path, after_commit):
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    class Store(LocalControlPlaneStore):
        fail_once = True

        def claim_record(self, record, **kwargs):
            if self.fail_once and record.result_payload and "delivery_tool" in record.result_payload:
                self.fail_once = False
                if after_commit:
                    super().claim_record(record, **kwargs)
                raise OSError("synthetic admission acknowledgement failure")
            return super().claim_record(record, **kwargs)

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        assert decision.admitted is after_commit

    plane, runtime, _, delivered, _ = delivery_plane(tmp_path, script, store=Store(tmp_path / "durable"))
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        history = plane.snapshot.participant_behavior_history.get(PARTICIPANT, ())
        assert len(history) == (3 if after_commit else 0)
        assert all(
            record.status.state.value not in {"accepted", "running"}
            for record in plane._operations.values()
            if record.result_payload and "delivery_tool" in record.result_payload
        )


@pytest.mark.parametrize("unreachable", ["participant", "ambiguous-offer"])
def test_plan_refuses_a_delivery_relation_the_port_cannot_execute(tmp_path, unreachable):
    from copy import deepcopy

    from raes_runtime.participant_delivery_driver import delivery_tool_driver_actions

    def authored(payload):
        temporal_payload(payload)
        if unreachable == "participant":
            payload["agents"]["other-agent"] = deepcopy(payload["agents"]["red-agent"])
            spec = payload["behavior_specifications"]["red-briefing"]
            spec["participant_refs"].append("other-agent")
            spec["tool_affordances"]["probe"]["participant_refs"] = ["other-agent"]

    plane, _, _, _, model = delivery_plane(tmp_path, payload_transform=authored)
    with plane:
        if unreachable == "ambiguous-offer":
            capability = plane._target.manifest.participant_runtime
            duplicate = replace(capability.execution_bindings[0], binding_id="overlapping-offer")
            capability = replace(capability, execution_bindings=(*capability.execution_bindings, duplicate))
            manifest = replace(
                plane._target.manifest,
                capabilities=replace(plane._target.manifest.capabilities, participant_runtime=capability),
            )
            plane._target = replace(plane._target, manifest=manifest)
        assert not delivery_tool_driver_actions(plane, model)
        assert any(
            item.code == "runtime.participant-temporal-driver-unsupported"
            for item in plane.plan(model.realization_instance).diagnostics
        )


def test_lost_dwell_dispatch_ack_retains_proofs_and_settles_unknown_once(tmp_path):
    from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.control_plane_store import LocalControlPlaneStore

    class Store(LocalControlPlaneStore):
        fail_once = True

        def commit_participant_transition(self, **kwargs):
            result = super().commit_participant_transition(**kwargs)
            record = kwargs["record"]
            if (
                self.fail_once
                and record.result_payload
                and "delivery_tool" in record.result_payload
                and record.status.state is OperationState.RUNNING
            ):
                self.fail_once = False
                raise OSError("synthetic lost dispatch acknowledgement")
            return result

    children = []

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        assert decision.admitted
        children.append(decision.action_instance_id)
        context = decision.binding.temporal_contexts[0].shared_time
        proof = ParticipantTemporalEvidenceModel(
            context=context,
            observation_boundary_address=decision.binding.observation_boundary_address,
            evidence_mode="continuous",
            condition_precondition_id="present",
            coverage=[{"start": context.bound_start, "end": context.bound_end, "condition_holds": True}],
            evidence_refs=(decision.binding.observation_boundary_evidence_refs[0],),
        )
        assert not port.dispatch(decision.action_instance_id, temporal_evidence=(proof,)).accepted

    plane, runtime, _, delivered, _ = delivery_plane(
        tmp_path, script, store=Store(tmp_path / "durable"), payload_transform=dwell_payload
    )
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        assert plane.get_operation(children[0]).state is OperationState.INDETERMINATE
        history = plane.snapshot.participant_behavior_history[PARTICIPANT]
        assert len(history) == 3
        assert history[-1]["invocation_tool_context"]["settlement"] == "indeterminate"
        assert plane._operations[children[0]].result_payload["delivery_tool"]["admission"]["temporal_evidence"]


def test_crossing_resolver_cannot_rewrite_runtime_owned_temporal_bounds(tmp_path):
    from types import SimpleNamespace

    from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
    from raes_runtime.participant_crossing_intents import action_subject
    from sem233_flow_sink_fixtures import Sem233FlowSinkResolver

    class Resolver(Sem233FlowSinkResolver):
        def resolve_operation(self, intent, snapshot, carrier):
            if isinstance(carrier, ParticipantActionAdmissionRequest):
                context = carrier.temporal_contexts[0].shared_time
                context.binding.end.tick = 1000
                context.bound_end.tick = 1000
                intent.subject = action_subject(SimpleNamespace(_snapshot=snapshot), carrier).model_copy(
                    update={"subject_ref": intent.subject.subject_ref},
                )
            return self.resolve(intent, snapshot)

    def script(invocation, port):
        decision = port.admit(tool_request(port), crossing_evidence=tool_evidence())
        assert not decision.admitted

    plane, runtime, _, delivered, _ = delivery_plane(
        tmp_path, script, resolver=Resolver(), payload_transform=temporal_payload
    )
    with plane:
        plane.invoke_participant_delivery(invocation_request(delivered), identity=caller())
        assert not runtime.errors, "\n".join(map(str, runtime.errors))
        assert not plane.snapshot.participant_behavior_history.get(PARTICIPANT)
