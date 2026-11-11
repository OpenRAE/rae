"""Small core SDL and executable protocol fixtures for delivery invocations."""

from copy import deepcopy
from dataclasses import replace

from deterministic_participant_fixtures import build_implementation_manifest, build_implementation_selection
from participant_inject_runtime_fixtures import PARTICIPANT, DisclosureOwner, configured_plane
from participant_inject_runtime_fixtures import caller as inject_caller
from raes_backend_protocols.participant_capabilities import ParticipantExecutionBinding, ParticipantFeatureSupport
from raes_contracts.contracts.participant_invocation_tools import ParticipantInvocationToolActionCapabilitiesModel
from raes_contracts.contracts.participant_tool_support import ParticipantToolProfilesModel
from raes_runtime.participant_control_runtime import ParticipantControlLiveCut

ACTION = "participant.action-contract.probe"
AFFORDANCE = "participant.behavior-specification.red-briefing.tool-affordance.probe"
BOUNDARY = "participant.observation-boundary.red-view"
TARGET = "provision.node.web"


def caller(*, controller=True, supervisor=False):
    identity = inject_caller(controller=controller)
    subjects = identity.participant_control_subjects[1:] if supervisor else identity.participant_control_subjects[:1]
    return replace(identity, participant_control_subjects=subjects)


def tool_payload(payload):
    payload["action_contracts"] = {
        "probe": {
            "semantic_version": "1.0.0",
            "lifecycle_state": "active",
            "behavioral_granularity": "atomic",
            "procedure_basis": "One bounded observation of the declared node.",
            "realization_profile": "backend-declared",
            "fidelity_claim": "Records the declared observation with an exact action binding.",
            "preconditions": [
                {
                    "precondition_id": "present",
                    "precondition_class": "target",
                    "description": "Declared node is present.",
                    "support_refs": ["nodes.web"],
                }
            ],
            "effects": [
                {
                    "effect_id": "observe",
                    "effect_class": "intended_effect",
                    "description": "Observe node.",
                    "target_refs": ["nodes.web"],
                }
            ],
            "observation_expectations": ["terminal node observation"],
            "failure_classes": ["backend_error", "unknown"],
        }
    }
    participant = payload["agents"]["red-agent"]
    participant.update(actions=["probe"], authority_anchors=["entities.red-team"], operating_scope=["nodes.web"])
    specification = payload["behavior_specifications"]["red-briefing"]
    specification["action_contract_refs"] = ["probe"]
    specification["tool_affordances"] = {
        "probe": {"action_contract_refs": ["probe"], "observation_boundary_refs": ["red-view"]}
    }
    boundary = payload["observation_boundaries"]["red-view"]
    boundary["evidence_refs"] = ["content.participant-observation"]
    reference = "behavior_specifications.red-briefing.tool_affordances.probe"
    boundary["observable_refs"].append(reference)
    boundary["view_rules"].append(
        {
            "information_ref": reference,
            "boundary_class": "observable_resource",
            "disposition": "observable",
            "visibility_basis": "Declared tool availability.",
        }
    )


class InvocationOwner(DisclosureOwner):
    revoked = False
    revoked_control_evidence = False

    def resolve_invocation_cut(self, invocation, request, snapshot):
        self.invocation_requests = [*getattr(self, "invocation_requests", ()), deepcopy(request)]
        history = snapshot.participant_crossing_history.get(PARTICIPANT, ())
        order = max((item["occurrence"]["effective_order"] for item in history), default=0) + 1
        return ParticipantControlLiveCut(
            request_ref=request.action_instance_id,
            effective_order=order,
            active_authority_basis_refs=[] if self.revoked else ["entities.red-team", "entities.blue-team"],
            authorized_scope_refs=[TARGET],
            evidence_refs=["evidence.operator.authorization"]
            if self.revoked_control_evidence
            else [
                "evidence.operator.authorization",
                "entities.red-team",
                "entities.blue-team",
            ],
        )


class DeliveryRuntime:
    """Composition uses the protocol, not a reference runtime subclass."""

    def __init__(self, ordinary, script):
        self.ordinary = ordinary
        self.script = script
        self.calls = 0
        self.port = None
        self.errors = []

    def __getattr__(self, name):
        return getattr(self.ordinary, name)

    def invoke_delivery(self, invocation, tools):
        from raes_contracts.contracts.participant_delivery_invocation import ParticipantDeliveryInvocationOutcomeModel

        self.calls += 1
        self.port = tools
        try:
            result = None if self.script is None else self.script(invocation, tools)
        except BaseException as error:
            self.errors.append(error)
            raise
        return result if result is not None else ParticipantDeliveryInvocationOutcomeModel(status="succeeded")


def delivery_plane(
    tmp_path, script=None, *, store=None, payload_transform=tool_payload, resolver=None, controlled=False
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    retained = {}

    def target_transform(selected, model):
        from raes_processor.compiler import compile_participant_invocation_tools

        selection = build_implementation_selection(PARTICIPANT)
        _, temporal = compile_participant_invocation_tools(
            model,
            "participant.behavior-specification.red-briefing",
            participant_implementation_ref=selection.manifest_ref,
            max_actions=4,
            max_in_flight=2,
        )
        binding = ParticipantExecutionBinding(
            binding_id="binding.delivery.probe",
            action_contract_address=ACTION,
            target_addresses=(TARGET,),
            participant_implementation_ref=selection.manifest_ref,
            constraint_refs=("constraint.probe",),
            evidence_refs=("evidence.probe",),
            max_action_attempts=4,
            max_in_flight=2,
            timeout_seconds=30,
            max_retries=0,
            temporal_contract_digests=tuple(item.contract_digest for item in temporal),
        )
        claim = ParticipantInvocationToolActionCapabilitiesModel(
            semantic_versions=["participant-invocation-tool-actions/v2"],
            max_tool_actions_per_invocation=4,
            max_concurrent_tool_actions_per_invocation=2,
        )
        capability = replace(
            selected.manifest.participant_runtime,
            supported_behavior_features=selected.manifest.participant_runtime.supported_behavior_features
            | {"tool_affordances", "scoped_tool_affordances"},
            feature_support=(
                *(
                    entry
                    for entry in selected.manifest.participant_runtime.feature_support
                    if entry.feature not in {"tool_affordances", "scoped_tool_affordances"}
                ),
                ParticipantFeatureSupport(
                    feature="tool_affordances", support_level="exact", evidence_refs=("evidence.probe",)
                ),
                ParticipantFeatureSupport(
                    feature="scoped_tool_affordances", support_level="exact", evidence_refs=("evidence.probe",)
                ),
            ),
            tool_profiles=ParticipantToolProfilesModel(
                semantic_versions=["participant-tool-profile/v1"],
                max_bindings_per_profile=4,
                max_participants_per_binding=4,
            ),
            invocation_tool_actions=claim,
            execution_bindings=(binding,),
        )
        runtime = DeliveryRuntime(selected.participant_runtime, script)
        retained.update(runtime=runtime, model=model)
        return replace(
            selected,
            participant_runtime=runtime,
            manifest=replace(
                selected.manifest, capabilities=replace(selected.manifest.capabilities, participant_runtime=capability)
            ),
        )

    plane, _, owner, application = configured_plane(
        tmp_path,
        store=store,
        payload_transform=payload_transform,
        target_transform=target_transform,
        owner_type=InvocationOwner,
        world_identity=caller(supervisor=controlled),
        resolver=resolver,
        controlled="external-direction" if controlled else None,
    )
    retained_delivery = next(
        (record for record in plane._operations.values() if record.inject_delivery is not None), None
    )
    if controlled and retained_delivery is None:
        from participant_inject_runtime_fixtures import apply_control
        from raes_contracts.canonical import canonical_json_digest

        target = apply_control(plane, "handoff", revision=0, head=0, order=1)
        event = apply_control(plane, "external-direction", revision=1, head=1, order=2, target=target)
        application = type(application).model_validate(
            {
                **application.model_dump(mode="json"),
                "expected_snapshot_revision": plane._snapshot_state.revision,
                "control": {
                    "event_id": event["event_id"],
                    "occurrence_revision": event["occurrence"]["occurrence_revision"],
                    "digest": canonical_json_digest(event),
                },
            }
        )
    receipt = (
        retained_delivery.receipt
        if retained_delivery is not None
        else plane.deliver_participant_inject(application, identity=caller(supervisor=controlled))
    )
    return plane, retained["runtime"], owner, receipt, retained["model"]


def invocation_request(receipt, **changes):
    from raes_contracts.contracts.participant_delivery_invocation import ParticipantDeliveryInvocationRequestModel

    return ParticipantDeliveryInvocationRequestModel(
        request_key="invoke-delivery-1",
        delivery_operation_id=receipt.operation_id,
        implementation_manifest=build_implementation_manifest(),
        implementation_selection=build_implementation_selection(PARTICIPANT),
        **changes,
    )


def tool_request(port, **changes):
    from raes_contracts.participant_tool_actions import ParticipantToolActionRequest

    values = dict(
        tool_call_id="call-1",
        invocation_action_instance_id=port.invocation_action_instance_id,
        participant_address=port.participant_address,
        episode_id=port.episode_id,
        participant_implementation_ref=port.participant_implementation_ref,
        tool_affordance_address=AFFORDANCE,
        action_contract_address=ACTION,
        observation_boundary_address=BOUNDARY,
        target_addresses=(TARGET,),
        execution_scope_ref=port.execution_scope_ref,
        execution_generation=port.execution_generation,
    )
    return ParticipantToolActionRequest(**{**values, **changes})


def tool_evidence():
    from participant_crossing_fixtures import evidence
    from participant_inject_runtime_fixtures import AUDIENCE

    return evidence().model_copy(update={"audience_scope_ref": AUDIENCE})


def tool_outcome(port, binding, **changes):
    from raes_contracts.contracts.participant_runtime import ParticipantActionResultModel

    values = dict(
        status="succeeded",
        participant_address=port.participant_address,
        episode_id=port.episode_id,
        action_instance_id=binding.action_instance_id,
        action_contract_address=binding.action_contract_address,
        observation_point=binding.temporal_contexts[0].observation_point
        if binding.temporal_contexts
        else port.observation_point,
    )
    return ParticipantActionResultModel(**{**values, **changes})


def temporal_payload(payload):
    from _act_614_temporal_fixtures import _bound_deadline_payload

    tool_payload(payload)
    source = _bound_deadline_payload()
    declaration = source["action_contracts"]["probe-customer-portal-login"]
    temporal = declaration["temporal_contracts"][0]
    temporal["clock_authority"] = "exercise-clock"
    temporal["time_domain"] = "scenario_time"
    temporal["shared_time_binding"]["clock_ref"] = "exercise-clock"
    payload["action_contracts"]["probe"].update(
        temporal_contracts=[temporal],
        backend_timing_disclosures=declaration["backend_timing_disclosures"],
    )
    constraint = source["temporal_constraints"]["finish-by-five"]
    constraint.update(clock_ref="exercise-clock", subject_refs=["action_contracts.probe"])
    payload["temporal_constraints"]["finish-by-five"] = constraint
