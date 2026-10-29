"""SEM-220 participant decision-surface contract and projection tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.contracts import (
    ParticipantContextViewModel,
    ParticipantDecisionSurfaceModel,
    ParticipantDecisionSurfaceSelectionModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    schema_bundle,
    validate_participant_decision_surface_context,
)
from raes_contracts.participant_binding import (
    ParticipantActionAdmissionRequest,
    ParticipantDecisionSurfaceBindingResolvers,
    ParticipantValidatedActionSelection,
    bind_participant_decision_surface_selection,
)
from raes_processor.models import (
    ParticipantActionContractRuntime,
    ParticipantBehaviorHistoryEvent,
    ParticipantBehaviorHistoryEventType,
    ParticipantBehaviorRuntime,
    ParticipantBehaviorSpecificationRuntime,
    ParticipantDecisionSurfaceActionAssessment,
    ParticipantDecisionSurfaceProjectionInput,
    ParticipantExposureAssessment,
    ParticipantExposureAuthorizationRecord,
    ParticipantExposurePolicyRevision,
    ParticipantExposureResolvers,
    ParticipantObservationBoundaryRuntime,
    ParticipantObservationStatus,
    ParticipantToolAffordanceRuntime,
    RuntimeModel,
    project_participant_decision_surface,
)
from raes_runtime.participant_control import ParticipantControlMixin

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "fixtures" / "control-plane" / "participant-decision-surface-v1"

PARTICIPANT = "participant.behavior.red-agent"
EPISODE = "episode-1"
BEHAVIOR = "participant.behavior-specification.red-surface"
BOUNDARY = "participant.observation-boundary.red-view"
SCAN = "participant.action-contract.scan"
EXFILTRATE = "participant.action-contract.exfiltrate"
SCAN_ENTRY = "decision-surface-entries.scan"
EXFILTRATE_ENTRY = "decision-surface-entries.exfiltrate"
SCAN_SHAPE = f"{SCAN}.argument-shape.sha256-" + "1" * 64
EXFILTRATE_SHAPE = f"{EXFILTRATE}.argument-shape.sha256-" + "2" * 64
SCAN_AFFORDANCE = f"{BEHAVIOR}.tool-affordance.scanner"
EXFILTRATE_AFFORDANCE = f"{BEHAVIOR}.tool-affordance.exfiltration"


def _surface_payload(*, surface_form: str = "candidate_action_set") -> dict[str, object]:
    entry = {
        "entry_id": SCAN,
        "action_contract_address": SCAN,
        "presentation_basis_ref": "projection-policy.red.v1",
        "visibility": "observable",
        "eligibility": "ineligible",
        "eligibility_reason_refs": ["sem211.precondition.authority.out-of-scope"],
        "constraint_refs": ["participant.action-contract.scan.preconditions"],
        "selection_shape_ref": "selection-shapes.scan.v1",
        "support": "supported",
        "support_refs": ["participant-implementation.reference.scan"],
        "affordance_refs": [SCAN_AFFORDANCE],
        "realization_refs": ["realizations.scan.reference.v1"],
    }
    forms: dict[str, dict[str, object]] = {
        "candidate_action_set": {
            "surface_form": "candidate_action_set",
            "selection_meaning_ref": "selection-meaning.candidate.v1",
            "candidate_entry_ids": [SCAN],
            "open_extension_binding_ref": None,
        },
        "open_ended_generation": {
            "surface_form": "open_ended_generation",
            "selection_meaning_ref": "selection-meaning.open.v1",
            "proposal_binding_ref": "proposal-bindings.governed-action.v1",
            "argument_shape_ref": "selection-shapes.scan.v1",
            "validation_policy_ref": "validation-policies.sem220.v1",
            "allowed_action_contract_addresses": [SCAN],
        },
        "constrained_form": {
            "surface_form": "constrained_form",
            "selection_meaning_ref": "selection-meaning.form.v1",
            "action_entry_id": SCAN,
            "argument_shape_ref": "selection-shapes.scan.v1",
            "validation_policy_ref": "validation-policies.sem220.v1",
            "constraint_refs": ["forms.scan.constraints.v1"],
            "default_disclosure_refs": ["forms.scan.defaults.v1"],
            "normalization_disclosure_refs": ["forms.scan.normalization.v1"],
            "omission_disclosure_refs": ["forms.scan.omission.v1"],
            "loss_disclosure_refs": ["forms.scan.loss.none.v1"],
        },
    }
    evidence_ref = "evidence.surface.red.order-0"
    provenance_ref = "provenance.surface.red.order-0"

    def exposure_binding(item_ref: str) -> dict[str, object]:
        return {
            "item_ref": item_ref,
            "authorization_record_ref": f"exposure-authorizations.{item_ref}.v1",
            "source_ref": item_ref,
            "source_layer_ref": f"source-layers.{item_ref}",
            "participant_address": PARTICIPANT,
            "episode_id": EPISODE,
            "audience_scope_ref": "audience.participant.red-agent",
            "observation_point": "behavior-history:0",
            "observation_order": 0,
            "visibility_basis_ref": f"visibility-bases.{item_ref}",
            "projection_policy_ref": "projection-policy.red.v1",
            "projection_policy_revision": "1",
            "exposure_policy_ref": "exposure-policy.red.v1",
            "exposure_policy_version": "1",
            "exposure_policy_digest": "sha256:" + "3" * 64,
            "operation": "disclosure",
            "operation_basis_ref": f"disclosures.{item_ref}.v1",
            "actor_ref": "actors.runtime-projector",
            "controller_ref": "controllers.red-agent",
            "authority_basis_ref": "authorities.red-agent.v1",
            "source_marking_definition_refs": ["markings.participant-visible.v1"],
            "result_marking_definition_refs": ["markings.participant-visible.v1"],
            "source_provenance_refs": [provenance_ref],
            "result_provenance_refs": [provenance_ref],
            "evidence_refs": [evidence_ref],
            "provenance_refs": [provenance_ref],
            "loss_and_limitations": ["No known projection loss"],
            "realization": None,
        }

    return {
        "surface_id": "decision-surfaces.red.episode-1.order-0",
        "participant_address": PARTICIPANT,
        "episode_id": EPISODE,
        "observation_point": "behavior-history:0",
        "observation_order": 0,
        "behavior_specification_address": BEHAVIOR,
        "observation_boundary_address": BOUNDARY,
        "context_view_ref": "context-views.red.episode-1.order-0",
        "implementation_selection_ref": "participant-selections.red.reference.v1",
        "decision_control_mode": "autonomous",
        "audience_scope_ref": "audience.participant.red-agent",
        "projection_policy_ref": "projection-policy.red.v1",
        "projection_policy_revision": "1",
        "exposure_policy_ref": "exposure-policy.red.v1",
        "visibility_projection_ref": "visibility-projection.red.order-0",
        "visible_context_refs": ["context.public"],
        "action_entries": [entry],
        "affordance_refs": [SCAN_AFFORDANCE],
        "exposure_bindings": [
            exposure_binding("context.public"),
            exposure_binding(SCAN),
            exposure_binding(SCAN_AFFORDANCE),
        ],
        "form": forms[surface_form],
        "evidence_refs": [evidence_ref],
        "provenance_refs": [provenance_ref],
        "marking_definition_refs": ["markings.participant-visible.v1"],
        "redaction_policy_ref": "redaction.red.v1",
        "semantic_limitations": ["Presentation does not imply selection, admission, execution, result, or outcome"],
    }


def _runtime_model(*, omitted_visibility_ref: str | None = None) -> RuntimeModel:
    initial_view_relation = {
        "context.public": "observable",
        SCAN: "observable",
        EXFILTRATE: "hidden",
        SCAN_AFFORDANCE: "observable",
        EXFILTRATE_AFFORDANCE: "hidden",
    }
    revealed_view_relation = {
        "context.public": "observable",
        SCAN: "observable",
        EXFILTRATE: "disclosed",
        SCAN_AFFORDANCE: "observable",
        EXFILTRATE_AFFORDANCE: "disclosed",
    }
    if omitted_visibility_ref is not None:
        initial_view_relation.pop(omitted_visibility_ref, None)
        revealed_view_relation.pop(omitted_visibility_ref, None)
    boundary = ParticipantObservationBoundaryRuntime(
        address=BOUNDARY,
        name="red-view",
        spec={},
        boundary_name="red-view",
        projection_basis="participant-local",
        view_transitions=(
            {
                "transition_id": "reveal-exfiltration",
                "history_event_type": "observation_emitted",
                "action_instance_id": "reveal-1",
                "information_ref": EXFILTRATE,
                "from_disposition": "hidden",
                "to_disposition": "disclosed",
                "effective_order": 1,
            },
            {
                "transition_id": "reveal-exfiltration-affordance",
                "history_event_type": "observation_emitted",
                "action_instance_id": "reveal-1",
                "information_ref": EXFILTRATE_AFFORDANCE,
                "from_disposition": "hidden",
                "to_disposition": "disclosed",
                "effective_order": 1,
            },
        ),
        view_relation_timeline=(
            {
                "transition_id": "initial",
                "effective_order": -1,
                "view_relation": initial_view_relation,
            },
            {
                "transition_id": "reveal-exfiltration",
                "effective_order": 1,
                "view_relation": revealed_view_relation,
            },
        ),
    )
    behavior = ParticipantBehaviorSpecificationRuntime(
        address=BEHAVIOR,
        name="red-surface",
        spec={},
        participant_addresses=(PARTICIPANT,),
        action_contract_addresses=(SCAN, EXFILTRATE),
        observation_boundary_addresses=(BOUNDARY,),
        tool_affordance_addresses=(SCAN_AFFORDANCE, EXFILTRATE_AFFORDANCE),
        behavior_mode="autonomous",
    )
    return RuntimeModel(
        scenario_name="sem-220",
        participant_behaviors={
            PARTICIPANT: ParticipantBehaviorRuntime(
                address=PARTICIPANT,
                name="red-agent",
                spec={},
                participant_name="red-agent",
                action_contract_addresses=(SCAN, EXFILTRATE),
                observation_boundary_addresses=(BOUNDARY,),
            )
        },
        action_contracts={
            SCAN: ParticipantActionContractRuntime(
                address=SCAN,
                name="scan",
                spec={},
                action_name="scan",
                argument_shape_ref=SCAN_SHAPE,
            ),
            EXFILTRATE: ParticipantActionContractRuntime(
                address=EXFILTRATE,
                name="exfiltrate",
                spec={},
                action_name="exfiltrate",
                argument_shape_ref=EXFILTRATE_SHAPE,
            ),
        },
        observation_boundaries={BOUNDARY: boundary},
        behavior_specifications={BEHAVIOR: behavior},
        tool_affordances={
            SCAN_AFFORDANCE: ParticipantToolAffordanceRuntime(
                address=SCAN_AFFORDANCE,
                name="scanner",
                spec={},
                affordance_id="scanner",
                behavior_specification_address=BEHAVIOR,
                action_contract_addresses=(SCAN,),
                observation_boundary_addresses=(BOUNDARY,),
            ),
            EXFILTRATE_AFFORDANCE: ParticipantToolAffordanceRuntime(
                address=EXFILTRATE_AFFORDANCE,
                name="exfiltration",
                spec={},
                affordance_id="exfiltration",
                behavior_specification_address=BEHAVIOR,
                action_contract_addresses=(EXFILTRATE,),
                observation_boundary_addresses=(BOUNDARY,),
            ),
        },
    )


def _history() -> tuple[ParticipantBehaviorHistoryEvent, ...]:
    return (
        ParticipantBehaviorHistoryEvent(
            event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
            timestamp="2026-07-20T08:00:00Z",
            participant_address=PARTICIPANT,
            episode_id=EPISODE,
            action_instance_id="setup-1",
            action_contract_address=SCAN,
            actor_provenance="participant:red-agent",
        ),
        ParticipantBehaviorHistoryEvent(
            event_type=ParticipantBehaviorHistoryEventType.OBSERVATION_EMITTED,
            timestamp="2026-07-20T08:00:01Z",
            participant_address=PARTICIPANT,
            episode_id=EPISODE,
            action_instance_id="reveal-1",
            action_contract_address=SCAN,
            observation_boundary_address=BOUNDARY,
            observation_status=ParticipantObservationStatus.TERMINAL,
            actor_provenance="participant:red-agent",
            post_state_digest="sha256:known-after-reveal",
            details={"evidence_refs": ["evidence.observation.reveal-1"]},
        ),
    )


def _assessment(
    action_address: str,
    *,
    entry_id: str | None = None,
    eligibility: str = "eligible",
) -> ParticipantDecisionSurfaceActionAssessment:
    return ParticipantDecisionSurfaceActionAssessment(
        entry_id=entry_id or f"decision-surface-entries.{action_address.rsplit('.', 1)[-1]}",
        action_contract_address=action_address,
        presentation_basis_ref="projection-policy.red.v1",
        eligibility=eligibility,
        eligibility_reason_refs=(() if eligibility == "eligible" else ("sem211.precondition.authority.out-of-scope",)),
        constraint_refs=(f"{action_address}.preconditions",),
        selection_shape_ref=SCAN_SHAPE if action_address == SCAN else EXFILTRATE_SHAPE,
        support="supported",
        support_refs=("participant-implementation.reference",),
        realization_refs=("realization.reference",),
    )


def _projection_exposure_authorization(
    item_ref: str,
    *,
    observation_order: int,
) -> ParticipantExposureAuthorizationRecord:
    evidence_ref = f"evidence.surface.red.order-{observation_order}"
    provenance_ref = f"provenance.surface.red.order-{observation_order}"
    return ParticipantExposureAuthorizationRecord(
        authorization_record_ref=f"exposure-authorizations.{item_ref}.order-{observation_order}",
        item_ref=item_ref,
        source_ref=item_ref,
        source_layer_ref=f"source-layers.{item_ref}",
        participant_address=PARTICIPANT,
        episode_id=EPISODE,
        audience_scope_ref="audience.participant.red-agent",
        effective_from_order=0,
        effective_through_order=None,
        implementation_selection_ref="participant-selections.red.agent.v1",
        projection_policy_ref="projection-policy.red.v1",
        projection_policy_revision="1",
        exposure_policy_ref="exposure-policy.red.v1",
        exposure_policy_version="1",
        exposure_policy_digest="sha256:" + "3" * 64,
        visibility_basis_ref=f"visibility-bases.{item_ref}",
        operation="disclosure",
        operation_basis_ref=f"disclosures.{item_ref}.v1",
        actor_ref="actors.runtime-projector",
        controller_ref="controllers.red-agent",
        authority_basis_ref="authorities.red-agent.v1",
        backend_support_ref="backend-support.reference.v1",
        source_marking_definition_refs=("markings.participant-visible.v1",),
        result_marking_definition_refs=("markings.participant-visible.v1",),
        source_provenance_refs=(provenance_ref,),
        result_provenance_refs=(provenance_ref,),
        evidence_refs=(evidence_ref,),
        provenance_refs=(provenance_ref,),
        loss_and_limitations=("No known projection loss",),
    )


def _projection_exposure_assessment(item_ref: str, *, observation_order: int) -> ParticipantExposureAssessment:
    return ParticipantExposureAssessment(
        item_ref=item_ref,
        authorization_record_ref=f"exposure-authorizations.{item_ref}.order-{observation_order}",
    )


def _projection_implementation_selection(
    *,
    decision_control_mode: str,
    permitted_refs: tuple[str, ...],
) -> ParticipantImplementationSelectionModel:
    return ParticipantImplementationSelectionModel.model_validate(
        {
            "participant_address": PARTICIPANT,
            "implementation_identity": {"name": "reference-red-agent", "version": "1.0.0"},
            "manifest_ref": "participant-implementation-manifests.reference.v1",
            "manifest_digest": "sha256:" + "1" * 64,
            "selected_decision_surface_mode": decision_control_mode,
            "participant_contract_versions": ["participant-behavior-history-event-stream-v1"],
            "exposure_policy": {
                "policy_id": "exposure-policy.red.v1",
                "policy_version": "1",
                "policy_digest": "sha256:" + "3" * 64,
                "exposure_policy_kinds": ["task-statement"],
                "disclosed_refs": list(permitted_refs),
                "withheld_refs": [],
                "tool_affordance_refs": [],
                "visibility_scope_refs": [],
                "constraints": {},
            },
        }
    )


def _projection_input(
    *,
    observation_order: int,
    action_address: str = SCAN,
    eligibility: str = "eligible",
    implementation_selection_ref: str = "participant-selections.red.agent.v1",
    decision_control_mode: str = "autonomous",
    surface_form: str = "candidate_action_set",
) -> ParticipantDecisionSurfaceProjectionInput:
    affordance_address = SCAN_AFFORDANCE if action_address == SCAN else EXFILTRATE_AFFORDANCE
    entry_id = SCAN_ENTRY if action_address == SCAN else EXFILTRATE_ENTRY
    emitted_refs = ("context.public", action_address, affordance_address)
    forms: dict[str, dict[str, object]] = {
        "candidate_action_set": {
            "surface_form": "candidate_action_set",
            "selection_meaning_ref": "selection-meaning.candidate.v1",
            "candidate_entry_ids": [entry_id],
            "open_extension_binding_ref": None,
        },
        "constrained_form": {
            "surface_form": "constrained_form",
            "selection_meaning_ref": "selection-meaning.form.v1",
            "action_entry_id": entry_id,
            "argument_shape_ref": SCAN_SHAPE if action_address == SCAN else EXFILTRATE_SHAPE,
            "validation_policy_ref": "validation-policies.sem220.v1",
            "constraint_refs": ["forms.action.constraints.v1"],
            "default_disclosure_refs": ["forms.action.defaults.v1"],
            "normalization_disclosure_refs": ["forms.action.normalization.v1"],
            "omission_disclosure_refs": ["forms.action.omission.v1"],
            "loss_disclosure_refs": ["forms.action.loss.none.v1"],
        },
        "open_ended_generation": {
            "surface_form": "open_ended_generation",
            "selection_meaning_ref": "selection-meaning.open.v1",
            "proposal_binding_ref": "proposal-bindings.governed-action.v1",
            "argument_shape_ref": SCAN_SHAPE if action_address == SCAN else EXFILTRATE_SHAPE,
            "validation_policy_ref": "validation-policies.sem220.v1",
            "allowed_action_contract_addresses": [action_address],
        },
    }
    return ParticipantDecisionSurfaceProjectionInput(
        surface_id=f"decision-surfaces.red.episode-1.order-{observation_order}",
        participant_address=PARTICIPANT,
        episode_id=EPISODE,
        observation_order=observation_order,
        observation_point=f"behavior-history:{observation_order}",
        behavior_specification_address=BEHAVIOR,
        observation_boundary_address=BOUNDARY,
        context_view_ref=f"context-views.red.episode-1.order-{observation_order}",
        implementation_selection_ref=implementation_selection_ref,
        decision_control_mode=decision_control_mode,
        audience_scope_ref="audience.participant.red-agent",
        projection_policy_ref="projection-policy.red.v1",
        projection_policy_revision="1",
        exposure_policy_ref="exposure-policy.red.v1",
        visibility_projection_ref=f"visibility-projection.red.order-{observation_order}",
        visible_context_refs=("context.public",),
        action_assessments={
            action_address: _assessment(
                action_address,
                entry_id=entry_id,
                eligibility=eligibility,
            )
        },
        exposure_assessments={
            item_ref: _projection_exposure_assessment(item_ref, observation_order=observation_order)
            for item_ref in emitted_refs
        },
        form=forms[surface_form],
        evidence_refs=(f"evidence.surface.red.order-{observation_order}",),
        provenance_refs=(f"provenance.surface.red.order-{observation_order}",),
        marking_definition_refs=("markings.participant-visible.v1",),
        redaction_policy_ref="redaction.red.v1",
        semantic_limitations=("Presentation does not imply selection, admission, execution, result, or outcome",),
    )


def _projection_exposure_resolvers(
    projection: ParticipantDecisionSurfaceProjectionInput,
) -> ParticipantExposureResolvers:
    emitted_refs = tuple(projection.exposure_assessments)
    selection = _projection_implementation_selection(
        decision_control_mode=projection.decision_control_mode,
        permitted_refs=emitted_refs,
    )
    authorizations = {
        item_ref: _projection_exposure_authorization(
            item_ref,
            observation_order=projection.observation_order,
        )
        for item_ref in emitted_refs
    }
    if projection.implementation_selection_ref != "participant-selections.red.agent.v1":
        authorizations = {
            item_ref: replace(
                authorization,
                implementation_selection_ref=projection.implementation_selection_ref,
            )
            for item_ref, authorization in authorizations.items()
        }
    return ParticipantExposureResolvers(
        apparatus=lambda **_: selection,
        projection_policy=lambda **_: (ParticipantExposurePolicyRevision(projection.projection_policy_ref, "1", 0),),
        authorization=lambda *, authorization_record_ref, item_ref: (
            authorizations.get(item_ref)
            if authorizations.get(item_ref) is not None
            and authorizations[item_ref].authorization_record_ref == authorization_record_ref
            else None
        ),
        occurrence=lambda **_: None,
    )


def _admission_request() -> ParticipantActionAdmissionRequest:
    manifest_payload = json.loads(
        (
            REPO_ROOT
            / "contracts"
            / "fixtures"
            / "participant-implementation-manifest"
            / "participant-implementation-manifest-v1"
            / "valid"
            / "reference.json"
        ).read_text(encoding="utf-8")
    )
    manifest = ParticipantImplementationManifestModel.model_validate(manifest_payload)
    selection = ParticipantImplementationSelectionModel.model_validate(
        {
            "participant_address": PARTICIPANT,
            "implementation_identity": manifest.identity.model_dump(mode="json"),
            "manifest_ref": "participant-implementation-manifests.reference.v1",
            "manifest_digest": "sha256:" + "1" * 64,
            "configuration_ref": "participant-configurations.red.v1",
            "configuration_digest": "sha256:" + "2" * 64,
            "selected_decision_surface_mode": "autonomous",
            "participant_contract_versions": ["participant-behavior-history-event-stream-v1"],
            "exposure_policy": {
                "policy_id": "red-policy",
                "policy_version": "1",
                "policy_digest": "sha256:" + "3" * 64,
                "exposure_policy_kinds": ["task-statement"],
                "disclosed_refs": ["context.public"],
                "withheld_refs": [],
                "tool_affordance_refs": [],
                "visibility_scope_refs": [],
                "constraints": {},
            },
        }
    )
    return ParticipantActionAdmissionRequest(
        participant_address=PARTICIPANT,
        action_contract_address=SCAN,
        observation_boundary_address=BOUNDARY,
        action_instance_id="scan-1",
        implementation_manifest=manifest,
        implementation_selection=selection,
    )


def _eligible_surface(*, surface_form: str = "candidate_action_set") -> ParticipantDecisionSurfaceModel:
    payload = _surface_payload(surface_form=surface_form)
    payload["action_entries"][0]["eligibility"] = "eligible"  # type: ignore[index]
    payload["action_entries"][0]["eligibility_reason_refs"] = []  # type: ignore[index]
    return ParticipantDecisionSurfaceModel.model_validate(payload)


def _surface_selection(
    surface: ParticipantDecisionSurfaceModel,
    *,
    action_contract_address: str = SCAN,
    argument_shape_ref: str | None = None,
) -> ParticipantDecisionSurfaceSelectionModel:
    return ParticipantDecisionSurfaceSelectionModel(
        surface_id=surface.surface_id,
        observation_order=surface.observation_order,
        action_contract_address=action_contract_address,
        argument_shape_ref=argument_shape_ref or surface.action_entries[0].selection_shape_ref,
        proposal_ref="proposals.selection.1",
    )


def _resolved_selection(**kwargs: object) -> ParticipantValidatedActionSelection:
    return ParticipantValidatedActionSelection(
        action_contract_address=str(kwargs["action_contract_address"]),
        argument_shape_ref=str(kwargs["argument_shape_ref"]),
        proposal_ref=str(kwargs["proposal_ref"]),
        normalized_arguments=(),
    )


def _bind_selection(
    surface: ParticipantDecisionSurfaceModel,
    selection: ParticipantDecisionSurfaceSelectionModel,
) -> ParticipantActionAdmissionRequest:
    request = _admission_request()
    return bind_participant_decision_surface_selection(
        surface=surface,
        selection=selection,
        admission_request=request,
        argument_shape_resolver=_resolved_selection,
        apparatus_resolver=lambda **_: request.implementation_selection,
    )


def test_decision_surface_schema_is_closed_discriminated_and_published() -> None:
    surface = ParticipantDecisionSurfaceModel.model_validate(_surface_payload())
    assert surface.form.surface_form == "candidate_action_set"

    schema = schema_bundle()["participant-decision-surface-v1"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["form"]["discriminator"]["propertyName"] == "surface_form"
    assert {entry["id"] for entry in schema["x-raes-invariants"]} >= {
        "decision-surface-entry-reference-agreement",
        "decision-surface-presentation-not-lifecycle-evidence",
        "decision-surface-sem226-item-exposure-agreement",
    }


def test_decision_surface_valid_and_invalid_fixtures_match_model_and_schema() -> None:
    validator = Draft202012Validator(schema_bundle()["participant-decision-surface-v1"])
    valid_paths = sorted((FIXTURE_ROOT / "valid").glob("*.json"))
    invalid_paths = sorted((FIXTURE_ROOT / "invalid").glob("*.json"))
    assert {path.stem for path in valid_paths} >= {"human-candidate", "script-form", "llm-open", "rl-candidate"}
    assert invalid_paths
    for path in valid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(payload)
        ParticipantDecisionSurfaceModel.model_validate(payload)
    for path in invalid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(payload)), path
        with pytest.raises(ValidationError):
            ParticipantDecisionSurfaceModel.model_validate(payload)


@pytest.mark.parametrize(
    ("entry_updates", "message"),
    (
        ({}, "not eligible"),
        (
            {
                "eligibility": "eligible",
                "eligibility_reason_refs": [],
                "support": "unsupported",
                "support_refs": [],
            },
            "not supported",
        ),
    ),
)
def test_candidate_membership_does_not_bypass_entry_admissibility(
    entry_updates: dict[str, object],
    message: str,
) -> None:
    payload = _surface_payload()
    payload["action_entries"][0].update(entry_updates)  # type: ignore[index,union-attr]
    surface = ParticipantDecisionSurfaceModel.model_validate(payload)
    selection = _surface_selection(surface)

    with pytest.raises(ValueError, match=message):
        _bind_selection(surface, selection)


def test_selection_must_be_a_candidate_member() -> None:
    payload = _surface_payload()
    payload["action_entries"][0]["eligibility"] = "eligible"  # type: ignore[index]
    payload["action_entries"][0]["eligibility_reason_refs"] = []  # type: ignore[index]
    exfiltrate_entry = dict(payload["action_entries"][0])  # type: ignore[index]
    exfiltrate_entry.update(
        {
            "entry_id": EXFILTRATE,
            "action_contract_address": EXFILTRATE,
            "selection_shape_ref": "selection-shapes.exfiltrate.v1",
            "affordance_refs": [EXFILTRATE_AFFORDANCE],
        }
    )
    payload["action_entries"].append(exfiltrate_entry)  # type: ignore[union-attr]
    exfiltrate_binding = dict(payload["exposure_bindings"][1])  # type: ignore[index]
    exfiltrate_binding.update(
        {
            "item_ref": EXFILTRATE,
            "source_ref": EXFILTRATE,
            "source_layer_ref": f"source-layers.{EXFILTRATE}",
            "visibility_basis_ref": f"visibility-bases.{EXFILTRATE}",
            "operation_basis_ref": f"disclosures.{EXFILTRATE}.v1",
        }
    )
    payload["exposure_bindings"].append(exfiltrate_binding)  # type: ignore[union-attr]
    payload["form"]["candidate_entry_ids"] = [EXFILTRATE]  # type: ignore[index]
    surface = ParticipantDecisionSurfaceModel.model_validate(payload)
    selection = _surface_selection(surface)

    with pytest.raises(ValueError, match="not a member"):
        _bind_selection(surface, selection)


def test_constrained_form_selection_must_match_its_action_entry() -> None:
    payload = _surface_payload(surface_form="constrained_form")
    payload["action_entries"][0]["eligibility"] = "eligible"  # type: ignore[index]
    payload["action_entries"][0]["eligibility_reason_refs"] = []  # type: ignore[index]
    exfiltrate_entry = dict(payload["action_entries"][0])  # type: ignore[index]
    exfiltrate_entry.update(
        {
            "entry_id": EXFILTRATE,
            "action_contract_address": EXFILTRATE,
            "selection_shape_ref": "selection-shapes.exfiltrate.v1",
            "affordance_refs": [EXFILTRATE_AFFORDANCE],
        }
    )
    payload["action_entries"].append(exfiltrate_entry)  # type: ignore[union-attr]
    exfiltrate_binding = dict(payload["exposure_bindings"][1])  # type: ignore[index]
    exfiltrate_binding.update(
        {
            "item_ref": EXFILTRATE,
            "source_ref": EXFILTRATE,
            "source_layer_ref": f"source-layers.{EXFILTRATE}",
            "visibility_basis_ref": f"visibility-bases.{EXFILTRATE}",
            "operation_basis_ref": f"disclosures.{EXFILTRATE}.v1",
        }
    )
    payload["exposure_bindings"].append(exfiltrate_binding)  # type: ignore[union-attr]
    surface = ParticipantDecisionSurfaceModel.model_validate(payload)

    selection = _surface_selection(
        surface,
        action_contract_address=EXFILTRATE,
        argument_shape_ref="selection-shapes.exfiltrate.v1",
    )
    with pytest.raises(ValueError, match="constrained-form action and argument shape"):
        _bind_selection(surface, selection)


def test_selection_shape_must_match_the_action_entry() -> None:
    surface = _eligible_surface()
    selection = _surface_selection(surface, argument_shape_ref="selection-shapes.other.v1")

    with pytest.raises(ValueError, match="argument_shape_ref must match"):
        _bind_selection(surface, selection)


def test_constrained_form_requires_mapping_disclosures() -> None:
    payload = _surface_payload(surface_form="constrained_form")
    del payload["form"]["loss_disclosure_refs"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="loss_disclosure_refs"):
        ParticipantDecisionSurfaceModel.model_validate(payload)


def test_projection_uses_time_indexed_visibility_and_rejects_future_state() -> None:
    runtime_model = _runtime_model()
    history = _history()
    hidden_projection = _projection_input(observation_order=0, action_address=EXFILTRATE)
    hidden_resolvers = _projection_exposure_resolvers(hidden_projection)

    with pytest.raises(ValueError, match="not participant-visible at observation_order 0"):
        project_participant_decision_surface(
            runtime_model,
            history_events=history,
            projection=hidden_projection,
            exposure_resolvers=hidden_resolvers,
        )

    visible_projection = _projection_input(observation_order=1, action_address=EXFILTRATE)
    surface = project_participant_decision_surface(
        runtime_model,
        history_events=history,
        projection=visible_projection,
        exposure_resolvers=_projection_exposure_resolvers(visible_projection),
    )
    assert surface.observation_order == 1
    assert surface.action_entries[0].visibility == "disclosed"


@pytest.mark.parametrize(
    "surface_form",
    ("candidate_action_set", "constrained_form", "open_ended_generation"),
)
def test_projection_preserves_distinct_entry_and_action_identities(surface_form: str) -> None:
    projection = _projection_input(
        observation_order=0,
        surface_form=surface_form,
    )

    surface = project_participant_decision_surface(
        _runtime_model(),
        history_events=_history(),
        projection=projection,
        exposure_resolvers=_projection_exposure_resolvers(projection),
    )

    assert surface.action_entries[0].entry_id == SCAN_ENTRY
    assert surface.action_entries[0].action_contract_address == SCAN
    selection = _surface_selection(surface)
    assert _bind_selection(surface, selection).action_contract_address == SCAN


def test_candidate_projection_rejects_an_action_address_used_as_an_entry_id() -> None:
    projection = _projection_input(observation_order=0)
    projection = replace(
        projection,
        form={
            "surface_form": "candidate_action_set",
            "selection_meaning_ref": "selection-meaning.candidate.v1",
            "candidate_entry_ids": [SCAN],
            "open_extension_binding_ref": None,
        },
    )
    runtime_model = _runtime_model()
    history_events = _history()
    exposure_resolvers = _projection_exposure_resolvers(projection)

    with pytest.raises(ValueError, match="candidate_entry_ids do not resolve"):
        project_participant_decision_surface(
            runtime_model,
            history_events=history_events,
            projection=projection,
            exposure_resolvers=exposure_resolvers,
        )


def test_projection_rejects_duplicate_surface_entry_ids() -> None:
    projection = _projection_input(observation_order=0)
    projection = replace(
        projection,
        action_assessments={
            SCAN: _assessment(SCAN, entry_id="decision-surface-entries.shared"),
            EXFILTRATE: _assessment(EXFILTRATE, entry_id="decision-surface-entries.shared"),
        },
    )
    runtime_model = _runtime_model()
    history_events = _history()
    exposure_resolvers = _projection_exposure_resolvers(projection)

    with pytest.raises(ValueError, match="action assessment entry_id values must be unique"):
        project_participant_decision_surface(
            runtime_model,
            history_events=history_events,
            projection=projection,
            exposure_resolvers=exposure_resolvers,
        )


def test_projection_rejects_assessment_for_a_different_compiled_argument_shape() -> None:
    projection = _projection_input(observation_order=0)
    projection = replace(
        projection,
        action_assessments={
            SCAN: replace(
                projection.action_assessments[SCAN],
                selection_shape_ref=EXFILTRATE_SHAPE,
            )
        },
    )
    runtime_model = _runtime_model()
    history_events = _history()
    exposure_resolvers = _projection_exposure_resolvers(projection)

    with pytest.raises(ValueError, match="does not match its compiled argument shape"):
        project_participant_decision_surface(
            runtime_model,
            history_events=history_events,
            projection=projection,
            exposure_resolvers=exposure_resolvers,
        )


@pytest.mark.parametrize("omitted_ref", (SCAN, SCAN_AFFORDANCE))
def test_projection_requires_visibility_proof_for_every_emitted_ref(omitted_ref: str) -> None:
    runtime_model = _runtime_model(omitted_visibility_ref=omitted_ref)
    history = _history()
    projection = _projection_input(observation_order=0)
    resolvers = _projection_exposure_resolvers(projection)

    with pytest.raises(ValueError, match="lack an effective view disposition"):
        project_participant_decision_surface(
            runtime_model,
            history_events=history,
            projection=projection,
            exposure_resolvers=resolvers,
        )


def test_projection_rejects_global_history_and_final_snapshot_substitution() -> None:
    runtime_model = _runtime_model()
    foreign = ParticipantBehaviorHistoryEvent(
        event_type=ParticipantBehaviorHistoryEventType.ACTION_ATTEMPTED,
        timestamp="2026-07-20T08:00:00Z",
        participant_address="participant.behavior.blue-agent",
        episode_id=EPISODE,
        action_instance_id="foreign-1",
        action_contract_address=SCAN,
        actor_provenance="participant:blue-agent",
    )
    global_history = (*_history(), foreign)
    projection = _projection_input(observation_order=0)
    resolvers = _projection_exposure_resolvers(projection)
    with pytest.raises(ValueError, match="one participant and episode"):
        project_participant_decision_surface(
            runtime_model,
            history_events=global_history,
            projection=projection,
            exposure_resolvers=resolvers,
        )
    with pytest.raises(ValueError, match="time-indexed history"):
        project_participant_decision_surface(
            runtime_model,
            history_events=(),
            projection=projection,
            exposure_resolvers=resolvers,
        )


@pytest.mark.parametrize(
    ("implementation_selection_ref", "decision_control_mode"),
    (
        ("participant-selections.red.human.v1", "human-supervised"),
        ("participant-selections.red.script.v1", "scripted"),
        ("participant-selections.red.llm.v1", "autonomous"),
        ("participant-selections.red.rl.v1", "autonomous"),
    ),
)
def test_realization_kind_preserves_surface_semantic_refs(
    implementation_selection_ref: str,
    decision_control_mode: str,
) -> None:
    projection = _projection_input(
        observation_order=0,
        implementation_selection_ref=implementation_selection_ref,
        decision_control_mode=decision_control_mode,
    )
    surface = project_participant_decision_surface(
        _runtime_model(),
        history_events=_history(),
        projection=projection,
        exposure_resolvers=_projection_exposure_resolvers(projection),
    )
    assert surface.action_entries[0].action_contract_address == SCAN
    assert surface.action_entries[0].selection_shape_ref == SCAN_SHAPE
    assert surface.form.selection_meaning_ref == "selection-meaning.candidate.v1"


@pytest.mark.parametrize(
    ("field_name", "mismatched_value"),
    (
        ("observation_point", "behavior-history:99"),
        ("evidence_refs", ["evidence.surface.other"]),
        ("provenance_refs", ["provenance.surface.other"]),
        ("marking_definition_refs", ["markings.other.v1"]),
        ("redaction_policy_ref", "redaction.other.v1"),
        ("semantic_limitations", ["Different limitation"]),
    ),
)
def test_context_envelope_and_payload_must_agree(field_name: str, mismatched_value: object) -> None:
    surface = ParticipantDecisionSurfaceModel.model_validate(_surface_payload())
    context = ParticipantContextViewModel.model_validate(
        {
            "view_id": surface.context_view_ref,
            "participant_address": PARTICIPANT,
            "episode_id": EPISODE,
            "generated_at": "2026-07-20T08:00:00Z",
            "source_snapshot_ref": "snapshots.run-1.order-0",
            "view_ref": "views.decision-surface.v1",
            "meaning_ref": "semantics.decision-surface.v1",
            "participant_scope": "participant_local",
            "audience_scope": "participant_visible",
            "observation_point": surface.observation_point,
            "derived_from_refs": ["snapshots.run-1.order-0"],
            "source_layers": [
                {
                    "source_id": "history-order-0",
                    "source_layer": "participant_behavior_history",
                    "ref": "snapshots.run-1.order-0",
                    "temporal_relation": "same_observation_point",
                    "observation_point": surface.observation_point,
                    "evidence_refs": surface.evidence_refs,
                    "provenance_refs": surface.provenance_refs,
                }
            ],
            "transformation": {
                "transformation_rule_ref": surface.projection_policy_ref,
                "description": "Project one participant-local decision surface at one order point",
                "input_source_ids": ["history-order-0"],
                "output_semantics_ref": "semantics.decision-surface.v1",
            },
            "comparability": {
                "comparability_class": "portable_equivalent",
                "comparison_basis_ref": "comparability.decision-surface.v1",
                "backend_disclosure_refs": [],
                "limitations": surface.semantic_limitations,
            },
            "evidence_refs": surface.evidence_refs,
            "provenance_refs": surface.provenance_refs,
            "semantic_limitations": surface.semantic_limitations,
            "derivation_basis_ref": surface.projection_policy_ref,
            "payload_ref": surface.surface_id,
            "visibility_projection_ref": surface.visibility_projection_ref,
            "marking_definition_refs": surface.marking_definition_refs,
            "redaction_policy_ref": surface.redaction_policy_ref,
        }
    )
    validate_participant_decision_surface_context(surface, context)

    mismatched = context.model_copy(update={field_name: mismatched_value})
    with pytest.raises(ValueError, match=field_name):
        validate_participant_decision_surface_context(surface, mismatched)


class _RecordingControl(ParticipantControlMixin):
    def __init__(self) -> None:
        self._target = SimpleNamespace(participant_runtime=object())
        self.admitted: ParticipantActionAdmissionRequest | None = None

    def _reject_diagnostics(self, **kwargs: object) -> str:
        return "rejected"

    def admit_participant_action(
        self,
        participant_behavior: object,
        admission_request: ParticipantActionAdmissionRequest,
        **kwargs: object,
    ) -> str:
        self.admitted = admission_request
        return "admitted"


def test_open_ended_proposal_validates_before_existing_admission_path() -> None:
    payload = _surface_payload(surface_form="open_ended_generation")
    payload["action_entries"][0]["eligibility"] = "eligible"  # type: ignore[index]
    payload["action_entries"][0]["eligibility_reason_refs"] = []  # type: ignore[index]
    surface = ParticipantDecisionSurfaceModel.model_validate(payload)
    selection = ParticipantDecisionSurfaceSelectionModel(
        surface_id=surface.surface_id,
        observation_order=surface.observation_order,
        action_contract_address=SCAN,
        argument_shape_ref="selection-shapes.scan.v1",
        proposal_ref="proposals.scan.1",
    )
    request = _admission_request()
    control = _RecordingControl()
    resolver_calls: list[str] = []
    apparatus_calls: list[tuple[str, str]] = []

    def resolve_apparatus(**kwargs: str) -> ParticipantImplementationSelectionModel:
        apparatus_calls.append((kwargs["implementation_selection_ref"], kwargs["exposure_policy_ref"]))
        return request.implementation_selection

    def reject_shape(**kwargs: str) -> bool:
        resolver_calls.append(kwargs["proposal_ref"])
        return False

    rejected = control.admit_participant_decision_surface_selection(
        SimpleNamespace(address=PARTICIPANT),
        surface=surface,
        selection=selection,
        admission_request=request,
        resolvers=ParticipantDecisionSurfaceBindingResolvers(
            argument_shape=reject_shape,
            apparatus=resolve_apparatus,
        ),
    )
    assert rejected == "rejected"
    assert resolver_calls == ["proposals.scan.1"]
    assert apparatus_calls == [(surface.implementation_selection_ref, surface.exposure_policy_ref)]
    assert control.admitted is None

    admitted = control.admit_participant_decision_surface_selection(
        SimpleNamespace(address=PARTICIPANT),
        surface=surface,
        selection=selection,
        admission_request=request,
        resolvers=ParticipantDecisionSurfaceBindingResolvers(
            argument_shape=_resolved_selection,
            apparatus=resolve_apparatus,
        ),
    )
    assert admitted == "admitted"
    assert control.admitted is not request
    assert control.admitted is not None
    assert control.admitted.validated_selection is not None
    assert control.admitted.validated_selection.proposal_ref == selection.proposal_ref


def test_selection_carries_concrete_arguments_into_the_admitted_portable_carrier() -> None:
    surface = _eligible_surface(surface_form="open_ended_generation")
    selection = _surface_selection(surface).model_copy(update={"arguments": {"query": " status "}})
    request = _admission_request()
    seen_arguments: list[dict[str, object]] = []

    def resolve_arguments(**kwargs: object) -> ParticipantValidatedActionSelection:
        seen_arguments.append(dict(kwargs["proposed_arguments"]))  # type: ignore[arg-type]
        return ParticipantValidatedActionSelection(
            action_contract_address=str(kwargs["action_contract_address"]),
            argument_shape_ref=str(kwargs["argument_shape_ref"]),
            proposal_ref=str(kwargs["proposal_ref"]),
            normalized_arguments=(("query", "status"),),
            normalization_disclosure_refs=("arguments.query.normalization.trim",),
            omission_disclosure_refs=("arguments.query.omission.reject",),
            loss_disclosure_refs=("arguments.query.loss.none",),
        )

    bound = bind_participant_decision_surface_selection(
        surface=surface,
        selection=selection,
        admission_request=request,
        argument_shape_resolver=resolve_arguments,
        apparatus_resolver=lambda **_: request.implementation_selection,
    )

    assert seen_arguments == [{"query": " status "}]
    assert bound.validated_selection is not None
    assert bound.validated_selection.argument_map == {"query": "status"}


@pytest.mark.parametrize(
    ("coordinate_name", "mismatched_value"),
    (
        ("argument_shape_ref", EXFILTRATE_SHAPE),
        ("proposal_ref", "proposals.selection.stale"),
    ),
)
def test_binding_rejects_resolver_result_for_different_proposal_coordinates(
    coordinate_name: str,
    mismatched_value: str,
) -> None:
    surface = _eligible_surface(surface_form="open_ended_generation")
    selection = _surface_selection(surface)
    request = _admission_request()

    def resolve_different_coordinates(**kwargs: object) -> ParticipantValidatedActionSelection:
        coordinates = {
            "action_contract_address": str(kwargs["action_contract_address"]),
            "argument_shape_ref": str(kwargs["argument_shape_ref"]),
            "proposal_ref": str(kwargs["proposal_ref"]),
        }
        coordinates[coordinate_name] = mismatched_value
        return ParticipantValidatedActionSelection(
            **coordinates,
            normalized_arguments=(),
        )

    with pytest.raises(ValueError, match="must match the governed proposal coordinates"):
        bind_participant_decision_surface_selection(
            surface=surface,
            selection=selection,
            admission_request=request,
            argument_shape_resolver=resolve_different_coordinates,
            apparatus_resolver=lambda **_: request.implementation_selection,
        )


def test_surface_apparatus_must_resolve_to_the_admission_selection() -> None:
    payload = _surface_payload(surface_form="open_ended_generation")
    payload["action_entries"][0]["eligibility"] = "eligible"  # type: ignore[index]
    payload["action_entries"][0]["eligibility_reason_refs"] = []  # type: ignore[index]
    surface = ParticipantDecisionSurfaceModel.model_validate(payload)
    selection = ParticipantDecisionSurfaceSelectionModel(
        surface_id=surface.surface_id,
        observation_order=surface.observation_order,
        action_contract_address=SCAN,
        argument_shape_ref="selection-shapes.scan.v1",
        proposal_ref="proposals.scan.1",
    )
    request = _admission_request()
    mismatched_selection = request.implementation_selection.model_copy(
        update={"configuration_ref": "participant-configurations.other.v1"}
    )
    control = _RecordingControl()
    shape_calls: list[str] = []

    rejected = control.admit_participant_decision_surface_selection(
        SimpleNamespace(address=PARTICIPANT),
        surface=surface,
        selection=selection,
        admission_request=request,
        resolvers=ParticipantDecisionSurfaceBindingResolvers(
            argument_shape=lambda **kwargs: shape_calls.append(kwargs["proposal_ref"]) or _resolved_selection(**kwargs),
            apparatus=lambda **_: mismatched_selection,
        ),
    )

    assert rejected == "rejected"
    assert shape_calls == []
    assert control.admitted is None

    mismatched_mode_surface = surface.model_copy(update={"decision_control_mode": "scripted"})
    rejected = control.admit_participant_decision_surface_selection(
        SimpleNamespace(address=PARTICIPANT),
        surface=mismatched_mode_surface,
        selection=selection,
        admission_request=request,
        resolvers=ParticipantDecisionSurfaceBindingResolvers(
            argument_shape=lambda **kwargs: shape_calls.append(kwargs["proposal_ref"]) or _resolved_selection(**kwargs),
            apparatus=lambda **_: request.implementation_selection,
        ),
    )

    assert rejected == "rejected"
    assert shape_calls == []
    assert control.admitted is None


def test_presentation_cannot_be_encoded_as_selection_result_or_outcome() -> None:
    payload = _surface_payload()
    payload["selected_action_contract_address"] = SCAN
    payload["outcome"] = "succeeded"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ParticipantDecisionSurfaceModel.model_validate(payload)
