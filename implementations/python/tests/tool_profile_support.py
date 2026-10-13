"""Shared harness for the participant tool-profile tests (issue #301, ACT-619).

It compiles SDL fixtures through the public pipeline and drives the real v2
projection, delivery, selection-binding and admission paths for one participant.
Every value is synthetic test data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from paths import REPO_ROOT
from raes import parse_sdl, parse_sdl_file
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts import (
    ParticipantActionResultModel,
    ParticipantDecisionSurfaceDeliveryV2Model,
    ParticipantDecisionSurfaceSelectionV2Model,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_binding_v2 import ParticipantDecisionSurfaceBindingResolversV2
from raes_contracts.participant_decision_surface_delivery import deliver_participant_decision_surface_v2
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import (
    ParticipantBehaviorHistoryEvent,
    ParticipantBehaviorProjectionAnchorRequestV2,
    ParticipantDecisionSurfaceActionAssessment,
    ParticipantDecisionSurfaceProjectionInputV2,
    ParticipantExposureAssessment,
    ParticipantExposureAuthorizationRecordV2,
    ParticipantExposurePolicyDecisionV2,
    ParticipantExposureResolversV2,
    RuntimeModel,
    project_participant_decision_surface_v2,
    resolve_participant_action_arguments,
    resolve_participant_behavior_projection_anchor_v2,
    resolve_participant_episode_readiness_anchor_v2,
)
from raes_runtime.control_plane import RuntimeControlPlane

FIXTURES = Path(__file__).parent / "fixtures" / "tool-profiles"
TOOLKIT = FIXTURES / "two-role-toolkit.sdl.yaml"
SPEC = "participant.behavior-specification.toolkit"
BLUE = "participant.behavior.analyst"
WHITE = "participant.behavior.observer"
BLUE_VIEW = "participant.observation-boundary.blue-view"
WHITE_VIEW = "participant.observation-boundary.white-view"
ACTIVE = "participant.action-contract.scan-active"
PASSIVE = "participant.action-contract.scan-passive"
SCANNER_BLUE = f"{SPEC}.tool-affordance.scanner-blue"
SCANNER_WHITE = f"{SPEC}.tool-affordance.scanner-white"
EPISODE = "episode-1"
REVEAL = "reveal-1"
CONTEXT = "context.public"
_MANIFEST = (
    REPO_ROOT
    / "contracts"
    / "fixtures"
    / "participant-implementation-manifest"
    / "participant-implementation-manifest-v1"
    / "valid"
    / "reference.json"
)


def toolkit_text() -> str:
    return TOOLKIT.read_text(encoding="utf-8")


def edited(text: str, *edits: tuple[str, str]) -> str:
    for authored, replacement in edits:
        assert text.count(authored) == 1, authored
        text = text.replace(authored, replacement)
    return text


def compiled(text: str | None = None) -> RuntimeModel:
    scenario = parse_sdl_file(TOOLKIT) if text is None else parse_sdl(text)
    return compile_runtime_model(scenario)


def _name(address: str) -> str:
    return address.rsplit(".", 1)[-1]


def implementation_selection(
    participant: str, *, permitted_refs: tuple[str, ...] = (CONTEXT,), tool_affordance_refs: tuple[str, ...] = ()
):
    return ParticipantImplementationSelectionModel.model_validate(
        {
            "participant_address": participant,
            "implementation_identity": {"name": "reference-red-agent", "version": "1.0.0"},
            "manifest_ref": "participant-implementation-manifests.reference.v1",
            "manifest_digest": "sha256:" + "1" * 64,
            "selected_decision_surface_mode": "autonomous",
            "participant_contract_versions": [
                "participant-behavior-history-event-stream-v1",
                "participant-decision-surface-v2",
            ],
            "exposure_policy": {
                "policy_id": f"exposure-policy.{_name(participant)}.v2",
                "policy_version": "2",
                "policy_digest": "sha256:" + "4" * 64,
                "exposure_policy_kinds": ["task-statement"],
                "disclosed_refs": list(permitted_refs),
                "withheld_refs": [],
                "tool_affordance_refs": list(tool_affordance_refs),
                "visibility_scope_refs": [],
                "constraints": {},
            },
        }
    )


def admission_request(
    participant: str,
    action: str,
    boundary: str,
    *,
    action_instance_id: str = "scan-1",
    selection: ParticipantImplementationSelectionModel | None = None,
    tool_expectations: tuple[str, ...] | None = None,
) -> ParticipantActionAdmissionRequest:
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    if tool_expectations is not None:
        payload["capabilities"]["tool_affordance_expectations"] = list(tool_expectations)
    manifest = ParticipantImplementationManifestModel.model_validate(payload)
    return ParticipantActionAdmissionRequest(
        participant_address=participant,
        action_contract_address=action,
        observation_boundary_address=boundary,
        action_instance_id=action_instance_id,
        implementation_manifest=manifest,
        implementation_selection=selection or implementation_selection(participant),
    )


def _assessment(model: RuntimeModel, action: str) -> ParticipantDecisionSurfaceActionAssessment:
    return ParticipantDecisionSurfaceActionAssessment(
        entry_id=f"decision-surface-entries.{_name(action)}",
        action_contract_address=action,
        presentation_basis_ref="projection-policy.toolkit.v2",
        eligibility="eligible",
        eligibility_reason_refs=(),
        constraint_refs=(f"{action}.preconditions",),
        selection_shape_ref=model.action_contracts[action].argument_shape_ref,
        support="supported",
        support_refs=("participant-implementation.reference",),
        realization_refs=("realization.reference",),
    )


def _authorization(item_ref: str, projection: ParticipantDecisionSurfaceProjectionInputV2):
    who = _name(projection.participant_address)
    return ParticipantExposureAuthorizationRecordV2(
        authorization_record_ref=f"exposure-authorizations.{who}.{item_ref}",
        item_ref=item_ref,
        source_ref=item_ref,
        source_layer_ref=f"source-layers.{item_ref}",
        participant_address=projection.participant_address,
        episode_id=projection.episode_id,
        audience_scope_ref=projection.audience_scope_ref,
        decision_epoch=projection.decision_epoch,
        decision_cut_ref=projection.decision_cut_ref,
        implementation_selection_ref=projection.implementation_selection_ref,
        projection_policy_ref=projection.projection_policy_ref,
        projection_policy_revision=projection.projection_policy_revision,
        projection_policy_decision_ref=projection.projection_policy_decision_ref,
        exposure_policy_ref=projection.exposure_policy_ref,
        exposure_policy_version="2",
        exposure_policy_digest="sha256:" + "4" * 64,
        visibility_basis_ref=f"visibility-bases.{item_ref}",
        operation="disclosure",
        operation_basis_ref=f"disclosures.{item_ref}",
        actor_ref="actors.runtime-projector",
        controller_ref=f"controllers.{who}",
        authority_basis_ref=f"authorities.{who}",
        backend_support_ref="backend-support.reference.v2",
        source_marking_definition_refs=("markings.participant-visible.v2",),
        result_marking_definition_refs=("markings.participant-visible.v2",),
        source_provenance_refs=("provenance.surface.v2",),
        result_provenance_refs=("provenance.surface.v2",),
        evidence_refs=("evidence.surface.v2",),
        provenance_refs=("provenance.surface.v2",),
        loss_and_limitations=("No known projection loss",),
    )


def _exposure_resolvers(
    projection: ParticipantDecisionSurfaceProjectionInputV2,
    selection: ParticipantImplementationSelectionModel,
) -> ParticipantExposureResolversV2:
    authorizations = {ref: _authorization(ref, projection) for ref in projection.exposure_assessments}
    decision = ParticipantExposurePolicyDecisionV2(
        policy_ref=projection.projection_policy_ref,
        revision=projection.projection_policy_revision,
        decision_ref=projection.projection_policy_decision_ref,
        decision_cut_ref=projection.decision_cut_ref,
        evidence_refs=("evidence.policy.v2",),
        provenance_refs=("provenance.policy.v2",),
        limitations=("Policy decision is scoped to the identified state cut",),
    )
    return ParticipantExposureResolversV2(
        apparatus=lambda **_: selection,
        projection_policy=lambda **_: decision,
        authorization=lambda *, authorization_record_ref, item_ref, decision_cut_ref: (
            authorizations[item_ref]
            if item_ref in authorizations
            and decision_cut_ref == projection.decision_cut_ref
            and authorizations[item_ref].authorization_record_ref == authorization_record_ref
            else None
        ),
    )


@dataclass
class Episode:
    """One participant's running episode on the reference runtime control plane."""

    model: RuntimeModel
    participant: str
    boundary: str
    control: RuntimeControlPlane
    spec: str = SPEC

    @classmethod
    def start(cls, model: RuntimeModel, participant: str, boundary: str) -> Episode:
        control = RuntimeControlPlane(create_stub_target())
        control.initialize_participant_episode(participant, episode_id=EPISODE)
        return cls(model, participant, boundary, control)

    def admit(self, action: str, *, action_instance_id: str = "scan-1", action_result=None):
        request = admission_request(self.participant, action, self.boundary, action_instance_id=action_instance_id)
        if action_result is not None:
            request = replace(request, action_result=action_result)
        return self.control.admit_participant_action(self.model.participant_behaviors[self.participant], request)

    def reveal(self, action: str, *, action_instance_id: str = REVEAL) -> None:
        """Record one terminal observation at this boundary; ``reveal-1`` anchors the fixture's view transitions."""

        result = ParticipantActionResultModel.model_validate(
            {
                "status": "succeeded",
                "participant_address": self.participant,
                "episode_id": EPISODE,
                "action_instance_id": action_instance_id,
                "action_contract_address": action,
                "observation_point": f"episode-step:{action_instance_id}:terminal-observation",
                "preconditions": [
                    {
                        "precondition_id": "authority-in-scope",
                        "precondition_class": "authority",
                        "status": "satisfied",
                        "participant_address": self.participant,
                        "episode_id": EPISODE,
                        "action_contract_address": action,
                        "observation_point": f"episode-step:{action_instance_id}:attempt",
                    }
                ],
                "effects": [
                    {"effect_id": "no-effect", "effect_class": "no_effect", "description": "no environment effect"}
                ],
            }
        )
        assert self.admit(action, action_instance_id=action_instance_id, action_result=result).accepted is True

    def anchor(self):
        snapshot = self.control.get_snapshot().snapshot
        history = snapshot.participant_behavior_history.get(self.participant, [])
        if not history:
            anchor = resolve_participant_episode_readiness_anchor_v2(
                snapshot,
                participant_address=self.participant,
                decision_epoch=0,
                evidence_refs=("evidence.episode-running",),
                provenance_refs=("provenance.runtime-control-plane",),
            )
            return snapshot, (), anchor
        events = tuple(ParticipantBehaviorHistoryEvent.from_payload(payload) for payload in history)
        anchor = resolve_participant_behavior_projection_anchor_v2(
            snapshot,
            runtime_model=self.model,
            request=ParticipantBehaviorProjectionAnchorRequestV2(
                participant_address=self.participant,
                episode_id=EPISODE,
                decision_epoch=1,
                behavior_history_order=len(events) - 1,
                evidence_refs=("evidence.scan-output",),
                provenance_refs=("provenance.runtime-control-plane",),
            ),
        )
        return snapshot, events, anchor

    def project(
        self,
        actions: tuple[str, ...],
        affordances: tuple[str, ...],
        *,
        exposure_refs: tuple[str, ...] | None = None,
        selection: ParticipantImplementationSelectionModel | None = None,
    ):
        """Project a v2 surface; ``affordances`` are the refs the exposure assessments must cover."""

        snapshot, events, anchor = self.anchor()
        who = _name(self.participant)
        emitted = exposure_refs if exposure_refs is not None else (CONTEXT, *actions, *affordances)
        projection = ParticipantDecisionSurfaceProjectionInputV2(
            surface_id=f"decision-surfaces.{who}.{EPISODE}.epoch-{anchor.decision_epoch}",
            participant_address=self.participant,
            episode_id=EPISODE,
            decision_epoch=anchor.decision_epoch,
            information_state_ref=f"information-states.{who}.epoch-{anchor.decision_epoch}",
            behavior_specification_address=self.spec,
            observation_boundary_address=self.boundary,
            context_view_ref=f"context-views.{who}.epoch-{anchor.decision_epoch}",
            implementation_selection_ref=f"participant-selections.{who}.v2",
            decision_control_mode="autonomous",
            audience_scope_ref=f"audience.participant.{who}",
            projection_policy_ref=f"projection-policy.{who}.v2",
            projection_policy_revision="2",
            projection_policy_decision_ref=f"projection-policy-decisions.{who}.epoch-{anchor.decision_epoch}",
            exposure_policy_ref=f"exposure-policy.{who}.v2",
            visibility_projection_ref=f"visibility-projection.{who}.epoch-{anchor.decision_epoch}",
            participant_memory_scope="persistent_across_episodes",
            memory_reset_authority_ref=None,
            visible_context_refs=(CONTEXT,),
            action_assessments={action: _assessment(self.model, action) for action in actions},
            exposure_assessments={
                ref: ParticipantExposureAssessment(
                    item_ref=ref, authorization_record_ref=f"exposure-authorizations.{who}.{ref}"
                )
                for ref in emitted
            },
            form={
                "surface_form": "candidate_action_set",
                "selection_meaning_ref": "selection-meaning.candidate.v2",
                "candidate_entry_ids": [f"decision-surface-entries.{_name(action)}" for action in actions],
            },
            evidence_refs=tuple(dict.fromkeys((*anchor.evidence_refs, "evidence.policy.v2", "evidence.surface.v2"))),
            provenance_refs=tuple(
                dict.fromkeys((*anchor.provenance_refs, "provenance.policy.v2", "provenance.surface.v2"))
            ),
            marking_definition_refs=("markings.participant-visible.v2",),
            redaction_policy_ref=f"redaction.{who}.v2",
            semantic_limitations=("Projection is not delivery, selection, admission, execution, or outcome",),
            derivation_anchor=anchor,
        )
        selection = selection or implementation_selection(self.participant, permitted_refs=emitted)
        return project_participant_decision_surface_v2(
            self.model,
            snapshot,
            history_events=events,
            projection=projection,
            exposure_resolvers=_exposure_resolvers(projection, selection),
        )


def delivery_for(surface) -> ParticipantDecisionSurfaceDeliveryV2Model:
    view = surface.participant_view
    return ParticipantDecisionSurfaceDeliveryV2Model(
        delivery_ref=f"decision-surface-deliveries.{view.surface_id}",
        surface_id=view.surface_id,
        participant_address=view.participant_address,
        episode_id=view.episode_id,
        decision_epoch=view.decision_epoch,
        participant_view_digest=surface.assurance.participant_view_digest,
        delivery_basis="emission_is_delivery",
        delivery_cut_ref=surface.assurance.derivation_anchor.state_cut.cut_ref,
        delivery_authorization_ref=f"delivery-authorizations.epoch-{view.decision_epoch}",
        delivery_policy_decision_ref=f"delivery-policy-decisions.epoch-{view.decision_epoch}",
        observation_ref=f"participant-view-observations.epoch-{view.decision_epoch}",
        evidence_refs=("evidence.surface-delivery.v2",),
        provenance_refs=("provenance.surface-delivery.v2",),
        limitations=("Synchronous reference-runtime delivery",),
    )


def deliver(surface):
    delivery = delivery_for(surface)
    return deliver_participant_decision_surface_v2(
        surface, delivery_ref=delivery.delivery_ref, resolver=lambda **_: delivery
    ), delivery


def selection_for(delivered, action: str, arguments: dict[str, object], *, digest: str | None = None):
    view = delivered.participant_view
    entry = next(entry for entry in view.action_entries if entry.action_contract_address == action)
    return ParticipantDecisionSurfaceSelectionV2Model(
        surface_id=view.surface_id,
        decision_epoch=view.decision_epoch,
        participant_view_digest=digest or delivered.assurance.participant_view_digest,
        delivery_ref=delivered.delivery.delivery_ref,
        action_contract_address=action,
        argument_shape_ref=entry.selection_shape_ref,
        proposal_ref=f"proposals.{_name(action)}.{_name(view.participant_address)}",
        arguments=arguments,
    )


def binding_resolvers(model: RuntimeModel, delivery, selection: ParticipantImplementationSelectionModel):
    """Resolve arguments through the compiled action contract, as the governed selection path does."""

    return ParticipantDecisionSurfaceBindingResolversV2(
        argument_shape=lambda **kwargs: resolve_participant_action_arguments(
            model.action_contracts[str(kwargs["action_contract_address"])], **kwargs
        ),
        apparatus=lambda **_: selection,
        delivery=lambda **_: delivery,
    )


def admit_selection(
    episode: Episode,
    surface,
    action: str,
    arguments: dict[str, object],
    *,
    tool_expectations: tuple[str, ...] | None = None,
):
    """Deliver ``surface`` and submit one selection through the v2 control-plane admission path."""

    delivered, delivery = deliver(surface)
    view_refs = tuple(
        dict.fromkeys(
            (
                *(entry.action_contract_address for entry in delivered.participant_view.action_entries),
                *delivered.participant_view.affordance_refs,
            )
        )
    )
    selection = implementation_selection(episode.participant, permitted_refs=view_refs)
    return episode.control.admit_participant_decision_surface_selection_v2(
        episode.model.participant_behaviors[episode.participant],
        surface=delivered,
        selection=selection_for(delivered, action, arguments),
        admission_request=admission_request(
            episode.participant, action, episode.boundary, selection=selection, tool_expectations=tool_expectations
        ),
        resolvers=binding_resolvers(episode.model, delivery, selection),
    )
