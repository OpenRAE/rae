"""Contract-layer exceptions and operational logs follow ADR-116 (issue #1678)."""

import json
import logging
from dataclasses import fields
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from raes_contracts import corpus
from raes_contracts._host_isolation import isolated_host_call
from raes_contracts.errors import ConflictError, EvidenceIntegrityError, InvalidInputError, OperationalError
from raes_contracts.json_ingress import StrictJsonIngressError

SENTINEL = "sentinel-1678-contracts-value"
_DUPLICATE_OBJECT = '{"secret":"' + SENTINEL + '","secret":"' + SENTINEL + '"}'


@pytest.fixture
def records(caplog):
    caplog.set_level(logging.DEBUG)

    def select(name: str) -> list[logging.LogRecord]:
        return [record for record in caplog.records if record.name == name]

    return select


def _assert_value_free(record: logging.LogRecord) -> None:
    assert SENTINEL not in record.getMessage()
    assert SENTINEL not in (record.exc_text or "")
    assert record.exc_info is None


def _fail(exception: BaseException):
    def callback(*_args: object, **_kwargs: object) -> None:
        raise exception

    return callback


# Isolation of host callbacks (H2, H3, L3).


def test_host_refusal_keeps_the_validation_contract_without_a_log_record(records):
    with pytest.raises(ValueError, match="^refused$") as refused, isolated_host_call("refused", keep_cause=False):
        raise ValueError(SENTINEL)
    assert refused.value.__suppress_context__ is True
    with pytest.raises(ValueError, match="^refused$") as conflict, isolated_host_call("refused"):
        raise ConflictError(SENTINEL)
    assert isinstance(conflict.value.__cause__, ConflictError)
    assert records("raes_contracts._host_isolation") == []


def test_unexpected_host_failure_is_logged_value_free_before_the_refusal(records):
    with pytest.raises(ValueError, match="^refused$") as refused, isolated_host_call("refused", keep_cause=False):
        raise KeyError(SENTINEL)
    assert refused.value.__suppress_context__ is True
    with pytest.raises(ValueError, match="^refused$") as degraded, isolated_host_call("refused", keep_cause=False):
        raise OperationalError(SENTINEL)
    assert degraded.value.__suppress_context__ is True
    failure, dependency = records("raes_contracts._host_isolation")
    assert (failure.levelno, dependency.levelno) == (logging.ERROR, logging.WARNING)
    # Host code is foreign code, so each record keeps only the RAES frames (ADR-116, H2).
    assert "ForeignCodeFailure" in failure.exc_text
    assert "ForeignCodeFailure" in dependency.exc_text
    _assert_value_free(failure)
    _assert_value_free(dependency)


def test_control_context_resolver_failure_is_logged_and_refused(records):
    from raes_contracts.contracts.participant_control_resolution import (
        validate_participant_control_resolved_context,
    )

    with pytest.raises(ValueError, match="trusted-context validation failed") as refused:
        validate_participant_control_resolved_context(object(), _fail(RuntimeError(SENTINEL)))
    assert SENTINEL not in str(refused.value)
    [record] = records("raes_contracts._host_isolation")
    _assert_value_free(record)


def test_flow_control_resolver_and_trusted_context_failures_are_logged(records):
    from raes_contracts.contracts.participant_flow_control_context import ParticipantFlowControlValidationContext
    from raes_contracts.contracts.participant_flow_control_validation import (
        validate_participant_flow_control_resolved_context,
    )

    with pytest.raises(ValueError, match="context resolution failed"):
        validate_participant_flow_control_resolved_context(object(), _fail(RuntimeError(SENTINEL)))
    with pytest.raises(ValueError, match="context resolution failed"):
        validate_participant_flow_control_resolved_context(object(), _fail(ValueError(SENTINEL)))
    [resolver_record] = records("raes_contracts._host_isolation")
    _assert_value_free(resolver_record)

    empty = {item.name: () for item in fields(ParticipantFlowControlValidationContext) if item.init}
    context = ParticipantFlowControlValidationContext(**empty)
    with pytest.raises(ValueError, match="context validation failed") as refused:
        validate_participant_flow_control_resolved_context(object(), lambda *_: context)
    assert refused.value.__context__ is None
    [context_record] = records("raes_contracts.contracts.participant_flow_control_validation")
    assert "ForeignCodeFailure" in context_record.exc_text
    _assert_value_free(context_record)


def test_feature_support_resolver_refusal_is_quiet_and_its_failure_is_logged(records):
    from raes_contracts.contracts.mixed_composition_resolution import _validate_feature_requirements, _WorkBudget

    requirement = SimpleNamespace(downgrade_policy_ref=None)
    allocation = SimpleNamespace(feature_requirements=(requirement,), provider_component_id="provider")
    for failure in (ValueError(SENTINEL), ConflictError(SENTINEL), LookupError(SENTINEL)):
        context = SimpleNamespace(feature_support_resolver=_fail(failure))
        with pytest.raises(ValueError, match="feature support resolution failed") as refused:
            _validate_feature_requirements("profile", allocation, context, _WorkBudget(8))
        assert refused.value.__suppress_context__ is True
    [record] = records("raes_contracts._host_isolation")
    assert "ForeignCodeFailure" in record.exc_text
    _assert_value_free(record)


def test_information_state_and_delivery_resolver_failures_name_their_record(records):
    from raes_contracts.contracts.participant_information_state import (
        validate_participant_information_state_resolved_context,
    )
    from raes_contracts.operational_logging import ForeignCodeFailure
    from raes_contracts.participant_decision_surface_delivery import validate_participant_decision_surface_v2_delivery

    # The refusal names the value-free record as its cause, never the host exception.
    with pytest.raises(ValueError, match="information-state context resolution failed") as state:
        validate_participant_information_state_resolved_context(object(), _fail(RuntimeError(SENTINEL)))
    assert isinstance(state.value.__cause__, ForeignCodeFailure)
    surface = SimpleNamespace(surface_state="delivered", delivery=SimpleNamespace(delivery_ref="delivery-1"))
    with pytest.raises(ValueError, match="delivery resolution failed") as delivery:
        validate_participant_decision_surface_v2_delivery(surface, _fail(RuntimeError(SENTINEL)))
    assert isinstance(delivery.value.__cause__, ForeignCodeFailure)
    logged = records("raes_contracts._host_isolation")
    assert len(logged) == 2
    for record in logged:
        _assert_value_free(record)


def test_native_readback_failure_returns_a_diagnostic_and_a_value_free_record(records):
    from raes_contracts.realization_operational_observation import invoke_native_readback

    class ProducerOnlyError(Exception):
        pass

    diagnostics, observations = invoke_native_readback(_fail(ProducerOnlyError(SENTINEL)))
    assert observations == ()
    assert [item.code for item in diagnostics] == ["observation.native-readback-failed"]
    assert SENTINEL not in diagnostics[0].message
    [record] = records("raes_contracts.realization_operational_observation")
    assert record.levelno == logging.ERROR
    _assert_value_free(record)
    # The producer is foreign code, so the record keeps only the RAES frames (ADR-116 section 5).
    assert "ForeignCodeFailure" in record.exc_text
    assert "ProducerOnlyError" not in record.exc_text


def test_optional_observation_failure_is_a_logged_loss(records):
    from raes_contracts.observation_demand import (
        ObservationDemandDocument,
        ObservationDemandRule,
        ObservationLifecycleDecision,
        ObservationPurpose,
        ObservationSelector,
        execute_observation_lifecycle,
        normalize_observation_demands,
    )

    selector = ObservationSelector(semantic_scope="/nodes/kali", data_kind="stream", names=("filesystem-trace",))
    document = ObservationDemandDocument(
        schema_version="observation-demand/v1",
        document_id="issue-1678",
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
            ),
        ),
    )
    result = execute_observation_lifecycle(
        normalize_observation_demands(document, target_scopes=("/nodes/kali",)),
        producers={selector.key: _fail(RuntimeError(SENTINEL))},
        supported=frozenset({selector.key}),
        protector=lambda item, _demand: item,
        optional_failure_is_loss=True,
    )
    assert result.collected == ()
    [record] = records("raes_contracts.observation_lifecycle")
    assert record.levelno == logging.WARNING
    # The producer is backend-owned observation runtime code, so the record keeps only the RAES frames.
    assert "ForeignCodeFailure" in record.exc_text
    assert "RuntimeError" not in record.exc_text
    _assert_value_free(record)


# A damaged behavioral profile is an installation failure (OperationalError); the other packaged
# resources and validators keep ValueError (E3) after the ingress re-parenting.


def test_behavioral_profile_loader_hides_and_logs_a_damaged_artifact(tmp_path, records):
    from raes_contracts.behavioral_relation_profiles import (
        behavioral_relation_profile_path,
        load_behavioral_relation_profile_from_path,
    )

    profile_id = "participant-opacity-baseline-v1"
    source = behavioral_relation_profile_path(profile_id).read_text(encoding="utf-8")
    damaged = tmp_path / "profile.json"
    damaged.write_text(source.replace("{", '{"' + SENTINEL + '":1,"' + SENTINEL + '":2,', 1), encoding="utf-8")
    # A damaged packaged profile is an installation failure, not a value finding.
    with pytest.raises(OperationalError, match="JSON or contract is invalid") as refused:
        load_behavioral_relation_profile_from_path(profile_id, damaged)
    assert refused.value.__suppress_context__ is True
    assert SENTINEL not in str(refused.value)
    [record] = records("raes_contracts._behavioral_profile_loader")
    assert "StrictJsonIngressError" in record.exc_text
    _assert_value_free(record)


def test_teaching_profile_loader_keeps_value_error_for_a_damaged_artifact(tmp_path, monkeypatch, records):
    from raes_contracts.contracts import participant_control_profiles

    (tmp_path / "participant-control").mkdir()
    (tmp_path / "participant-control" / "teaching-influence-rev1.json").write_text(_DUPLICATE_OBJECT, encoding="utf-8")
    monkeypatch.setattr(participant_control_profiles, "corpus_family_root", lambda _family: tmp_path)
    with pytest.raises(ValueError, match="teaching influence profile is invalid") as refused:
        participant_control_profiles.load_teaching_influence_profile()
    assert refused.value.__suppress_context__ is True
    [record] = records("raes_contracts.contracts.participant_control_profiles")
    _assert_value_free(record)


def test_damaged_published_evidence_schema_and_emitted_json_stay_value_errors(tmp_path, monkeypatch):
    from raes_contracts import evidence_output_validation
    from raes_contracts._evidence_content_validation import _parse_contract_document

    with pytest.raises(ValueError, match="does not satisfy the declared output_contract") as emitted:
        _parse_contract_document(
            _DUPLICATE_OBJECT.encode(), media_type="application/json", output_contract="experiment-evidence-record-v1"
        )
    assert isinstance(emitted.value.__cause__, StrictJsonIngressError)

    (tmp_path / "experiment-core").mkdir()
    (tmp_path / "experiment-core" / "experiment-evidence-record-v1.json").write_text(
        '{"type":"object","type":"object"}', encoding="utf-8"
    )
    monkeypatch.setattr(evidence_output_validation, "corpus_family_root", lambda _family: tmp_path)
    with pytest.raises(ValueError, match="no valid published schema") as schema:
        evidence_output_validation.resolve_evidence_output_contract("experiment-evidence-record-v1")
    assert isinstance(schema.value.__cause__, StrictJsonIngressError)


def test_validators_report_strict_json_failures_as_validation_errors():
    from raes_contracts.augmentation_preparation import AugmentationPreparation
    from raes_contracts.materialization import MaterializationSource

    with pytest.raises(ValidationError, match="duplicate-member"):
        AugmentationPreparation(binding_digest="sha256:" + "0" * 64, content=_DUPLICATE_OBJECT)
    with pytest.raises(ValidationError, match="duplicate-member") as source:
        MaterializationSource(
            snapshot=_DUPLICATE_OBJECT,
            authored_digest="sha256:" + "a" * 64,
            instantiated_digest="sha256:" + "b" * 64,
            run_id="run-1",
        )
    assert SENTINEL not in str(source.value)


# Ingress raises categories (E1); defects are not reported as refusals (E2, H5).


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_participant_control_evaluation_ingress_raises_invalid_input(version):
    from raes_contracts.contracts.participant_control_composition import parse_participant_control_evaluation
    from raes_contracts.contracts.participant_control_evaluation_v2 import parse_participant_control_evaluation_v2

    parse = parse_participant_control_evaluation if version == "v1" else parse_participant_control_evaluation_v2
    with pytest.raises(InvalidInputError, match="invalid participant control evaluation") as refused:
        parse(_DUPLICATE_OBJECT)
    assert refused.value.__suppress_context__ is True
    assert SENTINEL not in str(refused.value)
    with pytest.raises(TypeError):
        parse({"schema_version": "participant-control-evaluation/v1"})


@pytest.mark.parametrize("version", ["v1", "v2"])
@pytest.mark.parametrize(
    "source",
    ['{"value":' + "7" * 5000 + "}", '{"value":"\ud800"}'],
    ids=["integer-beyond-digit-limit", "unpaired-surrogate"],
)
def test_participant_control_evaluation_refuses_undecodable_content(version, source):
    from raes_contracts.contracts.participant_control_composition import parse_participant_control_evaluation
    from raes_contracts.contracts.participant_control_evaluation_v2 import parse_participant_control_evaluation_v2

    parse = parse_participant_control_evaluation if version == "v1" else parse_participant_control_evaluation_v2
    with pytest.raises(InvalidInputError, match="invalid participant control evaluation"):
        parse(source)


def test_mixed_composition_ingress_limits_raise_invalid_input():
    from raes_contracts.contracts.mixed_composition import (
        MixedCompositionValidationLimits,
        parse_mixed_composition_profile,
    )

    with pytest.raises(InvalidInputError, match="node limit"):
        parse_mixed_composition_profile('{"a":[1,2,3]}', limits=MixedCompositionValidationLimits(max_json_nodes=2))
    with pytest.raises(StrictJsonIngressError, match="depth limit"):
        parse_mixed_composition_profile('{"a":[[1]]}', limits=MixedCompositionValidationLimits(max_json_depth=2))


def test_run_archive_raises_categories_and_lets_defects_propagate(tmp_path, monkeypatch):
    from raes_operations.run_artifacts import RunMaterializationArchive
    from test_issue_1241_materialized_sdl import materialized_payload

    archive = RunMaterializationArchive(tmp_path / "archive")
    with pytest.raises(InvalidInputError, match="valid bounded SDL") as invalid:
        archive.publish("name: [" + SENTINEL)
    assert invalid.value.__suppress_context__ is True
    assert SENTINEL not in str(invalid.value)

    record = archive.publish(json.dumps(materialized_payload()))
    with pytest.raises(ConflictError, match="already binds different bytes"):
        archive.publish(json.dumps(materialized_payload(description="different")))
    path = tmp_path / "archive" / record.reference.ref_path
    path.write_bytes(path.read_bytes().replace(b"materialized-example", b"materialized-tampered"))
    with pytest.raises(EvidenceIntegrityError, match="do not match the retained record"):
        archive.read(record)

    monkeypatch.setattr("raes.parser.parse_sdl", _fail(KeyError(SENTINEL)))
    with pytest.raises(KeyError):
        archive.publish(json.dumps(materialized_payload()))


# Messages carry no values that the surface must not show (E7).


def test_autonomous_state_violation_names_fields_without_snapshot_values():
    from raes_contracts.participant_autonomous_state import iter_participant_autonomous_state_snapshot_violations

    violations = list(
        iter_participant_autonomous_state_snapshot_violations(
            {"state": {"policy_digest": SENTINEL, SENTINEL: SENTINEL}}
        )
    )
    assert violations
    assert all(SENTINEL not in message for _, message in violations)
    assert any("policy_address" in message for _, message in violations)


def test_stream_address_canonicalization_failure_omits_the_address_value():
    from raes_contracts.contracts.random_stream import StreamAddressModel, TrialCoordinateModel
    from raes_contracts.random_stream_engine import canonical_stream_address_bytes

    oversized = 2**60 + 1678
    address = StreamAddressModel.model_construct(
        namespace="namespace",
        trial_coordinate=TrialCoordinateModel(),
        selection_policy_id="policy",
        variation_point_id="point",
        draw_purpose="purpose",
        local_coordinate=oversized,
    )
    with pytest.raises(ValueError, match="canonicalization failed") as refused:
        canonical_stream_address_bytes(address)
    assert str(oversized) not in str(refused.value)


def test_profile_and_corpus_messages_omit_host_paths(tmp_path, monkeypatch):
    from raes_contracts.random_stream_profiles import load_random_stream_profile_from_path, random_stream_profile_path

    artifact = tmp_path / "profile.json"
    artifact.write_text(random_stream_profile_path("blake3-xof-v1").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="must match") as mismatch:
        load_random_stream_profile_from_path("blake3-xof-participant-v1", artifact)
    assert str(tmp_path) not in str(mismatch.value)

    monkeypatch.setattr(corpus, "_bundled_corpus_root", lambda: None)
    monkeypatch.setattr(corpus, "_source_checkout_corpus_root", lambda: None)
    corpus.corpus_root.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="contract corpus is unavailable") as unavailable:
            corpus.corpus_root()
    finally:
        corpus.corpus_root.cache_clear()
    assert corpus.__file__ not in str(unavailable.value)
