"""Machine-readable semantic comparison and impact analysis (GOV-904)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes.phase_contracts import ResolvedImportProvenance
from raes.scenario import Scenario
from raes_contracts.contracts import (
    ArtifactTransformationCheckModel,
    ArtifactTransformationIdentityMapModel,
    ArtifactTransformationKind,
    ArtifactTransformationPreservationModel,
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
    ExperimentCaptureSpecModel,
    ExperimentRunModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    ExternalConceptBindingDocumentModel,
    PreservationOutcome,
    TransformationCheckOutcome,
    schema_bundle,
)
from raes_contracts.json_ingress import StrictJsonIngressError
from raes_contracts.semantic_comparison import (
    ArtifactKind,
    ComparisonCompleteness,
    DependencyRelation,
    IdentityRelation,
    ImpactClosureStatus,
    RelationStatus,
    ScenarioCoordinateModel,
    SemanticComparisonContextModel,
    SemanticComparisonProfileModel,
    SemanticComparisonRequestModel,
    SemanticComparisonResultModel,
    canonical_impact_scope_digest,
    canonical_semantic_comparison_profile_digest,
    canonical_semantic_comparison_result_digest,
    parse_semantic_comparison_request,
)
from raes_processor.semantic_comparison import (
    analyze_semantic_comparison,
    build_impact_scope,
    coordinate_for_artifact,
)

_ROOT = Path(__file__).resolve().parents[3]
_PROFILE_PATH = _ROOT / "contracts/profiles/semantic-comparison/reference-v2.json"


def _fixture(relative: str, model: type):
    payload = json.loads((_ROOT / relative).read_text(encoding="utf-8"))
    return model.model_validate(payload)


@pytest.fixture(scope="module")
def profile() -> SemanticComparisonProfileModel:
    return SemanticComparisonProfileModel.model_validate_json(_PROFILE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def admitted_artifacts() -> tuple[object, ...]:
    return (
        Scenario(name="scenario-techvault", version="2026-05-26"),
        ResolvedImportProvenance(
            namespace=("arena",),
            requested_source="oci://example.invalid/arena",
            module_id="openrae/arena-module",
            module_version="1.0.0",
            resolved_source="oci://example.invalid/arena@sha256:" + "a" * 64,
            manifest_digest="sha256:" + "b" * 64,
            content_digest="sha256:" + "c" * 64,
            export_hash="sha256:" + "d" * 64,
        ),
        _fixture(
            "contracts/fixtures/experiment-core/experiment-task-v1/valid/reference.json",
            ExperimentTaskModel,
        ),
        _fixture(
            "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json",
            ExperimentRunModel,
        ),
        _fixture(
            "contracts/fixtures/experiment-core/experiment-capture-spec-v1/valid/reference.json",
            ExperimentCaptureSpecModel,
        ),
        _fixture(
            "contracts/fixtures/experiment-core/experiment-study-v1/valid/reference.json",
            ExperimentStudyModel,
        ),
        _fixture(
            "contracts/fixtures/concept-authority/external-concept-bindings-v1/valid/nist-csf.json",
            ExternalConceptBindingDocumentModel,
        ),
    )


def _request(
    profile: SemanticComparisonProfileModel,
    before: object,
    after: object,
    *,
    before_scope: tuple[object, ...] | None = None,
    after_scope: tuple[object, ...] | None = None,
    closure_status: ImpactClosureStatus = ImpactClosureStatus.COMPLETE,
) -> SemanticComparisonRequestModel:
    scope = build_impact_scope(
        before_scope or (before,),
        after_scope or (after,),
        traversal_roots=(coordinate_for_artifact(after).canonical_identity,),
        closure_status=closure_status,
    )
    return SemanticComparisonRequestModel(
        comparison_profile=profile.profile_id,
        comparison_profile_digest=canonical_semantic_comparison_profile_digest(profile),
        analyzer_profile="raes-reference-semantic-comparator/v1",
        before=coordinate_for_artifact(before),
        after=coordinate_for_artifact(after),
        impact_scope=scope,
    )


def test_profile_and_request_are_governed_bounded_portable_contracts(
    profile: SemanticComparisonProfileModel,
    admitted_artifacts: tuple[object, ...],
) -> None:
    before = admitted_artifacts[0]
    request = _request(profile, before, before)
    parsed = parse_semantic_comparison_request(request.model_dump_json())

    assert parsed == request
    assert request.impact_scope.scope_digest == canonical_impact_scope_digest(request.impact_scope)
    with pytest.raises(StrictJsonIngressError, match="duplicate JSON member"):
        parse_semantic_comparison_request('{"schema_version":"x","schema_version":"y"}')
    with pytest.raises(StrictJsonIngressError, match="byte limit"):
        parse_semantic_comparison_request(b"{" + b" " * 1_048_576 + b"}")


def test_owner_specific_adapters_cover_every_admitted_family(
    admitted_artifacts: tuple[object, ...],
) -> None:
    coordinates = tuple(coordinate_for_artifact(artifact) for artifact in admitted_artifacts)

    assert tuple(item.artifact_kind for item in coordinates) == (
        ArtifactKind.SCENARIO,
        ArtifactKind.MODULE,
        ArtifactKind.TASK,
        ArtifactKind.RUN,
        ArtifactKind.EVIDENCE_SPECIFICATION,
        ArtifactKind.STUDY,
        ArtifactKind.EXTERNAL_CONCEPT_BINDINGS,
    )
    assert len({type(item) for item in coordinates}) == 7
    assert all(item.canonical_identity and item.canonical_digest.startswith("sha256:") for item in coordinates)
    with pytest.raises(TypeError, match="admitted RAES artifact"):
        coordinate_for_artifact({"artifact_kind": "scenario", "semantic_digest": "caller-selected"})

    scenario_coordinate = coordinates[0]
    invalid_coordinate = scenario_coordinate.model_copy(
        update={"canonical_identity": "scenario:somebody-else"}
    ).model_dump(mode="json")
    with pytest.raises(ValidationError, match="canonical identity"):
        ScenarioCoordinateModel.model_validate(invalid_coordinate)


def test_typed_artifacts_are_compared_without_caller_supplied_projections(
    profile: SemanticComparisonProfileModel,
) -> None:
    before = Scenario(name="arena", version="1.0.0", description="before")
    after = Scenario(name="arena", version="1.0.0", description="after")
    request = _request(profile, before, after)

    result = analyze_semantic_comparison(profile, request, before, after)

    root = next(change for change in result.changes if change.identity == "scenario:arena")
    assert root.identity_relation == IdentityRelation.SAME
    assert root.textual_relation == RelationStatus.UNKNOWN
    assert root.structural_relation == RelationStatus.UNCHANGED
    assert root.semantic_relation == RelationStatus.UNCHANGED
    assert result.completeness == ComparisonCompleteness.INDETERMINATE
    assert "representation-evidence-missing" in {reason.value for reason in result.reason_codes}


def test_owner_semantics_exclude_module_integrity_and_study_rationale_fields(
    profile: SemanticComparisonProfileModel,
    admitted_artifacts: tuple[object, ...],
) -> None:
    module = admitted_artifacts[1]
    repacked_module = module.model_copy(update={"content_digest": "sha256:" + "e" * 64})
    module_result = analyze_semantic_comparison(
        profile,
        _request(profile, module, repacked_module),
        module,
        repacked_module,
    )
    assert module_result.changes[0].semantic_relation == RelationStatus.UNCHANGED

    study = admitted_artifacts[5]
    membership = dict(study.membership)
    first_key = sorted(membership)[0]
    membership[first_key] = membership[first_key].model_copy(
        update={"inclusion_rationale": "Editorial rationale changed without changing membership."}
    )
    revised_study = study.model_copy(update={"membership": membership})
    study_result = analyze_semantic_comparison(
        profile,
        _request(profile, study, revised_study),
        study,
        revised_study,
    )
    by_identity = {change.identity: change for change in study_result.changes}
    assert by_identity[f"study-member:{first_key}"].semantic_relation == RelationStatus.UNCHANGED


def test_scope_closure_controls_impact_completeness(
    profile: SemanticComparisonProfileModel,
    admitted_artifacts: tuple[object, ...],
) -> None:
    task = admitted_artifacts[2]
    request = _request(profile, task, task, closure_status=ImpactClosureStatus.PARTIAL)

    result = analyze_semantic_comparison(profile, request, task, task)

    assert result.completeness == ComparisonCompleteness.INDETERMINATE
    assert "impact-scope-partial" in {reason.value for reason in result.reason_codes}


def test_dependency_comparison_preserves_before_and_after_resolution(
    profile: SemanticComparisonProfileModel,
    admitted_artifacts: tuple[object, ...],
) -> None:
    before = admitted_artifacts[2]
    after = before.model_copy(
        update={
            "scenario_ref": before.scenario_ref.model_copy(
                update={"ref_id": "scenario-replacement", "ref_version": "2.0.0"}
            )
        }
    )
    request = _request(profile, before, after)

    result = analyze_semantic_comparison(profile, request, before, after)

    dependency = next(item for item in result.dependencies if item.rule_id == "experiment-task-scenario-reference")
    assert dependency.relation == DependencyRelation.CHANGED
    assert dependency.before is not None
    assert dependency.after is not None
    assert dependency.before.dependency_identity == "scenario:scenario-techvault"
    assert dependency.after.dependency_identity == "scenario:scenario-replacement"
    assert dependency.before.provenance_digests != dependency.after.provenance_digests


def test_changed_scenario_emits_rule_named_downstream_impact_path(
    profile: SemanticComparisonProfileModel,
    admitted_artifacts: tuple[object, ...],
) -> None:
    before = admitted_artifacts[0]
    after = before.model_copy(update={"version": "2026-08-01"})
    task = admitted_artifacts[2]
    request = _request(
        profile,
        before,
        after,
        before_scope=(before, task),
        after_scope=(after, task),
    )

    result = analyze_semantic_comparison(
        profile,
        request,
        before,
        after,
        before_scope=(before, task),
        after_scope=(after, task),
    )

    path = next(item for item in result.impact_paths if item.affected_identity.startswith("task:"))
    assert path.source_identity == "scenario:scenario-techvault"
    assert path.steps[0].rule_id == "experiment-task-scenario-reference"
    assert path.steps[0].evidence_side == "after"


def test_rename_requires_successful_digest_profile_and_phase_bound_evidence(
    profile: SemanticComparisonProfileModel,
) -> None:
    before = Scenario(name="old", version="1.0.0")
    after = Scenario(name="new", version="1.0.0")
    request = _request(profile, before, after)
    report = ArtifactTransformationReportModel(
        operation_profile="scenario-rename/v1",
        status=ArtifactTransformationStatus.SUCCESS,
        artifact_kind=ArtifactTransformationKind.PORTABLE_CONTRACT,
        source_profile="sdl-normalized-authoring/v1",
        target_profile="sdl-normalized-authoring/v1",
        canonicalization_profile="raes-canonical-sdl/v2",
        source_digest=request.before.canonical_digest,
        target_digest=request.after.canonical_digest,
        policy_digest="sha256:" + "a" * 64,
        derivation_digest="sha256:" + "b" * 64,
        preconditions=(
            ArtifactTransformationCheckModel(
                check_id="source-admitted",
                outcome=TransformationCheckOutcome.PASSED,
            ),
        ),
        affected_identities=("scenario:new", "scenario:old"),
        identity_map=(
            ArtifactTransformationIdentityMapModel(
                declaration_kind="scenario",
                before="scenario:old",
                after="scenario:new",
            ),
        ),
        preservation=ArtifactTransformationPreservationModel(
            profile="semantic-preservation/v1",
            outcome=PreservationOutcome.VERIFIED,
            evidence_digests=("sha256:" + "c" * 64,),
        ),
    )

    result = analyze_semantic_comparison(
        profile,
        request,
        before,
        after,
        context=SemanticComparisonContextModel(transformation_report=report),
    )

    assert len(result.changes) == 1
    assert result.changes[0].identity_relation == IdentityRelation.RENAMED

    mismatched = report.model_copy(update={"source_profile": "different-phase/v1"})
    rejected = analyze_semantic_comparison(
        profile,
        request,
        before,
        after,
        context=SemanticComparisonContextModel(transformation_report=mismatched),
    )
    assert {change.identity_relation for change in rejected.changes} == {
        IdentityRelation.ADDED,
        IdentityRelation.REMOVED,
    }


def test_profile_digest_mismatch_is_rejected_before_analysis(
    profile: SemanticComparisonProfileModel,
) -> None:
    scenario = Scenario(name="arena", version="1.0.0")
    request = _request(profile, scenario, scenario).model_copy(
        update={"comparison_profile_digest": "sha256:" + "0" * 64}
    )

    with pytest.raises(ValueError, match="comparison profile digest"):
        analyze_semantic_comparison(profile, request, scenario, scenario)


def test_published_schemas_and_fixtures_validate() -> None:
    bundle = schema_bundle()
    request_schema = bundle["semantic-comparison-request-v1"]
    result_schema = bundle["semantic-comparison-result-v1"]
    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator.check_schema(result_schema)

    fixture_root = _ROOT / "contracts/fixtures/semantic-comparison"
    for fixture in sorted((fixture_root / "semantic-comparison-request-v1/valid").glob("*.json")):
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        Draft202012Validator(request_schema).validate(payload)
        SemanticComparisonRequestModel.model_validate(payload)
    for fixture in sorted((fixture_root / "semantic-comparison-result-v1/valid").glob("*.json")):
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        Draft202012Validator(result_schema).validate(payload)
        result = SemanticComparisonResultModel.model_validate(payload)
        assert canonical_semantic_comparison_result_digest(result).startswith("sha256:")

    invalid_families = (
        (
            fixture_root / "semantic-comparison-request-v1/invalid",
            request_schema,
            SemanticComparisonRequestModel,
        ),
        (
            fixture_root / "semantic-comparison-result-v1/invalid",
            result_schema,
            SemanticComparisonResultModel,
        ),
    )
    expected_model_errors = {
        "filesystem-path-coordinate.json": (("before", "scenario", "canonical_identity"), "string_pattern_mismatch"),
        "path-without-edges.json": (("impact_paths", 0, "steps"), "too_short"),
    }
    for fixture_dir, schema, model in invalid_families:
        for fixture in sorted(fixture_dir.glob("*.json")):
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            assert Draft202012Validator(schema).is_valid(payload) is False
            with pytest.raises(ValidationError) as exc_info:
                model.model_validate(payload)
            expected_location, expected_type = expected_model_errors[fixture.name]
            assert (expected_location, expected_type) in {
                (error["loc"], error["type"]) for error in exc_info.value.errors()
            }


def test_result_contract_rejects_scope_digest_tampering(
    profile: SemanticComparisonProfileModel,
) -> None:
    scenario = Scenario(name="arena", version="1.0.0")
    request = _request(profile, scenario, scenario)
    result = analyze_semantic_comparison(profile, request, scenario, scenario)
    invalid_result = result.model_copy(update={"impact_scope_digest": "sha256:" + "f" * 64}).model_dump(mode="json")

    with pytest.raises(ValidationError, match="scope digest"):
        SemanticComparisonResultModel.model_validate(invalid_result)
