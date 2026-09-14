"""Source-neutral SDL candidate synthesis contracts and pipeline (issue #988)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import admit_instantiated_scenario, instantiate_scenario, parse_sdl
from raes.candidate_synthesis import SYNTHESIS_PROFILE, synthesize_sdl_candidate
from raes_conformance.conformance import validate_contract_payload
from raes_contracts.candidate_synthesis import parse_candidate_synthesis_input
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ArtifactTransformationLossKind,
    CandidateSynthesisAssumptionModel,
    CandidateSynthesisDecisionModel,
    CandidateSynthesisInputModel,
    CandidateSynthesisProfileCoordinateModel,
    CandidateSynthesisProfileDefinitionModel,
    CandidateSynthesisRecordModel,
    CandidateSynthesisSourceModel,
    CandidateSynthesisTargetModel,
    ConceptSourceAssertionModel,
    ExternalConceptSchemeCoordinateModel,
    SynthesisContributionKind,
    schema_bundle,
)
from raes_contracts.json_ingress import StrictJsonIngressError
from raes_contracts.semantic_comparison import (
    ImpactClosureStatus,
    RelationStatus,
    SemanticComparisonProfileModel,
    SemanticComparisonRequestModel,
    canonical_semantic_comparison_profile_digest,
)
from raes_processor.semantic_comparison import (
    analyze_semantic_comparison,
    build_impact_scope,
    coordinate_for_artifact,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "fixtures" / "candidate-synthesis" / "sdl-candidate-synthesis-input-v1"
VALID_ROOT = FIXTURE_ROOT / "valid"
INVALID_ROOT = FIXTURE_ROOT / "invalid"
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "candidate-synthesis" / "sdl-candidate-synthesis-input-v1.json"
RECORD_SCHEMA_PATH = (
    REPO_ROOT / "contracts" / "schemas" / "candidate-synthesis" / "sdl-candidate-synthesis-record-v1.json"
)
PROFILE_PATH = REPO_ROOT / "contracts" / "profiles" / "candidate-synthesis" / "concept-nodes-v1.json"
PROFILE_SCHEMA_PATH = (
    REPO_ROOT / "contracts" / "schemas" / "candidate-synthesis" / "sdl-candidate-synthesis-profile-v1.json"
)


def _profile(profile_id: str, version: str) -> CandidateSynthesisProfileCoordinateModel:
    digest = canonical_json_digest({"profile_id": profile_id, "version": version})
    return CandidateSynthesisProfileCoordinateModel(
        profile_id=profile_id,
        version=version,
        digest=digest,
    )


def _candidate_input(
    *,
    authority: str,
    scheme_id: str,
    assertion_format: str,
    concept_id: str,
) -> CandidateSynthesisInputModel:
    source_digest = canonical_json_digest(
        {
            "assertion_format": assertion_format,
            "authority": authority,
            "concept_id": concept_id,
            "scheme_id": scheme_id,
        }
    )
    assertions = (
        ConceptSourceAssertionModel(
            kind="concept",
            assertion_id="source-web",
            concept=ExternalConceptSchemeCoordinateModel(
                scheme_id=scheme_id,
                authority=authority,
                revision="2026.08",
                source_digest=source_digest,
                concept_id=concept_id,
            ),
        ),
    )
    return CandidateSynthesisInputModel(
        input_id="external-web-candidate",
        input_version="1",
        source=CandidateSynthesisSourceModel(
            source_id="external-knowledge",
            authority=authority,
            scheme_id=scheme_id,
            assertion_format=assertion_format,
            revision="2026.08",
            content_digest=source_digest,
            assertion_set_digest=canonical_json_digest([item.model_dump(mode="json") for item in assertions]),
            extraction_query=_profile("source-query/v1", "1"),
            adapter=_profile("source-adapter/v1", "1"),
            information_flow_policy_refs=(_profile("source-information-flow/v1", "1"),),
        ),
        assertions=assertions,
        target=CandidateSynthesisTargetModel(
            scenario_id="external-web",
            scenario_version="1.0.0",
        ),
        transformation_profile=SYNTHESIS_PROFILE.coordinate(),
        policy_digest=canonical_json_digest({"accepted_losses": []}),
        decisions=(
            CandidateSynthesisDecisionModel(
                decision_id="emit-web-node",
                actor_kind="author",
                actor_ref="author:reviewer",
                assertion_ids=("source-web",),
                target_ref="nodes.web",
                node_type="compute",
                basis="The source concept is intentionally authored as one compute node.",
            ),
        ),
    )


def test_unrelated_source_formats_use_one_contract_and_reproduce_candidate() -> None:
    attack = _candidate_input(
        authority="mitre",
        scheme_id="attack-enterprise",
        assertion_format="stix-bundle/2.1",
        concept_id="TA0002",
    )
    csf = _candidate_input(
        authority="nist",
        scheme_id="cybersecurity-framework",
        assertion_format="json-catalog/1",
        concept_id="PR.PS",
    )

    first = synthesize_sdl_candidate(attack)
    replay = synthesize_sdl_candidate(attack)
    unrelated = synthesize_sdl_candidate(csf)

    assert first.succeeded
    assert first.candidate_content == replay.candidate_content == unrelated.candidate_content
    assert first.record.candidate_exact_digest == replay.record.candidate_exact_digest
    assert first.record.candidate_canonical_digest == unrelated.record.candidate_canonical_digest
    assert (
        first.record.transformation_report.derivation_digest != unrelated.record.transformation_report.derivation_digest
    )
    assert parse_candidate_synthesis_input(attack.model_dump_json()) == attack
    assert first.record.input.source.information_flow_policy_refs == attack.source.information_flow_policy_refs


def test_candidate_reenters_ordinary_parse_and_instantiated_admission() -> None:
    result = synthesize_sdl_candidate(
        _candidate_input(
            authority="mitre",
            scheme_id="attack-enterprise",
            assertion_format="stix-bundle/2.1",
            concept_id="TA0002",
        )
    )

    assert result.candidate_content is not None
    reparsed = parse_sdl(result.candidate_content)
    instantiated = instantiate_scenario(reparsed)
    readmitted = admit_instantiated_scenario(instantiated.model_dump(mode="python"))

    assert reparsed.semantic_validated
    assert readmitted.semantic_validated
    assert readmitted.nodes["web"].type == "compute"


def test_construct_trace_keeps_source_inference_and_author_decision_distinct() -> None:
    result = synthesize_sdl_candidate(
        _candidate_input(
            authority="nist",
            scheme_id="cybersecurity-framework",
            assertion_format="json-catalog/1",
            concept_id="PR.PS",
        )
    )

    contributions = result.record.construct_traces[0].contributions
    assert tuple(item.kind for item in contributions) == (
        SynthesisContributionKind.IMPORTED_ASSERTION,
        SynthesisContributionKind.INFERRED_STRUCTURE,
        SynthesisContributionKind.AUTHOR_DECISION,
    )
    assert len({item.ref_id for item in contributions}) == 3


def test_profile_digest_binds_the_complete_published_transformation_artifact() -> None:
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile = CandidateSynthesisProfileDefinitionModel.model_validate(payload)
    published_schema = json.loads(PROFILE_SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(published_schema).validate(payload)
    assert profile == SYNTHESIS_PROFILE
    assert profile.profile_digest == canonical_json_digest(profile.model_dump(mode="json", exclude={"profile_digest"}))
    assert schema_bundle()["sdl-candidate-synthesis-profile-v1"] == published_schema
    assert validate_contract_payload("sdl-candidate-synthesis-profile-v1", payload) == ()
    for path in sorted(VALID_ROOT.glob("*.json")):
        candidate_input = CandidateSynthesisInputModel.model_validate_json(path.read_text(encoding="utf-8"))
        assert candidate_input.transformation_profile == profile.coordinate()

    changed_rule = json.loads(json.dumps(payload))
    changed_rule["rule_ids"] = ["alternate-node-emission", "concept-node-emission"]
    with pytest.raises(ValidationError, match="profile_digest does not match"):
        CandidateSynthesisProfileDefinitionModel.model_validate(changed_rule)


def test_unsupported_relation_emits_schema_admitted_semantic_omission() -> None:
    candidate_input = CandidateSynthesisInputModel.model_validate_json(
        (INVALID_ROOT / "unsupported-relation.json").read_text(encoding="utf-8")
    )

    report = synthesize_sdl_candidate(candidate_input).record.transformation_report
    payload = report.model_dump(mode="json")
    published_schema = json.loads(
        (
            REPO_ROOT / "contracts" / "schemas" / "artifact-transformations" / "artifact-transformation-report-v1.json"
        ).read_text(encoding="utf-8")
    )

    assert [(loss.kind, loss.affected_identity) for loss in report.losses] == [
        (ArtifactTransformationLossKind.SEMANTIC_OMISSION, "source-relation")
    ]
    assert report.losses[0].diagnostic.code == "candidate-synthesis.semantic-omission"
    Draft202012Validator(published_schema).validate(payload)
    assert validate_contract_payload("artifact-transformation-report-v1", payload) == ()


@pytest.mark.parametrize("path", sorted(VALID_ROOT.glob("*.json")), ids=lambda path: path.stem)
def test_positive_fixtures_share_published_contract_and_are_byte_stable(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidate_input = CandidateSynthesisInputModel.model_validate(payload)
    published_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(published_schema).validate(payload)
    first = synthesize_sdl_candidate(candidate_input)
    replay = synthesize_sdl_candidate(candidate_input)

    assert first.succeeded
    assert first.candidate_content == replay.candidate_content
    assert first.record == replay.record
    assert schema_bundle()["sdl-candidate-synthesis-input-v1"] == published_schema
    assert validate_contract_payload("sdl-candidate-synthesis-input-v1", payload) == ()


def test_synthesis_record_is_published_and_structurally_admitted() -> None:
    candidate_input = CandidateSynthesisInputModel.model_validate_json(
        (VALID_ROOT / "attack-enterprise.json").read_text(encoding="utf-8")
    )
    record = synthesize_sdl_candidate(candidate_input).record
    payload = record.model_dump(mode="json")
    published_schema = json.loads(RECORD_SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(published_schema).validate(payload)
    assert schema_bundle()["sdl-candidate-synthesis-record-v1"] == published_schema
    assert validate_contract_payload("sdl-candidate-synthesis-record-v1", payload) == ()


def test_record_recomputes_input_digest_and_resolves_every_contribution_owner() -> None:
    candidate_input = CandidateSynthesisInputModel.model_validate_json(
        (VALID_ROOT / "attack-enterprise.json").read_text(encoding="utf-8")
    )
    payload = synthesize_sdl_candidate(candidate_input).record.model_dump(mode="json")
    changed_input = json.loads(json.dumps(payload))
    changed_input["input"]["target"]["scenario_version"] = "2.0.0"
    dangling_trace = json.loads(json.dumps(payload))
    dangling_trace["construct_traces"][0]["contributions"][0]["ref_id"] = "missing-source-assertion"

    with pytest.raises(ValidationError, match="input_digest does not match"):
        CandidateSynthesisRecordModel.model_validate(changed_input)
    with pytest.raises(ValidationError, match="construct contribution reference does not resolve"):
        CandidateSynthesisRecordModel.model_validate(dangling_trace)


def test_assumptions_are_distinct_resolved_construct_contributions() -> None:
    candidate_input = _candidate_input(
        authority="mitre",
        scheme_id="attack-enterprise",
        assertion_format="stix-bundle/2.1",
        concept_id="TA0002",
    )
    with_assumption = CandidateSynthesisInputModel.model_validate(
        {
            **candidate_input.model_dump(mode="json"),
            "assumptions": [
                CandidateSynthesisAssumptionModel(
                    assumption_id="source-is-current",
                    assertion_ids=("source-web",),
                    statement="The pinned source assertion is the intended authoring basis.",
                ).model_dump(mode="json")
            ],
        }
    )

    record = synthesize_sdl_candidate(with_assumption).record

    assert any(
        item.kind == SynthesisContributionKind.TRANSFORMATION_ASSUMPTION and item.ref_id == "source-is-current"
        for item in record.construct_traces[0].contributions
    )


@pytest.mark.parametrize(
    ("filename", "reason"),
    [
        ("ambiguous-ordering.json", "ambiguous-ordering"),
        ("missing-native-semantics.json", "missing-native-semantics"),
        ("unsupported-relation.json", "unsupported-relation"),
        ("unresolved-parameterization.json", "unresolved-parameterization"),
        ("non-reproducible-transformation.json", "transformation-profile-unavailable"),
    ],
)
def test_negative_fixtures_refuse_without_partial_candidate(filename: str, reason: str) -> None:
    candidate_input = CandidateSynthesisInputModel.model_validate_json(
        (INVALID_ROOT / filename).read_text(encoding="utf-8")
    )

    result = synthesize_sdl_candidate(candidate_input)

    assert not result.succeeded
    assert result.candidate is None
    assert result.candidate_content is None
    assert result.record.candidate_exact_digest is None
    assert result.record.candidate_canonical_digest is None
    assert reason in {item.reason.value for item in result.record.unresolved_choices}


def test_stale_input_fixture_fails_closed_at_the_contract_join() -> None:
    payload = json.loads((INVALID_ROOT / "stale-input.json").read_text(encoding="utf-8"))

    with pytest.raises(ValidationError, match="stale against the pinned source envelope"):
        CandidateSynthesisInputModel.model_validate(payload)


def test_bounded_ingress_rejects_duplicate_members_and_excess_bytes() -> None:
    with pytest.raises(StrictJsonIngressError, match="duplicate JSON member"):
        parse_candidate_synthesis_input('{"schema_version":"x","schema_version":"y"}')
    with pytest.raises(StrictJsonIngressError, match="byte limit"):
        parse_candidate_synthesis_input(b"{" + b" " * 128 + b"}", max_bytes=64)


def test_changed_derivation_and_sdl_semantics_are_separate_axes() -> None:
    before_input = _candidate_input(
        authority="mitre",
        scheme_id="attack-enterprise",
        assertion_format="stix-bundle/2.1",
        concept_id="TA0002",
    )
    after_input = _candidate_input(
        authority="nist",
        scheme_id="cybersecurity-framework",
        assertion_format="json-catalog/1",
        concept_id="PR.PS",
    )
    before = synthesize_sdl_candidate(before_input)
    after = synthesize_sdl_candidate(after_input)
    profile = SemanticComparisonProfileModel.model_validate_json(
        (REPO_ROOT / "contracts" / "profiles" / "semantic-comparison" / "reference-v2.json").read_text(encoding="utf-8")
    )
    assert before.candidate is not None
    assert after.candidate is not None
    scope = build_impact_scope(
        (before.candidate,),
        (after.candidate,),
        traversal_roots=(coordinate_for_artifact(after.candidate).canonical_identity,),
        closure_status=ImpactClosureStatus.COMPLETE,
    )
    request = SemanticComparisonRequestModel(
        comparison_profile=profile.profile_id,
        comparison_profile_digest=canonical_semantic_comparison_profile_digest(profile),
        analyzer_profile=profile.analyzer_profile,
        before=coordinate_for_artifact(before.candidate),
        after=coordinate_for_artifact(after.candidate),
        impact_scope=scope,
    )

    comparison = analyze_semantic_comparison(profile, request, before.candidate, after.candidate)
    root = next(item for item in comparison.changes if item.identity == "scenario:external-web")

    assert before.record.transformation_report.derivation_digest != after.record.transformation_report.derivation_digest
    assert root.semantic_relation == RelationStatus.UNCHANGED
