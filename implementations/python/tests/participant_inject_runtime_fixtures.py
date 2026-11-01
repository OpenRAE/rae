"""Executing world and independent disclosure owners for #1368."""

from dataclasses import replace

import yaml
from inject_execution_fixtures import ExecutingFixture, fixture_target, reference
from participant_crossing_fixtures import evidence, policy_capable_target
from raes import parse_sdl
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import InjectTriggerRequestModel
from raes_contracts.contracts.participant_inject_application import (
    ParticipantInjectApplicationModel,
    ParticipantInjectContentModel,
)
from raes_contracts.contracts.plan_projection import runtime_plan_digest
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ParticipantAudienceSubjectBinding,
    ParticipantControlSubjectBinding,
)
from raes_runtime.participant_control_runtime import ParticipantControlLiveCut
from raes_runtime.participant_inject_delivery import ParticipantInjectResolution, ParticipantInjectRuntimeBinding
from raes_runtime.time_coordinator import TimeCoordinator
from sem233_flow_sink_fixtures import permit_resolver
from test_dsl_142_participant_inject_delivery import BINDING_ADDRESS, _scenario_yaml

PARTICIPANT = "participant.behavior.red-agent"
AUDIENCE = "audience.participant.red-agent"


class DisclosureOwner:
    calls = 0
    fail = False

    def resolve_delivery(self, delivery, application, correlation, snapshot):
        self.calls += 1
        if self.fail:
            raise RuntimeError("private projection details")
        proof = evidence().model_copy(update={"audience_scope_ref": AUDIENCE})
        proof = proof.model_copy(
            update={"required_evidence_refs": [*proof.required_evidence_refs, *delivery.evidence_requirement_addresses]}
        )
        return ParticipantInjectResolution(
            content=ParticipantInjectContentModel(
                view_id="disclosed:" + application.request_key,
                participant_address=application.participant_address,
                episode_id=application.episode_id,
                application=application,
                source_snapshot_ref=f"runtime.snapshot.revision.{application.expected_snapshot_revision}",
                correlation=correlation,
                disclosed_item=reference(delivery.result_item_address),
                visibility_projection_ref=delivery.disclosure_basis_ref,
                observation_boundary_ref=delivery.observation_boundary_address,
                content="Approved briefing result",
            ),
            evidence=proof,
            cut=ParticipantControlLiveCut(
                request_ref=application.request_key,
                effective_order=_delivery_order(snapshot) if delivery.control else 5,
                active_authority_basis_refs=["entities.red-team", "entities.blue-team"],
                authorized_scope_refs=["provision.node.web"],
                evidence_refs=[*proof.evidence_refs, "entity.red-team", "entity.blue-team"],
            ),
        )


def caller(*, audience=True, controller=True):
    return ControlPlaneIdentity(
        "operator",
        frozenset({ControlPlaneRole.OPERATOR}),
        "stub",
        participant_audience_subjects=(ParticipantAudienceSubjectBinding(PARTICIPANT, AUDIENCE),) if audience else (),
        participant_control_subjects=(
            ParticipantControlSubjectBinding(PARTICIPANT, PARTICIPANT),
            ParticipantControlSubjectBinding(PARTICIPANT, "participant.behavior.supervisor-agent"),
        )
        if controller
        else (),
    )


def configured_plane(
    tmp_path,
    *,
    store=None,
    controlled=None,
    tick=5,
    capture_fail=False,
    capture_available=True,
    capture_required=True,
    optional_capture_fail=False,
    resolver=None,
    delivery_revision=None,
    fresh_result=False,
    revalidate_mutation=False,
    epoch="scenario_start",
    profile=None,
    world_identity=None,
    participants=True,
    participant_control=None,
):
    from mixed_control_rev1_scenarios import rev1_delivery_scenario

    payload = rev1_delivery_scenario() if controlled else yaml.safe_load(_scenario_yaml())
    if fresh_result:
        payload["content"]["briefing-result"] = {
            **payload["content"]["briefing"],
            "path": "/opt/briefing-result.txt",
            "text": "Approved derived result",
            "sensitive": False,
        }
        payload["behavior_specifications"]["red-briefing"]["participant_inject_deliveries"]["briefing"][
            "result_item_ref"
        ] = "content.briefing-result"
        boundary = payload["observation_boundaries"]["red-view"]
        boundary["observable_refs"].append("content.briefing-result")
        boundary["view_rules"].append({**boundary["view_rules"][0], "information_ref": "content.briefing-result"})
    if controlled == "intervention":
        policy = payload["behavior_specifications"]["red-briefing"]["mixed_control"]
        policy["permitted_transitions"]["direct-briefing"]["transition_kind"] = "intervention"
        del policy["permitted_transitions"]["direct-briefing"]["target_kinds"]
        payload["behavior_specifications"]["red-briefing"]["participant_inject_deliveries"]["briefing"][
            "delivery_kind"
        ] = "intervention"
    if delivery_revision is not None:
        payload["behavior_specifications"]["red-briefing"]["participant_inject_deliveries"]["briefing"][
            "delivery_policy"
        ]["policy_revision"] = delivery_revision
    payload["nodes"]["web"]["injects"] = ["briefing-inject"]
    payload["clocks"]["exercise-clock"]["supports_reset"] = True
    payload["time_domains"]["exercise-time"]["epoch"] = epoch
    payload["injects"]["briefing-inject"]["source"] = {"name": "fixture-source", "version": "1"}
    payload["temporal_constraints"]["briefing-window"]["start"] = {"tick": 0}
    payload["time_progression_policies"] = {
        "exercise": {
            "clock_ref": "exercise-clock",
            "advancement_mode": "stepped",
            "synchronization_mode": "barrier",
            "step_ticks": 5,
            "reset_behavior": "new_segment_zero",
            "replay_behavior": "restore_recorded_advances",
            "description": "Test schedule progression",
        }
    }
    payload["evidence_requirements"]["briefing-delivery-evidence"]["observation_demand"] = {
        "rule_id": "briefing-capture",
        "scope": "/nodes/web",
        "purpose": "experimental",
        "mode": "selected",
        "selector": {
            "semantic_scope": "/nodes/web",
            "component_refs": payload["evidence_requirements"]["briefing-delivery-evidence"]["source_refs"],
            "data_kind": "stream",
            "names": ["log"],
            "window_refs": ["briefing delivery window"],
        },
        "collection": "require",
        "retention": "require",
        "export": "disable",
        "redaction": "none",
        "integrity": "checksum",
        "required": capture_required,
    }
    if optional_capture_fail:
        from copy import deepcopy

        optional = deepcopy(payload["evidence_requirements"]["briefing-delivery-evidence"])
        optional["observation_demand"].update(rule_id="optional-diagnostics", required=False)
        optional["observation_demand"]["selector"]["names"] = ["optional-diagnostics"]
        payload["evidence_requirements"]["optional-diagnostics"] = optional
    scenario = parse_sdl(yaml.safe_dump(payload))
    model = compile_runtime_model(scenario)

    class WorldFixture(ExecutingFixture):
        def admit(self, *args):
            from raes import canonical_instantiated_sdl_digest
            from raes_backend_protocols.inject_execution import InjectAdmission

            admission = super().admit(*args)
            self.claim = admission.occurrence.model_copy(
                update={
                    "scenario": admission.occurrence.scenario.model_copy(
                        update={"digest": canonical_instantiated_sdl_digest(model.realization_instance).value}
                    )
                }
            )
            return InjectAdmission(admission.plan, self.claim)

    backend = WorldFixture(tmp_path / "world")
    selected = fixture_target(backend)
    policy = policy_capable_target(
        "participant_ingress_admission",
        "participant_egress_projection",
        "participant_transformation",
        "participant_directed_inject_delivery",
        "participant_intervention",
        *(("participant_modular_control",) if participant_control is not None else ()),
    )
    selected = replace(selected, manifest=replace(selected.manifest, capabilities=policy.manifest.capabilities))
    from raes_contracts.observation_demand import ObservationLifecycleStage
    from raes_runtime.observation_execution import ConfiguredObservationRuntime
    from test_issue_1112_capture_admission import _offer
    from test_issue_1212_observation_demand import _runtime_capability

    offer = _offer(
        output_contract="experiment-evidence-record-v1",
        artifact_roles=frozenset({"delivery_evidence"}),
        source_classes=frozenset({"sdl-evidence-requirement"}),
        source_refs=frozenset(payload["evidence_requirements"]["briefing-delivery-evidence"]["source_refs"]),
        scopes=frozenset({"run"}),
        scope_refs=frozenset(payload["evidence_requirements"]["briefing-delivery-evidence"]["scope_refs"]),
        window_kinds=frozenset({"briefing delivery window"}),
    )
    observation = replace(selected.manifest.observation, capture_offers=(offer,))
    selected = replace(
        selected,
        manifest=replace(
            selected.manifest, capabilities=replace(selected.manifest.capabilities, observation=observation)
        ),
    )
    capabilities = tuple(
        replace(
            _runtime_capability(
                selector,
                stages=frozenset({ObservationLifecycleStage.COLLECTION, ObservationLifecycleStage.RETENTION}),
                integrity_policies=frozenset({"checksum"}),
            ),
            capture_kind="log",
            channel_kind="backend-log",
        )
        for demand in model.observation_demands
        for selector in demand.selectors
    )
    capture = ConfiguredObservationRuntime(
        capabilities=capabilities,
        producers={
            capability.capability_id: (
                lambda *args: (
                    (_ for _ in ()).throw(RuntimeError("private capture failure"))
                    if capture_fail or (optional_capture_fail and args[0].names == ("optional-diagnostics",))
                    else ({"evidence": "capture"},)
                )
            )
            for capability in capabilities
        },
        integrity_providers={"checksum": lambda key, values: canonical_json_digest(values)},
    )
    selected = replace(selected, observation_runtime=capture if capture_available else None)
    backend.plan, backend.scenario = plan(model, selected.manifest), scenario
    owner = DisclosureOwner()
    initial = TimeCoordinator(model.time_model).initialize()
    if tick:
        initial = TimeCoordinator(model.time_model).advance(initial, "time.clock.exercise-clock", ticks=tick)
    if store is not None:
        lease = store.admit_runtime(target_scope="target:stub", run_scope="run:default")
        try:
            if not store.load_records():
                store.save_snapshot(initial, expected_revision=store.load_snapshot_state().revision)
        finally:
            lease.close()
    options = {}
    resolver = resolver or permit_resolver()
    authored_policy = next(iter(model.participant_inject_deliveries.values()))
    resolver.policy = resolver.policy.model_copy(
        update={"policy_id": authored_policy.policy_ref, "policy_revision": authored_policy.policy_revision}
    )
    if controlled:
        from raes_runtime.participant_control_runtime import MixedControlRuntimeBinding
        from reusable_control_runtime_fixtures import CutOwner

        class Owner(CutOwner):
            def resolve_delivery_cut(self, policy, application, snapshot):
                return ParticipantControlLiveCut(
                    request_ref=application.request_key,
                    effective_order=_delivery_order(snapshot),
                    active_authority_basis_refs=sorted(
                        {ref for state in policy.states for ref in state.authority_basis_refs} - self.revoked
                    ),
                    authorized_scope_refs=sorted({ref for state in policy.states for ref in state.scope_refs}),
                    evidence_refs=sorted(
                        {
                            ref
                            for delivery in model.participant_inject_deliveries.values()
                            for ref in (delivery.control.evidence_addresses or delivery.control.evidence_refs)
                        }
                    ),
                )

        options["mixed_control"] = MixedControlRuntimeBinding(model=model, resolver=Owner())
    plane = RuntimeControlPlane(
        selected,
        initial_snapshot=initial if store is None else None,
        store=store,
        inject_execution=backend,
        operation_evidence=backend,
        profile=profile,
        inject_delivery=ParticipantInjectRuntimeBinding(model=model, resolver=owner),
        behavior_specifications=model.behavior_specifications,
        crossing_policy_resolver=resolver,
        participant_control=participant_control,
        **options,
    )
    if controlled:
        backend.plan = plan(model, selected.manifest, mixed_control_admission=plane.mixed_control_planning_admission())
    assert backend.plan.is_valid, backend.plan.diagnostics
    plane.register_planner_produced_plan(backend.plan)
    if revalidate_mutation:
        original_revalidate = backend.revalidate

        def revalidate(occurrence, snapshot):
            original_revalidate(occurrence, snapshot)
            state = plane._store.load_snapshot_state()
            plane._store.save_snapshot(
                state.snapshot.with_entries(dict(state.snapshot.entries), metadata={"cut": "advanced"}),
                expected_revision=state.revision,
            )

        backend.revalidate = revalidate
    if participants and PARTICIPANT not in plane.snapshot.participant_episode_results:
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1", identity=caller())
    request = InjectTriggerRequestModel(
        request_key="world-key-1",
        occurrence_id="world-occurrence-1",
        target_scope="target:stub",
        run_scope="run:default",
        plan={
            "contract_id": "orchestration-plan-v1",
            "artifact_id": "fixture-plan",
            "digest": runtime_plan_digest(backend.plan.orchestration),
        },
        inject="orchestration.inject.briefing-inject",
        bindings=(
            {
                "binding": "orchestration.inject-binding.web.briefing-inject",
                "node": "provision.node.web",
                "instance": "web-instance",
                "revision": "web-revision",
            },
        ),
        placement={
            "kind": "schedule",
            "event": "orchestration.event.briefing-event",
            "script": "orchestration.script.briefing-script",
            "story": "orchestration.story.briefing-story",
            "slot": "slot-1",
        },
        expected_head="inject-order:genesis",
    )
    receipt = plane.submit_inject(request, identity=world_identity or caller())
    backend.world_request = request
    application = ParticipantInjectApplicationModel(
        request_key="delivery-1",
        world_operation_id=receipt.operation_id,
        delivery_address=BINDING_ADDRESS,
        delivery_digest=canonical_json_digest(model.participant_inject_deliveries[BINDING_ADDRESS].spec),
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        expected_snapshot_revision=plane._snapshot_state.revision,
    )
    return plane, backend, owner, application


def apply_control(plane, kind, *, revision, head, order, target=None):
    from raes_contracts.runtime_state import OperationState
    from raes_runtime.participant_control_intents import (
        ParticipantExternalDirectionControlIntent,
        ParticipantHandoffControlIntent,
        ParticipantInterventionControlIntent,
    )

    policy = plane._behavior_specifications["participant.behavior-specification.red-briefing"].mixed_control_policy
    edge = next(
        item
        for item in policy.permitted_transitions
        if item.transition_id == ("take" if kind == "handoff" else "direct-briefing")
    )
    key = f"control-{order}"
    plane._mixed_control.resolver.orders[key] = order
    fields = dict(
        declaration_ref=edge.address,
        episode_id="episode-1",
        client_correlation_id=key,
        policy_revision=policy.policy_revision,
        expected_state_revision=revision,
        provenance_refs=["provenance:test"],
        evidence_refs=[*(edge.evidence_addresses or edge.evidence_refs), f"completion:{key}"],
        object_marking_refs=["marking:test"],
        limitation_refs=["limitation:none"],
        application={
            "semantics": policy.semantics,
            "policy_ref": policy.address,
            "prior_state_ref": edge.from_state_address,
            "expected_history_head": head,
            "effective_order": order,
        },
    )
    if kind == "handoff":
        intent = ParticipantHandoffControlIntent(**fields, completion_evidence_ref=f"completion:{key}")
    elif kind == "external-direction":
        intent = ParticipantExternalDirectionControlIntent(
            **fields,
            target_kind="control",
            target_ref=target["event_id"],
            target_revision=target["occurrence"]["occurrence_revision"],
        )
    else:
        intent = ParticipantInterventionControlIntent(
            **fields,
            affected_target_kind="control",
            affected_occurrence_ref=target["event_id"],
            affected_revision=target["occurrence"]["occurrence_revision"],
            intervention_ref=key,
        )
    receipt = plane.record_participant_control(
        PARTICIPANT,
        intent,
        identity=caller(),
        crossing_evidence=evidence().model_copy(update={"audience_scope_ref": AUDIENCE}),
        idempotency_key=key,
    )
    assert plane.get_operation(receipt.operation_id).state is OperationState.SUCCEEDED
    return plane.snapshot.participant_control_history[PARTICIPANT][-1]


def _delivery_order(snapshot):
    return (
        max(
            (
                event["occurrence"].get("effective_order", 0)
                for event in snapshot.participant_control_history.get(PARTICIPANT, ())
            ),
            default=0,
        )
        + 1
    )
