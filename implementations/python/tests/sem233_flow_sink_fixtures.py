"""Live-bound SEM-233 final-sink fixtures for issue #1003 runtime enforcement.

The published ``validate_participant_flow_control_resolved_context`` validator is
strict, so this module reuses the exact validated builder machinery from
``test_sem_233_flow_control_contracts`` and rebinds only the values that must
match the live prepared crossing: the participant address, the API-423 decision
identity, the RUN-319 history-head state cut, the audience scope, and the sink
kind. Every value is safe synthetic test data.

Live runtime crossing subjects are digest-only, so the SEM-233 crossing carrier
binding cannot mirror a live decided occurrence directly. The guard never
compares the relation's crossing records against the live crossing; it binds the
*sink decision* to the live cut. The relation therefore keeps the template's
revision-bearing synthetic crossing records (with the decision identity rebound
to the live ``decision_id``) and rebinds the sink decision to the live
participant, episode, audience, and history heads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import test_sem_233_flow_control_contracts as template
from participant_crossing_fixtures import AUDIENCE, PARTICIPANT, StaticCrossingResolver
from raes_contracts.contracts import (
    ParticipantControlDeclarationModel,
    ParticipantControlOccurrenceModel,
    ParticipantFlowActionAdmissionResolution,
    ParticipantFlowCapabilityResolution,
    ParticipantFlowControlRelationModel,
    ParticipantFlowControlValidationContext,
    ParticipantFlowFinalDisposition,
    ParticipantFlowHistoryHeadResolution,
    ParticipantFlowReleaseAuthorityCoordinate,
    ParticipantFlowSinkCoordinate,
    ParticipantFlowSinkKind,
    RuntimeFactBindingPlaneModel,
)
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingSubjectReferenceModel,
)
from raes_contracts.participant_action_arguments import ParticipantValidatedActionSelection
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_operations.deterministic_participant_fixtures import (
    build_implementation_manifest,
    build_implementation_selection,
)
from raes_runtime.participant_flow_sink import ParticipantFlowSinkResolution

_TEMPLATE_PARTICIPANT = "participants.red.operator"
_TEMPLATE_AUDIENCE = "audience:red-operator"
_TEMPLATE_DECISION = "crossing-decision.1"
_ACTION_CONTRACT = "participant.action-contract.contain-host"
_OBSERVATION = "participant.observation-boundary.red-view"

_NON_PERMIT_ORDER = (
    ParticipantFlowFinalDisposition.DENY,
    ParticipantFlowFinalDisposition.UNSUPPORTED,
    ParticipantFlowFinalDisposition.STALE,
    ParticipantFlowFinalDisposition.UNRESOLVED,
)


def sem233_plane(resolver, **options):
    """Build a plane that explicitly selects the legacy SEM-233 final-sink path.

    RUN-320 removed method-presence discovery (PC-15), so a SEM-233 fixture
    states that selection instead of relying on the resolver exposing a hook.
    """

    from participant_crossing_fixtures import action_plane

    return action_plane(resolver, enforce_final_sink_flow_control=True, **options)


@dataclass(frozen=True)
class FlowSinkToggles:
    """Deterministic toggles that force one non-permit final-sink outcome."""

    capability_disposition: ParticipantFlowFinalDisposition = ParticipantFlowFinalDisposition.PERMIT
    history_disposition: ParticipantFlowFinalDisposition = ParticipantFlowFinalDisposition.PERMIT
    relation_head_refs: tuple[str, ...] | None = None
    relation_audience: str | None = None
    relation_sink_kind: ParticipantFlowSinkKind | None = None
    api_423_ref: str | None = None
    raise_exception: bool = False
    return_non_resolution: bool = False


def _combined_disposition(
    capability: ParticipantFlowFinalDisposition,
    history: ParticipantFlowFinalDisposition,
) -> ParticipantFlowFinalDisposition:
    values = {capability, history}
    for disposition in _NON_PERMIT_ORDER:
        if disposition in values:
            return disposition
    return ParticipantFlowFinalDisposition.PERMIT


def _substitute(payload: object, *, participant: str, audience: str, decision_id: str) -> object:
    encoded = json.dumps(payload)
    encoded = encoded.replace(_TEMPLATE_PARTICIPANT, participant)
    encoded = encoded.replace(_TEMPLATE_AUDIENCE, audience)
    encoded = encoded.replace(_TEMPLATE_DECISION, decision_id)
    return json.loads(encoded)


def _sink_coordinate(relation: ParticipantFlowControlRelationModel) -> ParticipantFlowSinkCoordinate:
    sink = relation.sink_decisions[0].sink
    return ParticipantFlowSinkCoordinate(
        sink_kind=sink.sink_kind,
        sink_ref=sink.sink_ref,
        destination_ref=sink.destination_ref,
        audience_scope_ref=sink.audience_scope_ref,
    )


def _live_admission(participant: str) -> tuple[ParticipantValidatedActionSelection, ParticipantActionAdmissionRequest]:
    selection = ParticipantValidatedActionSelection(
        action_contract_address=_ACTION_CONTRACT,
        argument_shape_ref="shape:contain-host",
        proposal_ref="proposal.1",
        normalized_arguments=(("target", "host:synthetic"),),
    )
    admission = ParticipantActionAdmissionRequest(
        participant_address=participant,
        action_contract_address=selection.action_contract_address,
        observation_boundary_address=_OBSERVATION,
        action_instance_id="action-1",
        implementation_manifest=build_implementation_manifest(),
        implementation_selection=build_implementation_selection(participant),
        evidence_refs=("evidence:action",),
        observation_boundary_evidence_refs=("evidence:action",),
        validated_selection=selection,
    )
    return selection, admission


def _live_control(participant: str) -> tuple[ParticipantControlOccurrenceModel, ParticipantControlDeclarationModel]:
    path = (
        template.REPO_ROOT
        / "contracts/fixtures/participant-runtime/participant-control-occurrence-v1/valid/proposal.json"
    )
    raw = json.loads(
        json.dumps(json.loads(path.read_text(encoding="utf-8"))).replace(_TEMPLATE_PARTICIPANT, participant)
    )
    record = ParticipantControlOccurrenceModel.model_validate(raw)
    occurrence = record.occurrence
    declaration = ParticipantControlDeclarationModel.model_validate(
        {
            "declaration_ref": occurrence.declaration_ref,
            "kind": occurrence.kind,
            "participant_address": record.participant_address,
            "episode_id": record.episode_id,
            "controller_ref": occurrence.controller_ref,
            "controller_state_ref": occurrence.controller_state_ref,
            "authority_basis_refs": occurrence.authority_basis_refs,
            "controlled_scope_refs": occurrence.controlled_scope_refs,
            "behavior_specification_ref": occurrence.behavior_specification_ref,
            "mixed_control_policy_ref": occurrence.mixed_control_policy_ref,
            "policy_revision": occurrence.policy_revision,
            "expected_state_revision": occurrence.expected_state_revision,
            "effective_order": occurrence.effective_order,
            "valid_from_order": occurrence.valid_from_order,
            "valid_until_order": occurrence.valid_until_order,
        }
    )
    return record, declaration


def _live_crossing_context(participant: str, decision_id: str):
    records, subject, policy = template._crossing_records()
    rebound = [
        item.__class__.model_validate(
            _substitute(
                item.model_dump(mode="json", exclude_none=True),
                participant=participant,
                audience=AUDIENCE,
                decision_id=decision_id,
            )
        )
        for item in records
    ]
    rebound_subject = ParticipantCrossingSubjectReferenceModel.model_validate(
        _substitute(
            subject.model_dump(mode="json", exclude_none=True),
            participant=participant,
            audience=AUDIENCE,
            decision_id=decision_id,
        )
    )
    return rebound, rebound_subject, policy


def _live_runtime_fact_plane(participant: str) -> RuntimeFactBindingPlaneModel:
    return RuntimeFactBindingPlaneModel.model_validate(
        _substitute(
            template._runtime_fact_plane().model_dump(mode="json", exclude_none=True),
            participant=participant,
            audience=AUDIENCE,
            decision_id=_TEMPLATE_DECISION,
        )
    )


def build_flow_sink_resolution(
    *,
    participant: str,
    episode: str,
    audience: str,
    decision_id: str,
    head_refs: tuple[str, ...],
    sink_kind: ParticipantFlowSinkKind,
    toggles: FlowSinkToggles | None = None,
) -> ParticipantFlowSinkResolution:
    """Return a live-bound ``ParticipantFlowSinkResolution`` for one crossing."""

    toggles = toggles or FlowSinkToggles()
    relation_audience = toggles.relation_audience or audience
    relation_decision = toggles.api_423_ref or decision_id
    relation_head_refs = tuple(toggles.relation_head_refs) if toggles.relation_head_refs is not None else head_refs
    final = _combined_disposition(toggles.capability_disposition, toggles.history_disposition)
    reason_code = (
        "all-conjuncts-satisfied"
        if final is ParticipantFlowFinalDisposition.PERMIT
        else f"participant-flow-sink-{final.value}"
    )

    payload = _substitute(
        template._context_relation_payload(),
        participant=participant,
        audience=relation_audience,
        decision_id=relation_decision,
    )
    sink_decision = payload["sink_decisions"][0]
    sink_decision["expected_history_head_refs"] = list(relation_head_refs)
    # A resolver that returns a validator-valid permit for a *different* sink kind
    # than the caller is invoking must still be rejected by the runtime guard.
    sink_decision["sink"]["sink_kind"] = (toggles.relation_sink_kind or sink_kind).value
    sink_decision["final_disposition"] = final.value
    sink_decision["reason_code"] = reason_code
    relation = ParticipantFlowControlRelationModel.model_validate(payload)

    sink = _sink_coordinate(relation)
    selection, admission = _live_admission(participant)
    control_record, declaration = _live_control(participant)
    crossing_records, crossing_subject, crossing_policy = _live_crossing_context(participant, relation_decision)
    profile = template.load_participant_boundary_flow_policy_profile(template.PROFILE_ID)

    context = ParticipantFlowControlValidationContext(
        profiles={(profile.profile_id, profile.profile_revision): profile},
        source_labels={label.label_id: label for label in relation.labels[:2]},
        policy_cuts={relation.labels[0].policy.decision_cut_ref: relation.labels[0].policy},
        release_authorities=frozenset(
            ParticipantFlowReleaseAuthorityCoordinate(
                kind=release.kind,
                authority_basis_ref=release.authority_basis_ref,
                authority_revision=release.authority_revision,
                sink_ref=release.sink_ref,
                destination_ref=release.destination_ref,
                audience_scope_ref=release.audience_scope_ref,
            )
            for release in relation.releases
        ),
        known_sinks=frozenset({sink}),
        runtime_fact_planes={"runtime-fact-plane.1": _live_runtime_fact_plane(participant)},
        action_selections={(selection.action_contract_address, selection.proposal_ref): selection},
        action_admissions={"action-admission.1": admission},
        action_admission_resolutions={
            "action-admission.1": ParticipantFlowActionAdmissionResolution(
                action_admission_ref="action-admission.1",
                participant_address=participant,
                episode_id=episode,
                action_contract_address=admission.action_contract_address,
                action_instance_id=admission.action_instance_id,
                sink=sink,
                disposition=ParticipantFlowFinalDisposition.PERMIT,
            )
        },
        capability_resolutions={
            "capability-resolution.1": ParticipantFlowCapabilityResolution(
                capability_resolution_ref="capability-resolution.1",
                participant_address=participant,
                episode_id=episode,
                sink=sink,
                disposition=toggles.capability_disposition,
            )
        },
        history_head_resolutions=frozenset(
            {
                ParticipantFlowHistoryHeadResolution(
                    participant_address=participant,
                    episode_id=episode,
                    sink=sink,
                    history_head_refs=tuple(relation_head_refs),
                    disposition=toggles.history_disposition,
                )
            }
        ),
        control_records=(control_record,),
        control_declarations=(declaration,),
        control_known_targets=(),
        crossing_records=tuple(crossing_records),
        crossing_subjects=(crossing_subject,),
        crossing_policies=(crossing_policy,),
        known_evidence_refs=frozenset(
            {
                "evidence:crossing-1",
                "evidence-requirement:crossing-decision",
                *(f"evidence:{item['label_id']}" for item in payload["labels"]),
                "evidence:derivation.1",
                "evidence:declassification.1",
                "evidence:endorsement.1",
                "evidence:sink-decision.1",
            }
        ),
        known_authority_refs=frozenset(
            {"authority:red-team", "authority:declassification.1", "authority:endorsement.1"}
        ),
    )
    return ParticipantFlowSinkResolution(relation=relation, context=context)


class Sem233FlowSinkResolver(StaticCrossingResolver):
    """A crossing resolver that also serves the SEM-233 final-sink permit."""

    def __init__(self, *, toggles: FlowSinkToggles | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.toggles = toggles or FlowSinkToggles()
        self.flow_sink_calls: list[ParticipantFlowSinkKind] = []

    def resolve_flow_sink_decision(
        self,
        *,
        snapshot: object,
        intent: object,
        crossing: object,
        sink_kind: ParticipantFlowSinkKind,
        expected_history_head_refs: tuple[str, ...],
    ) -> ParticipantFlowSinkResolution | None:
        del snapshot
        self.flow_sink_calls.append(sink_kind)
        if self.toggles.raise_exception:
            raise PermissionError("secret flow-sink policy detail must not leak")
        if self.toggles.return_non_resolution:
            return None
        return build_flow_sink_resolution(
            participant=intent.participant_address,
            episode=intent.episode_id,
            audience=intent.audience_scope_ref,
            decision_id=crossing.decision.occurrence.decision_id,
            head_refs=tuple(expected_history_head_refs),
            sink_kind=sink_kind,
            toggles=self.toggles,
        )


def permit_resolver() -> Sem233FlowSinkResolver:
    return Sem233FlowSinkResolver()


def deny_resolver(toggles: FlowSinkToggles) -> Sem233FlowSinkResolver:
    return Sem233FlowSinkResolver(toggles=toggles)


__all__ = (
    "AUDIENCE",
    "PARTICIPANT",
    "FlowSinkToggles",
    "Sem233FlowSinkResolver",
    "build_flow_sink_resolution",
    "deny_resolver",
    "permit_resolver",
)
