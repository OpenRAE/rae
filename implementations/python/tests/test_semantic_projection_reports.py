"""Scheme-neutral semantic projection and report tests for issue #987."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes.external_concept_subjects import external_concept_subjects
from raes.scenarios import load_scenario
from raes_conformance.conformance.validators import _STRUCTURAL_ONLY_VALIDATORS, validate_contract_payload
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    ArtifactTransformationCheckModel,
    ArtifactTransformationKind,
    ArtifactTransformationPreservationModel,
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
    ExperimentEvidenceRecordModel,
    ExternalConceptBindingDocumentModel,
    ExternalConceptSubjectModel,
    PreservationOutcome,
    PropositionTruthResultModel,
    SemanticProjectionBindingCoordinateModel,
    SemanticProjectionEvidenceBoundaryModel,
    SemanticProjectionFrameModel,
    SemanticProjectionNotApplicableCoordinateModel,
    SemanticProjectionPerspectiveModel,
    SemanticProjectionPredicateProfileModel,
    SemanticProjectionQuantifierModel,
    SemanticProjectionReportModel,
    SemanticProjectionSchemeScopeModel,
    SemanticProjectionSubjectScopeModel,
    SemanticProjectionWitnessModel,
    TransformationCheckOutcome,
    ValidationBasisDisclosureDocumentModel,
    canonical_semantic_projection_frame_digest,
    governed_semantic_projection_predicate_profile,
)
from raes_contracts.external_concept_bindings import (
    adapt_attack_enterprise_tactics_snapshot,
    adapt_nist_csf_defensive_categories_snapshot,
)
from raes_contracts.semantic_projection import (
    adapt_admitted_semantic_projection_fact,
    adapt_declared_semantic_projection_fact,
    adapt_observed_semantic_projection_fact,
    adapt_verified_semantic_projection_fact,
    project_semantic_concepts,
    semantic_projection_declared_configuration_coordinate,
    semantic_projection_observed_state_coordinate,
    semantic_projection_transformation_coordinate,
)
from raes_contracts.vocabulary_sources import (
    load_attack_enterprise_tactics_source,
    load_nist_csf_defensive_categories_source,
)
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
BINDING_FIXTURES = REPO_ROOT / "contracts" / "fixtures" / "concept-authority" / "external-concept-bindings-v1"
SUBJECT_PATH = BINDING_FIXTURES / "context" / "subject.sdl.yaml"
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "concept-authority" / "semantic-projection-report-v1.json"
_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64
_DIGEST_D = "sha256:" + "d" * 64


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document(filename: str) -> ExternalConceptBindingDocumentModel:
    return ExternalConceptBindingDocumentModel.model_validate(_load_json(BINDING_FIXTURES / "valid" / filename))


def _subject(document: ExternalConceptBindingDocumentModel):
    expected = next(iter(document.bindings.values())).subject
    subjects = external_concept_subjects(load_scenario(SUBJECT_PATH))
    return next((subject for subject in subjects if subject == expected), expected)


def _profile(
    predicate_id: str,
    *,
    allow_approximate_bindings: bool = True,
    allow_lossy_bindings: bool = True,
) -> SemanticProjectionPredicateProfileModel:
    return governed_semantic_projection_predicate_profile(
        predicate_id,
        allow_approximate_bindings=allow_approximate_bindings,
        allow_lossy_bindings=allow_lossy_bindings,
    )


def _owner_subject(
    *,
    subject_kind: str,
    owning_contract_id: str,
    lifecycle_phase: str,
    canonical_ref: str,
    artifact_digest: str,
) -> ExternalConceptSubjectModel:
    return ExternalConceptSubjectModel(
        subject_kind=subject_kind,
        owning_contract_id=owning_contract_id,
        lifecycle_phase=lifecycle_phase,
        canonical_ref=canonical_ref,
        artifact_digest=artifact_digest,
    )


def _rebind_document(
    document: ExternalConceptBindingDocumentModel,
    subject: ExternalConceptSubjectModel,
) -> ExternalConceptBindingDocumentModel:
    binding_id, binding = next(iter(document.bindings.items()))
    payload = document.model_dump(mode="json")
    payload["bindings"][binding_id] = binding.model_copy(update={"subject": subject}).model_dump(mode="json")
    return ExternalConceptBindingDocumentModel.model_validate(payload)


def _observed_owner(
    document: ExternalConceptBindingDocumentModel,
    result: PropositionTruthResultModel,
) -> tuple[ExternalConceptBindingDocumentModel, ExternalConceptSubjectModel, PropositionTruthResultModel]:
    payload = result.model_dump(mode="json")
    payload["temporal_context"] = {
        "boundary_ref": "evidence-cut-1",
        "time_domain": "logical",
        "clock_authority": "run-clock",
    }
    result = PropositionTruthResultModel.model_validate(payload)
    digest = canonical_json_digest(result.model_dump(mode="json"))
    subject = _owner_subject(
        subject_kind="proposition-truth-result",
        owning_contract_id="proposition-truth-result-v1",
        lifecycle_phase="observed",
        canonical_ref=result.result_id,
        artifact_digest=digest,
    )
    return _rebind_document(document, subject), subject, result


def _evidence_boundary(boundary_id: str = "internal-evidence") -> SemanticProjectionEvidenceBoundaryModel:
    return SemanticProjectionEvidenceBoundaryModel(
        boundary_id=boundary_id,
        boundary_revision="1",
        boundary_digest=_DIGEST_C,
        freshness_policy_id="exact-cut-no-ambient-clock",
        freshness_policy_revision="1",
        freshness_policy_digest=_DIGEST_D,
        evaluation_cut_ref="evidence-cut-1",
        time_domain="logical",
        clock_authority="run-clock",
    )


def _frame(
    document: ExternalConceptBindingDocumentModel,
    snapshot,
    *,
    predicate_id: str = "declared",
    quantifier: str = "existential",
    perspective_kind: str = "author",
    evidence_boundary_id: str = "internal-evidence",
    allow_approximate_bindings: bool = True,
    allow_lossy_bindings: bool = True,
    scope_complete: bool = True,
    observed_results: tuple[PropositionTruthResultModel, ...] = (),
    transformation_reports: tuple[ArtifactTransformationReportModel, ...] = (),
) -> SemanticProjectionFrameModel:
    subject = _subject(document)
    participant = perspective_kind == "participant"
    evidence_boundary = _evidence_boundary(evidence_boundary_id)
    transformations = tuple(
        sorted(
            (semantic_projection_transformation_coordinate(report) for report in transformation_reports),
            key=lambda item: (
                item.transformation_id,
                item.transformation_version,
                item.transformation_digest,
            ),
        )
    )
    return SemanticProjectionFrameModel(
        scheme=SemanticProjectionSchemeScopeModel(
            scheme_id=snapshot.scheme_id,
            authority=snapshot.authority,
            revision=snapshot.revision,
            source_digest=snapshot.source_digest,
            included_concept_ids=(next(iter(document.bindings.values())).scheme.concept_id,),
        ),
        subject_scope=SemanticProjectionSubjectScopeModel(
            subject_kind=subject.subject_kind,
            owning_contract_id=subject.owning_contract_id,
            lifecycle_phase=subject.lifecycle_phase,
            artifact_digests=(subject.artifact_digest,),
            complete=scope_complete,
        ),
        predicate_profile=_profile(
            predicate_id,
            allow_approximate_bindings=allow_approximate_bindings,
            allow_lossy_bindings=allow_lossy_bindings,
        ),
        perspective=SemanticProjectionPerspectiveModel(
            perspective_kind=perspective_kind,
            party_ref="participants.blue" if participant else "authors.reference",
            participant_address="participants.blue" if participant else None,
            episode_id="episode-1" if participant else None,
            audience_ref="audiences.blue" if participant else None,
            projection_policy_id="participant-boundary-flow/v1" if participant else None,
            projection_policy_revision="1" if participant else None,
            projection_policy_digest=_DIGEST_C if participant else None,
            applicable_cut_ref="cut-7" if participant else None,
        ),
        configuration=(
            semantic_projection_declared_configuration_coordinate((subject,))
            if predicate_id == "declared"
            else SemanticProjectionNotApplicableCoordinateModel(
                posture="not-applicable",
                basis_ref=f"{predicate_id}-configuration-not-applicable",
            )
        ),
        state=(
            semantic_projection_observed_state_coordinate(
                observed_results,
                evaluation_cut_ref=evidence_boundary.evaluation_cut_ref,
            )
            if predicate_id == "observed"
            else SemanticProjectionNotApplicableCoordinateModel(
                posture="not-applicable",
                basis_ref=f"{predicate_id}-state-not-applicable",
            )
        ),
        quantifier=SemanticProjectionQuantifierModel(
            kind=quantifier,
            quantified_unit="distinct-native-subjects",
            threshold=1 if quantifier == "threshold" else None,
        ),
        evidence_boundary=evidence_boundary,
        binding=SemanticProjectionBindingCoordinateModel(
            schema_version=document.schema_version,
            binding_set_id=document.binding_set_id,
            binding_set_version=document.binding_set_version,
            binding_set_digest=canonical_json_digest(document.model_dump(mode="json")),
        ),
        transformations=transformations,
    )


@pytest.mark.parametrize(
    ("fixture_name", "snapshot_factory"),
    [
        (
            "attack-enterprise.json",
            lambda: adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source()),
        ),
        (
            "nist-csf.json",
            lambda: adapt_nist_csf_defensive_categories_snapshot(load_nist_csf_defensive_categories_source()),
        ),
    ],
)
def test_unrelated_schemes_use_the_same_projection_and_report_contract(fixture_name: str, snapshot_factory) -> None:
    document = _document(fixture_name)
    subject = _subject(document)
    snapshot = snapshot_factory()

    report = project_semantic_concepts(
        _frame(document, snapshot),
        document=document,
        subjects=(subject,),
        scheme_snapshot=snapshot,
        native_facts=(adapt_declared_semantic_projection_fact(subject),),
    )

    included_row = next(row for row in report.rows if row.concept_id in report.frame.scheme.included_concept_ids)
    assert included_row.classification == "witness"
    assert included_row.witnesses[0].subject == subject
    assert included_row.witnesses[0].evidence_digests
    assert report.summary.included_denominator == 1
    assert report.summary.witness_count == 1
    assert report.summary.qualified_fraction.startswith("declared:")
    assert not {"coverage", "coverage_percent", "score", "quality", "maturity"} & set(report.model_dump(mode="json"))


def _evidence_record(evidence_ref: str, source_digest: str) -> ExperimentEvidenceRecordModel:
    payload = _load_json(
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "experiment-core"
        / "experiment-evidence-record-v1"
        / "valid"
        / "reference.json"
    )
    payload["evidence_record_id"] = evidence_ref
    payload["capture_window_ref"] = "evidence-cut-1"
    payload["source_refs"] = [
        {
            "ref_kind": "other",
            "ref_id": "semantic-projection-owner",
            "ref_version": "1",
            "ref_digest": source_digest,
        }
    ]
    return ExperimentEvidenceRecordModel.model_validate(payload)


def _evidence_resolver(*records: ExperimentEvidenceRecordModel):
    by_ref = {record.evidence_record_id: record for record in records}
    by_ref.update({canonical_json_digest(record.model_dump(mode="json")): record for record in records})

    def resolve(*, evidence_ref: str, evidence_boundary: SemanticProjectionEvidenceBoundaryModel):
        assert evidence_boundary.evaluation_cut_ref == "evidence-cut-1"
        return by_ref.get(evidence_ref)

    return resolve


def _verified_report(
    subject: ExternalConceptSubjectModel,
    *,
    profile: SemanticProjectionPredicateProfileModel,
    evidence_digest: str,
) -> ArtifactTransformationReportModel:
    return ArtifactTransformationReportModel(
        operation_profile="verify-semantic-predicate/v1",
        status=ArtifactTransformationStatus.SUCCESS,
        artifact_kind=ArtifactTransformationKind.PORTABLE_CONTRACT,
        source_profile="external-concept-bindings/v1",
        target_profile="external-concept-bindings/v1",
        canonicalization_profile="rfc8785-jcs-sha256/v1",
        source_digest=subject.artifact_digest,
        target_digest=subject.artifact_digest,
        policy_digest=profile.profile_digest,
        derivation_digest=_DIGEST_C,
        preconditions=(
            ArtifactTransformationCheckModel(
                check_id="source-admitted",
                outcome=TransformationCheckOutcome.PASSED,
            ),
        ),
        preservation=ArtifactTransformationPreservationModel(
            profile="semantic-predicate-witness/v1",
            outcome=PreservationOutcome.VERIFIED,
            evidence_digests=(evidence_digest,),
        ),
        affected_identities=(subject.canonical_ref,),
    )


def test_native_predicate_views_are_independent_and_never_form_a_ladder() -> None:
    base_document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    declared_subject = _subject(base_document)
    validation = ValidationBasisDisclosureDocumentModel.model_validate(
        _load_json(
            REPO_ROOT
            / "contracts"
            / "fixtures"
            / "profiles"
            / "validation-basis-disclosure-v1"
            / "valid"
            / "structural-scenario.json"
        )
    )
    truth = PropositionTruthResultModel.model_validate(
        _load_json(
            REPO_ROOT
            / "contracts"
            / "fixtures"
            / "control-plane"
            / "proposition-truth-result-v1"
            / "valid"
            / "positive-observed.json"
        )
    )
    disclosure_digest = canonical_json_digest(validation.model_dump(mode="json"))
    admitted_subject = _owner_subject(
        subject_kind=validation.disclosure.subject_kind,
        owning_contract_id="validation-basis-disclosure-v1",
        lifecycle_phase="reported",
        canonical_ref=validation.disclosure.subject_ref.ref_id,
        artifact_digest=disclosure_digest,
    )
    admitted_document = _rebind_document(base_document, admitted_subject)
    observed_document, observed_subject, truth = _observed_owner(base_document, truth)
    assert truth.probe_binding is not None
    observed_evidence = _evidence_record(truth.evidence_refs[0], truth.probe_binding.artifact_digest)
    observed_resolver = _evidence_resolver(observed_evidence)
    verified_profile = _profile("verified")
    verified_evidence = _evidence_record("verified-semantic-evidence", declared_subject.artifact_digest)
    verified_resolver = _evidence_resolver(verified_evidence)
    transformation = _verified_report(
        declared_subject,
        profile=verified_profile,
        evidence_digest=canonical_json_digest(verified_evidence.model_dump(mode="json")),
    )
    cases = {
        "declared": (
            base_document,
            declared_subject,
            adapt_declared_semantic_projection_fact(declared_subject),
            None,
        ),
        "admitted": (
            admitted_document,
            admitted_subject,
            adapt_admitted_semantic_projection_fact(admitted_subject, validation),
            None,
        ),
        "observed": (
            observed_document,
            observed_subject,
            adapt_observed_semantic_projection_fact(
                observed_subject,
                truth,
                evidence_boundary=_evidence_boundary(),
                evidence_resolver=observed_resolver,
            ),
            observed_resolver,
        ),
        "verified": (
            base_document,
            declared_subject,
            adapt_verified_semantic_projection_fact(
                declared_subject,
                transformation,
                evidence_boundary=_evidence_boundary(),
                predicate_profile=verified_profile,
                evidence_resolver=verified_resolver,
            ),
            verified_resolver,
        ),
    }
    reports = {}
    for predicate, (document, subject, fact, evidence_resolver) in cases.items():
        reports[predicate] = project_semantic_concepts(
            _frame(
                document,
                snapshot,
                predicate_id=predicate,
                observed_results=(truth,) if predicate == "observed" else (),
                transformation_reports=(transformation,) if predicate == "verified" else (),
            ),
            document=document,
            subjects=(subject,),
            scheme_snapshot=snapshot,
            native_facts=(fact,),
            evidence_resolver=evidence_resolver,
        )

    assert all(report.summary.witness_count == 1 for report in reports.values())
    assert len({report.frame_digest for report in reports.values()}) == 4
    declared_only = project_semantic_concepts(
        _frame(base_document, snapshot, predicate_id="verified"),
        document=base_document,
        subjects=(declared_subject,),
        scheme_snapshot=snapshot,
        native_facts=(),
    )
    assert declared_only.summary.unknown_count == 1
    assert declared_only.summary.witness_count == 0


def test_frame_digest_changes_without_mutating_native_semantics() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    subject = _subject(document)
    alternate_subject = subject.model_copy(update={"artifact_digest": _DIGEST_D})
    alternate_document = _rebind_document(document, alternate_subject)
    frames = (
        _frame(document, snapshot),
        _frame(alternate_document, snapshot),
        _frame(document, snapshot, perspective_kind="observer"),
        _frame(document, snapshot, quantifier="universal"),
        _frame(document, snapshot, evidence_boundary_id="public-redacted-evidence"),
    )

    assert len({canonical_semantic_projection_frame_digest(frame) for frame in frames}) == len(frames)
    assert frames[0].configuration != frames[1].configuration


def test_declared_configuration_coordinate_must_match_the_exact_subject_scope() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    subject = _subject(document)
    frame = _frame(document, snapshot)
    forged = frame.model_copy(
        update={"configuration": frame.configuration.model_copy(update={"coordinate_digest": _DIGEST_D})}
    )
    fact = adapt_declared_semantic_projection_fact(subject)

    with pytest.raises(ValueError, match="configuration coordinate.*exact native subject scope"):
        project_semantic_concepts(
            forged,
            document=document,
            subjects=(subject,),
            scheme_snapshot=snapshot,
            native_facts=(fact,),
        )


def test_gap_requires_complete_scope_and_a_decisive_native_negative() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    negative = PropositionTruthResultModel.model_validate(
        _load_json(
            REPO_ROOT
            / "contracts"
            / "fixtures"
            / "control-plane"
            / "proposition-truth-result-v1"
            / "valid"
            / "negative-observed.json"
        )
    )
    document, subject, negative = _observed_owner(document, negative)
    assert negative.probe_binding is not None
    evidence = _evidence_record(negative.evidence_refs[0], negative.probe_binding.artifact_digest)
    resolver = _evidence_resolver(evidence)
    fact = adapt_observed_semantic_projection_fact(
        subject,
        negative,
        evidence_boundary=_evidence_boundary(),
        evidence_resolver=resolver,
    )

    complete = project_semantic_concepts(
        _frame(
            document,
            snapshot,
            predicate_id="observed",
            scope_complete=True,
            observed_results=(negative,),
        ),
        document=document,
        subjects=(subject,),
        scheme_snapshot=snapshot,
        native_facts=(fact,),
        evidence_resolver=resolver,
    )
    incomplete = project_semantic_concepts(
        _frame(
            document,
            snapshot,
            predicate_id="observed",
            scope_complete=False,
            observed_results=(negative,),
        ),
        document=document,
        subjects=(subject,),
        scheme_snapshot=snapshot,
        native_facts=(fact,),
        evidence_resolver=resolver,
    )

    assert complete.summary.gap_count == 1
    assert complete.summary.unknown_count == 0
    complete_row = next(row for row in complete.rows if row.classification == "gap")
    assert complete_row.reason_codes == ("decisive-native-negative",)
    assert incomplete.summary.gap_count == 0
    assert incomplete.summary.unknown_count == 1
    incomplete_row = next(row for row in incomplete.rows if row.classification == "unknown")
    assert incomplete_row.reason_codes == ("native-result-undecidable",)


def test_projection_rejects_thresholds_above_the_exact_finite_population() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    subject = _subject(document)
    frame = _frame(document, snapshot).model_copy(
        update={
            "quantifier": SemanticProjectionQuantifierModel(
                kind="threshold",
                quantified_unit="distinct-native-subjects",
                threshold=2,
            )
        }
    )
    fact = adapt_declared_semantic_projection_fact(subject)

    with pytest.raises(ValueError, match="threshold.*population"):
        project_semantic_concepts(
            frame,
            document=document,
            subjects=(subject,),
            scheme_snapshot=snapshot,
            native_facts=(fact,),
        )


def test_unresolved_subjects_remain_in_universal_and_threshold_populations() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    primary = _subject(document)
    binding_id, binding = next(iter(document.bindings.items()))
    unresolved = primary.model_copy(update={"canonical_ref": "nodes.unresolved", "artifact_digest": _DIGEST_D})
    stale_binding = binding.model_copy(
        update={
            "binding_id": f"{binding_id}-stale",
            "subject": unresolved,
            "scheme": binding.scheme.model_copy(update={"revision": "stale-revision"}),
        }
    )
    payload = document.model_dump(mode="json")
    payload["bindings"][stale_binding.binding_id] = stale_binding.model_dump(mode="json")
    document = ExternalConceptBindingDocumentModel.model_validate(payload)
    subject_scope = SemanticProjectionSubjectScopeModel(
        subject_kind=primary.subject_kind,
        owning_contract_id=primary.owning_contract_id,
        lifecycle_phase=primary.lifecycle_phase,
        artifact_digests=tuple(sorted((primary.artifact_digest, unresolved.artifact_digest))),
        complete=True,
    )
    fact = adapt_declared_semantic_projection_fact(primary)

    configuration = semantic_projection_declared_configuration_coordinate((primary, unresolved))
    universal_frame = _frame(document, snapshot, quantifier="universal").model_copy(
        update={"subject_scope": subject_scope, "configuration": configuration}
    )
    universal = project_semantic_concepts(
        universal_frame,
        document=document,
        subjects=(primary, unresolved),
        scheme_snapshot=snapshot,
        native_facts=(fact,),
    )
    threshold_frame = _frame(document, snapshot).model_copy(
        update={
            "subject_scope": subject_scope,
            "configuration": configuration,
            "quantifier": SemanticProjectionQuantifierModel(
                kind="threshold",
                quantified_unit="distinct-native-subjects",
                threshold=2,
            ),
        }
    )
    threshold = project_semantic_concepts(
        threshold_frame,
        document=document,
        subjects=(primary, unresolved),
        scheme_snapshot=snapshot,
        native_facts=(fact,),
    )

    assert universal.summary.witness_count == 0
    assert universal.summary.unknown_count == 1
    assert threshold.summary.witness_count == 0
    assert threshold.summary.unknown_count == 1


def test_verified_adapter_rejects_evidence_free_claims_even_after_model_bypass() -> None:
    document = _document("attack-enterprise.json")
    subject = _subject(document)
    profile = _profile("verified")
    evidence = _evidence_record("verified-semantic-evidence", subject.artifact_digest)
    resolver = _evidence_resolver(evidence)
    report = _verified_report(
        subject,
        profile=profile,
        evidence_digest=canonical_json_digest(evidence.model_dump(mode="json")),
    ).model_copy(
        update={
            "preservation": ArtifactTransformationPreservationModel.model_construct(
                profile="semantic-predicate-witness/v1",
                outcome=PreservationOutcome.VERIFIED,
                evidence_digests=(),
                limitations=(),
            )
        }
    )
    boundary = _evidence_boundary()

    with pytest.raises(ValueError, match="predicate-specific verifier"):
        adapt_verified_semantic_projection_fact(
            subject,
            report,
            evidence_boundary=boundary,
            predicate_profile=profile,
            evidence_resolver=resolver,
        )


def test_governed_profiles_and_owner_adapters_reject_substitution() -> None:
    profile = _profile("observed")
    tampered = profile.model_dump(mode="json") | {"adapter_digest": _DIGEST_A}
    with pytest.raises(ValidationError, match="fixed trusted implementation"):
        SemanticProjectionPredicateProfileModel.model_validate(tampered)

    document = _document("attack-enterprise.json")
    unrelated_subject = _subject(document)
    disclosure = ValidationBasisDisclosureDocumentModel.model_validate(
        _load_json(
            REPO_ROOT
            / "contracts"
            / "fixtures"
            / "profiles"
            / "validation-basis-disclosure-v1"
            / "valid"
            / "structural-scenario.json"
        )
    )
    with pytest.raises(ValueError, match="exact disclosure"):
        adapt_admitted_semantic_projection_fact(unrelated_subject, disclosure)
    verified_profile = _profile("verified")
    evidence = _evidence_record("verified-semantic-evidence", unrelated_subject.artifact_digest)
    resolver = _evidence_resolver(evidence)
    generic = _verified_report(
        unrelated_subject,
        profile=verified_profile,
        evidence_digest=canonical_json_digest(evidence.model_dump(mode="json")),
    ).model_copy(update={"operation_profile": "canonicalize-portable-contract/v1"})
    boundary = _evidence_boundary()
    with pytest.raises(ValueError, match="predicate-specific verifier"):
        adapt_verified_semantic_projection_fact(
            unrelated_subject,
            generic,
            evidence_boundary=boundary,
            predicate_profile=verified_profile,
            evidence_resolver=resolver,
        )


def test_observed_fact_is_bound_to_its_exact_evidence_policy() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    truth = PropositionTruthResultModel.model_validate(
        _load_json(
            REPO_ROOT
            / "contracts"
            / "fixtures"
            / "control-plane"
            / "proposition-truth-result-v1"
            / "valid"
            / "positive-observed.json"
        )
    )
    document, subject, truth = _observed_owner(document, truth)
    assert truth.probe_binding is not None
    evidence = _evidence_record(truth.evidence_refs[0], truth.probe_binding.artifact_digest)
    resolver = _evidence_resolver(evidence)
    fact = adapt_observed_semantic_projection_fact(
        subject,
        truth,
        evidence_boundary=_evidence_boundary(),
        evidence_resolver=resolver,
    )
    frame = _frame(
        document,
        snapshot,
        predicate_id="observed",
        observed_results=(truth,),
    )
    forged_state = frame.model_copy(update={"state": frame.state.model_copy(update={"coordinate_digest": _DIGEST_D})})

    with pytest.raises(ValueError, match="state coordinate.*exact proposition truth result set"):
        project_semantic_concepts(
            forged_state,
            document=document,
            subjects=(subject,),
            scheme_snapshot=snapshot,
            native_facts=(fact,),
            evidence_resolver=resolver,
        )

    mismatched_frame = _frame(
        document,
        snapshot,
        predicate_id="observed",
        evidence_boundary_id="different-boundary",
        observed_results=(truth,),
    )
    with pytest.raises(ValueError, match="fixed owner adapter output"):
        project_semantic_concepts(
            mismatched_frame,
            document=document,
            subjects=(subject,),
            scheme_snapshot=snapshot,
            native_facts=(fact,),
            evidence_resolver=resolver,
        )


def test_verified_transformation_coordinates_must_match_the_exact_owner_reports() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    subject = _subject(document)
    profile = _profile("verified")
    evidence = _evidence_record("verified-semantic-evidence", subject.artifact_digest)
    resolver = _evidence_resolver(evidence)
    report = _verified_report(
        subject,
        profile=profile,
        evidence_digest=canonical_json_digest(evidence.model_dump(mode="json")),
    )
    fact = adapt_verified_semantic_projection_fact(
        subject,
        report,
        evidence_boundary=_evidence_boundary(),
        predicate_profile=profile,
        evidence_resolver=resolver,
    )
    frame = _frame(
        document,
        snapshot,
        predicate_id="verified",
        transformation_reports=(report,),
    )
    forged = frame.model_copy(
        update={"transformations": (frame.transformations[0].model_copy(update={"derivation_digest": _DIGEST_D}),)}
    )

    with pytest.raises(ValueError, match="transformation coordinates.*exact owner reports"):
        project_semantic_concepts(
            forged,
            document=document,
            subjects=(subject,),
            scheme_snapshot=snapshot,
            native_facts=(fact,),
            evidence_resolver=resolver,
        )


def test_report_rejects_witnesses_outside_the_embedded_subject_and_profile_scope() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    subject = _subject(document)
    report = project_semantic_concepts(
        _frame(document, snapshot),
        document=document,
        subjects=(subject,),
        scheme_snapshot=snapshot,
        native_facts=(adapt_declared_semantic_projection_fact(subject),),
    )
    payload = report.model_dump(mode="json")
    witness_row = next(row for row in payload["rows"] if row["classification"] == "witness")
    witness_row["witnesses"][0]["producer_contract_id"] = "untrusted-producer-v1"
    with pytest.raises(ValidationError, match="exact frame subject, producer, and profile"):
        SemanticProjectionReportModel.model_validate(payload)


def test_ambiguous_approximate_stale_and_lossy_bindings_remain_visible() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    subject = _subject(document)
    binding = next(iter(document.bindings.values()))

    approximate_binding = binding.model_copy(
        update={
            "approximation": type(binding.approximation).model_validate(
                {"posture": "approximate", "loss_details": ["broader mapping"]}
            )
        }
    )
    approximate_document = ExternalConceptBindingDocumentModel.model_validate(
        document.model_dump(mode="json")
        | {"bindings": {binding.binding_id: approximate_binding.model_dump(mode="json")}}
    )
    approximate_report = project_semantic_concepts(
        _frame(approximate_document, snapshot, allow_approximate_bindings=False),
        document=approximate_document,
        subjects=(subject,),
        scheme_snapshot=snapshot,
        native_facts=(adapt_declared_semantic_projection_fact(subject),),
    )
    row = next(
        row for row in approximate_report.rows if row.concept_id in approximate_report.frame.scheme.included_concept_ids
    )
    assert row.classification == "unknown"
    assert row.bindings[0].approximation_posture == "approximate"
    assert row.bindings[0].loss_details == ("broader mapping",)

    stale_snapshot = snapshot.model_copy(update={"revision": "stale-revision"})
    stale_frame = _frame(document, stale_snapshot)
    stale_report = project_semantic_concepts(
        stale_frame,
        document=document,
        subjects=(subject,),
        scheme_snapshot=stale_snapshot,
        native_facts=(adapt_declared_semantic_projection_fact(subject),),
    )
    stale_row = next(row for row in stale_report.rows if row.concept_id in stale_frame.scheme.included_concept_ids)
    assert stale_row.classification == "unknown"
    assert stale_row.bindings[0].resolution_outcome == "stale"

    concept = next(term for term in snapshot.concepts if term.concept_id == binding.scheme.concept_id)
    ambiguous_snapshot = snapshot.model_copy(update={"concepts": [*snapshot.concepts, concept]})
    ambiguous_report = project_semantic_concepts(
        _frame(document, ambiguous_snapshot),
        document=document,
        subjects=(subject,),
        scheme_snapshot=ambiguous_snapshot,
        native_facts=(adapt_declared_semantic_projection_fact(subject),),
    )
    ambiguous_row = next(
        row for row in ambiguous_report.rows if row.concept_id in ambiguous_report.frame.scheme.included_concept_ids
    )
    assert ambiguous_row.classification == "ambiguous"
    assert ambiguous_row.bindings[0].resolution_outcome == "ambiguous"

    lossy_document = _document("nist-csf.json")
    lossy_subject = _subject(lossy_document)
    lossy_snapshot = adapt_nist_csf_defensive_categories_snapshot(load_nist_csf_defensive_categories_source())
    lossy_report = project_semantic_concepts(
        _frame(lossy_document, lossy_snapshot, allow_lossy_bindings=False),
        document=lossy_document,
        subjects=(lossy_subject,),
        scheme_snapshot=lossy_snapshot,
        native_facts=(adapt_declared_semantic_projection_fact(lossy_subject),),
    )
    lossy_row = next(
        row for row in lossy_report.rows if row.concept_id in lossy_report.frame.scheme.included_concept_ids
    )
    assert lossy_row.classification == "unknown"
    assert lossy_row.bindings[0].approximation_posture == "lossy"
    assert lossy_row.bindings[0].loss_details


def test_participant_projection_is_owned_by_the_incumbent_exposure_policy_service() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    subject = _subject(document)
    frame = _frame(document, snapshot, perspective_kind="participant")
    fact = adapt_declared_semantic_projection_fact(subject)

    with pytest.raises(ValueError, match="incumbent exposure-policy service"):
        project_semantic_concepts(
            frame,
            document=document,
            subjects=(subject,),
            scheme_snapshot=snapshot,
            native_facts=(fact,),
        )


def test_negative_contract_shapes_fail_model_and_normative_schema() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    subject = _subject(document)
    report = project_semantic_concepts(
        _frame(document, snapshot),
        document=document,
        subjects=(subject,),
        scheme_snapshot=snapshot,
        native_facts=(adapt_declared_semantic_projection_fact(subject),),
    )
    published = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    mutations = []
    unknown_predicate = report.model_dump(mode="json")
    unknown_predicate["frame"]["predicate_profile"]["predicate_id"] = "fabricated"
    mutations.append(unknown_predicate)
    implicit_denominator = report.model_dump(mode="json")
    implicit_denominator["frame"]["scheme"]["included_concept_ids"] = []
    mutations.append(implicit_denominator)
    missing_revision = report.model_dump(mode="json")
    del missing_revision["frame"]["scheme"]["revision"]
    mutations.append(missing_revision)
    evidence_free_verification = report.model_dump(mode="json")
    evidence_free_verification["frame"]["predicate_profile"]["predicate_id"] = "verified"
    witness_row = next(row for row in evidence_free_verification["rows"] if row["witnesses"])
    witness_row["witnesses"][0]["evidence_digests"] = []
    mutations.append(evidence_free_verification)

    for payload in mutations:
        with pytest.raises(ValidationError):
            SemanticProjectionReportModel.model_validate(payload)
        assert not Draft202012Validator(published).is_valid(payload)


@pytest.mark.parametrize(
    ("filename", "model_type"),
    [
        ("unknown-predicate.json", SemanticProjectionPredicateProfileModel),
        ("implicit-denominator.json", SemanticProjectionSchemeScopeModel),
        ("missing-scheme-revision.json", SemanticProjectionSchemeScopeModel),
        ("evidence-free-verification.json", SemanticProjectionWitnessModel),
    ],
)
def test_negative_projection_fixtures_reject_the_targeted_invalid_shape(filename: str, model_type: type) -> None:
    fixture = (
        REPO_ROOT
        / "contracts"
        / "fixtures"
        / "concept-authority"
        / "semantic-projection-report-v1"
        / "invalid"
        / filename
    )
    payload = _load_json(fixture)

    with pytest.raises(ValidationError):
        model_type.model_validate(payload)


def test_report_is_published_and_registered_with_canonical_conformance() -> None:
    document = _document("attack-enterprise.json")
    snapshot = adapt_attack_enterprise_tactics_snapshot(load_attack_enterprise_tactics_source())
    subject = _subject(document)
    report = project_semantic_concepts(
        _frame(document, snapshot),
        document=document,
        subjects=(subject,),
        scheme_snapshot=snapshot,
        native_facts=(adapt_declared_semantic_projection_fact(subject),),
    )
    payload = report.model_dump(mode="json")

    assert "semantic-projection-report-v1" in _STRUCTURAL_ONLY_VALIDATORS
    assert validate_contract_payload("semantic-projection-report-v1", payload) == ()
    assert schema_bundle()["semantic-projection-report-v1"] == json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
