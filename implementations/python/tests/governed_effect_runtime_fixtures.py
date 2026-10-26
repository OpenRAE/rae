"""Installed v2 providers and independent effect-owner resolutions for #1369."""

from dataclasses import replace

from participant_control_contract_fixtures import ref
from participant_control_runtime_fixtures import _effect_evidence, _handoff_intent, handoff_effect_payload
from participant_control_v2_fixtures import Provider, Resolver, binding
from participant_crossing_fixtures import CONTROLLER, PARTICIPANT, StaticCrossingResolver, control_specification
from raes_contracts.contracts.participant_control_applicability import (
    ParticipantControlSelectionV2Model,
    control_digest,
)
from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.participant_control_effects import ParticipantControlEffectOperation
from test_issue_1069_participant_control_effects import _target


class EffectProvider(Provider):
    def resolve_stage(self, invocation):
        slot_id = invocation.requested_slot_ids[0]
        if slot_id != "effect" and slot_id not in self.resolver.effect_specs:
            return super().resolve_stage(invocation)
        owner = self.resolver
        request, _ = owner.projections[invocation.projection]
        owner.calls.append("effect")
        effect = handoff_effect_payload()["results"][1]["payload"]
        effect.update(
            phase=owner.phase,
            parent_outcome=owner.parent_outcome,
            allowed_parent_dispositions=["permit", "deny", "withhold"] if owner.phase == "independent" else [],
            originating_principal_ref=owner.principal,
            trigger=ref("trigger-1", "trigger"),
        )
        effect["key"].update(run_ref=request.context.run.ref, trigger_root=request.context.trigger_root)
        effect["effect_id"] = owner.effect_id
        effect["key"]["slot"] = owner.effect_id
        effect["target"].update(
            participant_address=PARTICIPANT,
            prior_controller_ref=CONTROLLER,
            resulting_controller_ref="participant.behavior.next-supervisor",
        )
        if owner.target is not None:
            effect["target"] = owner.target
        override = owner.effect_specs.get(slot_id, {})
        effect.update({**override, "key": {**effect["key"], **override.get("key", {})}})
        result = ControlMechanismResultV2Model(
            result_id="result-" + slot_id,
            slot_id=slot_id,
            instance_id=self.instance_id,
            binding_digest=invocation.binding_digest,
            context_digest=invocation.context_digest,
            invocation_digest=control_digest(invocation),
            status="resolved",
            payload=effect,
            evidence=(ref("effect-evidence"),),
            next_provider_state=None,
        )
        self.results.append(result)
        return (result,)


class EffectResolver(Resolver):
    def __init__(self, *, decision="permit", phase="independent", parent_outcome="none", target=None):
        super().__init__()
        self.decision, self.phase, self.parent_outcome, self.target = decision, phase, parent_outcome, target
        selection = self.selection.model_dump(mode="json")
        selection["slots"].append(
            dict(
                slot_id="effect",
                instance_id="influence",
                kind="effect-request",
                role="mandatory",
                dependencies=[dict(slot_id="assessment", kind="advisory")],
            )
        )
        selection["obligations"].append(
            dict(
                obligation_id="effect-owner",
                profile=selection["bindings"][0]["profiles"][0],
                required_kind="effect-request",
                required_strength="exact",
                constraints=[],
            )
        )
        self.selection = ParticipantControlSelectionV2Model.model_validate(selection)
        self.obligation_slots = {"parent": "rule", "effect-owner": "effect"}
        self.providers = {name: EffectProvider(self, name) for name in ("influence", "monitor")}
        self.available = True
        self.operation = None
        self.inject_deliveries = {}
        self.inject_coordinates = {}
        self.principal = "operator.red"
        self.effect_id = "effect-1"
        self.effect_specs = {}
        self.cuts = {}
        self.trigger_key = None
        self.effect_depth = 0
        self.context_override = lambda context, coordinates: context.update(
            audience_ref=coordinates["crossing"].intent.audience_scope_ref,
            depth=self.effect_depth if coordinates["crossing"].record.receipt.context.parent_operation_id else 0,
        )

    def resolve(self, **coordinates):
        from raes_contracts.contracts.participant_crossing import ParticipantCrossingSubjectKind

        self.empty = (
            coordinates["crossing"].record.idempotency_key != self.trigger_key
            if self.trigger_key is not None
            else coordinates["crossing"].intent.subject.subject_kind
            is not ParticipantCrossingSubjectKind.PARTICIPANT_ACTION_ADMISSION
        )
        resolution = super().resolve(**coordinates)
        self.cuts[control_digest(resolution.request)] = (resolution, self.records)
        return resolution

    def validation_context(self, evaluation):
        context = super().validation_context(evaluation)
        resolution, records = self.cuts[control_digest(evaluation.request)]
        from participant_control_runtime_fixtures import _admitted_safe_references, _distinct
        from raes_contracts.contracts.participant_control_resolution import control_references

        return replace(
            context,
            admitted_request=resolution.request,
            admitted_crossing=resolution.request.context.crossing,
            installed_bindings={item.instance_id: item for item in resolution.request.selection.bindings},
            resolved_coverage={item.obligation_id: item for item in resolution.request.applicability.coverage},
            resolved_support={(item.obligation_id, item.instance_id): item for item in resolution.support},
            crossing_records=records,
            crossing_subjects=_distinct(item.occurrence.subject for item in records),
            crossing_policies=_distinct(item.occurrence.policy for item in records),
            safe_references=frozenset(control_references(evaluation))
            | _admitted_safe_references(resolution.request.context, records),
            authorized_effects={
                control_digest(effect): evaluation.request.context for effect in evaluation.effect_plan.effects
            },
            inject_deliveries=self.inject_deliveries,
            inject_coordinates=self.inject_coordinates,
        )

    def effect_operation(self, effect, context):
        self.effect_depth = context.depth + 1
        if self.operation is not None:
            return self.operation(effect, context)
        if not self.available or effect.target.kind != "handoff":
            return None
        return ParticipantControlEffectOperation(
            kind="handoff",
            intent=_handoff_intent(context, effect.target),
            crossing_evidence=_effect_evidence(context),
        )


def effect_plane(owner=None, *, store=None, crossing_resolver=None):
    owner = owner or EffectResolver()
    specification = control_specification()
    specification = replace(
        specification,
        controller_states=(
            specification.controller_states[0],
            replace(
                specification.controller_states[1],
                controller_address="participant.behavior.next-supervisor",
                controller_ref="next-supervisor",
            ),
        ),
    )
    plane = RuntimeControlPlane(
        _target(),
        crossing_policy_resolver=crossing_resolver or StaticCrossingResolver(),
        behavior_specifications={specification.address: specification},
        participant_control=binding(owner),
        enforce_final_sink_flow_control=False,
        store=store,
    )
    if PARTICIPANT not in plane.snapshot.participant_episode_results:
        plane.initialize_participant_episode(PARTICIPANT, episode_id="episode-1")
    return plane, owner
