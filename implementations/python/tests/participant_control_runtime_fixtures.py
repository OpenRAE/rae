"""Synthetic RUN-320 providers and trusted resolvers bound to a live cut.

Every value is safe synthetic test data. A provider here is an operator-created
pure resolver: it establishes no installation, capability, authority or
realization, exactly as ``ParticipantControlProvider`` documents.

The published API-424 template in ``participant_control_contract_fixtures`` uses
its own illustrative participant, audience and crossing identities, so — like
``sem233_flow_sink_fixtures`` — this module rebinds those coordinates onto the
live prepared crossing before a provider ever sees them. The trusted context
then carries the *actual* prepared crossing occurrence, so a resolver that
cannot name the live record cannot pass validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from participant_control_contract_fixtures import (
    delivery_payload,
    evaluation_payload,
    ref,
)
from participant_crossing_fixtures import AUDIENCE as LIVE_AUDIENCE
from participant_crossing_fixtures import PARTICIPANT as LIVE_PARTICIPANT
from raes.participant_inject_delivery import ParticipantInjectDelivery
from raes_contracts._canonical import canonical_json_digest
from raes_contracts.contracts.participant_control_composition import (
    ParticipantControlRequestModel,
    control_digest,
)
from raes_contracts.contracts.participant_control_coordinates import ControlArtifactReferenceModel
from raes_contracts.contracts.participant_control_resolution import (
    ParticipantControlValidationContext,
    control_references,
)
from raes_contracts.contracts.participant_control_results import (
    ControlEffectiveSupportModel,
    ControlMechanismResultModel,
)
from raes_contracts.contracts.participant_control_selection import ParticipantControlSelectionModel
from raes_contracts.contracts.participant_crossing import ParticipantCrossingOccurrenceModel
from raes_runtime.participant_control_binding import (
    ParticipantControlResolution,
    ParticipantControlRuntimeBinding,
)
from raes_runtime.participant_control_effects import ParticipantControlEffectOperation
from raes_runtime.participant_control_intents import ParticipantHandoffControlIntent

INSTANCE = "influence"
MONITOR = "monitor"
_TEMPLATE_PARTICIPANT = "participants.student"
_TEMPLATE_AUDIENCE = "student-audience"
_TEMPLATE_CROSSING = "crossing-1"


ADMITTED_APPLICABILITY = (
    ("ingress", "action-argument", "participant-action-admission"),
    ("ingress", "participant-crossing", "participant-control-occurrence"),
    ("egress", "participant-output", "participant-status-view"),
    ("ingress", "teaching-observation", "participant-observation"),
)


def admitted_payload(payload: dict | None = None, *, participant: str, audience: str) -> dict:
    """Bind one template to the participant and sinks this apparatus admits.

    PC-01 keeps the selection fixed for the admitted binding: applicability is
    declared here, once, for every crossing coordinate the run may reach. Only
    the exact context changes per cut.
    """

    admitted = _substituted(
        payload or evaluation_payload(),
        participant=participant,
        audience=audience,
        crossing_ref=_TEMPLATE_CROSSING,
    )
    for binding in admitted["request"]["selection"]["bindings"]:
        binding["applicability"] = [
            {
                "participant_address": participant,
                "episode_id": "episode-1",
                "direction": direction,
                "sink_ref": sink_ref,
                "phase_ref": "practice",
                "subject_kind": subject_kind,
            }
            for direction, sink_ref, subject_kind in ADMITTED_APPLICABILITY
        ]
    return admitted


def _substituted(payload: dict, *, participant: str, audience: str, crossing_ref: str) -> dict:
    encoded = json.dumps(payload)
    encoded = encoded.replace(_TEMPLATE_PARTICIPANT, participant)
    encoded = encoded.replace(_TEMPLATE_AUDIENCE, audience)
    encoded = encoded.replace(_TEMPLATE_CROSSING, crossing_ref)
    return json.loads(encoded)


def live_payload(payload: dict, *, crossing: object, sink_kind: object, head_refs: tuple[str, ...]) -> dict:
    """Rebind one portable template onto the live prepared crossing cut."""

    intent = crossing.intent
    decision = committed_crossing_record(crossing)
    rebound = _substituted(
        payload,
        participant=intent.participant_address,
        audience=intent.audience_scope_ref,
        crossing_ref=decision.event_id,
    )
    context = rebound["request"]["context"]
    context["episode_id"] = intent.episode_id
    context["direction"] = intent.direction.value
    context["controller_ref"] = intent.controller_ref
    context["sink_ref"] = sink_kind.value
    context["subject"] = decision.occurrence.subject.model_dump(mode="json")
    context["policy"] = {
        **context["policy"],
        **decision.occurrence.policy.model_dump(mode="json"),
    }
    context["state_cut"] = {**context["state_cut"], "cut_ref": context["policy"]["decision_cut_ref"]}
    context["order"] = context["policy"]["effective_order"]
    context["authority"] = {**context["authority"], "ref": decision.occurrence.authority_basis_refs[0]}
    context["expected_history_heads"] = [ref(item, "history") for item in head_refs]
    context["crossing"]["digest"] = live_crossing_digest(decision)
    _rebind_inject_delivery(rebound, context)
    return _rebound_context_digests(rebound)


def _declare_retained_consumption(payload: dict, snapshot: object) -> None:
    """Carry the consumption this causal root already committed into the cut.

    A trusted resolver derives the exact context from committed state, so the
    retained logical claims and firing epochs travel with it; declaring zero
    again would let one root re-spend an exhausted budget.
    """

    from raes_runtime.participant_control_causal_state import causal_state_from_history

    context = payload["request"]["context"]
    history = getattr(snapshot, "participant_control_evaluation_history", {}).get(context["participant_address"], ())
    state = causal_state_from_history(
        history,
        run_ref=context["run"]["ref"],
        trigger_root=context["trigger_root"],
    )
    if state.claims:
        context["prior_effect_claims"] = [claim.model_dump(mode="json") for claim in state.claims.values()]
        context["rule_firings"] = [
            {"rule_id": rule, "rule_revision": revision, "firing_epochs": sorted(epochs)}
            for (rule, revision), epochs in sorted(state.firings.items())
        ]
        context["effects_consumed"] = max(context["effects_consumed"], state.effects_consumed)
        context["depth"] = max(context["depth"], 1)
    # An attempt is spent by every committed evaluation under this root, so it
    # is declared even when the root has claimed no effect.
    context["attempt"] = max(context["attempt"], state.next_attempt)
    _rebound_context_digests(payload)


def _name_decision_identity(payload: dict, decision: ParticipantCrossingOccurrenceModel) -> None:
    """Name the decision's own identifier instead of the occurrence event.

    This is the shape a resolver produces when it reconstructs the occurrence
    instead of naming the committed record, and the runtime must refuse it.
    """

    context = payload["request"]["context"]
    reconstructed = decision.model_copy(update={"event_id": decision.occurrence.decision_id})
    context["crossing"] = {
        **context["crossing"],
        "ref": reconstructed.event_id,
        "digest": live_crossing_digest(reconstructed),
    }
    _rebound_context_digests(payload)


def _distinct(records: object) -> tuple:
    """Order-preserving de-duplication for unhashable contract models."""

    unique: list = []
    for record in records:
        if record not in unique:
            unique.append(record)
    return tuple(unique)


def committed_crossing_records(crossing: object) -> tuple[ParticipantCrossingOccurrenceModel, ...]:
    """This participant's crossing chain as the committed RUN-319 carrier holds it.

    A real resolver reads these records back out of committed state, so the
    trusted context is built from that projection rather than from the
    runtime's in-memory models. API-423 resolves a decided record against its
    own request predecessor, so the whole chain travels together.
    """

    history = crossing.next_snapshot.participant_crossing_history[crossing.decision.participant_address]
    return tuple(ParticipantCrossingOccurrenceModel.model_validate(item) for item in history)


def committed_crossing_record(crossing: object) -> ParticipantCrossingOccurrenceModel:
    """The decided occurrence this exact cut names, as committed state holds it."""

    event_id = crossing.decision.event_id
    return next(item for item in committed_crossing_records(crossing) if item.event_id == event_id)


def live_crossing_digest(decision: ParticipantCrossingOccurrenceModel) -> str:
    """Digest a crossing record exactly as API-424 resolves it.

    ``participant_control_resolution._validate_crossing`` digests the record's
    original wire projection, so unset incumbent optional fields stay absent.
    """

    return canonical_json_digest(decision.model_dump(mode="json", exclude_unset=True))


def _rebind_inject_delivery(payload: dict, context: dict) -> None:
    delivery = live_delivery(context)
    digest = canonical_json_digest(delivery.model_dump(mode="json"))
    for result in payload["results"]:
        target = (result.get("payload") or {}).get("target")
        if target is not None and target.get("kind") == "inject":
            target["participant_address"] = context["participant_address"]
            target["episode_id"] = context["episode_id"]
            target["delivery_ref"] = {**target["delivery_ref"], "digest": digest}


def live_delivery(context: dict) -> ParticipantInjectDelivery:
    """The admitted DSL-142 delivery this inject request names, at the live cut."""

    payload = delivery_payload()
    payload["participant_ref"] = context["participant_address"]
    payload["delivery_policy"] = {
        **payload["delivery_policy"],
        "audience_scope_ref": context["audience_ref"],
    }
    return ParticipantInjectDelivery.model_validate(payload)


def _rebound_context_digests(payload: dict) -> dict:
    """Rebind every result and support record to the edited exact context."""

    digest = canonical_json_digest(payload["request"]["context"])
    selection = ParticipantControlSelectionModel.model_validate(payload["request"]["selection"])
    bindings = {binding.instance_id: control_digest(binding) for binding in selection.bindings}
    payload["results"] = [
        {**result, "context_digest": digest, "binding_digest": bindings[result["instance_id"]]}
        for result in payload["results"]
    ]
    payload["support"] = [{**item, "context_digest": digest} for item in payload["support"]]
    return payload


def _admitted_safe_references(
    context: object,
    records: tuple[ParticipantCrossingOccurrenceModel, ...] = (),
) -> frozenset[ControlArtifactReferenceModel]:
    """The operator's own admitted evidence and authority refs for this cut.

    Safe references are admitted independently of what a *control* record
    happens to carry, so an unresolved contribution does not silently narrow
    the set the incumbent API-423 validators resolve against. The live crossing
    occurrence is a different matter: the incumbent owner already admitted its
    evidence and authority basis, and API-423 re-resolves them here, so the
    operator admits exactly what that record was decided against.
    """

    admitted = {
        ControlArtifactReferenceModel.model_validate(ref(item))
        for item in ("result-evidence", "binding-evidence", "effect-evidence", "gate-evidence")
    }
    admitted.add(ControlArtifactReferenceModel.model_validate(ref(context.authority.ref, "authority")))
    for record in records:
        occurrence = record.occurrence
        admitted.update(
            ControlArtifactReferenceModel.model_validate(ref(item))
            for item in (*record.evidence_refs, *record.provenance_refs, *occurrence.required_evidence_refs)
        )
        admitted.update(
            ControlArtifactReferenceModel.model_validate(ref(item, "authority"))
            for item in occurrence.authority_basis_refs
        )
    return frozenset(admitted)


@dataclass
class DuplicateSlotProvider:
    """Return two contributions for one slot, as a malformed provider would."""

    instance_id: str = INSTANCE
    _results: tuple[dict, ...] = ()

    def bind(self, payload: dict) -> DuplicateSlotProvider:
        self._results = tuple(item for item in payload["results"] if item["instance_id"] == self.instance_id)
        return self

    def resolve(self, request: ParticipantControlRequestModel) -> tuple[ControlMechanismResultModel, ...]:
        resolved = [ControlMechanismResultModel.model_validate(item) for item in self._results]
        first = resolved[0]
        return (first, first.model_copy(update={"result_id": first.result_id + ".rival"}), *resolved[1:])


@dataclass
class SyntheticControlProvider:
    """Return the template results this instance owns for the exact request."""

    instance_id: str = INSTANCE
    calls: list[ParticipantControlRequestModel] = field(default_factory=list)
    raises: bool = False
    returns_invalid: bool = False
    omits_slot: str | None = None
    reverse: bool = False
    _results: tuple[dict, ...] = ()

    def bind(self, payload: dict) -> SyntheticControlProvider:
        self._results = tuple(item for item in payload["results"] if item["instance_id"] == self.instance_id)
        return self

    def resolve(self, request: ParticipantControlRequestModel) -> tuple[ControlMechanismResultModel, ...]:
        self.calls.append(request)
        if self.raises:
            raise RuntimeError("provider failure detail must never reach a caller")
        if self.returns_invalid:
            return ("not-a-result",)  # type: ignore[return-value]
        selected = [item for item in self._results if item["slot_id"] != self.omits_slot]
        resolved = tuple(ControlMechanismResultModel.model_validate(item) for item in selected)
        return tuple(reversed(resolved)) if self.reverse else resolved


@dataclass
class SyntheticControlResolver:
    """Trusted owner-resolved request, support and incumbent gate for one cut."""

    payload: dict
    providers: tuple[SyntheticControlProvider, ...] = ()
    incumbent_gate_disposition: str = "permit"
    resolutions: int = 0
    returns_none: bool = False
    raises: bool = False
    stale_heads: bool = False
    effect_operations: bool = True
    effect_participant: str | None = None
    effect_state_revision: int | None = None
    effect_inject_lineage: str | None = None
    effect_declaration_ref: str | None = None
    effect_evidence: bool = True
    replacement_crossing: bool = False
    live: dict | None = None
    live_crossing: ParticipantCrossingOccurrenceModel | None = None
    live_crossing_chain: tuple[ParticipantCrossingOccurrenceModel, ...] = ()

    def resolve(
        self,
        *,
        snapshot: object,
        intent: object,
        crossing: object,
        sink_kind: object,
        expected_history_head_refs: tuple[str, ...],
    ) -> ParticipantControlResolution | None:
        del intent
        self.resolutions += 1
        if self.raises:
            raise RuntimeError("resolver failure detail must never reach a caller")
        if self.returns_none:
            return None
        head_refs = (
            ("participant_control_evaluation_history:stale",) if self.stale_heads else expected_history_head_refs
        )
        self.live_crossing = committed_crossing_record(crossing)
        self.live_crossing_chain = committed_crossing_records(crossing)
        self.live = live_payload(self.payload, crossing=crossing, sink_kind=sink_kind, head_refs=head_refs)
        if self.replacement_crossing:
            # Name the decision's own identifier rather than the occurrence
            # event the RUN-319 record is filed under, as a resolver working
            # from a reconstructed record would.
            _name_decision_identity(self.live, self.live_crossing)
        _declare_retained_consumption(self.live, snapshot)
        for provider in self.providers:
            provider.bind(self.live)
        return ParticipantControlResolution(
            request=ParticipantControlRequestModel.model_validate(self.live["request"]),
            support=tuple(ControlEffectiveSupportModel.model_validate(item) for item in self.live["support"]),
            incumbent_gate_disposition=self.incumbent_gate_disposition,
            incumbent_gate_evidence=ref("gate-evidence"),
        )

    def effect_operation(self, request: object, context: object) -> ParticipantControlEffectOperation | None:
        """Return the incumbent owner input this admitted effect names."""

        if not self.effect_operations:
            return None
        participant = self.effect_participant or request.target.participant_address
        owner_evidence = _effect_evidence(context) if self.effect_evidence else None
        if request.target.kind == "inject":
            return ParticipantControlEffectOperation(
                kind="inject",
                view=_inject_view(
                    participant,
                    context,
                    request.target,
                    result_item_ref=self.effect_inject_lineage,
                ),
                crossing_evidence=owner_evidence,
            )
        if request.target.kind == "handoff":
            return ParticipantControlEffectOperation(
                kind="handoff",
                intent=_handoff_intent(
                    context,
                    request.target,
                    expected_state_revision=self.effect_state_revision,
                    declaration_ref=self.effect_declaration_ref,
                ),
                crossing_evidence=owner_evidence,
            )
        return None

    def validation_context(self, evaluation: object) -> ParticipantControlValidationContext:  # noqa: D102
        context = evaluation.request.context
        crossing = self.live_crossing
        assert crossing is not None
        return ParticipantControlValidationContext(
            admitted_request=evaluation.request,
            safe_references=frozenset(control_references(evaluation))
            | _admitted_safe_references(context, self.live_crossing_chain),
            installed_bindings={binding.instance_id: binding for binding in evaluation.request.selection.bindings},
            effective_support={item.instance_id: item for item in evaluation.support},
            resolved_results={result.result_id: result for result in evaluation.results if result.status == "resolved"},
            authorized_effects={
                control_digest(result.payload): context
                for result in evaluation.results
                if result.payload is not None and result.payload.kind == "effect-request"
            },
            incumbent_gate_evidence=evaluation.composition.incumbent_gate_evidence,
            incumbent_gate_disposition=evaluation.composition.incumbent_gate_disposition,
            support_resolver=lambda _binding, support: support.declared_level,
            realization_receipts={item.receipt.ref: item for item in evaluation.realizations},
            crossing_records=self.live_crossing_chain,
            crossing_subjects=_distinct(item.occurrence.subject for item in self.live_crossing_chain),
            crossing_policies=_distinct(item.occurrence.policy for item in self.live_crossing_chain),
            inject_deliveries={"delivery-binding": live_delivery(context.model_dump(mode="json"))},
        )


@dataclass
class ForgetfulConsumptionResolver(SyntheticControlResolver):
    """Re-declare zero consumption for a root that already spent its budget."""

    def resolve(self, **coordinates: object) -> ParticipantControlResolution | None:
        resolution = super().resolve(**coordinates)
        if resolution is None:
            return None
        context = self.live["request"]["context"]
        context["prior_effect_claims"] = []
        context["rule_firings"] = []
        context["effects_consumed"] = 0
        context["attempt"] = 1
        _rebound_context_digests(self.live)
        for provider in self.providers:
            provider.bind(self.live)
        return ParticipantControlResolution(
            request=ParticipantControlRequestModel.model_validate(self.live["request"]),
            support=tuple(ControlEffectiveSupportModel.model_validate(item) for item in self.live["support"]),
            incumbent_gate_disposition=self.incumbent_gate_disposition,
            incumbent_gate_evidence=ref("gate-evidence"),
        )


def control_binding(
    payload: dict | None = None,
    *,
    providers: dict[str, SyntheticControlProvider] | None = None,
    resolver: SyntheticControlResolver | None = None,
    **resolver_options: object,
) -> ParticipantControlRuntimeBinding:
    """Bind one admitted selection to its synthetic providers and resolver."""

    template = admitted_payload(payload, participant=LIVE_PARTICIPANT, audience=LIVE_AUDIENCE)
    selection = ParticipantControlSelectionModel.model_validate(template["request"]["selection"])
    bound = providers or {
        binding.instance_id: SyntheticControlProvider(instance_id=binding.instance_id) for binding in selection.bindings
    }
    bound_resolver = resolver or SyntheticControlResolver(
        payload=template,
        providers=tuple(bound.values()),
        **resolver_options,
    )
    bound_resolver.providers = tuple(bound.values())
    return ParticipantControlRuntimeBinding(selection=selection, providers=bound, resolver=bound_resolver)


def fact_only_payload() -> dict:
    """An eligible composition that resolves no effect at all.

    An evaluation still spends an attempt on its causal root even when nothing
    is requested, which is what makes PC-12's attempt bound meaningful.
    """

    payload = evaluation_payload()
    selection = payload["request"]["selection"]
    selection["slots"] = [slot for slot in selection["slots"] if slot["slot_id"] != "rule"]
    payload["results"] = [result for result in payload["results"] if result["slot_id"] != "rule"]
    return payload


def advisory_monitor_payload() -> dict:
    """Add a second mechanism and published profile with an advisory-only slot."""

    payload = evaluation_payload()
    selection = payload["request"]["selection"]
    monitor_binding = {
        **selection["bindings"][0],
        "instance_id": MONITOR,
        "profiles": [{**ref("participant-boundary-flow-policy-v1", "profile"), "digest": _security_profile_digest()}],
        "mechanism": ref("monitor", "mechanism"),
    }
    selection["bindings"].append(monitor_binding)
    selection["slots"].append(
        {"slot_id": "advice", "instance_id": MONITOR, "kind": "advisory", "role": "advisory", "dependencies": []}
    )
    payload["results"].append(
        {
            "result_id": "result-advice",
            "slot_id": "advice",
            "instance_id": MONITOR,
            "binding_digest": payload["results"][0]["binding_digest"],
            "context_digest": payload["results"][0]["context_digest"],
            "status": "resolved",
            "payload": {
                "kind": "advisory",
                "assessment": "negative",
                "score": 0.75,
                "sample": ref("monitor-sample"),
            },
            "evidence": [ref("result-evidence")],
            "next_provider_state": None,
        }
    )
    payload["support"].append({**payload["support"][0], "instance_id": MONITOR})
    payload["request"]["context"]["provider_states"].append(
        {"instance_id": MONITOR, "state": ref("monitor-state-1", "provider-state")}
    )
    return payload


def _effect_evidence(context: object):
    """The owner's crossing evidence, resolved for the admitted cut's audience."""

    from participant_crossing_fixtures import evidence

    return evidence().model_copy(update={"audience_scope_ref": context.audience_ref})


def _inject_view(participant: str, context: object, target: object, *, result_item_ref: str | None = None):
    """The already-projected carrier this admitted inject names.

    Its identity is the effect's fresh result item and its projection is the
    admitted disclosure, so the owner receipt records that exact inject.
    """

    from raes_contracts.contracts.participant_views import ParticipantStatusViewModel

    return ParticipantStatusViewModel.model_validate(
        {
            "view_id": result_item_ref or target.result_item_ref,
            "participant_address": participant,
            "episode_id": context.episode_id,
            "generated_at": "2026-09-20T00:00:00Z",
            "source_snapshot_ref": context.state_cut.cut_ref,
            "visibility_projection_ref": target.disclosure_ref.ref,
        }
    )


def _handoff_intent(
    context: object,
    target: object,
    *,
    expected_state_revision: int | None = None,
    declaration_ref: str | None = None,
) -> ParticipantHandoffControlIntent:
    """The incumbent RUN-310 controller transition this admitted rule requests."""

    return ParticipantHandoffControlIntent(
        declaration_ref=declaration_ref or target.transition.ref,
        episode_id=context.episode_id,
        client_correlation_id="control-effect-handoff",
        policy_revision="1.0.0",
        expected_state_revision=(
            target.expected_state_revision if expected_state_revision is None else expected_state_revision
        ),
        provenance_refs=["provenance:handoff"],
        evidence_refs=["evidence:handoff"],
        object_marking_refs=["marking:participant-control"],
        limitation_refs=["limitation:none"],
        completion_evidence_ref=target.completion_obligation.ref,
    )


def handoff_effect_payload(*, expected_state_revision: int = 0) -> dict:
    """Replace the teaching inject with a non-inject RUN-310 handoff effect."""

    payload = evaluation_payload()
    request = payload["results"][1]["payload"]
    # The target names the exact RUN-310 declaration and completion evidence the
    # owner will be asked to record, so the runtime can bind the owner input.
    request["target"] = {
        "kind": "handoff",
        "transition": ref(
            "participant.behavior-specification.controlled.control-transition.handoff",
            "control",
        ),
        "participant_address": _TEMPLATE_PARTICIPANT,
        "episode_id": "episode-1",
        "prior_controller_ref": "teacher",
        "resulting_controller_ref": "supervisor",
        "expected_state_revision": expected_state_revision,
        "completion_obligation": ref("evidence:handoff"),
    }
    return payload


def dependent_effects_payload(*, phase: str = "subsequent", reverse_records: bool = True) -> dict:
    """An ordered pair: the audit effect declares the inject as its predecessor."""

    payload = evaluation_payload()
    payload["request"]["selection"]["slots"].append(
        {
            "slot_id": "followup-audit",
            "instance_id": INSTANCE,
            "kind": "effect-request",
            "role": "mandatory",
            "dependencies": [],
        }
    )
    dependent = json.loads(json.dumps(payload["results"][1]))
    dependent["result_id"] = "result-followup-audit"
    dependent["slot_id"] = "followup-audit"
    dependent["payload"]["effect_id"] = "effect-2"
    dependent["payload"]["phase"] = phase
    dependent["payload"]["key"] = {**dependent["payload"]["key"], "slot": "followup-audit"}
    dependent["payload"]["predecessor_effect_ids"] = ["effect-1"]
    dependent["payload"]["target"] = {
        "kind": "audit",
        "subject": payload["request"]["context"]["subject"],
        "audit_record": ref("followup-audit", "audit"),
        "audience_ref": payload["request"]["context"]["audience_ref"],
        "retention_policy": ref("teaching-policy", "policy"),
    }
    # Serialization order deliberately contradicts the declared causal order.
    payload["results"] = (
        [payload["results"][0], dependent, payload["results"][1]]
        if reverse_records
        else [*payload["results"], dependent]
    )
    payload["request"]["selection"]["bounds"] = {
        **payload["request"]["selection"]["bounds"],
        "max_effects": 4,
        "max_fanout": 4,
        "max_firings_per_rule": 2,
    }
    return payload


def required_predecessor_payload() -> dict:
    """A required-predecessor effect: the composition withholds its parent."""

    payload = dependent_effects_payload(phase="required-predecessor", reverse_records=False)
    for result in payload["results"]:
        request = result.get("payload") or {}
        if request.get("effect_id") == "effect-2":
            # The review obligation precedes its parent, not the other way round.
            request["predecessor_effect_ids"] = []
        elif request.get("effect_id") == "effect-1":
            request["predecessor_effect_ids"] = ["effect-2"]
    payload["composition"] = {
        **payload["composition"],
        "disposition": "withhold",
        "blockers": ["predecessor:effect-2"],
        "contributing_result_ids": ["result-fact", "result-rule", "result-followup-audit"],
    }
    return payload


def conflicting_effect_payload() -> dict:
    """Two unordered mandatory effect requests for one parent; PC-07 conflict.

    Neither request declares the other as a predecessor, so their order is
    ambiguous and composition conflicts. No arrival order, rule identity, or
    canonical sort selects a winner.
    """

    payload = evaluation_payload()
    payload["request"]["selection"]["slots"].append(
        {"slot_id": "rival", "instance_id": INSTANCE, "kind": "effect-request", "role": "mandatory", "dependencies": []}
    )
    rival = json.loads(json.dumps(payload["results"][1]))
    rival["result_id"] = "result-rival"
    rival["slot_id"] = "rival"
    rival["payload"]["effect_id"] = "effect-2"
    rival["payload"]["key"] = {**rival["payload"]["key"], "slot": "rival"}
    payload["results"].append(rival)
    return payload


def _security_profile_digest() -> str:
    from raes_contracts.contracts.participant_flow_control import (
        PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST,
    )

    return PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_REV1_DIGEST


def with_status(payload: dict, slot_id: str, status: str) -> dict:
    """Return the payload with one slot's result recorded as unresolved."""

    results = []
    for result in payload["results"]:
        if result["slot_id"] == slot_id:
            results.append({**result, "status": status, "payload": None, "next_provider_state": None})
        else:
            results.append(result)
    return {**payload, "results": results}


@dataclass
class ReentrantValidationResolver(SyntheticControlResolver):
    """A trusted-context callback that tries to mutate the runtime re-entrantly."""

    plane: object | None = None
    reentry_errors: list = field(default_factory=list)

    def validation_context(self, evaluation: object) -> ParticipantControlValidationContext:  # noqa: D102
        try:
            self.plane.initialize_participant_episode("participants.reentrant", episode_id="episode-reentrant")
        except RuntimeError as error:
            self.reentry_errors.append(str(error))
            raise
        return super().validation_context(evaluation)
