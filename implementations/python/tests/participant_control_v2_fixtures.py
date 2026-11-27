"""Safe installed v2 providers with an explicitly resolved projection store."""

import json
from copy import deepcopy

from participant_control_contract_fixtures import ref
from participant_control_runtime_fixtures import (
    _admitted_safe_references,
    _distinct,
    admitted_payload,
    advisory_monitor_payload,
    committed_crossing_records,
    live_payload,
)
from participant_crossing_fixtures import AUDIENCE, PARTICIPANT
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_applicability import (
    ParticipantControlRequestV2Model,
    ParticipantControlSelectionV2Model,
    control_digest,
)
from raes_contracts.contracts.participant_control_coordinates import ControlArtifactReferenceModel
from raes_contracts.contracts.participant_control_invocation import ControlMechanismResultV2Model
from raes_contracts.contracts.participant_control_resolution import (
    ParticipantControlValidationContextV2,
    control_references,
)
from raes_contracts.contracts.participant_control_results import ControlEffectiveSupportModel
from raes_contracts.contracts.participant_control_support_v2 import ControlSupportAssessmentV2Model
from raes_runtime.participant_control_binding import ParticipantControlResolution, ParticipantControlRuntimeBinding


class Resolver:
    def __init__(self):
        self.base = admitted_payload(advisory_monitor_payload(), participant=PARTICIPANT, audience=AUDIENCE)
        selection = deepcopy(self.base["request"]["selection"])
        selection.update(
            schema_version="participant-control-selection/v2", interpretation="participant-control-applicability/rev1"
        )
        for item in selection["bindings"]:
            item["protocol_revision"] = "participant-control-provider/v2"
            item["state_scope"] = dict(
                scope_id=item["instance_id"],
                sharing="participant",
                authority=item["authority"],
                configuration_digest=item["configuration_digest"],
            )
        # A.fact -> B.assessment -> A.rule; B's negative opinion has no veto.
        selection["slots"] = [
            dict(slot_id="fact", instance_id="influence", kind="ifc-fact", role="mandatory", dependencies=[]),
            dict(
                slot_id="assessment",
                instance_id="monitor",
                kind="advisory",
                role="advisory",
                dependencies=[dict(slot_id="fact", kind="ifc-fact")],
            ),
            dict(
                slot_id="rule",
                instance_id="influence",
                kind="decision",
                role="mandatory",
                dependencies=[dict(slot_id="assessment", kind="advisory")],
            ),
        ]
        selection["obligations"] = [
            dict(
                obligation_id="parent",
                profile=selection["bindings"][0]["profiles"][0],
                required_kind="decision",
                required_strength="exact",
                constraints=[],
            )
        ]
        self.selection = ParticipantControlSelectionV2Model.model_validate(selection)
        self.providers = {name: Provider(self, name) for name in ("influence", "monitor")}
        self.calls = []
        self.projections = {}
        self.optional = False
        self.empty = False
        self.obligation_slots = None
        self.coverage = "applies"
        self.bad_coverage = False
        self.none = False
        self.stale = False
        self.writes = set()
        self.next_states = {}
        self.support_relation = "exact"
        self.effective_level = "exact"
        self.decision = "permit"
        self.fact_tokens = None
        self.content_decision = False
        self.context_override = None

    def resolve(self, **coords):
        self.records = committed_crossing_records(coords["crossing"])
        if self.none:
            return None
        live = live_payload(
            json.loads(json.dumps(self.base).replace(PARTICIPANT, coords["intent"].participant_address)),
            crossing=coords["crossing"],
            sink_kind=coords["sink_kind"],
            head_refs=coords["expected_history_head_refs"],
        )
        self.live = live
        context = live["request"]["context"]
        from raes_runtime.participant_control_causal_state import causal_state_from_history

        retained = causal_state_from_history(
            tuple(
                item
                for records in coords["snapshot"].participant_control_evaluation_history.values()
                for item in records
            ),
            run_ref=context["run"]["ref"],
            trigger_root=context["trigger_root"],
        )
        context["attempt"] = retained.next_attempt
        context["prior_effect_claims"] = [item.model_dump(mode="json") for item in retained.claims.values()]
        context["effects_consumed"] = retained.effects_consumed
        context["rule_firings"] = [
            dict(rule_id=key[0], rule_revision=key[1], firing_epochs=sorted(value))
            for key, value in retained.firings.items()
        ]
        matching = {
            item.instance_id
            for item in self.selection.bindings
            if any(
                (app.direction, app.sink_ref, app.subject_kind)
                == (context["direction"], context["sink_ref"], context["subject"]["subject_kind"])
                for app in item.applicability
            )
        }
        applicable = (
            [item.slot_id for item in self.selection.slots if item.instance_id in matching] if not self.empty else []
        )
        active_instances = {item.instance_id for item in self.selection.slots if item.slot_id in applicable}
        context["provider_states"] = [
            dict(instance_id=item.instance_id, state=ref("state-" + item.instance_id, "provider-state"))
            for item in self.selection.bindings
            if item.instance_id in active_instances
        ]
        if self.context_override:
            self.context_override(context, coords)
        required = (["fact"] if self.optional else applicable) if applicable else []
        mapping = self.obligation_slots or {"parent": "fact" if self.optional else "rule"}
        coverage = []
        for obligation, slot in mapping.items():
            status = self.coverage if slot in applicable else "proven-inapplicable"
            coverage.append(
                dict(
                    obligation_id=obligation,
                    status=status,
                    slot_ids=[slot] if status == "applies" else [],
                    evidence=[ref("coverage")],
                )
            )
        if self.bad_coverage:
            coverage = []
        if self.stale:
            context["expected_history_heads"] = [ref("stale-head", "history")]
        request = ParticipantControlRequestV2Model.model_validate(
            dict(
                selection=self.selection.model_dump(mode="json"),
                context=context,
                applicability=dict(
                    selection_digest=control_digest(self.selection),
                    context_digest=canonical_json_digest(context),
                    applicable_slot_ids=applicable,
                    required_slot_ids=required,
                    coverage=coverage,
                    derivation_evidence=[ref("derivation")],
                ),
            )
        )
        self.request = request
        support = []
        for slot_id in required:
            slot = next(item for item in self.selection.slots if item.slot_id == slot_id)
            identity = next(
                (
                    key
                    for key, value in mapping.items()
                    if value == slot_id
                    and any(item["obligation_id"] == key and item["status"] == "applies" for item in coverage)
                ),
                "input:" + slot_id,
            )
            observed = deepcopy(next(item for item in live["support"] if item["instance_id"] == slot.instance_id))
            observed["context_digest"] = control_digest(request.context)
            observed["effective_level"] = self.effective_level
            if self.effective_level == "bounded":
                observed["constraints"] = [ref("bounded-constraint", "constraint")]
            support.append(
                ControlSupportAssessmentV2Model(
                    obligation_id=identity,
                    instance_id=slot.instance_id,
                    required_strength=next(
                        (
                            item.required_strength
                            for item in self.selection.obligations
                            if item.obligation_id == identity
                        ),
                        slot.required_strength,
                    ),
                    required_constraints=next(
                        (item.constraints for item in self.selection.obligations if item.obligation_id == identity),
                        slot.constraints,
                    ),
                    effective_support=ControlEffectiveSupportModel.model_validate(observed),
                    relation=self.support_relation,
                    evidence=(ref("support-assessment"),),
                )
            )
        self.support = tuple(support)
        return ParticipantControlResolution(
            request=request,
            support=self.support,
            incumbent_gate_disposition="permit",
            incumbent_gate_evidence=ref("gate-evidence"),
        )

    def projection(self, request, slot_id, predecessors):
        # Explicit scoped content resolution, addressed only by the supplied projection.
        reference = ControlArtifactReferenceModel.model_validate(ref("projection-" + slot_id, "projection"))
        reference = reference.model_copy(
            update={"digest": canonical_json_digest([item.model_dump(mode="json") for item in predecessors])}
        )
        self.projections[reference] = (request, tuple(predecessors))
        return reference

    def validation_context(self, evaluation):
        return ParticipantControlValidationContextV2(
            admitted_request=self.request,
            admitted_crossing=self.request.context.crossing,
            installed_bindings={item.instance_id: item for item in self.selection.bindings},
            resolved_coverage={item.obligation_id: item for item in self.request.applicability.coverage},
            resolved_results={item.slot_id: item for item in evaluation.results},
            resolved_support={(item.obligation_id, item.instance_id): item for item in self.support},
            authorized_effects={},
            safe_references=frozenset(control_references(evaluation))
            | _admitted_safe_references(self.request.context, self.records),
            support_resolver=lambda item: True,
            incumbent_gate_disposition="permit",
            crossing_records=self.records,
            crossing_subjects=_distinct(item.occurrence.subject for item in self.records),
            crossing_policies=_distinct(item.occurrence.policy for item in self.records),
            authorized_state_proposals={item.invocation_id: item for item in evaluation.state_proposals},
        )

    def effect_operation(self, request, context):
        return None


class Provider:
    def __init__(self, resolver, instance_id):
        self.resolver = resolver
        self.instance_id = instance_id
        self.failure = None
        self.hook = None
        self.results = []

    def resolve_stage(self, invocation):
        owner = self.resolver
        slot_id = invocation.requested_slot_ids[0]
        owner.calls.append(slot_id)
        if self.hook:
            self.hook(invocation)
        if self.failure == "exception":
            raise RuntimeError("private provider failure")
        if self.failure == "malformed":
            return ({"private": "provider value"},)
        if self.failure == "missing":
            return ()
        request, predecessors = owner.projections[invocation.projection]
        if slot_id == "fact":
            payload = deepcopy(owner.live["results"][0]["payload"])
            if owner.fact_tokens is not None:
                payload["tokens"] = owner.fact_tokens
        elif slot_id == "assessment":
            if predecessors:
                assert predecessors[0].payload.kind == "ifc-fact"
            payload = deepcopy(next(item["payload"] for item in owner.live["results"] if item["slot_id"] == "advice"))
            if owner.content_decision and predecessors:
                payload["assessment"] = "negative" if predecessors[0].payload.tokens else "positive"
                payload["score"] = 1.0 if predecessors[0].payload.tokens else 0.0
        else:
            assert predecessors[0].payload.kind == "advisory"
            disposition = owner.decision
            if owner.content_decision:
                disposition = "deny" if predecessors[0].payload.assessment == "negative" else "permit"
            payload = dict(kind="decision", disposition=disposition, rule=ref("decision-rule", "rule"))
        result = ControlMechanismResultV2Model.model_validate(
            dict(
                result_id="result-" + slot_id,
                slot_id=slot_id,
                instance_id=self.instance_id,
                binding_digest=invocation.binding_digest,
                context_digest=invocation.context_digest,
                invocation_digest=control_digest(invocation),
                status="resolved",
                payload=payload,
                evidence=[ref("result-evidence")],
                next_provider_state=owner.next_states.get(slot_id, ref("next-" + slot_id, "provider-state"))
                if slot_id in owner.writes
                else None,
            )
        )
        if self.failure == "stale":
            result = result.model_copy(update={"invocation_digest": "sha256:" + "0" * 64})
        self.results.append(result)
        return (result,)


def binding(resolver=None, *, serial=False):
    from raes_runtime.participant_control_binding import ParticipantControlStageBinding
    from raes_schemas import schema_bundle

    owner = resolver or Resolver()
    stages = {
        item.slot_id: ParticipantControlStageBinding(
            unavailable_projection=ControlArtifactReferenceModel.model_validate(
                ref("unavailable-" + item.slot_id, "projection")
            ),
            commit_on="evaluation" if item.slot_id in owner.writes else None,
            state_predecessor_slot_id="fact" if serial and item.slot_id == "rule" else None,
        )
        for item in owner.selection.slots
    }
    pins = {
        key: canonical_json_digest(schema_bundle()[key])
        for key in ("participant-control-selection-v2", "participant-control-evaluation-v2")
    }
    return ParticipantControlRuntimeBinding(
        selection=owner.selection, providers=owner.providers, resolver=owner, stages=stages, contract_digests=pins
    )


def optional_advice():
    owner = Resolver()
    data = owner.selection.model_dump(mode="json")
    data["slots"] = data["slots"][:2]
    data["obligations"][0]["required_kind"] = "ifc-fact"
    owner.selection = ParticipantControlSelectionV2Model.model_validate(data)
    owner.optional = True
    return owner
