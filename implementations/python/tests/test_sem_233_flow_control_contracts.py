"""Portable SEM-233 flow-control profile and relation contract tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from deterministic_participant_fixtures import (
    build_implementation_manifest,
    build_implementation_selection,
)
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_conformance.conformance.validators import (
    contract_validation_strength,
    supported_contract_ids,
    validate_contract_payload,
)
from raes_contracts.contracts import (
    ParticipantBoundaryFlowPolicyProfileModel,
    ParticipantControlDeclarationModel,
    ParticipantControlOccurrenceModel,
    ParticipantCrossingOccurrenceModel,
    ParticipantFlowActionAdmissionResolution,
    ParticipantFlowBindingKind,
    ParticipantFlowCapabilityResolution,
    ParticipantFlowControlRelationModel,
    ParticipantFlowControlValidationContext,
    ParticipantFlowCoordinateResult,
    ParticipantFlowFinalDisposition,
    ParticipantFlowHistoryHeadResolution,
    ParticipantFlowLabelResolutionStatus,
    ParticipantFlowRelationTargetKind,
    ParticipantFlowReleaseAuthorityCoordinate,
    ParticipantFlowReleaseKind,
    ParticipantFlowSinkCoordinate,
    ParticipantFlowSinkKind,
    ParticipantFlowSubjectKind,
    RuntimeFactBindingPlaneModel,
    schema_bundle,
    validate_participant_flow_control_resolved_context,
)
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingPolicyReferenceModel,
    ParticipantCrossingSubjectReferenceModel,
)
from raes_contracts.controlled_vocabularies import load_controlled_vocabulary_catalog
from raes_contracts.participant_action_arguments import ParticipantValidatedActionSelection
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_flow_policy_profiles import (
    PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_ID,
    load_participant_boundary_flow_policy_profile,
    load_participant_boundary_flow_policy_profile_from_path,
    load_participant_boundary_flow_policy_profile_revision,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILE_ID = "participant-boundary-flow-policy-v1"
PROFILE_REVISION = "rev1"


def _published_profile_payload() -> dict[str, object]:
    path = REPO_ROOT / "contracts" / "profiles" / "participant-boundary-flow-policy" / f"{PROFILE_ID}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_published_flow_profile_is_closed_revisioned_and_digest_bound() -> None:
    profile = load_participant_boundary_flow_policy_profile(PROFILE_ID)

    assert PARTICIPANT_BOUNDARY_FLOW_POLICY_PROFILE_ID == PROFILE_ID
    assert profile.profile_id == PROFILE_ID
    assert profile.profile_revision == PROFILE_REVISION
    assert profile.authority_revision == "sem-233/rev1"
    assert profile.confidentiality_obligation_refs
    assert profile.integrity_obligation_refs
    assert profile.unknown_confidentiality_obligation_ref in profile.confidentiality_obligation_refs
    assert profile.unknown_integrity_obligation_ref in profile.integrity_obligation_refs
    assert profile.unknown_source_posture == "unsupported-top"
    assert profile.canonical_digest.startswith("sha256:")

    assert (
        load_participant_boundary_flow_policy_profile_revision(
            PROFILE_ID,
            PROFILE_REVISION,
            profile.canonical_digest,
        )
        == profile
    )


@pytest.mark.parametrize(
    "profile_id",
    [
        "latest",
        "participant-boundary-flow-policy-v2",
        "../participant-boundary-flow-policy-v1",
        "/tmp/participant-boundary-flow-policy-v1",
    ],
)
def test_flow_profile_loader_rejects_aliases_unknown_ids_and_paths(profile_id: str) -> None:
    with pytest.raises(ValueError, match="profile id|unsupported"):
        load_participant_boundary_flow_policy_profile(profile_id)


def test_flow_profile_loader_rejects_unknown_revision_and_digest() -> None:
    profile = load_participant_boundary_flow_policy_profile(PROFILE_ID)

    with pytest.raises(ValueError, match="revision"):
        load_participant_boundary_flow_policy_profile_revision(
            PROFILE_ID,
            "rev2",
            profile.canonical_digest,
        )
    with pytest.raises(ValueError, match="digest"):
        load_participant_boundary_flow_policy_profile_revision(
            PROFILE_ID,
            PROFILE_REVISION,
            "sha256:" + "0" * 64,
        )


def test_flow_profile_ingress_is_bounded_closed_and_identity_checked(tmp_path: Path) -> None:
    payload = _published_profile_payload()
    payload["policy_expression"] = "permit if caller says trusted"
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON or contract is invalid"):
        load_participant_boundary_flow_policy_profile_from_path(PROFILE_ID, path)

    path.write_bytes(b"{" + b" " * (256 * 1024) + b"}")
    with pytest.raises(ValueError, match="JSON or contract is invalid"):
        load_participant_boundary_flow_policy_profile_from_path(PROFILE_ID, path)


def test_flow_profile_requires_canonical_two_coordinate_universes() -> None:
    payload = _published_profile_payload()
    payload["confidentiality_obligation_refs"] = [
        "confidentiality:restricted",
        "confidentiality:restricted",
    ]

    with pytest.raises(ValidationError, match="canonical sorted order"):
        ParticipantBoundaryFlowPolicyProfileModel.model_validate(payload)

    payload = _published_profile_payload()
    del payload["integrity_obligation_refs"]
    with pytest.raises(ValidationError, match="integrity_obligation_refs"):
        ParticipantBoundaryFlowPolicyProfileModel.model_validate(payload)


def test_flow_profile_nonclaims_are_complete_and_canonical() -> None:
    payload = _published_profile_payload()
    payload["nonclaims"] = ["runtime-enforcement"]

    with pytest.raises(ValidationError, match="nonclaims"):
        ParticipantBoundaryFlowPolicyProfileModel.model_validate(payload)

    payload = _published_profile_payload()
    payload["description"] = "caller-selected alternate rev1 meaning"
    with pytest.raises(ValidationError, match="exact published rev1"):
        ParticipantBoundaryFlowPolicyProfileModel.model_validate(payload)


def _profile_ref() -> dict[str, object]:
    profile = load_participant_boundary_flow_policy_profile(PROFILE_ID)
    return {
        "profile_id": profile.profile_id,
        "profile_revision": profile.profile_revision,
        "profile_digest": profile.canonical_digest,
        "authority_revision": profile.authority_revision,
    }


def _policy() -> dict[str, object]:
    return {
        "policy_id": "participant-crossing-policy:red",
        "policy_revision": "revision-3",
        "policy_digest": "sha256:" + "a" * 64,
        "policy_decision_ref": "participant-crossing-policy-decision:red:episode-1:8",
        "decision_cut_ref": "participant-policy-cut:red:episode-1:8",
        "decision_cut_revision": "cut-rev8",
        "effective_order": 8,
    }


def _subject(
    kind: str,
    ref: str,
    *,
    participant: str = "participants.red.operator",
    episode: str = "episode-1",
) -> dict[str, object]:
    return {
        "subject_kind": kind,
        "subject_ref": ref,
        "subject_revision": "1",
        "participant_address": participant,
        "episode_id": episode,
    }


def _label(
    label_id: str,
    subject: dict[str, object],
    confidentiality: list[str],
    integrity: list[str],
    *,
    provenance: list[str],
    influence: list[str],
    resolution: str = "resolved",
) -> dict[str, object]:
    return {
        "label_id": label_id,
        "subject": subject,
        "profile": _profile_ref(),
        "policy": _policy(),
        "resolution_status": resolution,
        "confidentiality_obligation_refs": confidentiality,
        "integrity_obligation_refs": integrity,
        "provenance_refs": provenance,
        "influence_refs": influence,
        "evidence_refs": [f"evidence:{label_id}"],
    }


def _relation_payload() -> dict[str, object]:
    fact = _subject("runtime-fact-version", "fact-version.1")
    argument = _subject("action-argument", "action-proposal.1:target")
    derived = _subject("derived-result", "derived-result.1")
    declassified = _subject("derived-result", "declassified-result.1")
    endorsed = _subject("derived-result", "endorsed-result.1")
    labels = [
        _label(
            "label.fact.1",
            fact,
            ["confidentiality:restricted"],
            ["integrity:untrusted"],
            provenance=["provenance:fact.1"],
            influence=["fact-version.1"],
        ),
        _label(
            "label.argument.1",
            argument,
            [],
            ["integrity:untrusted"],
            provenance=["provenance:argument.1"],
            influence=["action-proposal.1:target"],
        ),
        _label(
            "label.derived.1",
            derived,
            ["confidentiality:restricted"],
            ["integrity:untrusted"],
            provenance=["provenance:argument.1", "provenance:derivation.1", "provenance:fact.1"],
            influence=[
                "action-proposal.1:target",
                "fact-version.1",
                "influence:derivation.1",
            ],
        ),
        _label(
            "label.declassified.1",
            declassified,
            [],
            ["integrity:untrusted"],
            provenance=[
                "provenance:argument.1",
                "provenance:declassification.1",
                "provenance:derivation.1",
                "provenance:fact.1",
            ],
            influence=[
                "action-proposal.1:target",
                "derived-result.1",
                "fact-version.1",
                "influence:derivation.1",
            ],
        ),
        _label(
            "label.endorsed.1",
            endorsed,
            [],
            ["integrity:endorsed"],
            provenance=[
                "provenance:argument.1",
                "provenance:declassification.1",
                "provenance:derivation.1",
                "provenance:endorsement.1",
                "provenance:fact.1",
            ],
            influence=[
                "action-proposal.1:target",
                "declassified-result.1",
                "derived-result.1",
                "fact-version.1",
                "influence:derivation.1",
            ],
        ),
    ]
    return {
        "schema_version": "participant-flow-control-relation/v1",
        "document_id": "participant-flow-control-relation:red:episode-1",
        "document_revision": "rev1",
        "profile": _profile_ref(),
        "labels": labels,
        "derivations": [
            {
                "derivation_id": "derivation.1",
                "profile": _profile_ref(),
                "policy": _policy(),
                "inputs": [
                    {"subject": argument, "label_ref": "label.argument.1"},
                    {"subject": fact, "label_ref": "label.fact.1"},
                ],
                "result_subject": derived,
                "result_label_ref": "label.derived.1",
                "rule_ref": "sem-233:complete-possible-input-join",
                "rule_revision": "rev1",
                "apparatus_ref": "apparatus:participant-runtime.red",
                "apparatus_revision": "rev4",
                "predecessor_refs": ["action-proposal.1:target", "fact-version.1"],
                "provenance_refs": ["provenance:derivation.1"],
                "influence_refs": ["influence:derivation.1"],
                "evidence_refs": ["evidence:derivation.1"],
            }
        ],
        "releases": [
            {
                "kind": "declassification",
                "release_id": "release.declassification.1",
                "profile": _profile_ref(),
                "policy": _policy(),
                "source_subject": derived,
                "source_label_ref": "label.derived.1",
                "result_subject": declassified,
                "result_label_ref": "label.declassified.1",
                "removed_confidentiality_obligation_refs": ["confidentiality:restricted"],
                "sink_ref": "sink:participant-output.1",
                "destination_ref": "destination:operator-console",
                "audience_scope_ref": "audience:red-operator",
                "authority_basis_ref": "authority:declassification.1",
                "authority_revision": "rev2",
                "predecessor_refs": ["derived-result.1"],
                "evidence_refs": ["evidence:declassification.1"],
                "limitation_refs": ["limitation:explicit-flow-only"],
            },
            {
                "kind": "endorsement",
                "release_id": "release.endorsement.1",
                "profile": _profile_ref(),
                "policy": _policy(),
                "source_subject": declassified,
                "source_label_ref": "label.declassified.1",
                "result_subject": endorsed,
                "result_label_ref": "label.endorsed.1",
                "integrity_obligation_replacements": [
                    {
                        "source_obligation_ref": "integrity:untrusted",
                        "result_obligation_ref": "integrity:endorsed",
                    }
                ],
                "sink_ref": "sink:participant-output.1",
                "destination_ref": "destination:operator-console",
                "audience_scope_ref": "audience:red-operator",
                "authority_basis_ref": "authority:endorsement.1",
                "authority_revision": "rev5",
                "predecessor_refs": ["declassified-result.1"],
                "evidence_refs": ["evidence:endorsement.1"],
                "limitation_refs": ["limitation:explicit-flow-only"],
            },
        ],
        "sink_decisions": [
            {
                "decision_id": "sink-decision.1",
                "profile": _profile_ref(),
                "policy": _policy(),
                "subject": endorsed,
                "label_ref": "label.endorsed.1",
                "sink": {
                    "sink_kind": "participant-output",
                    "sink_ref": "sink:participant-output.1",
                    "destination_ref": "destination:operator-console",
                    "audience_scope_ref": "audience:red-operator",
                },
                "confidentiality_result": "satisfied",
                "integrity_result": "satisfied",
                "release_refs": ["release.declassification.1", "release.endorsement.1"],
                "api_423_decision_ref": "crossing-decision.1",
                "action_admission_ref": "action-admission.1",
                "capability_resolution_ref": "capability-resolution.1",
                "expected_history_head_refs": ["history-head:participant.1"],
                "final_disposition": "permit",
                "reason_code": "all-conjuncts-satisfied",
                "evidence_refs": ["evidence:sink-decision.1"],
                "limitation_refs": ["limitation:contract-record-only"],
            }
        ],
        "bindings": [
            {
                "kind": "runtime-fact",
                "binding_id": "binding.runtime-fact.1",
                "profile": _profile_ref(),
                "policy": _policy(),
                "relation_target": {"target_kind": "label", "target_ref": "label.fact.1"},
                "source_participant_address": "participants.red.operator",
                "source_episode_id": "episode-1",
                "target_participant_address": "participants.red.operator",
                "target_episode_id": "episode-1",
                "crossing_refs": [],
                "memory_predecessor_refs": [],
                "plane_ref": "runtime-fact-plane.1",
                "declaration_ref": "fact.observed-host",
                "fact_version_ref": "fact-version.1",
                "sink_ref": "sink.scan-target",
                "binding_event_ref": "fact-binding.scan-0001.1",
            }
        ],
    }


def test_relation_accepts_conservative_derivation_distinct_releases_and_sink_decision() -> None:
    relation = ParticipantFlowControlRelationModel.model_validate(_relation_payload())

    assert relation.labels[2].confidentiality_obligation_refs == ("confidentiality:restricted",)
    assert relation.releases[0].kind == "declassification"
    assert relation.releases[1].kind == "endorsement"
    assert relation.sink_decisions[0].final_disposition == "permit"


def test_effective_label_requires_both_canonical_coordinates_and_rejects_payloads() -> None:
    payload = _relation_payload()
    del payload["labels"][0]["integrity_obligation_refs"]
    with pytest.raises(ValidationError, match="integrity_obligation_refs"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    payload = _relation_payload()
    payload["labels"][0]["confidentiality_obligation_refs"] = [
        "confidentiality:restricted",
        "confidentiality:restricted",
    ]
    with pytest.raises(ValidationError, match="canonical sorted order"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    payload = _relation_payload()
    payload["labels"][0]["prompt"] = "hidden prompt"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ParticipantFlowControlRelationModel.model_validate(payload)


def test_derivation_requires_exact_union_and_conservative_provenance_and_influence() -> None:
    payload = _relation_payload()
    payload["labels"][2]["confidentiality_obligation_refs"] = []
    with pytest.raises(ValidationError, match="coordinate-wise union"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    payload = _relation_payload()
    payload["labels"][2]["provenance_refs"].remove("provenance:fact.1")
    with pytest.raises(ValidationError, match="provenance"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    payload = _relation_payload()
    payload["labels"][2]["influence_refs"].remove("fact-version.1")
    with pytest.raises(ValidationError, match="influence"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    payload = _relation_payload()
    duplicate = json.loads(json.dumps(payload["derivations"][0]))
    duplicate["derivation_id"] = "derivation.duplicate-producer"
    payload["derivations"].append(duplicate)
    with pytest.raises(ValidationError, match="fresh result identity"):
        ParticipantFlowControlRelationModel.model_validate(payload)


@pytest.mark.parametrize(
    ("coordinate", "value"),
    [
        ("subject_revision", "2"),
        ("participant_address", "participants.blue.operator"),
        ("episode_id", "episode-2"),
    ],
)
def test_subject_freshness_uses_every_exact_identity_coordinate(coordinate: str, value: str) -> None:
    payload = _relation_payload()
    result_subject = json.loads(json.dumps(payload["labels"][0]["subject"]))
    result_subject[coordinate] = value
    payload["labels"][2]["subject"] = result_subject
    payload["derivations"][0]["result_subject"] = result_subject
    payload["releases"][0]["source_subject"] = result_subject

    ParticipantFlowControlRelationModel.model_validate(payload)


def test_unresolved_derivation_cannot_become_resolved_or_empty() -> None:
    payload = _relation_payload()
    payload["labels"][0]["resolution_status"] = "unresolved"

    with pytest.raises(ValidationError, match="unresolved input"):
        ParticipantFlowControlRelationModel.model_validate(payload)


def test_release_cannot_promote_an_unresolved_source_to_resolved() -> None:
    payload = _relation_payload()
    payload["labels"][2]["resolution_status"] = "unresolved"

    with pytest.raises(ValidationError, match="release with an unresolved source"):
        ParticipantFlowControlRelationModel.model_validate(payload)


def test_declassification_and_endorsement_are_exact_fresh_coordinate_specific_releases() -> None:
    payload = _relation_payload()
    payload["labels"][3]["integrity_obligation_refs"] = []
    with pytest.raises(ValidationError, match="integrity coordinate unchanged"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    payload = _relation_payload()
    payload["labels"][4]["confidentiality_obligation_refs"] = ["confidentiality:unknown"]
    with pytest.raises(ValidationError, match="confidentiality coordinate unchanged"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    payload = _relation_payload()
    payload["releases"][0]["result_subject"] = payload["releases"][0]["source_subject"]
    with pytest.raises(ValidationError, match="fresh result identity"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    payload = _relation_payload()
    payload["releases"][0]["destination_ref"] = "destination:other"
    with pytest.raises(ValidationError, match="exact final sink"):
        ParticipantFlowControlRelationModel.model_validate(payload)


def test_sink_decision_disposition_is_the_exact_two_coordinate_result() -> None:
    payload = _relation_payload()
    payload["sink_decisions"][0]["integrity_result"] = "deny"

    with pytest.raises(ValidationError, match="final disposition"):
        ParticipantFlowControlRelationModel.model_validate(payload)


def test_relation_requires_a_typed_carrier_binding_and_one_exact_policy_cut() -> None:
    payload = _relation_payload()
    payload["bindings"] = []
    with pytest.raises(ValidationError, match="bindings"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    payload = _relation_payload()
    payload["derivations"][0]["policy"]["decision_cut_revision"] = "caller-selected-cut"
    with pytest.raises(ValidationError, match="policy and cut"):
        ParticipantFlowControlRelationModel.model_validate(payload)


def _load_fixture(relative: str) -> dict[str, object]:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def _runtime_fact_plane() -> RuntimeFactBindingPlaneModel:
    payload = _load_fixture(
        "contracts/fixtures/participant-runtime/runtime-fact-binding-plane-v1/valid/observation-to-action.json"
    )
    payload["declarations"][0]["visibility"]["participant_addresses"] = ["participants.red.operator"]
    payload["sinks"][0]["action_contract_address"] = "participant.action-contract.contain-host"
    payload["versions"][0]["version_id"] = "fact-version.1"
    payload["events"][0]["fact_version_id"] = "fact-version.1"
    payload["projections"][0]["fact_version_id"] = "fact-version.1"
    for item in (*payload["versions"], *payload["events"], *payload["projections"]):
        if "participant_address" in item:
            item["participant_address"] = "participants.red.operator"
        if isinstance(item.get("scope"), dict):
            item["scope"]["participant_address"] = "participants.red.operator"
    payload["events"][0]["action_contract_address"] = "participant.action-contract.contain-host"
    return RuntimeFactBindingPlaneModel.model_validate(payload)


def _action_selection_and_admission() -> tuple[
    ParticipantValidatedActionSelection,
    ParticipantActionAdmissionRequest,
]:
    selection = ParticipantValidatedActionSelection(
        action_contract_address="participant.action-contract.contain-host",
        argument_shape_ref="shape:contain-host",
        proposal_ref="proposal.1",
        normalized_arguments=(("target", "host:synthetic"),),
    )
    admission = ParticipantActionAdmissionRequest(
        participant_address="participants.red.operator",
        action_contract_address=selection.action_contract_address,
        observation_boundary_address="participant.observation-boundary.red-view",
        action_instance_id="action-1",
        implementation_manifest=build_implementation_manifest(),
        implementation_selection=build_implementation_selection("participants.red.operator"),
        evidence_refs=("evidence:action",),
        observation_boundary_evidence_refs=("evidence:action",),
        validated_selection=selection,
    )
    return selection, admission


def _control_record_and_declaration() -> tuple[
    ParticipantControlOccurrenceModel,
    ParticipantControlDeclarationModel,
]:
    payload = _load_fixture(
        "contracts/fixtures/participant-runtime/participant-control-occurrence-v1/valid/proposal.json"
    )
    record = ParticipantControlOccurrenceModel.model_validate(payload)
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


def _crossing_records(
    *, denied: bool = False
) -> tuple[
    list[ParticipantCrossingOccurrenceModel],
    ParticipantCrossingSubjectReferenceModel,
    ParticipantCrossingPolicyReferenceModel,
]:
    request_payload = _load_fixture(
        "contracts/fixtures/participant-runtime/participant-crossing-occurrence-v1/valid/request.json"
    )
    request = ParticipantCrossingOccurrenceModel.model_validate(request_payload)
    decision_payload = json.loads(json.dumps(request_payload))
    decision_payload["event_id"] = "crossing-occurrence.decided.1"
    decision_payload["predecessor_event_refs"] = [request.event_id]
    decision_payload["occurrence"].update(
        {
            "stage": "decided",
            "request_ref": "crossing-request.1",
            "decision_id": "crossing-decision.1",
            "decision_revision": 1,
            "gates": {
                "caller_authorization": "permit",
                "target_authorization": "permit",
                "participant_authority": "permit",
                "action_admission": "permit",
                "visibility": "permit",
                "marking_authorization": "permit",
                "declassification": "not-applicable",
                "backend_support": "permit",
                "transformation_validity": "not-applicable",
            },
            "disposition": "permit",
            "reason_code": "policy-satisfied",
            "required_evidence_refs": ["evidence-requirement:crossing-decision"],
            "effective_order": 11,
        }
    )
    for field in ("request_id", "requested_operation", "action_or_projection_ref"):
        del decision_payload["occurrence"][field]
    if denied:
        decision_payload["occurrence"]["gates"]["caller_authorization"] = "deny"
        decision_payload["occurrence"]["disposition"] = "deny"
    decision = ParticipantCrossingOccurrenceModel.model_validate(decision_payload)
    subject = ParticipantCrossingSubjectReferenceModel.model_validate(request.occurrence.subject)
    policy = ParticipantCrossingPolicyReferenceModel.model_validate(request.occurrence.policy)
    return [request, decision], subject, policy


def _context_relation_payload() -> dict[str, object]:
    payload = _relation_payload()
    argument_subject = payload["labels"][1]["subject"]
    argument_subject["subject_ref"] = "proposal.1:target"
    payload["derivations"][0]["inputs"][0]["subject"] = argument_subject
    payload["derivations"][0]["predecessor_refs"] = sorted(["proposal.1:target", "fact-version.1"])
    for label in payload["labels"][1:]:
        label["influence_refs"] = sorted(
            {
                *(
                    "proposal.1:target" if value == "action-proposal.1:target" else value
                    for value in label["influence_refs"]
                ),
                "control-occurrence.proposal.1",
            }
        )
    common = {
        "profile": _profile_ref(),
        "policy": _policy(),
        "source_participant_address": "participants.red.operator",
        "source_episode_id": "episode-1",
        "target_participant_address": "participants.red.operator",
        "target_episode_id": "episode-1",
        "crossing_refs": [],
        "memory_predecessor_refs": [],
    }
    payload["bindings"] = [
        {
            **common,
            "kind": "runtime-fact",
            "binding_id": "binding.runtime-fact.1",
            "relation_target": {"target_kind": "label", "target_ref": "label.fact.1"},
            "plane_ref": "runtime-fact-plane.1",
            "declaration_ref": "fact.observed-host",
            "fact_version_ref": "fact-version.1",
            "sink_ref": "sink.scan-target",
            "binding_event_ref": "fact-binding.scan-0001.1",
        },
        {
            **common,
            "kind": "action-argument",
            "binding_id": "binding.action-argument.1",
            "relation_target": {"target_kind": "label", "target_ref": "label.argument.1"},
            "action_contract_address": "participant.action-contract.contain-host",
            "proposal_ref": "proposal.1",
            "normalized_argument_name": "target",
            "action_admission_ref": "action-admission.1",
        },
        {
            **common,
            "kind": "participant-control",
            "binding_id": "binding.participant-control.1",
            "relation_target": {"target_kind": "label", "target_ref": "label.argument.1"},
            "event_id": "control-occurrence.proposal.1",
            "occurrence_kind": "proposal",
            "occurrence_revision": 1,
            "participant_address": "participants.red.operator",
            "episode_id": "episode-1",
            "controller_ref": "controller.human.red",
            "authority_basis_refs": ["authority:red-team"],
            "control_policy_revision": "policy-v3",
            "occurrence_identity_ref": "proposal.1",
            "related_occurrence_refs": [],
            "predecessor_event_refs": [],
        },
        {
            **common,
            "kind": "participant-crossing",
            "binding_id": "binding.participant-crossing.1",
            "relation_target": {"target_kind": "sink-decision", "target_ref": "sink-decision.1"},
            "event_id": "crossing-occurrence.decided.1",
            "stage": "decided",
            "stage_identity_ref": "crossing-decision.1",
            "related_stage_refs": ["crossing-request.1"],
            "participant_address": "participants.red.operator",
            "episode_id": "episode-1",
            "subject_kind": "participant-control-occurrence",
            "subject_contract_id": "participant-control-occurrence-v1",
            "subject_ref": "control-occurrence.proposal.1",
            "subject_revision": "1",
            "crossing_policy_id": "participant-crossing-policy:red",
            "crossing_policy_revision": "revision-3",
            "crossing_policy_digest": "sha256:" + "a" * 64,
            "crossing_policy_decision_ref": "participant-crossing-policy-decision:red:episode-1:8",
            "crossing_decision_cut_ref": "participant-policy-cut:red:episode-1:8",
            "predecessor_event_refs": ["crossing-occurrence.requested.1"],
        },
    ]
    return payload


def _validation_context(*, crossing_denied: bool = False) -> ParticipantFlowControlValidationContext:
    profile = load_participant_boundary_flow_policy_profile(PROFILE_ID)
    relation = ParticipantFlowControlRelationModel.model_validate(_context_relation_payload())
    selection, admission = _action_selection_and_admission()
    control, declaration = _control_record_and_declaration()
    crossing_records, crossing_subject, crossing_policy = _crossing_records(denied=crossing_denied)
    sink = ParticipantFlowSinkCoordinate(
        sink_kind=relation.sink_decisions[0].sink.sink_kind,
        sink_ref=relation.sink_decisions[0].sink.sink_ref,
        destination_ref=relation.sink_decisions[0].sink.destination_ref,
        audience_scope_ref=relation.sink_decisions[0].sink.audience_scope_ref,
    )
    return ParticipantFlowControlValidationContext(
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
        runtime_fact_planes={"runtime-fact-plane.1": _runtime_fact_plane()},
        action_selections={(selection.action_contract_address, selection.proposal_ref): selection},
        action_admissions={"action-admission.1": admission},
        action_admission_resolutions={
            "action-admission.1": ParticipantFlowActionAdmissionResolution(
                action_admission_ref="action-admission.1",
                participant_address="participants.red.operator",
                episode_id="episode-1",
                action_contract_address=admission.action_contract_address,
                action_instance_id=admission.action_instance_id,
                sink=sink,
                disposition=ParticipantFlowFinalDisposition.PERMIT,
            )
        },
        capability_resolutions={
            "capability-resolution.1": ParticipantFlowCapabilityResolution(
                capability_resolution_ref="capability-resolution.1",
                participant_address="participants.red.operator",
                episode_id="episode-1",
                sink=sink,
                disposition=ParticipantFlowFinalDisposition.PERMIT,
            )
        },
        history_head_resolutions=frozenset(
            {
                ParticipantFlowHistoryHeadResolution(
                    participant_address="participants.red.operator",
                    episode_id="episode-1",
                    sink=sink,
                    history_head_refs=("history-head:participant.1",),
                    disposition=ParticipantFlowFinalDisposition.PERMIT,
                )
            }
        ),
        control_records=(control,),
        control_declarations=(declaration,),
        control_known_targets=(),
        crossing_records=tuple(crossing_records),
        crossing_subjects=(crossing_subject,),
        crossing_policies=(crossing_policy,),
        known_evidence_refs=frozenset(
            {
                "evidence:crossing-1",
                "evidence-requirement:crossing-decision",
                *(f"evidence:{item['label_id']}" for item in _context_relation_payload()["labels"]),
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


def test_resolved_context_accepts_exact_incumbent_carriers_and_all_sink_conjuncts() -> None:
    relation = ParticipantFlowControlRelationModel.model_validate(_context_relation_payload())
    context = _validation_context()

    validate_participant_flow_control_resolved_context(relation, lambda _document, _scope: context)


@pytest.mark.parametrize("resolver", [None, lambda _document, _scope: None])
def test_resolved_context_requires_a_typed_trusted_resolver(resolver: object) -> None:
    relation = ParticipantFlowControlRelationModel.model_validate(_context_relation_payload())

    with pytest.raises(ValueError, match="context resolver is required|context did not resolve"):
        validate_participant_flow_control_resolved_context(relation, resolver)


def test_resolved_context_redacts_resolver_exceptions() -> None:
    relation = ParticipantFlowControlRelationModel.model_validate(_context_relation_payload())

    def resolver(_document: object, _scope: object) -> object:
        raise RuntimeError("sensitive caller-selected value")

    with pytest.raises(ValueError, match="context resolution failed") as exc_info:
        validate_participant_flow_control_resolved_context(relation, resolver)
    assert "sensitive caller-selected value" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_resolved_context_requires_exact_profile_rules() -> None:
    payload = _context_relation_payload()
    payload["derivations"][0]["rule_ref"] = "caller-selected:weak-join"
    relation = ParticipantFlowControlRelationModel.model_validate(payload)

    with pytest.raises(ValueError, match="exact profile derivation rule"):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: _validation_context(),
        )


def test_resolved_context_requires_trusted_source_labels_policy_cuts_and_release_authority() -> None:
    payload = _context_relation_payload()
    payload["labels"][0]["subject"]["subject_revision"] = "2"
    payload["derivations"][0]["inputs"][1]["subject"]["subject_revision"] = "2"
    relation = ParticipantFlowControlRelationModel.model_validate(payload)
    with pytest.raises(ValueError, match="trusted source label"):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: _validation_context(),
        )

    payload = _context_relation_payload()
    for family in ("labels", "derivations", "releases", "sink_decisions", "bindings"):
        for record in payload[family]:
            record["policy"]["decision_cut_revision"] = "caller-selected-cut"
    relation = ParticipantFlowControlRelationModel.model_validate(payload)
    with pytest.raises(ValueError, match="trusted policy cut"):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: _validation_context(),
        )

    payload = _context_relation_payload()
    payload["releases"][0]["authority_revision"] = "caller-selected-authority"
    relation = ParticipantFlowControlRelationModel.model_validate(payload)
    with pytest.raises(ValueError, match="exact release authority"):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: _validation_context(),
        )


def test_final_sink_disposition_conjoins_coordinate_and_api_423_results() -> None:
    payload = _context_relation_payload()
    payload["sink_decisions"][0]["final_disposition"] = "deny"
    payload["sink_decisions"][0]["reason_code"] = "incumbent-crossing-denied"
    relation = ParticipantFlowControlRelationModel.model_validate(payload)

    validate_participant_flow_control_resolved_context(
        relation,
        lambda _document, _scope: _validation_context(crossing_denied=True),
    )
    with pytest.raises(ValueError, match="exact final disposition"):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: _validation_context(),
        )

    permit_relation = ParticipantFlowControlRelationModel.model_validate(_context_relation_payload())
    with pytest.raises(ValueError, match="exact final disposition"):
        validate_participant_flow_control_resolved_context(
            permit_relation,
            lambda _document, _scope: _validation_context(crossing_denied=True),
        )


def test_final_sink_requires_exact_scoped_capability_and_history_resolution() -> None:
    relation = ParticipantFlowControlRelationModel.model_validate(_context_relation_payload())
    context = _validation_context()
    admission = context.action_admission_resolutions["action-admission.1"]
    mismatched_admission = replace(
        context,
        action_admission_resolutions={"action-admission.1": replace(admission, episode_id="episode-other")},
    )
    with pytest.raises(ValueError, match="action admission"):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: mismatched_admission,
        )

    missing_capability = replace(_validation_context(), capability_resolutions={})

    with pytest.raises(ValueError, match="capability resolution"):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: missing_capability,
        )

    capability = context.capability_resolutions["capability-resolution.1"]
    mismatched_capability = replace(
        context,
        capability_resolutions={
            "capability-resolution.1": replace(capability, participant_address="participants.other")
        },
    )
    with pytest.raises(ValueError, match="capability resolution"):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: mismatched_capability,
        )

    history = next(iter(context.history_head_resolutions))
    mismatched_history = replace(
        context,
        history_head_resolutions=frozenset({replace(history, episode_id="episode-other")}),
    )
    with pytest.raises(ValueError, match="expected history head"):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: mismatched_history,
        )


@pytest.mark.parametrize(
    ("context_field", "disposition"),
    [
        ("action_admission_resolutions", ParticipantFlowFinalDisposition.DENY),
        ("capability_resolutions", ParticipantFlowFinalDisposition.UNSUPPORTED),
        ("history_head_resolutions", ParticipantFlowFinalDisposition.STALE),
    ],
)
def test_final_sink_conjoins_every_incumbent_decision_state(
    context_field: str,
    disposition: ParticipantFlowFinalDisposition,
) -> None:
    context = _validation_context()
    resolutions = getattr(context, context_field)
    if isinstance(resolutions, dict):
        denied = {key: replace(value, disposition=disposition) for key, value in resolutions.items()}
    else:
        denied = frozenset(replace(value, disposition=disposition) for value in resolutions)
    denied_context = replace(context, **{context_field: denied})

    permit_relation = ParticipantFlowControlRelationModel.model_validate(_context_relation_payload())
    with pytest.raises(ValueError, match="exact final disposition"):
        validate_participant_flow_control_resolved_context(
            permit_relation,
            lambda _document, _scope: denied_context,
        )

    payload = _context_relation_payload()
    payload["sink_decisions"][0]["final_disposition"] = disposition.value
    relation = ParticipantFlowControlRelationModel.model_validate(payload)
    validate_participant_flow_control_resolved_context(
        relation,
        lambda _document, _scope: denied_context,
    )


@pytest.mark.parametrize(
    ("binding_index", "field", "value", "message"),
    [
        (0, "plane_ref", "runtime-fact-plane.missing", "runtime fact binding plane must resolve"),
        (1, "action_admission_ref", "action-admission.missing", "participant action admission must resolve"),
        (2, "occurrence_kind", "handoff", "control occurrence"),
        (3, "crossing_policy_revision", "revision-stale", "crossing occurrence"),
    ],
)
def test_resolved_context_rejects_unknown_stale_or_mismatched_incumbent_bindings(
    binding_index: int,
    field: str,
    value: str,
    message: str,
) -> None:
    payload = _context_relation_payload()
    payload["bindings"][binding_index][field] = value
    relation = ParticipantFlowControlRelationModel.model_validate(payload)

    with pytest.raises(ValueError, match=message):
        validate_participant_flow_control_resolved_context(
            relation,
            lambda _document, _scope: _validation_context(),
        )


def test_cross_participant_binding_requires_boundary_memory_and_preserved_influence() -> None:
    payload = _context_relation_payload()
    binding = payload["bindings"][2]
    binding["target_participant_address"] = "participants.blue.operator"
    payload["bindings"][1]["target_participant_address"] = "participants.blue.operator"
    payload["labels"][1]["subject"]["participant_address"] = "participants.blue.operator"
    payload["derivations"][0]["inputs"][0]["subject"]["participant_address"] = "participants.blue.operator"

    with pytest.raises(ValidationError, match="crossing and memory predecessor refs"):
        ParticipantFlowControlRelationModel.model_validate(payload)

    binding["crossing_refs"] = ["crossing-occurrence.handoff.1"]
    binding["memory_predecessor_refs"] = ["history-head:source.1"]
    payload["bindings"][1]["crossing_refs"] = ["crossing-occurrence.handoff.1"]
    payload["bindings"][1]["memory_predecessor_refs"] = ["history-head:source.1"]
    payload["labels"][1]["influence_refs"].remove("control-occurrence.proposal.1")
    with pytest.raises(ValidationError, match="erase its upstream influence"):
        ParticipantFlowControlRelationModel.model_validate(payload)


def test_schema_valid_relation_without_context_is_not_accepted_as_trusted() -> None:
    payload = _context_relation_payload()

    diagnostics = validate_contract_payload("participant-flow-control-relation-v1", payload)

    assert {item.code for item in diagnostics} == {"conformance.semantic-context-required"}


@pytest.mark.parametrize(
    ("contract_id", "schema_directory", "model"),
    [
        (
            "participant-boundary-flow-policy-v1",
            "profiles",
            ParticipantBoundaryFlowPolicyProfileModel,
        ),
        (
            "participant-flow-control-relation-v1",
            "participant-runtime",
            ParticipantFlowControlRelationModel,
        ),
    ],
)
def test_flow_contract_schemas_fixtures_bundle_and_conformance_are_published(
    contract_id: str,
    schema_directory: str,
    model: type,
) -> None:
    schema = schema_bundle()[contract_id]
    published_path = REPO_ROOT / "contracts" / "schemas" / schema_directory / f"{contract_id}.json"
    assert json.loads(published_path.read_text(encoding="utf-8")) == schema
    assert schema["additionalProperties"] is False

    fixture_root = REPO_ROOT / "contracts" / "fixtures" / schema_directory / contract_id
    valid_paths = sorted((fixture_root / "valid").glob("*.json"))
    invalid_paths = sorted((fixture_root / "invalid").glob("*.json"))
    assert valid_paths
    assert invalid_paths
    validator = Draft202012Validator(schema)
    for path in valid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(payload)
        model.model_validate(payload)
    for path in invalid_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(validator.iter_errors(payload))
        with pytest.raises(ValidationError):
            model.model_validate(payload)

    assert contract_id in supported_contract_ids()


def test_relation_conformance_strength_requires_context_and_accepts_the_trusted_resolver() -> None:
    payload = _context_relation_payload()

    assert contract_validation_strength("participant-flow-control-relation-v1") == "structural-context-required"
    assert not validate_contract_payload(
        "participant-flow-control-relation-v1",
        payload,
        flow_control_context_resolver=lambda _document, _scope: _validation_context(),
    )


def test_flow_control_closed_vocabularies_have_one_concept_authority() -> None:
    catalog = load_controlled_vocabulary_catalog()
    expected = {
        "participant-flow-label-resolution-statuses": {value.value for value in ParticipantFlowLabelResolutionStatus},
        "participant-flow-subject-kinds": {value.value for value in ParticipantFlowSubjectKind},
        "participant-flow-release-kinds": {value.value for value in ParticipantFlowReleaseKind},
        "participant-flow-coordinate-results": {value.value for value in ParticipantFlowCoordinateResult},
        "participant-flow-final-dispositions": {value.value for value in ParticipantFlowFinalDisposition},
        "participant-flow-sink-kinds": {value.value for value in ParticipantFlowSinkKind},
        "participant-flow-binding-kinds": {value.value for value in ParticipantFlowBindingKind},
        "participant-flow-relation-target-kinds": {value.value for value in ParticipantFlowRelationTargetKind},
    }

    for vocabulary_id, terms in expected.items():
        vocabulary = catalog.vocabularies[vocabulary_id]
        assert vocabulary.extension_policy == "closed"
        assert set(vocabulary.terms) == terms
