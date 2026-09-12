"""ACT-604 dynamic participant information-state contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_conformance.conformance import _semantic_diagnostics, validate_contract_payload
from raes_contracts.contracts import (
    ParticipantContextViewModel,
    ParticipantDecisionSurfaceV2Model,
    ParticipantInformationReconstructionProfileModel,
    ParticipantInformationStateRecordModel,
    ParticipantInformationStateSourceCoordinate,
    ParticipantInformationStateValidationContext,
    ParticipantObservationEnvelopeModel,
    schema_bundle,
    validate_participant_information_state_context,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot, RuntimeSnapshotEnvelope
from raes_runtime.backend_calls import _BackendCallContext, _call_backend_apply, _RealizationApplyContext
from raes_runtime.control_plane_api_models import _snapshot_model
from raes_runtime.control_plane_store import (
    _require_expected_history_heads,
    _snapshot_from_payload,
    _snapshot_payload,
)
from raes_runtime.control_plane_store_local import _participant_transition_count
from raes_runtime.operational_apparatus import _runtime_surface_summary
from raes_runtime.participant_result_contracts import (
    participant_runtime_history_transition_diagnostics,
    participant_runtime_state_contract_diagnostics,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
OBSERVATION_FIXTURE = (
    REPO_ROOT
    / "contracts"
    / "fixtures"
    / "participant-runtime"
    / "participant-observation-envelope-v1"
    / "valid"
    / "rl-observation-only.json"
)
CONTEXT_FIXTURE = (
    REPO_ROOT
    / "contracts"
    / "fixtures"
    / "control-plane"
    / "participant-context-view-v1"
    / "valid"
    / "network-posture-context.json"
)
INFORMATION_STATE_FIXTURE_ROOT = (
    REPO_ROOT / "contracts" / "fixtures" / "participant-runtime" / "participant-information-state-record-v1"
)
RECONSTRUCTION_PROFILE_FIXTURE_ROOT = (
    REPO_ROOT / "contracts" / "fixtures" / "profiles" / "participant-information-reconstruction-profile-v1"
)
DECISION_SURFACE_FIXTURE = (
    REPO_ROOT
    / "contracts"
    / "fixtures"
    / "control-plane"
    / "participant-decision-surface-v2"
    / "valid"
    / "projected-initial.json"
)
SOURCE_FIXTURES = {
    "participant-context-view-v1": (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "control-plane"
        / "participant-context-view-v1"
        / "valid"
        / "network-posture-context.json"
    ),
    "participant-shared-state-record-v1": (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "participant-runtime"
        / "participant-shared-state-record-v1"
        / "valid"
        / "serialized-service-state-commit.json"
    ),
    "participant-behavior-history-event-stream-v1": (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "control-plane"
        / "participant-behavior-history-event-stream-v1"
        / "valid"
        / "terminal-observation.json"
    ),
    "participant-episode-state-envelope-v1": (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "control-plane"
        / "participant-episode-state-envelope-v1"
        / "valid"
        / "initialized.json"
    ),
}


def _observation(**overrides: object) -> dict[str, object]:
    payload = json.loads(OBSERVATION_FIXTURE.read_text(encoding="utf-8"))
    payload.update(overrides)
    return payload


def _profile(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "participant-information-reconstruction-profile/v1",
        "profile_id": "occurrence-prefix-evidence-v1",
        "title": "Occurrence-prefix evidence reconstruction",
        "description": "Validates an exact participant-visible occurrence prefix and proof digest.",
        "algorithm_id": "raes.occurrence-prefix-evidence",
        "algorithm_version": "1.0.0",
        "information_state_schema_version": "1.0.0",
        "projection_version": "projection.blue.v1",
        "determinism_basis": "exact_occurrence_prefix_and_proof_digest",
        "accepted_input_contracts": ["participant-observation-envelope-v1"],
        "accepted_order_semantics": ["sequence_prefix", "causal_frontier"],
        "fixture_format": "participant-information-reconstruction-fixture/v1",
        "proof_artifact_format": "participant-information-reconstruction-proof/v1",
        "normative_artifact_ref": "specs/formal/participant-runtime/README.md",
        "normative_artifact_digest": "sha256:" + "1" * 64,
    }
    payload.update(overrides)
    return payload


def _information_state(**overrides: object) -> dict[str, object]:
    payload = _observation(
        event_id="information-state-blue-43",
        schema_name="raes.participant_runtime.information_state",
        schema_version="1.0.0",
        event_type="participant_information_state",
    )
    for field_name in (
        "observation_ref",
        "phase_ref",
        "delivery_basis",
        "delivery_point_ref",
        "delivered_at",
        "action_observation_history_ref",
        "hidden_state_refs",
        "centralized_state_refs",
        "loss_descriptor",
        "stochastic_context",
        "noise_model_ref",
        "reconstruction_algorithm_ref",
        "reconstruction_proof_ref",
        "belief_support_ref",
        "redacted_field_refs",
    ):
        payload.pop(field_name, None)
    payload.update(
        {
            "information_state_ref": "information-state.blue.ep002.cut43",
            "information_state_digest": "sha256:" + "a" * 64,
            "payload_ref": "payloads.information-state.blue.ep002.cut43",
            "state_cut": {
                "cut_kind": "sequence_prefix",
                "cut_ref": "cut.blue.ep002.43",
                "history_domain": "participant_behavior_history",
                "order_model": "backend_serialized_order",
                "anchor_event_ref": "evt-blue-43",
                "anchor_order": 43,
                "history_prefix_length": 44,
                "predecessor_event_refs": ["evt-blue-42"],
            },
            "participant_memory_scope": "episode_local_reset",
            "memory_reset_authority_ref": "episode-reset.blue.ep002",
            "audience_scope_ref": "audiences.participant.blue",
            "projection_version": "projection.blue.v1",
            "projection_policy_revision": "projection.blue.v1",
            "redaction_policy_revision": "redaction.blue.v1",
            "information_guarantee": "history_consistent",
            "source_refs": [
                {
                    "contract_id": "participant-observation-envelope-v1",
                    "ref": "observations.blue.local.telemetry.43",
                    "relation": "observed",
                }
            ],
            "occurrence_history_ref": "history.blue.ep002.prefix43",
            "reconstruction_profile_ref": "occurrence-prefix-evidence-v1",
            "reconstruction_algorithm_id": "raes.occurrence-prefix-evidence",
            "reconstruction_algorithm_version": "1.0.0",
            "reconstruction_proof_ref": "proofs.information-state.blue.ep002.cut43",
            "reconstructed_state_digest": "sha256:" + "a" * 64,
            "occurrence_order_witness_ref": None,
            "loss_disclosures": [],
            "predecessor_information_state_refs": [],
            "supersedes_information_state_ref": None,
        }
    )
    payload.update(overrides)
    return payload


def _resolved_context(
    record: ParticipantInformationStateRecordModel,
    *,
    observation: ParticipantObservationEnvelopeModel | None = None,
    proof_digest: str | None = None,
    source_cut_member: bool = True,
) -> ParticipantInformationStateValidationContext:
    resolved_observation = observation or ParticipantObservationEnvelopeModel.model_validate(
        _observation(
            information_guarantee="history_consistent",
            information_state_ref=record.information_state_ref,
            reconstruction_algorithm_ref=record.reconstruction_profile_ref,
            reconstruction_proof_ref=record.reconstruction_proof_ref,
        )
    )
    source_key = ("participant-observation-envelope-v1", resolved_observation.observation_ref)
    return ParticipantInformationStateValidationContext(
        occurrence_histories={record.occurrence_history_ref: [resolved_observation]},
        resolved_sources={source_key: resolved_observation},
        source_coordinates={
            source_key: _source_coordinate(
                record,
                state_cut=(
                    record.state_cut
                    if source_cut_member
                    else record.state_cut.model_copy(
                        update={
                            "anchor_order": record.state_cut.anchor_order - 1,
                            "history_prefix_length": record.state_cut.history_prefix_length - 1,
                        }
                    )
                ),
            )
        },
        proof_digests={
            record.reconstruction_proof_ref: proof_digest or record.information_state_digest,
        },
    )


def _source_coordinate(
    record: ParticipantInformationStateRecordModel,
    **overrides: object,
) -> ParticipantInformationStateSourceCoordinate:
    values: dict[str, object] = {
        "participant_address": record.participant_address,
        "episode_id": record.episode_id,
        "state_cut": record.state_cut,
        "audience_scope_ref": record.audience_scope_ref,
        "visibility_projection_ref": record.visibility_projection_ref,
        "projection_policy_revision": record.projection_policy_revision,
        "redaction_policy_ref": record.redaction_policy_ref,
        "redaction_policy_revision": record.redaction_policy_revision,
    }
    values.update(overrides)
    return ParticipantInformationStateSourceCoordinate(**values)


def _context_resolver(
    record: ParticipantInformationStateRecordModel,
    _scope: object | None = None,
) -> ParticipantInformationStateValidationContext:
    return _resolved_context(record)


@pytest.mark.parametrize("guarantee", ["history_consistent", "perfect_recall"])
def test_strong_observation_guarantees_require_reconstruction_authority(guarantee: str) -> None:
    payload = _observation(
        information_guarantee=guarantee,
        action_observation_history_ref=None,
        information_state_ref=None,
        reconstruction_algorithm_ref=None,
        reconstruction_proof_ref=None,
    )

    with pytest.raises(ValidationError, match="strong information guarantee requires"):
        ParticipantObservationEnvelopeModel.model_validate(payload)
    assert list(Draft202012Validator(schema_bundle()["participant-observation-envelope-v1"]).iter_errors(payload))


def test_lossy_observation_guarantee_requires_loss_disclosure() -> None:
    payload = _observation(
        information_guarantee="lossy_projection",
        loss_descriptor=None,
    )

    with pytest.raises(ValidationError, match="lossy_projection requires loss_descriptor"):
        ParticipantObservationEnvelopeModel.model_validate(payload)


def test_information_state_record_and_reconstruction_profile_are_closed_contracts() -> None:
    record = ParticipantInformationStateRecordModel.model_validate(_information_state())
    profile = ParticipantInformationReconstructionProfileModel.model_validate(_profile())

    assert record.information_state_ref == "information-state.blue.ep002.cut43"
    assert profile.profile_id == "occurrence-prefix-evidence-v1"

    invalid_record = _information_state(untrusted_fact_bag={"hidden_truth": True})
    with pytest.raises(ValidationError):
        ParticipantInformationStateRecordModel.model_validate(invalid_record)


def test_strong_information_state_requires_reconstruction_refs_and_matching_digest() -> None:
    missing_profile = _information_state(reconstruction_profile_ref=None)
    with pytest.raises(ValidationError, match="strong information state requires"):
        ParticipantInformationStateRecordModel.model_validate(missing_profile)
    assert list(
        Draft202012Validator(schema_bundle()["participant-information-state-record-v1"]).iter_errors(missing_profile)
    )

    mismatched_digest = _information_state(reconstructed_state_digest="sha256:" + "b" * 64)
    with pytest.raises(ValidationError, match="reconstructed_state_digest must equal"):
        ParticipantInformationStateRecordModel.model_validate(mismatched_digest)


def test_perfect_recall_information_state_requires_occurrence_order_witness() -> None:
    payload = _information_state(information_guarantee="perfect_recall")
    with pytest.raises(ValidationError, match="perfect_recall requires occurrence_order_witness_ref"):
        ParticipantInformationStateRecordModel.model_validate(payload)


def test_contextual_information_state_validation_resolves_profile_history_sources_and_proof() -> None:
    record = ParticipantInformationStateRecordModel.model_validate(_information_state())
    profile = ParticipantInformationReconstructionProfileModel.model_validate(_profile())
    observation = ParticipantObservationEnvelopeModel.model_validate(
        _observation(
            information_guarantee="history_consistent",
            information_state_ref=record.information_state_ref,
            reconstruction_algorithm_ref=profile.profile_id,
            reconstruction_proof_ref=record.reconstruction_proof_ref,
        )
    )

    validate_participant_information_state_context(
        record,
        reconstruction_profiles={profile.profile_id: profile},
        occurrence_histories={record.occurrence_history_ref: [observation]},
        resolved_sources={("participant-observation-envelope-v1", observation.observation_ref): observation},
        source_coordinates={
            ("participant-observation-envelope-v1", observation.observation_ref): _source_coordinate(record),
        },
        proof_digests={
            record.reconstruction_proof_ref: record.information_state_digest,
        },
    )


def test_contextual_information_state_validation_rejects_projection_mismatch() -> None:
    record = ParticipantInformationStateRecordModel.model_validate(_information_state())
    profile = ParticipantInformationReconstructionProfileModel.model_validate(
        _profile(projection_version="projection.red.v1")
    )

    with pytest.raises(ValueError, match="projection version"):
        validate_participant_information_state_context(
            record,
            reconstruction_profiles={profile.profile_id: profile},
            occurrence_histories={record.occurrence_history_ref: []},
            resolved_sources={},
            proof_digests={record.reconstruction_proof_ref: record.information_state_digest},
        )


def test_observation_only_information_state_does_not_claim_reconstruction() -> None:
    record = ParticipantInformationStateRecordModel.model_validate(
        _information_state(
            information_guarantee="observation_only",
            occurrence_history_ref=None,
            reconstruction_profile_ref=None,
            reconstruction_algorithm_id=None,
            reconstruction_algorithm_version=None,
            reconstruction_proof_ref=None,
            reconstructed_state_digest=None,
        )
    )
    observation = ParticipantObservationEnvelopeModel.model_validate(_observation())

    validate_participant_information_state_context(
        record,
        reconstruction_profiles={},
        occurrence_histories={},
        resolved_sources={("participant-observation-envelope-v1", observation.observation_ref): observation},
        proof_digests={},
        source_coordinates={
            ("participant-observation-envelope-v1", observation.observation_ref): _source_coordinate(record),
        },
    )


def test_every_typed_source_must_resolve_inside_the_exact_cut_and_policy_coordinate() -> None:
    record = ParticipantInformationStateRecordModel.model_validate(
        _information_state(
            information_guarantee="observation_only",
            occurrence_history_ref=None,
            reconstruction_profile_ref=None,
            reconstruction_algorithm_id=None,
            reconstruction_algorithm_version=None,
            reconstruction_proof_ref=None,
            reconstructed_state_digest=None,
        )
    )
    after_cut = ParticipantObservationEnvelopeModel.model_validate(_observation(sequence_number=44))
    source_key = ("participant-observation-envelope-v1", after_cut.observation_ref)
    source_coordinate = _source_coordinate(record)

    with pytest.raises(ValueError, match="exact sequence cut"):
        validate_participant_information_state_context(
            record,
            reconstruction_profiles={},
            occurrence_histories={},
            resolved_sources={source_key: after_cut},
            source_coordinates={source_key: source_coordinate},
            proof_digests={},
        )

    cut_observation = after_cut.model_copy(update={"sequence_number": 43})
    earlier_cut = record.state_cut.model_copy(update={"anchor_order": 42, "history_prefix_length": 43})
    cut_coordinate = _source_coordinate(record, state_cut=earlier_cut)
    with pytest.raises(ValueError, match="cut membership"):
        validate_participant_information_state_context(
            record,
            reconstruction_profiles={},
            occurrence_histories={},
            resolved_sources={source_key: cut_observation},
            source_coordinates={source_key: cut_coordinate},
            proof_digests={},
        )

    wrong_policy = after_cut.model_copy(
        update={
            "sequence_number": 43,
            "redaction_policy_ref": "redaction.other.v1",
        }
    )
    with pytest.raises(ValueError, match="redaction policy"):
        validate_participant_information_state_context(
            record,
            reconstruction_profiles={},
            occurrence_histories={},
            resolved_sources={source_key: wrong_policy},
            source_coordinates={source_key: source_coordinate},
            proof_digests={},
        )


@pytest.mark.parametrize(
    ("coordinate_field", "wrong_value", "error"),
    [
        ("participant_address", "participants.other", "participant or episode coordinate"),
        ("episode_id", "episode-other", "participant or episode coordinate"),
        ("audience_scope_ref", "audiences.other", "audience scope coordinate"),
        ("visibility_projection_ref", "projection.other", "visibility projection coordinate"),
        ("projection_policy_revision", "projection-policy.other", "projection policy revision coordinate"),
        ("redaction_policy_ref", "redaction.other", "redaction policy coordinate"),
        ("redaction_policy_revision", "redaction-revision.other", "redaction policy revision coordinate"),
    ],
)
def test_source_governed_coordinate_rejects_each_identity_and_policy_mismatch(
    coordinate_field: str,
    wrong_value: str,
    error: str,
) -> None:
    record = ParticipantInformationStateRecordModel.model_validate(
        _information_state(
            information_guarantee="observation_only",
            occurrence_history_ref=None,
            reconstruction_profile_ref=None,
            reconstruction_algorithm_id=None,
            reconstruction_algorithm_version=None,
            reconstruction_proof_ref=None,
            reconstructed_state_digest=None,
        )
    )
    observation = ParticipantObservationEnvelopeModel.model_validate(_observation(sequence_number=43))
    source_key = ("participant-observation-envelope-v1", observation.observation_ref)
    mismatched_coordinate = _source_coordinate(record, **{coordinate_field: wrong_value})

    with pytest.raises(ValueError, match=error):
        validate_participant_information_state_context(
            record,
            reconstruction_profiles={},
            occurrence_histories={},
            resolved_sources={source_key: observation},
            source_coordinates={source_key: mismatched_coordinate},
            proof_digests={},
        )


@pytest.mark.parametrize(
    ("contract_id", "source_ref", "relation", "error"),
    [
        (
            "participant-context-view-v1",
            "views.context.participants.blue.rl.network-posture.0001",
            "derived",
            "context-view source coordinate",
        ),
        (
            "participant-shared-state-record-v1",
            "state-web01-http-rev8",
            "observed",
            "shared-state source coordinate",
        ),
        (
            "participant-behavior-history-event-stream-v1",
            "history.participant.alice.ep-0001",
            "observed",
            "behavior-history source coordinate",
        ),
        (
            "participant-episode-state-envelope-v1",
            "ep-0001",
            "derived",
            "episode-state source coordinate",
        ),
    ],
)
def test_each_typed_source_validator_rejects_cross_participant_resolution(
    contract_id: str,
    source_ref: str,
    relation: str,
    error: str,
) -> None:
    record = ParticipantInformationStateRecordModel.model_validate(
        _information_state(
            information_guarantee="observation_only",
            source_refs=[{"contract_id": contract_id, "ref": source_ref, "relation": relation}],
            occurrence_history_ref=None,
            reconstruction_profile_ref=None,
            reconstruction_algorithm_id=None,
            reconstruction_algorithm_version=None,
            reconstruction_proof_ref=None,
            reconstructed_state_digest=None,
        )
    )
    resolved = json.loads(SOURCE_FIXTURES[contract_id].read_text(encoding="utf-8"))
    if isinstance(resolved, list):
        resolved[0]["participant_address"] = "participants.other"
    else:
        resolved["participant_address"] = "participants.other"
    source_key = (contract_id, source_ref)
    source_coordinate = _source_coordinate(record)

    with pytest.raises(ValueError, match=error):
        validate_participant_information_state_context(
            record,
            reconstruction_profiles={},
            occurrence_histories={},
            resolved_sources={source_key: resolved},
            source_coordinates={source_key: source_coordinate},
            proof_digests={},
        )


def test_strong_information_state_cannot_collapse_distinct_occurrences() -> None:
    record = ParticipantInformationStateRecordModel.model_validate(_information_state())
    profile = ParticipantInformationReconstructionProfileModel.model_validate(_profile())
    first = ParticipantObservationEnvelopeModel.model_validate(
        _observation(
            information_guarantee="history_consistent",
            information_state_ref=record.information_state_ref,
            reconstruction_algorithm_ref=profile.profile_id,
            reconstruction_proof_ref=record.reconstruction_proof_ref,
        )
    )
    second = ParticipantObservationEnvelopeModel.model_validate(
        _observation(
            event_id="obs-blue-42-contradictory",
            observation_ref="observations.blue.local.telemetry.42-contradictory",
            sequence_number=42,
            information_guarantee="history_consistent",
            information_state_ref=record.information_state_ref,
            reconstruction_algorithm_ref=profile.profile_id,
            reconstruction_proof_ref=record.reconstruction_proof_ref,
        )
    )

    with pytest.raises(ValueError, match="every occurrence"):
        validate_participant_information_state_context(
            record,
            reconstruction_profiles={profile.profile_id: profile},
            occurrence_histories={record.occurrence_history_ref: [first, second]},
            resolved_sources={
                ("participant-observation-envelope-v1", first.observation_ref): first,
                ("participant-observation-envelope-v1", second.observation_ref): second,
            },
            proof_digests={record.reconstruction_proof_ref: record.information_state_digest},
        )


@pytest.mark.parametrize(
    ("coordinate_field", "wrong_value", "error"),
    [
        ("participant_address", "participants.other", "identity"),
        ("episode_id", "episode-other", "identity"),
        ("state_cut", None, "cut"),
        ("audience_scope_ref", "audiences.other", "audience scope"),
        ("projection_policy_revision", "projection-policy.other", "projection revision"),
        ("visibility_projection_ref", "projection.other", "visibility projection"),
        ("participant_memory_scope", "episode_local_reset", "memory scope"),
        ("memory_reset_authority_ref", "episode-reset.other", "reset authority"),
        ("redaction_policy_ref", "redaction.other", "redaction policy"),
    ],
)
def test_decision_surface_information_state_join_enforces_every_coordinate(
    coordinate_field: str,
    wrong_value: str | None,
    error: str,
) -> None:
    surface = ParticipantDecisionSurfaceV2Model.model_validate_json(
        DECISION_SURFACE_FIXTURE.read_text(encoding="utf-8")
    )
    view = surface.participant_view
    assurance = surface.assurance
    history_ref = "history.red.episode-1.initial"
    observation_ref = "observations.red.initial"
    record = ParticipantInformationStateRecordModel.model_validate(
        _information_state(
            participant_address=view.participant_address,
            episode_id=view.episode_id,
            information_state_ref=view.information_state_ref,
            state_cut=assurance.derivation_anchor.state_cut.model_dump(mode="json"),
            participant_memory_scope=assurance.participant_memory_scope,
            memory_reset_authority_ref=assurance.memory_reset_authority_ref,
            audience_scope_ref=assurance.audience_scope_ref,
            visibility_projection_ref=assurance.visibility_projection_ref,
            redaction_policy_ref=view.redaction_policy_ref,
            projection_policy_revision=assurance.projection_policy_revision,
            source_refs=[
                {
                    "contract_id": "participant-observation-envelope-v1",
                    "ref": observation_ref,
                    "relation": "observed",
                }
            ],
            occurrence_history_ref=history_ref,
        )
    )
    profile = ParticipantInformationReconstructionProfileModel.model_validate(_profile())
    observation = ParticipantObservationEnvelopeModel.model_validate(
        _observation(
            participant_address=view.participant_address,
            episode_id=view.episode_id,
            sequence_number=1,
            observation_ref=observation_ref,
            action_observation_history_ref=history_ref,
            visibility_projection_ref=assurance.visibility_projection_ref,
            redaction_policy_ref=view.redaction_policy_ref,
            information_guarantee="history_consistent",
            information_state_ref=record.information_state_ref,
            reconstruction_algorithm_ref=profile.profile_id,
            reconstruction_proof_ref=record.reconstruction_proof_ref,
        )
    )
    context = {
        "reconstruction_profiles": {profile.profile_id: profile},
        "occurrence_histories": {history_ref: [observation]},
        "resolved_sources": {("participant-observation-envelope-v1", observation_ref): observation},
        "source_coordinates": {("participant-observation-envelope-v1", observation_ref): _source_coordinate(record)},
        "proof_digests": {record.reconstruction_proof_ref: record.information_state_digest},
        "decision_surfaces": [surface],
    }

    validate_participant_information_state_context(record, **context)

    if coordinate_field in {"participant_address", "episode_id", "redaction_policy_ref"}:
        mismatched_surface = surface.model_copy(
            update={"participant_view": view.model_copy(update={coordinate_field: wrong_value})}
        )
    elif coordinate_field == "state_cut":
        mismatched_cut = assurance.derivation_anchor.state_cut.model_copy(
            update={"anchor_order": assurance.derivation_anchor.state_cut.anchor_order + 1}
        )
        mismatched_anchor = assurance.derivation_anchor.model_copy(update={"state_cut": mismatched_cut})
        mismatched_surface = surface.model_copy(
            update={"assurance": assurance.model_copy(update={"derivation_anchor": mismatched_anchor})}
        )
    else:
        mismatched_surface = surface.model_copy(
            update={"assurance": assurance.model_copy(update={coordinate_field: wrong_value})}
        )
    mismatched_context = dict(context)
    mismatched_context["decision_surfaces"] = [mismatched_surface]

    with pytest.raises(ValueError, match=error):
        validate_participant_information_state_context(record, **mismatched_context)


def test_schema_bundle_and_conformance_publish_information_state_contracts() -> None:
    bundle = schema_bundle()

    assert "participant-information-state-record-v1" in bundle
    assert "participant-information-reconstruction-profile-v1" in bundle
    assert validate_contract_payload("participant-information-state-record-v1", _information_state())
    assert not validate_contract_payload(
        "participant-information-state-record-v1",
        _information_state(),
        information_state_context_resolver=_context_resolver,
    )
    assert not validate_contract_payload("participant-information-reconstruction-profile-v1", _profile())


def test_context_view_accepts_information_state_as_a_closed_source_layer() -> None:
    payload = json.loads(CONTEXT_FIXTURE.read_text(encoding="utf-8"))
    source = payload["source_layers"][0]
    prior_ref = source["ref"]
    source["source_layer"] = "participant_information_state"
    source["ref"] = "information-state.blue.ep002.cut43"
    payload["derived_from_refs"] = [
        "information-state.blue.ep002.cut43" if ref == prior_ref else ref for ref in payload["derived_from_refs"]
    ]

    model = ParticipantContextViewModel.model_validate(payload)

    assert model.source_layers[0].source_layer == "participant_information_state"


def test_reconstruction_profile_loader_is_closed_and_path_safe() -> None:
    from raes_contracts.participant_information_reconstruction_profiles import (
        load_participant_information_reconstruction_profile,
        participant_information_reconstruction_profile_path,
    )

    profile = load_participant_information_reconstruction_profile("occurrence-prefix-evidence-v1")

    assert profile.profile_id == "occurrence-prefix-evidence-v1"
    assert participant_information_reconstruction_profile_path(profile.profile_id).is_file()
    with pytest.raises(ValueError, match="portable SDL identifier"):
        participant_information_reconstruction_profile_path("../../outside")
    with pytest.raises(ValueError, match="unsupported participant information reconstruction profile"):
        participant_information_reconstruction_profile_path("unknown-profile-v1")


def test_runtime_snapshot_round_trips_first_class_information_state_history() -> None:
    record = _information_state()
    snapshot = RuntimeSnapshot(
        information_state_history={record["participant_address"]: [record]},
    )

    payload = _snapshot_payload(snapshot)
    restored = _snapshot_from_payload(payload)

    assert payload["information_state_history"][record["participant_address"]][0] == record
    assert restored.information_state_history == snapshot.information_state_history
    assert not validate_contract_payload("runtime-snapshot-v1", payload)


def test_information_state_history_participates_in_expected_heads_and_restart_count() -> None:
    record = _information_state()
    participant = str(record["participant_address"])
    snapshot = RuntimeSnapshot(information_state_history={participant: [record]})

    _require_expected_history_heads(
        snapshot,
        {f"information_state_history:{participant}": str(record["event_id"])},
    )

    assert _participant_transition_count(snapshot) == 1


def test_information_state_snapshot_semantics_reject_key_mismatch_and_metadata_smuggling() -> None:
    record = _information_state()
    mismatched = RuntimeSnapshot(information_state_history={"participants.red.llm": [record]})
    smuggled = RuntimeSnapshot(metadata={"information_state_history": {"hidden": [record]}})

    mismatch_messages = [
        diagnostic.message for diagnostic in participant_runtime_state_contract_diagnostics(mismatched)
    ]
    smuggling_messages = [diagnostic.message for diagnostic in participant_runtime_state_contract_diagnostics(smuggled)]

    assert any("map key" in message and "participant_address" in message for message in mismatch_messages)
    assert any("must not contain 'information_state_history'" in message for message in smuggling_messages)


def test_information_state_history_is_append_only_across_backend_apply() -> None:
    original = _information_state()
    rewritten = _information_state(
        information_state_digest="sha256:" + "b" * 64,
        reconstructed_state_digest="sha256:" + "b" * 64,
    )
    participant = str(original["participant_address"])
    base_snapshot = RuntimeSnapshot(information_state_history={participant: [original]})

    def _backend_apply(_request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                information_state_history={participant: [rewritten]},
            ),
            changed_addresses=[participant],
        )

    result = _call_backend_apply(
        _backend_apply,
        object(),
        base_snapshot,
        address="runtime.participant-information-state",
        snapshot=base_snapshot,
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({participant})
        ),
    )

    assert result.success is False
    assert any("information_state_history must be append-only" in item.message for item in result.diagnostics)


def test_information_state_history_transition_rejects_removal() -> None:
    record = _information_state()
    participant = str(record["participant_address"])
    previous = RuntimeSnapshot(information_state_history={participant: [record]})

    diagnostics = participant_runtime_history_transition_diagnostics(previous, RuntimeSnapshot())

    assert any("information-state history was removed" in item.message for item in diagnostics)


@pytest.mark.parametrize(
    ("fixture_root", "model_type"),
    [
        (INFORMATION_STATE_FIXTURE_ROOT, ParticipantInformationStateRecordModel),
        (RECONSTRUCTION_PROFILE_FIXTURE_ROOT, ParticipantInformationReconstructionProfileModel),
    ],
)
def test_information_state_contract_fixture_corpora(
    fixture_root: Path,
    model_type: type[ParticipantInformationStateRecordModel] | type[ParticipantInformationReconstructionProfileModel],
) -> None:
    valid_paths = sorted((fixture_root / "valid").glob("*.json"))
    invalid_paths = sorted((fixture_root / "invalid").glob("*.json"))

    assert valid_paths
    assert invalid_paths
    for path in valid_paths:
        model_type.model_validate_json(path.read_text(encoding="utf-8"))
    for path in invalid_paths:
        invalid_payload = path.read_text(encoding="utf-8")
        with pytest.raises(ValidationError):
            model_type.model_validate_json(invalid_payload)


def test_runtime_snapshot_conformance_preserves_information_state_semantics() -> None:
    record = _information_state(predecessor_information_state_refs=["information-state.blue.ep002.missing"])
    participant = str(record["participant_address"])
    payload = _snapshot_payload(RuntimeSnapshot(information_state_history={participant: [record]}))

    diagnostics = _semantic_diagnostics("runtime-snapshot-v1", payload)

    assert any("predecessor_information_state_refs" in item.message for item in diagnostics)


def test_conformance_and_runtime_snapshot_acceptance_fail_closed_without_context() -> None:
    record = ParticipantInformationStateRecordModel.model_validate(_information_state())
    participant = str(record.participant_address)
    snapshot = RuntimeSnapshot(
        information_state_history={participant: [record.model_dump(mode="json")]},
    )
    payload = _snapshot_payload(snapshot)

    conformance = _semantic_diagnostics("runtime-snapshot-v1", payload)
    runtime = participant_runtime_state_contract_diagnostics(snapshot)

    assert any("context resolver is required" in item.message for item in conformance)
    assert any("context resolver is required" in item.message for item in runtime)
    assert not _semantic_diagnostics(
        "runtime-snapshot-v1",
        payload,
        information_state_context_resolver=_context_resolver,
    )
    assert not participant_runtime_state_contract_diagnostics(
        snapshot,
        information_state_context_resolver=_context_resolver,
    )


def test_backend_ingestion_rejects_unresolved_or_forged_new_information_state() -> None:
    record = ParticipantInformationStateRecordModel.model_validate(_information_state())
    participant = str(record.participant_address)

    def _backend_apply(_request: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries),
                information_state_history={participant: [record.model_dump(mode="json")]},
            ),
            changed_addresses=[participant],
        )

    without_context = _call_backend_apply(
        _backend_apply,
        object(),
        RuntimeSnapshot(),
        address="runtime.participant-information-state",
        snapshot=RuntimeSnapshot(),
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({participant})
        ),
    )

    def _forged_resolver(
        candidate: ParticipantInformationStateRecordModel,
        _scope: object | None = None,
    ) -> ParticipantInformationStateValidationContext:
        return _resolved_context(candidate, proof_digest="sha256:" + "b" * 64)

    forged = _call_backend_apply(
        _backend_apply,
        object(),
        RuntimeSnapshot(),
        address="runtime.participant-information-state",
        snapshot=RuntimeSnapshot(),
        call=_BackendCallContext(information_state_context_resolver=_forged_resolver),
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({participant})
        ),
    )
    accepted = _call_backend_apply(
        _backend_apply,
        object(),
        RuntimeSnapshot(),
        address="runtime.participant-information-state",
        snapshot=RuntimeSnapshot(),
        call=_BackendCallContext(information_state_context_resolver=_context_resolver),
        realization=_RealizationApplyContext(
            effect_owners=frozenset({"participant"}), effect_targets=frozenset({participant})
        ),
    )

    assert without_context.success is False
    assert forged.success is False
    assert accepted.success is True


def test_control_plane_snapshot_model_exposes_information_state_history() -> None:
    record = _information_state()
    participant = str(record["participant_address"])
    snapshot = RuntimeSnapshot(information_state_history={participant: [record]})

    model = _snapshot_model(RuntimeSnapshotEnvelope(snapshot=snapshot))

    assert model.information_state_history[participant][0].information_state_ref == record["information_state_ref"]


def test_operational_summary_counts_information_state_history_without_payloads() -> None:
    record = _information_state()
    participant = str(record["participant_address"])

    summary = _runtime_surface_summary(RuntimeSnapshot(information_state_history={participant: [record]}))

    assert summary["information_state_history"] == 1
    assert record["information_state_ref"] not in str(summary)
