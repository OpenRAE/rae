"""E7 sweep: messages carry no foreign exception text, and no decision reads it (issue #1678)."""

import json
import types
from typing import Annotated

import pytest
import raes.validator._workflows_verify as workflows_verify
import raes_contracts.controlled_vocabularies as controlled_vocabularies
import yaml
from pydantic import AfterValidator, BaseModel, TypeAdapter, ValidationError
from raes import SDLParseError, SDLValidationError, parse_sdl
from raes._identifiers import PortableIdentifier, require_portable_identifier, require_qualified_identifier
from raes._model_diagnostics import _model_parse_error
from raes.semantics.participant_behavior._behavior_spec import (
    _backend_feature_support_issue,
    _behavior_mode_issue,
)
from raes_contracts import experiment_spec
from raes_contracts import participant_control_context as control_context
from raes_contracts._validation import enum_value, text_value
from raes_contracts.errors import ConflictError
from raes_contracts.experiment_spec import ExperimentSpecValidationError, parse_experiment_spec
from raes_contracts.participant_episode import ParticipantEpisodeStatus
from raes_contracts.participant_episode_closure import iter_participant_episode_closure_violations
from raes_contracts.participant_episode_snapshot import iter_participant_episode_snapshot_violations
from raes_contracts.realization_envelope import (
    ConcernDisposition,
    ObservationStrength,
    RealizationConcern,
    RealizationConcernDisclosureModel,
    RealizerConfigurationModel,
)
from raes_mcp.tools.operation_support import stage_error

SECRET = "sentinel-e7-4c1f-secret"
# str() refuses an integer beyond the interpreter digit limit with interpreter text.
_HUGE_INTEGER = 10**5000


def _episode_result(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "state_schema_version": "participant-episode-state/v1",
        "participant_address": "participant.alice",
        "episode_id": "ep-0001",
        "sequence_number": 0,
        "status": "running",
        "terminal_reason": None,
        "initialized_at": "2026-04-12T10:00:00Z",
        "updated_at": "2026-04-12T10:00:05Z",
        "terminated_at": None,
        "last_control_action": "initialize",
        "previous_episode_id": None,
    }
    payload.update(overrides)
    return payload


def _history_event(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "episode_initialized",
        "timestamp": "2026-04-12T10:00:00Z",
        "participant_address": "participant.alice",
        "episode_id": "ep-0001",
        "sequence_number": 0,
        "control_action": "initialize",
    }
    payload.update(overrides)
    return payload


def _closure_record(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "participant_address": "participant.alice",
        "episode_id": "ep-0001",
        "sequence_number": 0,
        "source_signal": "rl_termination",
        "mapped_terminal_reason": "completed",
        "deriving_authority": "authority.closure",
        "evidence_refs": ["evidence.closure"],
        "derived_at": "2026-04-12T10:00:06Z",
    }
    payload.update(overrides)
    return payload


def _value_errors(exc: ValidationError) -> list[tuple[tuple[object, ...], str, str]]:
    return [
        (tuple(error["loc"]), error["type"], error["msg"])
        for error in exc.errors(include_url=False, include_context=False, include_input=False)
    ]


def test_enum_value_refusal_names_the_enum_without_the_rejected_value() -> None:
    with pytest.raises(ValueError) as raised:
        enum_value(ParticipantEpisodeStatus, SECRET)

    assert str(raised.value) == "value is not a valid ParticipantEpisodeStatus"
    assert isinstance(raised.value.__cause__, ValueError)


def test_episode_result_violation_omits_the_rejected_enum_value() -> None:
    violations = list(
        iter_participant_episode_snapshot_violations({"participant.alice": _episode_result(status=SECRET)}, {})
    )

    assert violations == [
        ("participant.alice", "participant episode result is invalid: value is not a valid ParticipantEpisodeStatus")
    ]


def test_episode_result_violation_keeps_the_designed_detail() -> None:
    payload = _episode_result()
    del payload["episode_id"]

    violations = list(iter_participant_episode_snapshot_violations({"participant.alice": payload}, {}))

    assert violations == [
        (
            "participant.alice",
            "participant episode result is invalid: participant episode payload is missing required fields: episode_id",
        )
    ]


def test_episode_history_violation_omits_the_rejected_enum_value() -> None:
    event = _history_event(event_type=SECRET)

    violations = list(iter_participant_episode_snapshot_violations({}, {"participant.alice": [event]}))

    assert violations == [
        (
            "participant.alice[0]",
            "participant episode history event is invalid: value is not a valid ParticipantEpisodeHistoryEventType",
        )
    ]


def test_episode_closure_violation_omits_the_rejected_enum_value() -> None:
    record = _closure_record(source_signal=SECRET)

    violations = list(iter_participant_episode_closure_violations({"participant.alice": [record]}, {}))

    assert violations == [
        (
            "participant.alice[0]",
            "participant episode closure record is invalid: value is not a valid ParticipantEpisodeClosureSignal",
        )
    ]


def test_text_value_refusal_omits_the_interpreter_text() -> None:
    with pytest.raises(ValueError) as raised:
        text_value(_HUGE_INTEGER, "episode_id")

    assert str(raised.value) == "episode_id cannot be represented as text"
    assert isinstance(raised.value.__cause__, ValueError)


def test_episode_result_violation_omits_the_interpreter_text() -> None:
    result = _episode_result(participant_address=_HUGE_INTEGER)

    violations = list(iter_participant_episode_snapshot_violations({"participant.alice": result}, {}))

    assert violations == [
        (
            "participant.alice",
            "participant episode result is invalid: participant_address cannot be represented as text",
        )
    ]


def test_episode_history_violation_omits_the_interpreter_text() -> None:
    event = _history_event(timestamp=_HUGE_INTEGER)

    violations = list(iter_participant_episode_snapshot_violations({}, {"participant.alice": [event]}))

    assert violations == [
        (
            "participant.alice[0]",
            "participant episode history event is invalid: timestamp cannot be represented as text",
        )
    ]


def test_episode_closure_violation_omits_the_interpreter_text() -> None:
    record = _closure_record(deriving_authority=_HUGE_INTEGER)

    violations = list(iter_participant_episode_closure_violations({"participant.alice": [record]}, {}))

    assert violations == [
        (
            "participant.alice[0]",
            "participant episode closure record is invalid: deriving_authority cannot be represented as text",
        )
    ]


def test_episode_payloads_keep_their_text_coercion() -> None:
    history = {"participant.alice": [_history_event(episode_id=7)]}
    record = _closure_record(deriving_authority=7)

    assert list(iter_participant_episode_snapshot_violations({}, history)) == []
    assert list(iter_participant_episode_closure_violations({"participant.alice": [record]}, history)) == [
        (
            "participant.alice[0]",
            "participant episode closure record references episode_id 'ep-0001' sequence_number 0 "
            "with no realized terminal event in the episode history",
        )
    ]


def test_realizer_architecture_refusal_omits_the_vocabulary_error_text() -> None:
    with pytest.raises(ValidationError) as raised:
        RealizerConfigurationModel(
            mode="techvault-appliance",
            configuration_digest="sha256:" + "a" * 64,
            architecture=SECRET,
            image_policy="pinned",
            network_policy="isolated",
            supported_node_types=["compute"],
            supported_os_families=["linux"],
            memory_mib={"minimum": 1024},
            vcpus={"minimum": 1},
        )

    assert _value_errors(raised.value) == [
        ((), "value_error", "Value error, architecture must be a governed node CPU architecture term")
    ]


def test_compute_substrate_mechanism_refusal_omits_the_vocabulary_error_text() -> None:
    with pytest.raises(ValidationError) as raised:
        RealizationConcernDisclosureModel(
            concern=RealizationConcern.COMPUTE_SUBSTRATE,
            disposition=ConcernDisposition.REALIZED,
            observation_strength=ObservationStrength.DRIVER_REPORTED,
            mechanism=SECRET,
        )

    assert _value_errors(raised.value) == [
        ((), "value_error", "Value error, compute-substrate mechanism must be a governed term")
    ]


def test_experiment_spec_duplicate_key_is_a_typed_refusal() -> None:
    document = f"schema_version: experiment-authoring-input/v1\nspec_id: safe-id\nspec_id: {SECRET}\n"

    with pytest.raises(ExperimentSpecValidationError) as raised:
        parse_experiment_spec(document)

    assert raised.value.code == "duplicate-key"
    assert raised.value.details == "Experiment spec YAML is invalid."
    assert SECRET not in str(raised.value)


def test_experiment_spec_other_yaml_error_with_the_same_text_is_not_a_duplicate_key() -> None:
    document = "schema_version: experiment-authoring-input/v1\nspec_id: !custom duplicate mapping key\n"

    with pytest.raises(ExperimentSpecValidationError) as raised:
        parse_experiment_spec(document)

    assert raised.value.code == "invalid-yaml"
    assert raised.value.details == "Experiment spec YAML is invalid."


def test_experiment_yaml_reader_still_raises_a_yaml_error_for_a_duplicate_key() -> None:
    # tools/example_library_checks.py reads templates with this reader and catches yaml.YAMLError.
    with pytest.raises(yaml.YAMLError) as raised:
        experiment_spec._load_yaml("spec_id: safe-id\nspec_id: other-id\n")

    assert isinstance(raised.value.__cause__, experiment_spec._DuplicateMappingKey)


def _refuse_with_foreign_text(condition: bool, code: str) -> None:
    if not condition:
        failure = control_context._AgreementFailure(code)
        failure.args = (SECRET,)
        raise failure


def test_control_context_change_code_comes_from_the_typed_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control_context, "_require", _refuse_with_foreign_text)
    change = types.SimpleNamespace(scope_ref="scope.a", effective_cut="cut.1")
    context = types.SimpleNamespace(scope_ref="scope.b", record_cut="cut.1")

    (diagnostic,) = control_context.validate_control_context_change(change, context)

    assert diagnostic.code == "control-context.scope-mismatch"
    assert diagnostic.address == "#"
    assert diagnostic.message == "Participant control-context agreement failed: scope-mismatch"


def test_control_context_record_code_comes_from_the_typed_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control_context, "_require", _refuse_with_foreign_text)
    record = types.SimpleNamespace(scope_ref="scope.a")
    context = types.SimpleNamespace(scope_ref="scope.b")

    (diagnostic,) = control_context.validate_control_context_record(record, context)

    assert diagnostic.code == "control-context.scope-mismatch"
    assert diagnostic.address == "#"
    assert diagnostic.message == "Participant control-context agreement failed: scope-mismatch"


def test_control_context_host_conflict_with_the_same_text_is_not_an_agreement_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _host_conflict(_reference: object, _context: object) -> None:
        raise ConflictError("version-conflict")

    monkeypatch.setattr(control_context, "_resolve", _host_conflict)
    change = types.SimpleNamespace(scope_ref="scope.a", effective_cut="cut.1", asset_ref=object())
    context = types.SimpleNamespace(scope_ref="scope.a", record_cut="cut.1")

    with pytest.raises(ConflictError) as raised:
        control_context.validate_control_context_change(change, context)

    assert type(raised.value) is ConflictError


def test_mcp_stage_error_keeps_the_parse_details() -> None:
    failure = SDLParseError("Invalid YAML: mapping values are not allowed here")

    assert stage_error("parse", failure) == {
        "status": "invalid",
        "stage": "parse",
        "diagnostics": [
            {"stage": "parse", "severity": "error", "message": "Invalid YAML: mapping values are not allowed here"}
        ],
    }


def test_mcp_stage_error_omits_the_text_of_another_exception() -> None:
    result = stage_error("parse", RuntimeError(f"backend detail {SECRET}"))

    assert SECRET not in json.dumps(result)
    assert result == {
        "status": "invalid",
        "stage": "parse",
        "diagnostics": [
            {"stage": "parse", "severity": "error", "message": "The scenario was rejected at the parse stage."}
        ],
    }


# Phase 2: SDL producers in the raes package.

_UNGOVERNED_FEATURE = (
    "it is neither a listed term nor an accepted extension term of the participant runtime behavior "
    "or interaction feature vocabularies"
)


def _vocabulary_refusal_with_secret(*_args: object, **_kwargs: object) -> None:
    raise ValueError(f"controlled vocabulary refused {SECRET}")


def _goal_validation_errors(old: str = "", new: str = "") -> list[str]:
    from test_sce_004_goal_oriented_steps import _governed_goal_scenario

    with pytest.raises(SDLValidationError) as raised:
        parse_sdl(_governed_goal_scenario().replace(old, new))
    return raised.value.errors


def test_workflow_capability_refusal_omits_the_vocabulary_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workflows_verify, "validate_controlled_vocabulary_value", _vocabulary_refusal_with_secret)

    errors = _goal_validation_errors()

    assert not any(SECRET in error for error in errors)
    assert (
        "Workflow 'response' step 'restore' references ungoverned participant capability 'action_contracts': "
        + _UNGOVERNED_FEATURE
    ) in errors


def test_workflow_capability_refusal_keeps_the_ref_and_the_rule() -> None:
    errors = _goal_validation_errors("capability_refs: [action_contracts]", "capability_refs: [unlisted-capability]")

    assert [error for error in errors if "capability" in error] == [
        "Workflow 'response' step 'restore' references ungoverned participant capability 'unlisted-capability': "
        + _UNGOVERNED_FEATURE
    ]


def test_workflow_fact_binding_refusal_omits_the_vocabulary_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        workflows_verify, "validate_controlled_vocabulary_scope_values", _vocabulary_refusal_with_secret
    )

    errors = _goal_validation_errors()

    assert not any(SECRET in error for error in errors)
    assert (
        "Workflow 'response' step 'restore' references ungoverned runtime-fact binding 'x-raes:service-endpoint': "
        "it is neither a listed term nor an accepted extension term of the workflow step fact-binding vocabulary"
    ) in errors


def test_behavior_mode_issue_omits_the_vocabulary_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _behavior_mode_issue(spec_name="red-scan-behavior", behavior_mode="autonomous") is None
    monkeypatch.setattr(
        controlled_vocabularies, "validate_controlled_vocabulary_scope_values", _vocabulary_refusal_with_secret
    )

    issue = _behavior_mode_issue(spec_name="red-scan-behavior", behavior_mode="autonomous")

    assert issue is not None
    assert (issue.code, issue.spec_name, issue.ref) == (
        "participant.behavior-spec-mode-ungoverned",
        "red-scan-behavior",
        "autonomous",
    )
    assert issue.message == "it is neither a listed term nor an accepted extension term of that vocabulary"


def test_backend_feature_issue_omits_the_vocabulary_error_text(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _backend_feature_support_issue(spec_name="red-scan-behavior", feature_ref="action_contracts") is None
    monkeypatch.setattr(
        controlled_vocabularies, "validate_controlled_vocabulary_value", _vocabulary_refusal_with_secret
    )

    issue = _backend_feature_support_issue(spec_name="red-scan-behavior", feature_ref="action_contracts")

    assert issue is not None
    assert (issue.code, issue.spec_name, issue.ref) == (
        "participant.behavior-spec-feature-ungoverned",
        "red-scan-behavior",
        "action_contracts",
    )
    assert issue.message == _UNGOVERNED_FEATURE


def test_behavior_specification_vocabulary_refusals_keep_the_ref_and_the_rule() -> None:
    from test_sem_208_participant_behavior import _scenario_yaml

    source = _scenario_yaml() + (
        "behavior_specifications:\n"
        "  red-scan-behavior:\n"
        "    semantic_version: 1.0.0\n"
        "    lifecycle_state: active\n"
        "    participant_refs: [red-agent]\n"
        "    action_contract_refs: [scan]\n"
        "    behavior_mode: supervised\n"
        "    backend_feature_support_refs: [participant-behavior-history]\n"
        "    extension_policy: governed-extension\n"
    )

    with pytest.raises(SDLValidationError) as raised:
        parse_sdl(source)

    assert [error for error in raised.value.errors if error.startswith("Behavior specification")] == [
        "Behavior specification 'red-scan-behavior' behavior_mode 'supervised' is not in "
        "participant-decision-surface-modes: it is neither a listed term nor an accepted extension term "
        "of that vocabulary",
        "Behavior specification 'red-scan-behavior' backend_feature_support_ref 'participant-behavior-history' "
        "is not a governed participant runtime feature: " + _UNGOVERNED_FEATURE,
    ]


class _IdentifierProbe(BaseModel):
    value: PortableIdentifier


def test_model_identifier_code_comes_from_the_error_type() -> None:
    with pytest.raises(ValidationError) as raised:
        _IdentifierProbe(value="Bad.Name")
    qualified = TypeAdapter(
        Annotated[str, AfterValidator(lambda ref: require_qualified_identifier(ref, field_name="ref"))]
    )
    with pytest.raises(ValidationError) as qualified_raised:
        qualified.validate_python("bad name.")

    (portable,) = _model_parse_error(raised.value, path=None, source_ranges={}).diagnostics
    (qualified_diagnostic,) = _model_parse_error(qualified_raised.value, path=None, source_ranges={}).diagnostics

    assert (portable.code, portable.pointer) == ("sdl.identifier.invalid", "/value")
    assert portable.message == (
        "value must be a portable SDL identifier: 1-64 lowercase ASCII letters, digits, hyphens, or underscores, "
        "starting with a letter or digit"
    )
    assert (qualified_diagnostic.code, qualified_diagnostic.message) == (
        "sdl.identifier.invalid",
        "ref must be a qualified SDL identifier",
    )


def test_model_error_with_identifier_text_is_not_an_identifier_error() -> None:
    unrelated = ValidationError.from_exception_data(
        "Probe",
        [
            {
                "type": "value_error",
                "loc": ("mode",),
                "input": "portable SDL identifier",
                "ctx": {"error": ValueError("term 'portable SDL identifier' is not a qualified SDL identifier term")},
            }
        ],
    )

    (diagnostic,) = _model_parse_error(unrelated, path=None, source_ranges={}).diagnostics

    assert diagnostic.code == "sdl.model.invalid"
    assert diagnostic.pointer == "/mode"


def test_identifier_refusals_stay_value_errors_outside_model_validation() -> None:
    with pytest.raises(ValueError) as portable:
        require_portable_identifier("Bad.Name", field_name="namespace")
    with pytest.raises(ValueError) as qualified:
        require_qualified_identifier("bad name.", field_name="ref")

    assert str(portable.value).startswith("namespace must be a portable SDL identifier: ")
    assert str(qualified.value) == "ref must be a qualified SDL identifier"
    assert isinstance(qualified.value.__cause__, ValueError)
