"""API-406/407/408/411 participant backend-facing contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_contracts.contracts import (
    VIEW_SCOPE_PROJECTED_FIELDS,
    ParticipantBehaviorHistoryEventModel,
    ParticipantContextViewModel,
    ParticipantCrossingOccurrenceModel,
    ParticipantEpisodeHistoryEventModel,
    ParticipantEpisodeStateModel,
    ParticipantHistoryViewBehaviorEventModel,
    ParticipantHistoryViewEpisodeEventModel,
    ParticipantHistoryViewModel,
    ParticipantJointActionRecordModel,
    ParticipantLifecycleEventModel,
    ParticipantObservationEnvelopeModel,
    ParticipantOutcomeReportModel,
    ParticipantSharedStateRecordModel,
    ParticipantStatusViewEpisodeStateModel,
    ParticipantStatusViewModel,
    ParticipantTimeManagementContextModel,
)
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_ROOT = REPO_ROOT / "contracts" / "fixtures"

PARTICIPANT_RUNTIME_FIXTURE_MODELS = {
    "participant-lifecycle-event-v1": ParticipantLifecycleEventModel,
    "participant-observation-envelope-v1": ParticipantObservationEnvelopeModel,
    "participant-shared-state-record-v1": ParticipantSharedStateRecordModel,
    "participant-joint-action-record-v1": ParticipantJointActionRecordModel,
    "participant-time-management-context-v1": ParticipantTimeManagementContextModel,
    "participant-crossing-occurrence-v1": ParticipantCrossingOccurrenceModel,
    "participant-outcome-report-v1": ParticipantOutcomeReportModel,
}
CONTROL_PLANE_VIEW_FIXTURE_MODELS = {
    "participant-status-view-v1": ParticipantStatusViewModel,
    "participant-history-view-v1": ParticipantHistoryViewModel,
    "participant-context-view-v1": ParticipantContextViewModel,
}
FIXTURE_ROOTS_BY_CONTRACT = {
    **{contract_id: FIXTURES_ROOT / "participant-runtime" for contract_id in PARTICIPANT_RUNTIME_FIXTURE_MODELS},
    **{contract_id: FIXTURES_ROOT / "control-plane" for contract_id in CONTROL_PLANE_VIEW_FIXTURE_MODELS},
}
ALL_FIXTURE_MODELS = {**PARTICIPANT_RUNTIME_FIXTURE_MODELS, **CONTROL_PLANE_VIEW_FIXTURE_MODELS}

_ORDERING_BASIS_TERMS = [
    "total_order",
    "partial_order",
    "simultaneous",
    "serialized_backend_order",
    "simulation_tick",
    "control_plane_order",
    "logical_clock",
    "vector_clock",
    "wall_clock_only",
    "unknown",
    "unsupported",
]


def _valid_fixture(contract_id: str) -> dict:
    fixture_dir = FIXTURE_ROOTS_BY_CONTRACT[contract_id] / contract_id / "valid"
    path = sorted(fixture_dir.glob("*.json"))[0]
    return json.loads(path.read_text(encoding="utf-8"))


def test_participant_backend_contracts_are_published_closed_world():
    generated = schema_bundle()
    for contract_id in ALL_FIXTURE_MODELS:
        assert contract_id in generated
        schema = generated[contract_id]
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == f"https://openrae.github.io/rae/schemas/{contract_id}.json"
        assert schema["additionalProperties"] is False


def test_participant_runtime_carriers_embed_one_shared_base_envelope():
    generated = schema_bundle()
    base_envelope_fields = {
        "event_id",
        "schema_name",
        "schema_version",
        "event_type",
        "extension_policy",
        "event_classification",
        "source_status",
        "participant_address",
        "episode_id",
        "sequence_number",
        "occurred_at",
        "recorded_at",
        "ingested_at",
        "clock_authority",
        "temporal_context",
        "ordering_basis",
        "logical_order_ref",
        "predecessor_event_refs",
        "actor_ref",
        "producer_ref",
        "source_system_ref",
        "source_record_ref",
        "source_raw_ref",
        "source_pipeline",
        "raw_data_integrity",
        "confidence",
        "provenance_refs",
        "evidence_refs",
        "marking_definition_refs",
        "object_marking_refs",
        "markings",
        "granular_markings",
        "redaction_policy_ref",
        "authorization_scope",
    }
    for contract_id in PARTICIPANT_RUNTIME_FIXTURE_MODELS:
        schema = generated[contract_id]
        assert base_envelope_fields <= set(schema["properties"]), contract_id
        assert schema["properties"]["ordering_basis"]["enum"] == _ORDERING_BASIS_TERMS
        substructures = (
            "EventClassificationModel",
            "SourceStatusModel",
            "SourcePipelineModel",
            "RawDataIntegrityModel",
        )
        for substructure in substructures:
            assert substructure in schema["$defs"], (contract_id, substructure)


def test_participant_outcome_report_publishes_no_score_or_reward_surface():
    schema = schema_bundle()["participant-outcome-report-v1"]
    forbidden = {"score", "reward", "objective_success", "max_score", "return_value"}
    assert not forbidden & set(schema["properties"])
    source_schema = schema["$defs"]["ParticipantOutcomeReportSourceModel"]
    assert source_schema["properties"]["source_kind"]["enum"] == ["action_result", "episode_status", "evidence"]
    assert schema["properties"]["outcome_sources"]["minItems"] == 1
    assert schema["properties"]["state_relationships"]["minItems"] == 1


def test_participant_outcome_report_requires_state_relationships():
    payload = _valid_fixture("participant-outcome-report-v1")
    payload["state_relationships"] = []

    with pytest.raises(ValidationError, match="state_relationships"):
        ParticipantOutcomeReportModel.model_validate(payload)


def test_participant_history_view_schema_requires_completeness_basis_when_not_complete():
    schema = schema_bundle()["participant-history-view-v1"]
    assert {
        "if": {
            "properties": {"completeness": {"enum": ["truncated", "filtered"]}},
            "required": ["completeness"],
        },
        "then": {
            "required": ["completeness_basis"],
            "properties": {"completeness_basis": {"type": "string", "minLength": 1}},
        },
    } in schema["allOf"]


def test_participant_views_reuse_published_episode_shapes():
    generated = schema_bundle()
    status_schema = generated["participant-status-view-v1"]
    history_schema = generated["participant-history-view-v1"]

    assert "ParticipantStatusViewEpisodeStateModel" in status_schema["$defs"]
    assert history_schema["properties"]["episode_history"]["items"]["$ref"] == (
        "#/$defs/ParticipantHistoryViewEpisodeEventModel"
    )
    assert history_schema["properties"]["behavior_history"]["items"]["$ref"] == (
        "#/$defs/ParticipantHistoryViewBehaviorEventModel"
    )
    context_schema = generated["participant-context-view-v1"]
    assert context_schema["properties"]["derived_from_refs"]["minItems"] == 1
    assert context_schema["properties"]["source_layers"]["minItems"] == 1
    assert context_schema["properties"]["evidence_refs"]["minItems"] == 1
    assert context_schema["properties"]["provenance_refs"]["minItems"] == 1
    assert context_schema["properties"]["semantic_limitations"]["minItems"] == 1
    assert {
        "meaning_ref",
        "participant_scope",
        "audience_scope",
        "observation_point",
        "source_layers",
        "transformation",
        "comparability",
        "evidence_refs",
        "provenance_refs",
        "semantic_limitations",
    } <= set(context_schema["required"])


def test_participant_backend_contract_valid_fixtures_pass_schema_and_model_validation():
    generated = schema_bundle()
    for contract_id, model_cls in ALL_FIXTURE_MODELS.items():
        fixture_root = FIXTURE_ROOTS_BY_CONTRACT[contract_id] / contract_id
        validator = Draft202012Validator(generated[contract_id])
        valid_paths = sorted((fixture_root / "valid").glob("*.json"))
        assert valid_paths, f"{contract_id} must publish at least one valid fixture"
        for path in valid_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validator.validate(payload)
            model_cls.model_validate(payload)


def test_participant_backend_contract_invalid_fixtures_fail_schema_and_model_validation():
    generated = schema_bundle()
    for contract_id, model_cls in ALL_FIXTURE_MODELS.items():
        fixture_root = FIXTURE_ROOTS_BY_CONTRACT[contract_id] / contract_id
        validator = Draft202012Validator(generated[contract_id])
        invalid_paths = sorted((fixture_root / "invalid").glob("*.json"))
        assert invalid_paths, f"{contract_id} must publish at least one invalid fixture"
        for path in invalid_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert list(validator.iter_errors(payload)), path
            with pytest.raises(ValidationError):
                model_cls.model_validate(payload)


def test_participant_history_view_requires_completeness_basis_unless_complete():
    payload = _valid_fixture("participant-history-view-v1")
    payload["completeness"] = "filtered"
    payload["completeness_basis"] = None

    with pytest.raises(ValidationError, match="completeness_basis"):
        ParticipantHistoryViewModel.model_validate(payload)

    payload["completeness"] = "complete"
    model = ParticipantHistoryViewModel.model_validate(payload)
    assert model.completeness_basis is None


def _projected_field_parity(source_cls, projected_cls):
    source_fields = dict(source_cls.model_fields)
    for field_name in VIEW_SCOPE_PROJECTED_FIELDS:
        assert field_name in source_fields, f"{source_cls.__name__} no longer carries {field_name}"
        source_fields.pop(field_name)
    projected_fields = projected_cls.model_fields
    assert set(projected_fields) == set(source_fields), (
        f"{projected_cls.__name__} drifted from {source_cls.__name__}: "
        f"missing={set(source_fields) - set(projected_fields)} "
        f"extra={set(projected_fields) - set(source_fields)}"
    )
    for field_name, source_field in source_fields.items():
        assert projected_fields[field_name].annotation == source_field.annotation, (
            f"{projected_cls.__name__}.{field_name} type drifted from {source_cls.__name__}"
        )
        assert projected_fields[field_name].is_required() == source_field.is_required(), (
            f"{projected_cls.__name__}.{field_name} requiredness drifted from {source_cls.__name__}"
        )


def test_view_projected_models_track_recorded_contract_shapes():
    assert _projected_field_parity(ParticipantEpisodeStateModel, ParticipantStatusViewEpisodeStateModel) is None
    assert _projected_field_parity(ParticipantEpisodeHistoryEventModel, ParticipantHistoryViewEpisodeEventModel) is None
    assert (
        _projected_field_parity(ParticipantBehaviorHistoryEventModel, ParticipantHistoryViewBehaviorEventModel) is None
    )


def test_participant_status_view_rejects_episode_state_restating_scope():
    payload = _valid_fixture("participant-status-view-v1")
    payload["episode_state"]["participant_address"] = "participants.red.llm"

    with pytest.raises(ValidationError, match="participant_address"):
        ParticipantStatusViewModel.model_validate(payload)


def test_participant_status_view_requires_episode_id_when_state_embedded():
    payload = _valid_fixture("participant-status-view-v1")
    payload["episode_id"] = None

    with pytest.raises(ValidationError, match="episode_id"):
        ParticipantStatusViewModel.model_validate(payload)


def test_participant_history_view_rejects_events_restating_scope():
    payload = _valid_fixture("participant-history-view-v1")
    payload["episode_history"][0]["participant_address"] = "participants.red.llm"

    with pytest.raises(ValidationError, match="participant_address"):
        ParticipantHistoryViewModel.model_validate(payload)

    payload = _valid_fixture("participant-history-view-v1")
    payload["behavior_history"][0]["episode_id"] = "ep-blue-001"

    with pytest.raises(ValidationError, match="episode_id"):
        ParticipantHistoryViewModel.model_validate(payload)


def _scoped_action_result(participant_address: str, episode_id: str) -> dict:
    return {
        "status": "succeeded",
        "participant_address": participant_address,
        "episode_id": episode_id,
        "action_instance_id": "act-blue-42",
        "action_contract_address": "contracts.defense.isolate-host.v1",
        "observation_point": "order.sim.42.blue",
        "preconditions": [
            {
                "precondition_id": "pre-1",
                "precondition_class": "authority",
                "status": "satisfied",
                "participant_address": participant_address,
                "episode_id": episode_id,
                "action_contract_address": "contracts.defense.isolate-host.v1",
                "observation_point": "order.sim.42.blue",
            }
        ],
    }


def _history_payload_with_action_result(participant_address: str, episode_id: str) -> dict:
    payload = _valid_fixture("participant-history-view-v1")
    event = payload["behavior_history"][0]
    event["event_type"] = "action_attempted"
    event["action_result"] = _scoped_action_result(participant_address, episode_id)
    return payload


def test_participant_history_view_accepts_in_scope_nested_records():
    payload = _history_payload_with_action_result("participants.blue.rl", "ep-blue-002")
    view = ParticipantHistoryViewModel.model_validate(payload)
    assert view.behavior_history[0].action_result is not None


def test_participant_history_view_rejects_nested_action_result_for_another_participant():
    payload = _history_payload_with_action_result("participants.red.llm", "ep-blue-002")

    with pytest.raises(ValidationError, match="participant_address"):
        ParticipantHistoryViewModel.model_validate(payload)


def test_participant_history_view_rejects_nested_precondition_for_another_episode():
    payload = _history_payload_with_action_result("participants.blue.rl", "ep-blue-002")
    payload["behavior_history"][0]["action_result"]["preconditions"][0]["episode_id"] = "ep-blue-001"

    with pytest.raises(ValidationError, match="episode_id"):
        ParticipantHistoryViewModel.model_validate(payload)


def test_participant_history_view_rejects_nested_attribution_edge_out_of_scope():
    payload = _valid_fixture("participant-history-view-v1")
    event = payload["behavior_history"][-1]
    event["attribution_edges"] = [
        {
            "edge_id": "edge-1",
            "participant_address": "participants.red.llm",
            "episode_id": "ep-blue-002",
            "observation_point": "order.sim.42.blue",
            "cause_candidate": {
                "candidate_kind": "action",
                "ref": "act-blue-42",
                "description": "isolate host attempt",
            },
            "effect_candidate": {
                "candidate_kind": "observation",
                "ref": "obs-blue-43",
                "description": "telemetry delta",
            },
            "ordering_basis": {
                "basis_kind": "backend_event_order",
                "relation_ref": "order.sim.42",
                "description": "simulation tick order",
                "ordered_event_refs": ["act-blue-42", "obs-blue-43"],
            },
            "evidence_basis": {
                "capture_apparatus": "cyborg.sim",
                "granularity": "event",
                "loss_model": "none",
                "redaction_policy": "redaction.blue-observation.v1",
                "observer_effects": ["none_declared"],
            },
            "support_class": "observation_support",
            "confidence": "high",
            "strength": "supported",
            "limitations": ["single-run evidence"],
            "evidence_refs": ["evidence.obs-blue-43-redacted"],
        }
    ]

    with pytest.raises(ValidationError, match="participant_address"):
        ParticipantHistoryViewModel.model_validate(payload)


def test_participant_history_view_rejects_nested_outcome_interpretation_out_of_scope():
    payload = _valid_fixture("participant-history-view-v1")
    event = payload["behavior_history"][-1]
    event["outcome_interpretations"] = [
        {
            "interpretation_id": "interp-1",
            "rule_address": "rules.outcome.blue.v1",
            "participant_address": "participants.blue.rl",
            "episode_id": "ep-blue-001",
            "observation_point": "order.sim.42.blue",
            "source_bindings": [
                {
                    "source_id": "src-1",
                    "source_layer": "participant_action_outcome",
                    "ref": "act-blue-42",
                    "observed_value": "succeeded",
                }
            ],
            "target_bindings": [
                {
                    "target_id": "tgt-1",
                    "target_layer": "objective_result",
                    "ref": "objectives.contain-intrusion",
                    "interpreted_value": "progressed",
                    "evidence_refs": ["evidence.obs-blue-43-redacted"],
                    "limitations": ["partial coverage"],
                }
            ],
            "evidence_refs": ["evidence.obs-blue-43-redacted"],
            "limitations": ["single-run evidence"],
        }
    ]

    with pytest.raises(ValidationError, match="episode_id"):
        ParticipantHistoryViewModel.model_validate(payload)


def test_participant_context_view_requires_source_snapshot_ref():
    payload = _valid_fixture("participant-context-view-v1")
    payload.pop("source_snapshot_ref")

    with pytest.raises(ValidationError, match="source_snapshot_ref"):
        ParticipantContextViewModel.model_validate(payload)


def test_participant_context_view_rejects_hidden_or_global_source_layers():
    payload = _valid_fixture("participant-context-view-v1")
    payload["source_layers"][0]["source_layer"] = "global_runtime_state"

    with pytest.raises(ValidationError, match="source_layer"):
        ParticipantContextViewModel.model_validate(payload)


def test_participant_context_view_rejects_future_state_sources():
    payload = _valid_fixture("participant-context-view-v1")
    payload["source_layers"][0]["temporal_relation"] = "future_state"

    with pytest.raises(ValidationError, match="temporal_relation"):
        ParticipantContextViewModel.model_validate(payload)


def test_participant_context_view_bounded_staleness_requires_basis():
    payload = _valid_fixture("participant-context-view-v1")
    payload["source_layers"][0]["temporal_relation"] = "bounded_staleness"
    payload["source_layers"][0].pop("freshness_basis_ref", None)

    with pytest.raises(ValidationError, match="freshness_basis_ref"):
        ParticipantContextViewModel.model_validate(payload)


def test_participant_context_view_weak_comparability_requires_backend_disclosure():
    payload = _valid_fixture("participant-context-view-v1")
    payload["comparability"]["comparability_class"] = "portable_with_disclosed_weakening"
    payload["comparability"]["backend_disclosure_refs"] = []

    with pytest.raises(ValidationError, match="backend_disclosure_refs"):
        ParticipantContextViewModel.model_validate(payload)


def test_participant_lifecycle_event_rejects_unknown_mapping_loss():
    payload = _valid_fixture("participant-lifecycle-event-v1")
    payload["mapping_loss"] = "collapsed"

    with pytest.raises(ValidationError, match="mapping_loss"):
        ParticipantLifecycleEventModel.model_validate(payload)


def test_participant_observation_envelope_rejects_unknown_information_guarantee():
    payload = _valid_fixture("participant-observation-envelope-v1")
    payload["information_guarantee"] = "total_recall"

    with pytest.raises(ValidationError, match="information_guarantee"):
        ParticipantObservationEnvelopeModel.model_validate(payload)


def test_participant_shared_state_record_rejects_unknown_conflict_policy():
    payload = _valid_fixture("participant-shared-state-record-v1")
    payload["conflict_policy"] = "last_write_wins"

    with pytest.raises(ValidationError, match="conflict_policy"):
        ParticipantSharedStateRecordModel.model_validate(payload)


def test_participant_joint_action_record_rejects_implicit_last_writer_wins():
    payload = _valid_fixture("participant-joint-action-record-v1")
    payload["conflict_class"] = "none"
    payload["conflict_policy"] = "none"
    payload["realized_order"] = []

    with pytest.raises(ValidationError, match="conflict_class"):
        ParticipantJointActionRecordModel.model_validate(payload)


def test_participant_time_management_context_rejects_timestamp_only_exact_claim():
    payload = _valid_fixture("participant-time-management-context-v1")
    payload["basis"] = "wall_clock_only"
    payload["claim_strength"] = "exact"

    with pytest.raises(ValidationError, match="wall_clock_only"):
        ParticipantTimeManagementContextModel.model_validate(payload)
