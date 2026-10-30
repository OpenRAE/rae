"""Issue #1678 sweep of the contract and operations packages (ADR-116 rules E1, E9, H2, H3, L6)."""

import logging
from types import SimpleNamespace

import pytest

SENTINEL = "sentinel-1678-sweep-c-value"
# A Unicode digit that str.isdigit() accepts and int() refuses, and an index beyond the int() digit limit.
_NOT_INDEX_TOKENS = ("²", "1" * 5000)
_NOT_INDEX_IDS = ("unicode-digit", "beyond-digit-limit")


class ObservationRuntimeOnlyError(Exception):
    """A failure type that only the backend observation runtime defines."""


@pytest.fixture
def lifecycle_records(caplog):
    caplog.set_level(logging.DEBUG)

    def select() -> list[logging.LogRecord]:
        return [record for record in caplog.records if record.name == "raes_contracts.observation_lifecycle"]

    return select


def _fail(*_args: object, **_kwargs: object) -> tuple[object, ...]:
    raise ObservationRuntimeOnlyError(SENTINEL)


def _resolution(*, required: bool = False):
    from raes_contracts.observation_demand import (
        ObservationDemandDocument,
        ObservationDemandRule,
        ObservationLifecycleDecision,
        ObservationPurpose,
        ObservationSelector,
        normalize_observation_demands,
    )

    selector = ObservationSelector(semantic_scope="/nodes/kali", data_kind="stream", names=("filesystem-trace",))
    document = ObservationDemandDocument(
        schema_version="observation-demand/v1",
        document_id="issue-1678-sweep-c",
        scope_profile="recursive-realization-constraint/v1",
        rules=(
            ObservationDemandRule(
                rule_id="filesystem",
                scope="/nodes/kali",
                purpose=ObservationPurpose.EXPERIMENTAL,
                mode="selected",
                selector=selector,
                collection=ObservationLifecycleDecision.REQUIRE,
                redaction="redact-sensitive",
                integrity="checksum",
                required=required,
            ),
        ),
    )
    return normalize_observation_demands(document, target_scopes=("/nodes/kali",)), selector.key


def _assert_foreign_record(record: logging.LogRecord) -> None:
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert SENTINEL not in record.getMessage()
    assert SENTINEL not in (record.exc_text or "")
    # The observation runtime is backend-owned code: its type name, message and frames stay out.
    assert "ForeignCodeFailure" in record.exc_text
    assert "ObservationRuntimeOnlyError" not in record.exc_text


def test_optional_producer_failure_records_only_raes_frames(lifecycle_records):
    from raes_contracts.observation_demand import execute_observation_lifecycle

    resolution, key = _resolution()
    result = execute_observation_lifecycle(
        resolution,
        producers={key: _fail},
        supported=frozenset({key}),
        optional_failure_is_loss=True,
    )
    assert result.collected == ()
    [record] = lifecycle_records()
    _assert_foreign_record(record)


def test_optional_protector_failure_records_only_raes_frames(lifecycle_records):
    from raes_contracts.observation_demand import execute_observation_lifecycle

    resolution, key = _resolution()
    result = execute_observation_lifecycle(
        resolution,
        producers={key: lambda: ("value",)},
        supported=frozenset({key}),
        protector=_fail,
        optional_failure_is_loss=True,
    )
    assert result.collected == ()
    [record] = lifecycle_records()
    _assert_foreign_record(record)


@pytest.mark.parametrize("required", [False, True])
def test_a_failure_that_is_not_an_optional_loss_propagates_without_a_record(lifecycle_records, required):
    from raes_contracts.observation_demand import execute_observation_lifecycle

    resolution, key = _resolution(required=required)
    supported = frozenset({key})
    with pytest.raises(ObservationRuntimeOnlyError):
        execute_observation_lifecycle(
            resolution,
            producers={key: _fail},
            supported=supported,
            optional_failure_is_loss=required,
        )
    assert lifecycle_records() == []


# The run archive refuses SDL that the parser cannot load (ADR-116 rules E1, E9).


def test_run_archive_refuses_an_integer_beyond_the_digit_limit(tmp_path):
    from raes_contracts.errors import InvalidInputError
    from raes_operations.run_artifacts import RunMaterializationArchive

    digits = "7" * 5000
    archive = RunMaterializationArchive(tmp_path / "archive")
    with pytest.raises(InvalidInputError, match="valid bounded SDL") as refused:
        archive.publish(f"name: materialized\ncount: {digits}\n")
    assert refused.value.__suppress_context__ is True
    assert digits[:64] not in str(refused.value)
    assert not (tmp_path / "archive").exists()


# An RFC 6901 array index is ASCII digits; any other token does not name a list position (ADR-116 rule E9).

_PROFILE = "raes-recursive-realization/v1"


def _closure(posture: str):
    from raes_contracts.realization_structure import RealizationClosure

    return RealizationClosure(posture=posture, universe="sweep-c/v1", profile=_PROFILE)


def _relation_outcome(result) -> tuple[object, list[str]]:
    return result.status, [diagnostic.message for diagnostic in result.diagnostics]


@pytest.mark.parametrize("token", [*_NOT_INDEX_TOKENS, "٣"], ids=[*_NOT_INDEX_IDS, "non-ascii-decimal-digit"])
def test_evidence_field_selector_with_a_non_index_token_does_not_resolve(token):
    from raes_contracts._evidence_content_validation import _json_pointer_resolves, _validate_field_selectors

    document = {"items": [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]}
    assert _json_pointer_resolves(document, f"/items/{token}") is False
    requirement = SimpleNamespace(field_selectors=[f"/items/{token}"])
    with pytest.raises(ValueError, match="^emitted evidence is missing required field selector"):
        _validate_field_selectors(requirement, document)


def test_evidence_field_selector_keeps_ascii_indexes():
    from raes_contracts._evidence_content_validation import _json_pointer_resolves

    document = {"items": [{"a": 1}, {"a": 2}]}
    assert _json_pointer_resolves(document, "/items/0/a")
    # RFC 6901 gives each index one spelling, so a leading zero names no position.
    assert not _json_pointer_resolves(document, "/items/01/a")
    assert not _json_pointer_resolves(document, "/items/2")


@pytest.mark.parametrize("pointers", [("/items/{}",), ("/items", "/items/{}")], ids=["advance", "closed-extras"])
def test_scope_overlay_treats_a_non_index_token_like_a_member_name(pointers):
    from raes_contracts.realization_structure import (
        RealizationConstraintDocument,
        RealizationRecordConstraint,
        RealizationScope,
        evaluate_realization_constraint,
    )

    def evaluate(token: str):
        document = RealizationConstraintDocument(
            semantic_profile=_PROFILE,
            default_closure=_closure("open"),
            scopes=tuple(
                RealizationScope(field_pointer=pointer.format(token), closure=_closure("closed"))
                for pointer in pointers
            ),
            root=RealizationRecordConstraint(kind="recursive-record", fields={}),
        )
        return evaluate_realization_constraint(document, {"items": ["a", "b"]})

    assert _relation_outcome(evaluate("²")) == _relation_outcome(evaluate("x"))


@pytest.mark.parametrize("keyed", [False, True], ids=["plain", "keyed"])
def test_scope_normalization_treats_a_non_index_token_like_a_member_name(keyed):
    from raes_contracts.realization_structure import (
        RealizationCollectionProfile,
        RealizationNormalizationMetadata,
        RealizationScope,
        normalize_realization_literal,
    )

    profiles = (
        (
            RealizationCollectionProfile(
                field_pointer="/items", collection_kind="items", identity_fields=("name",), closure=_closure("closed")
            ),
        )
        if keyed
        else ()
    )

    def normalize(token: str):
        metadata = RealizationNormalizationMetadata(
            scopes=(RealizationScope(field_pointer=f"/items/{token}", closure=_closure("closed")),),
            collection_profiles=profiles,
        )
        return normalize_realization_literal(
            {"items": [{"name": "a"}, {"name": "b"}]}, semantic_profile=_PROFILE, metadata=metadata
        )

    assert _relation_outcome(normalize("²")) == _relation_outcome(normalize("x"))


@pytest.mark.parametrize("token", _NOT_INDEX_TOKENS, ids=_NOT_INDEX_IDS)
def test_semantic_address_with_a_non_index_token_does_not_resolve(token):
    from raes_contracts.realization_structure import RealizationConstraintLimits, canonical_semantic_address

    limits = RealizationConstraintLimits(max_scalar_bytes=8192)
    with pytest.raises(ValueError, match="^semantic sequence address does not resolve$"):
        canonical_semantic_address(f"/items/{token}", {"items": ["a"]}, limits=limits)


@pytest.mark.parametrize("token", _NOT_INDEX_TOKENS, ids=_NOT_INDEX_IDS)
def test_authority_pointer_with_a_non_index_token_selects_no_value(token):
    from raes_contracts.planning import (
        ChangeAction,
        ProvisioningPlan,
        ProvisionOp,
        RealizationAuthorityMode,
        RealizationResolutionSource,
        ResolvedRealizationAuthority,
    )
    from raes_contracts.realization_authority import planned_realization_selection_diagnostics

    def diagnostics(index_token: str):
        authority = ResolvedRealizationAuthority(
            address="provision.node.web",
            field_path="nodes.web.items",
            domain="runtime-realization",
            requirement_kind="items",
            payload_pointer=f"/items/{index_token}",
            mode=RealizationAuthorityMode.CLOSED,
            source=RealizationResolutionSource.AUTHORED_LEAF,
        )
        operation = ProvisionOp(
            action=ChangeAction.CREATE, address="provision.node.web", resource_type="node", payload={"items": ["a"]}
        )
        plan = ProvisioningPlan(operations=[operation], realization_authority=(authority,))
        return [diagnostic.code for diagnostic in planned_realization_selection_diagnostics(plan)]

    assert diagnostics("0") == ["realization.authority-selection-invalid"]
    assert diagnostics(token) == diagnostics("5") == []


# The experiment specification loader refuses input that its YAML composer cannot nest (ADR-116 rule E9).


def test_experiment_spec_refuses_yaml_nested_beyond_the_recursion_limit():
    from raes_contracts.experiment_spec import (
        MAX_EXPERIMENT_SPEC_BYTES,
        ExperimentSpecValidationError,
        parse_experiment_spec,
    )

    text = "spec_id: " + "[" * 20_000 + "]" * 20_000
    assert len(text.encode("utf-8")) <= MAX_EXPERIMENT_SPEC_BYTES
    with pytest.raises(ExperimentSpecValidationError, match="Experiment spec YAML is invalid") as refused:
        parse_experiment_spec(text)
    assert refused.value.code == "invalid-yaml"


def test_experiment_spec_does_not_report_a_loader_defect_as_a_refusal(monkeypatch):
    from raes_contracts import experiment_spec

    def defect(_raw: str) -> object:
        raise KeyError(SENTINEL)

    monkeypatch.setattr(experiment_spec, "_load_yaml", defect)
    with pytest.raises(KeyError):
        experiment_spec.parse_experiment_spec("spec_id: sweep-c")


# A negative initial state ordinal is refused by the model check input validator (ADR-116 rule E3).


@pytest.mark.parametrize("ordinals", [(-1, 0), (-5, 0)], ids=["last-state-alias", "beyond-the-states"])
def test_opacity_model_input_refuses_a_negative_initial_state_ordinal(ordinals):
    from pydantic import ValidationError
    from raes_conformance.conformance.validators import validate_contract_payload
    from raes_contracts.participant_opacity import ParticipantOpacityModelCheckInputModel
    from test_issue_962_participant_opacity_model_check import _request, _state

    request, _, _ = _request(
        (
            _state(0, secret=True, observation="observation:shared"),
            _state(1, secret=False, observation="observation:shared"),
        ),
        initial_state_ordinals=(0, 1),
    )
    payload = request.model_dump(mode="json")
    payload["initial_state_ordinals"] = list(ordinals)

    with pytest.raises(ValidationError, match="initial state ordinals must reference declared states"):
        ParticipantOpacityModelCheckInputModel.model_validate(payload)
    diagnostics = validate_contract_payload("participant-opacity-model-check-input-v1", payload)
    assert diagnostics
    assert all(item.severity.value == "error" for item in diagnostics)


# Stored temporal history is input to its validator, so malformed shapes are refusals (ADR-116 rule E3).


@pytest.mark.parametrize("contexts", [-1, "x", [[]], [1]], ids=["integer", "string", "nested-list", "scalar-item"])
def test_temporal_record_selection_refuses_a_malformed_context_list(contexts):
    from raes_contracts.participant_temporal_history_index import TemporalRecordIndex, explicit_temporal_record

    record = {"episode_id": "episode-1", "action_instance_id": "action-1", "temporal_contexts": contexts}
    with pytest.raises(ValueError, match="temporal contexts must be a list of objects"):
        explicit_temporal_record(record)
    # The incremental index marks the history invalid, so the exhaustive validator decides.
    assert TemporalRecordIndex().append(0, record).valid is False


def test_temporal_record_selection_keeps_well_formed_records():
    from raes_contracts.participant_temporal_history_index import explicit_temporal_record

    assert explicit_temporal_record({"temporal_contexts": [{"shared_time": {"clock": "c"}}]}) is True
    assert explicit_temporal_record({"temporal_contexts": ()}) is False
    assert explicit_temporal_record({}) is False


@pytest.mark.parametrize(
    "raw",
    [
        ["not", "an", "object"],
        {"episode_id": [1], "action_instance_id": "action-1"},
        {"episode_id": "episode-1", "action_instance_id": {"nested": "object"}},
    ],
    ids=["non-mapping", "list-episode-id", "object-action-id"],
)
def test_temporal_history_refuses_malformed_records_with_value_error(raw):
    from raes_contracts.contracts.participant_runtime import ParticipantBehaviorHistoryEventModel
    from raes_contracts.participant_temporal import _temporal_history_record

    with pytest.raises(ValueError, match="temporal history record"):
        _temporal_history_record(raw, {}, ParticipantBehaviorHistoryEventModel)
