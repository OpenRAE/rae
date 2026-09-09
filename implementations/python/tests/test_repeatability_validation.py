"""ASR-514 bounded determinism, stability, and replay-consistency validation."""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field, fields, replace
from functools import cache
from pathlib import Path

import pytest
from raes_conformance.repeatability_evidence import (
    CleanupVerificationRecord,
    RepeatabilityRunInput,
    RepeatabilityRunPair,
    RepeatabilityVerificationRecords,
    ResetVerificationRecord,
    VariationVerificationRecord,
    VerificationBinding,
    VerificationDisposition,
    assemble_repeatability_consistency_evidence,
)
from raes_conformance.repeatability_types import (
    _ASSEMBLY_TOKEN,
    ProjectionOutcome,
    RepeatabilityConsistencyEvidence,
    RepetitionProjection,
)
from raes_conformance.repeatability_validation import (
    RepeatabilityConsistencyCase,
    RepeatabilityConsistencyOutcome,
    RepeatabilityVerificationAuthority,
    RepetitionRef,
    VariationPolicy,
    compare_repeatability_consistency,
)
from raes_contracts.behavioral_relations import validate_behavioral_claim_binding
from raes_contracts.contracts import (
    BehavioralClaimBindingModel,
    ExperimentCaptureSpecModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    ExperimentTaskModel,
)
from raes_contracts.satisfiability import canonical_contract_digest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64
_DIGEST_D = "sha256:" + "d" * 64
_SUBJECT_REF = "scenario-snapshot:scenario-techvault@1.0.0"
_PROJECTION_REF = "repeatability.projection.canonical-artifact"
_DIAGNOSTIC_ADDRESS = "/conformance/repeatability-comparison"
_JSON_POINTER_RE = re.compile(r"^(?:/(?:[^~/]|~[01])*)*$")
_EVIDENCE_BYTES = (
    _REPO_ROOT
    / "contracts/fixtures/control-plane/participant-behavior-history-event-stream-v1/valid/terminal-observation.json"
).read_bytes()


@cache
def _task() -> ExperimentTaskModel:
    task_payload = json.loads(
        (_REPO_ROOT / "contracts/fixtures/experiment-core/experiment-task-v1/valid/reference.json").read_text()
    )
    task_payload["task_id"] = "task-techvault-repeat"
    task_payload["scenario_ref"].update(ref_id="scenario-techvault", ref_version="1.0.0", ref_digest=_DIGEST_A)
    return ExperimentTaskModel.model_validate(task_payload)


def _artifact_ref(index: int) -> str:
    return f"projected-artifact:run-techvault-{index}#{_PROJECTION_REF}"


@cache
def _run_and_evidence(index: int) -> tuple[ExperimentRunModel, ExperimentEvidenceRecordModel]:
    task = _task()
    run_id = f"run-techvault-{index}"
    evidence_id = f"evidence-techvault-{index}"

    run_payload = json.loads(
        (_REPO_ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json").read_text()
    )
    run_payload["run_id"] = run_id
    run_payload["participant_implementation_provenance"]["run_id"] = run_id
    run_payload["task_ref"].update(ref_id=task.task_id, ref_version=task.task_version)
    run_payload["scenario_snapshot_ref"] = task.scenario_ref.model_dump(mode="json")
    for disclosure in run_payload["realized_form_disclosures"]:
        for reference in disclosure["evidence_refs"]:
            reference["ref_id"] = evidence_id
    run_version = run_payload["run_version"]
    artifact = run_payload["evidence_artifacts"][0]
    artifact["checksum"] = {"algorithm": "sha256", "value": hashlib.sha256(_EVIDENCE_BYTES).hexdigest()}
    artifact["size_bytes"] = len(_EVIDENCE_BYTES)

    evidence_payload = json.loads(
        (
            _REPO_ROOT / "contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/reference.json"
        ).read_text()
    )
    evidence_payload["evidence_record_id"] = evidence_id
    evidence_payload["run_ref"].update(ref_id=run_id, ref_version=run_version)
    evidence_payload["task_ref"].update(ref_id=task.task_id, ref_version=task.task_version)
    evidence_payload["capture_requirement_ref"] = "auth-log-evidence"
    evidence_payload["raw_content"] = {
        "content_uri": run_payload["evidence_artifacts"][0]["uri"],
        "content_checksum": run_payload["evidence_artifacts"][0]["checksum"],
    }
    evidence = ExperimentEvidenceRecordModel.model_validate(evidence_payload)

    # The digest-verified run declares which evidence-record identities belong to it.
    run_payload["traceability"]["evidence_record_refs"] = [
        {
            "ref_kind": "evidence-record",
            "ref_id": evidence_id,
            "ref_version": evidence.record_version,
        }
    ]
    run = ExperimentRunModel.model_validate(run_payload)
    return run, evidence


def _evidence_inputs(record: ExperimentEvidenceRecordModel) -> ExperimentRunEvidenceInputs:
    payload = json.loads(
        (_REPO_ROOT / "contracts/fixtures/experiment-core/experiment-capture-spec-v1/valid/reference.json").read_text()
    )
    requirement = next(iter(payload["capture_requirements"].values()))
    requirement["requirement_id"] = "auth-log-evidence"
    payload["capture_requirements"] = {"auth-log-evidence": requirement}
    capture_spec = ExperimentCaptureSpecModel.model_validate(payload)
    return ExperimentRunEvidenceInputs(
        capture_specs={capture_spec.capture_spec_id: capture_spec},
        evidence_records={record.evidence_record_id: record},
        artifact_readers={"auth-log-evidence": io.BytesIO(_EVIDENCE_BYTES)},
    )


def _run_ref(run: ExperimentRunModel) -> str:
    return f"experiment-run:{run.run_id}@{run.run_version}"


def _snapshot_ref(run: ExperimentRunModel) -> str:
    snapshot = run.scenario_snapshot_ref
    return f"scenario-snapshot:{snapshot.ref_id}@{snapshot.ref_version}"


def _repetition_ref(index: int) -> RepetitionRef:
    run, _ = _run_and_evidence(index)
    snapshot = run.scenario_snapshot_ref
    assert snapshot.ref_digest is not None
    return RepetitionRef(
        repetition_id=f"rep-{index}",
        run_ref=_run_ref(run),
        run_digest=canonical_contract_digest(run),
        subject_ref=_snapshot_ref(run),
        subject_digest=snapshot.ref_digest,
        projected_artifact_ref=_artifact_ref(index),
    )


def _claim(
    relation_id: str = "canonical-artifact-identity",
    *,
    taxonomy_revision: str = "rev8",
    left_index: int = 0,
    right_index: int = 1,
) -> BehavioralClaimBindingModel:
    return BehavioralClaimBindingModel(
        taxonomy_id="raes-behavioral-relations",
        taxonomy_revision=taxonomy_revision,
        relation_id=relation_id,
        subject="The repetition realizes the same canonical artifact as the baseline.",
        left_carrier_ref=_artifact_ref(left_index),
        right_carrier_ref=_artifact_ref(right_index),
        observation_projection_ref=_PROJECTION_REF,
        observation_projection_revision="rev1",
        quantifier_scope="finite-cases",
        evidence_scope="finite",
        evidence_boundary="One admitted baseline-to-repetition comparison.",
        assurance_status="tested",
        evidence_refs=[],
        limitations=["The result covers only the named pair, projection, and criterion."],
        explicit_non_claims=["Does not establish universal determinism or backend equivalence."],
    )


def _binding() -> VerificationBinding:
    return VerificationBinding(
        producer_id="example/repeatability-verifier",
        producer_version="1.0.0",
        producer_digest=_DIGEST_C,
        validator_id="raes/repeatability-verification-validator",
        validator_version="1.0.0",
        validator_digest=_DIGEST_D,
    )


def _case(
    *,
    claim: BehavioralClaimBindingModel | None = None,
    baseline: RepetitionRef | None = None,
    repetition: RepetitionRef | None = None,
    criterion_id: str = "canonical-projection-equality",
    criterion_version: str = "1.0.0",
) -> RepeatabilityConsistencyCase:
    return RepeatabilityConsistencyCase(
        case_id="repeatability:techvault-determinism",
        claim=claim or _claim(),
        subject_ref=_SUBJECT_REF,
        baseline=baseline or _repetition_ref(0),
        repetition=repetition or _repetition_ref(1),
        observation_projection_ref=_PROJECTION_REF,
        observation_projection_revision="rev1",
        criterion_id=criterion_id,
        criterion_version=criterion_version,
        variation_policy=VariationPolicy(
            policy_id="variation:techvault",
            policy_version="1.0.0",
            held_fixed_dimensions=("subject", "apparatus", "parameters"),
            permitted_variation_refs=("random-seed", "wall-clock"),
        ),
        required_capability_refs=("observation.projection", "reset.verified", "comparison.canonical"),
        verification_authority=RepeatabilityVerificationAuthority(**_binding().__dict__),
    )


def _rep_index(rep: RepetitionRef) -> int:
    return int(rep.repetition_id.rsplit("-", 1)[1])


@dataclass(frozen=True)
class _FixtureEvidenceValidator:
    binding: VerificationBinding
    digest_by_run_ref: dict[str, str]
    outcome_by_run_ref: dict[str, ProjectionOutcome] = field(default_factory=dict)
    projection_evidence_override: dict[str, str] = field(default_factory=dict)
    variation_disposition: VerificationDisposition = VerificationDisposition.VERIFIED
    reset_disposition: VerificationDisposition = VerificationDisposition.VERIFIED
    cleanup_disposition: VerificationDisposition = VerificationDisposition.VERIFIED

    def project_outcome(
        self,
        *,
        role: str,
        case: RepeatabilityConsistencyCase,
        run: ExperimentRunModel,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> RepetitionProjection:
        del role, case
        run_ref = _run_ref(run)
        outcome = self.outcome_by_run_ref.get(run_ref, ProjectionOutcome.DECIDED)
        evidence_ref = self.projection_evidence_override.get(
            run_ref,
            next(record.evidence_record_id for record in evidence_records if record.run_ref.ref_id == run.run_id),
        )
        if outcome is ProjectionOutcome.DECIDED:
            return RepetitionProjection(
                run_ref=run_ref,
                outcome=outcome,
                projected_digest=self.digest_by_run_ref[run_ref],
                evidence_refs=(evidence_ref,),
            )
        return RepetitionProjection(run_ref=run_ref, outcome=outcome, projected_digest=None, evidence_refs=())

    def verify_variation(self, **_kwargs: object) -> VerificationDisposition:
        return self.variation_disposition

    def verify_reset(self, **_kwargs: object) -> VerificationDisposition:
        return self.reset_disposition

    def verify_cleanup(self, **_kwargs: object) -> VerificationDisposition:
        return self.cleanup_disposition


def _default_records(case: RepeatabilityConsistencyCase, ver_ref: str) -> RepeatabilityVerificationRecords:
    pair_run_refs = (case.baseline.run_ref, case.repetition.run_ref)
    return RepeatabilityVerificationRecords(
        variation=VariationVerificationRecord(
            record_id="verification:variation",
            record_version="1.0.0",
            pair_run_refs=pair_run_refs,
            policy_id=case.variation_policy.policy_id,
            policy_version=case.variation_policy.policy_version,
            observed_variation_refs=case.variation_policy.permitted_variation_refs,
            evidence_record_refs=(ver_ref,),
        ),
        reset=ResetVerificationRecord(
            record_id="verification:reset",
            record_version="1.0.0",
            pair_run_refs=pair_run_refs,
            evidence_record_refs=(ver_ref,),
        ),
        cleanup=CleanupVerificationRecord(
            record_id="verification:cleanup",
            record_version="1.0.0",
            subject_ref=case.subject_ref,
            residual_state=(),
            evidence_record_refs=(ver_ref,),
        ),
    )


def _evidence(
    *,
    case: RepeatabilityConsistencyCase | None = None,
    baseline_digest: str = _DIGEST_B,
    repetition_digest: str = _DIGEST_B,
    baseline_outcome: ProjectionOutcome = ProjectionOutcome.DECIDED,
    repetition_outcome: ProjectionOutcome = ProjectionOutcome.DECIDED,
    projection_evidence_override: dict[str, str] | None = None,
    variation_disposition: VerificationDisposition = VerificationDisposition.VERIFIED,
    reset_disposition: VerificationDisposition = VerificationDisposition.VERIFIED,
    cleanup_disposition: VerificationDisposition = VerificationDisposition.VERIFIED,
    observed_variation_refs: tuple[str, ...] | None = None,
    residual_state: tuple[str, ...] = (),
    validator_binding: VerificationBinding | None = None,
    records: RepeatabilityVerificationRecords | None = None,
    runs: RepeatabilityRunPair | None = None,
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...] | None = None,
    task_override: dict[int, ExperimentTaskModel] | None = None,
) -> RepeatabilityConsistencyEvidence:
    case = case or _case()
    b_idx, r_idx = _rep_index(case.baseline), _rep_index(case.repetition)
    b_run, b_ev = _run_and_evidence(b_idx)
    r_run, r_ev = _run_and_evidence(r_idx)
    task_override = task_override or {}
    if runs is None:
        runs = RepeatabilityRunPair(
            baseline=RepeatabilityRunInput(
                case.baseline.repetition_id,
                task_override.get(b_idx, _task()),
                b_run,
                _evidence_inputs(b_ev),
            ),
            repetition=RepeatabilityRunInput(
                case.repetition.repetition_id,
                task_override.get(r_idx, _task()),
                r_run,
                _evidence_inputs(r_ev),
            ),
        )
    if evidence_records is None:
        evidence_records = (b_ev, r_ev)
    if records is None:
        records = _default_records(case, b_ev.evidence_record_id)
        if observed_variation_refs is not None:
            records = replace(
                records, variation=replace(records.variation, observed_variation_refs=observed_variation_refs)
            )
        if residual_state:
            records = replace(records, cleanup=replace(records.cleanup, residual_state=residual_state))
    validator = _FixtureEvidenceValidator(
        binding=validator_binding or _binding(),
        digest_by_run_ref={case.baseline.run_ref: baseline_digest, case.repetition.run_ref: repetition_digest},
        outcome_by_run_ref={
            case.baseline.run_ref: baseline_outcome,
            case.repetition.run_ref: repetition_outcome,
        },
        projection_evidence_override=projection_evidence_override or {},
        variation_disposition=variation_disposition,
        reset_disposition=reset_disposition,
        cleanup_disposition=cleanup_disposition,
    )
    return assemble_repeatability_consistency_evidence(
        case,
        runs=runs,
        evidence_records=evidence_records,
        verification_records=records,
        validator=validator,
    )


_CAPABILITIES = frozenset({"observation.projection", "reset.verified", "comparison.canonical"})


def _codes(result) -> set[str]:
    return {diagnostic.code for diagnostic in result.diagnostics}


def test_claim_binds_the_existing_canonical_artifact_identity_relation() -> None:
    validate_behavioral_claim_binding(_claim())


def test_verified_equal_pair_is_consistent() -> None:
    case = _case()

    result = compare_repeatability_consistency(case, _evidence(), available_capability_refs=_CAPABILITIES)

    assert result.outcome is RepeatabilityConsistencyOutcome.CONSISTENT
    assert result.consistent
    assert result.case_id == case.case_id
    assert result.case_digest == case.digest
    assert result.claim == case.claim
    assert result.subject_ref == case.subject_ref
    assert result.baseline_artifact_ref == _artifact_ref(0)
    assert result.repetition_artifact_ref == _artifact_ref(1)
    assert (result.baseline_run_ref, result.repetition_run_ref) == (case.baseline.run_ref, case.repetition.run_ref)
    assert set(result.evidence_refs) == {"evidence-techvault-0", "evidence-techvault-1"}
    assert {identity.record_id for identity in result.verification_identities} == {
        "verification:variation",
        "verification:reset",
        "verification:cleanup",
    }
    assert {identity.producer_id for identity in result.verification_identities} == {"example/repeatability-verifier"}
    assert not result.diagnostics


def test_divergent_projected_outcomes_refute_without_execution_failure() -> None:
    result = compare_repeatability_consistency(
        _case(),
        _evidence(repetition_digest=_DIGEST_C),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is RepeatabilityConsistencyOutcome.DIVERGENT
    assert not result.consistent
    assert not result.diagnostics


def test_comparison_evidence_cannot_be_constructed_directly() -> None:
    with pytest.raises(TypeError, match="assemble_repeatability_consistency_evidence"):
        RepeatabilityConsistencyEvidence()


@pytest.mark.parametrize(
    "record_type",
    (VariationVerificationRecord, ResetVerificationRecord, CleanupVerificationRecord),
)
def test_verification_inputs_cannot_assert_disposition_binding_or_digest(record_type: type[object]) -> None:
    field_names = {item.name for item in fields(record_type)}

    assert field_names.isdisjoint({"disposition", "binding", "record_digest"})


def test_comparator_rejects_an_unsealed_copy_of_assembled_evidence() -> None:
    assembled = _evidence()
    unsealed = object.__new__(RepeatabilityConsistencyEvidence)
    for field_name in RepeatabilityConsistencyEvidence.__dataclass_fields__:
        value = object() if field_name == "_assembly_token" else getattr(assembled, field_name)
        object.__setattr__(unsealed, field_name, value)

    result = compare_repeatability_consistency(_case(), unsealed, available_capability_refs=_CAPABILITIES)

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.repeatability-evidence-unauthenticated"}


def _tampered_evidence(**overrides: object) -> RepeatabilityConsistencyEvidence:
    assembled = _evidence()
    tampered = object.__new__(RepeatabilityConsistencyEvidence)
    for field_name in RepeatabilityConsistencyEvidence.__dataclass_fields__:
        if field_name == "_assembly_token":
            value: object = _ASSEMBLY_TOKEN
        elif field_name in overrides:
            value = overrides[field_name]
        else:
            value = getattr(assembled, field_name)
        object.__setattr__(tampered, field_name, value)
    return tampered


def test_comparator_rejects_authority_mismatch_in_sealed_evidence() -> None:
    tampered = _tampered_evidence(verification_binding=replace(_binding(), validator_digest=_DIGEST_A))

    result = compare_repeatability_consistency(_case(), tampered, available_capability_refs=_CAPABILITIES)

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.repeatability-verification-authority-mismatch"}


def test_comparator_rejects_pair_evidence_mismatch_in_sealed_evidence() -> None:
    tampered = _tampered_evidence(baseline_artifact_ref="projected-artifact:other#x")

    result = compare_repeatability_consistency(_case(), tampered, available_capability_refs=_CAPABILITIES)

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.repeatability-pair-evidence-mismatch"}


def test_case_digest_changes_for_every_join_identity() -> None:
    case = _case()
    variants = (
        replace(case, case_id="repeatability:other"),
        replace(case, observation_projection_ref="repeatability.projection.other"),
        replace(case, observation_projection_revision="rev2"),
        replace(case, criterion_id="other-criterion"),
        replace(case, criterion_version="2.0.0"),
        replace(case, repetition=_repetition_ref(2)),
        replace(case, variation_policy=replace(case.variation_policy, policy_version="1.0.1")),
        replace(case, required_capability_refs=("observation.projection",)),
        replace(case, verification_authority=replace(case.verification_authority, validator_digest=_DIGEST_A)),
    )

    assert all(case.digest != variant.digest for variant in variants)


def test_indeterminate_projected_outcome_is_inconclusive() -> None:
    result = compare_repeatability_consistency(
        _case(),
        _evidence(repetition_outcome=ProjectionOutcome.INDETERMINATE),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is RepeatabilityConsistencyOutcome.INCONCLUSIVE
    assert _codes(result) == {"conformance.repeatability-outcome-inconclusive"}


def test_unsupported_projected_outcome_remains_unsupported() -> None:
    result = compare_repeatability_consistency(
        _case(),
        _evidence(baseline_outcome=ProjectionOutcome.UNSUPPORTED),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.repeatability-outcome-unsupported"}


@pytest.mark.parametrize(
    "disposition_field",
    ("variation_disposition", "reset_disposition", "cleanup_disposition"),
)
def test_unsupported_verification_disposition_remains_unsupported(disposition_field: str) -> None:
    result = compare_repeatability_consistency(
        _case(),
        _evidence(**{disposition_field: VerificationDisposition.UNSUPPORTED}),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.repeatability-verification-unsupported"}


@pytest.mark.parametrize(
    ("evidence", "expected_code"),
    [
        (
            _evidence(
                variation_disposition=VerificationDisposition.FAILED,
                observed_variation_refs=("random-seed", "wall-clock", "apparatus"),
            ),
            "conformance.repeatability-variation-unverified",
        ),
        (_evidence(reset_disposition=VerificationDisposition.FAILED), "conformance.repeatability-reset-unverified"),
        (_evidence(cleanup_disposition=VerificationDisposition.FAILED), "conformance.repeatability-cleanup-unverified"),
        (_evidence(residual_state=("resource:leaked",)), "conformance.repeatability-residual-state"),
    ],
)
def test_variation_reset_and_cleanup_gates_fail_closed(
    evidence: RepeatabilityConsistencyEvidence,
    expected_code: str,
) -> None:
    result = compare_repeatability_consistency(_case(), evidence, available_capability_refs=_CAPABILITIES)

    assert result.outcome is RepeatabilityConsistencyOutcome.INCONCLUSIVE
    assert expected_code in _codes(result)


def test_unpermitted_observed_variation_makes_the_pair_incomparable() -> None:
    result = compare_repeatability_consistency(
        _case(),
        _evidence(observed_variation_refs=("random-seed", "apparatus")),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is RepeatabilityConsistencyOutcome.INCONCLUSIVE
    assert "conformance.repeatability-variation-unverified" in _codes(result)


@pytest.mark.parametrize(
    ("claim", "expected_code"),
    [
        (_claim("bounded-probe-success"), "conformance.repeatability-claim-relation-invalid"),
        (_claim(taxonomy_revision="rev4"), "conformance.repeatability-claim-invalid"),
    ],
)
def test_wrong_relation_or_stale_catalog_coordinate_fails_before_comparison(
    claim: BehavioralClaimBindingModel,
    expected_code: str,
) -> None:
    case = _case(claim=claim)
    result = compare_repeatability_consistency(case, _evidence(case=case), available_capability_refs=_CAPABILITIES)

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {expected_code}


def test_non_finite_claim_boundary_is_not_interpreted_by_the_comparator() -> None:
    claim = _claim().model_copy(update={"quantifier_scope": "sampled-population", "evidence_scope": "statistical"})
    case = _case(claim=claim)

    result = compare_repeatability_consistency(case, _evidence(case=case), available_capability_refs=_CAPABILITIES)

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.repeatability-claim-boundary-invalid"}


def test_claim_carriers_must_identify_the_baseline_and_repetition_artifacts() -> None:
    baseline_mismatch = _claim().model_copy(update={"left_carrier_ref": "projected-artifact:other#x"})
    projection_mismatch = _claim().model_copy(update={"observation_projection_ref": "repeatability.projection.other"})

    for claim in (baseline_mismatch, projection_mismatch):
        case = _case(claim=claim)
        result = compare_repeatability_consistency(case, _evidence(case=case), available_capability_refs=_CAPABILITIES)
        assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
        assert _codes(result) == {"conformance.repeatability-claim-case-mismatch"}


def test_unsupported_criterion_is_rejected_before_comparison() -> None:
    case = _case(criterion_id="other-criterion", criterion_version="2.0.0")

    result = compare_repeatability_consistency(case, _evidence(case=case), available_capability_refs=_CAPABILITIES)

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.repeatability-criterion-unsupported"}


def test_case_digest_mismatch_is_rejected_before_comparison() -> None:
    evidence = _evidence()
    other_case = replace(_case(), case_id="repeatability:other")

    result = compare_repeatability_consistency(other_case, evidence, available_capability_refs=_CAPABILITIES)

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.repeatability-case-evidence-mismatch"}


def test_missing_comparator_capability_fails_before_evidence_interpretation() -> None:
    result = compare_repeatability_consistency(
        _case(),
        _evidence(),
        available_capability_refs=frozenset({"observation.projection"}),
    )

    assert result.outcome is RepeatabilityConsistencyOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.repeatability-capability-unsupported"}


def test_diagnostics_use_a_stable_json_pointer_address_and_hide_untrusted_values() -> None:
    secret_like = "secret-token-do-not-render"
    result = compare_repeatability_consistency(
        _case(),
        _evidence(residual_state=(secret_like,)),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.diagnostics
    for diagnostic in result.diagnostics:
        assert diagnostic.address == _DIAGNOSTIC_ADDRESS
        assert _JSON_POINTER_RE.fullmatch(diagnostic.address)
    rendered = " ".join(
        f"{diagnostic.code} {diagnostic.address} {diagnostic.message}" for diagnostic in result.diagnostics
    )
    assert secret_like not in rendered


# --- Assembler fail-closed join, identity, and content-integrity guards -----


@pytest.mark.parametrize(("role", "index"), (("baseline", 0), ("repetition", 1)))
def test_assembler_rejects_a_side_that_does_not_match_the_typed_run(role: str, index: int) -> None:
    mismatched = replace(_repetition_ref(index), run_ref="experiment-run:other@1")
    case = _case(
        baseline=mismatched if role == "baseline" else None,
        repetition=mismatched if role == "repetition" else None,
    )

    with pytest.raises(ValueError, match=rf"{role} does not match the validated task, run"):
        _evidence(case=case)


@pytest.mark.parametrize(("role", "index"), (("baseline", 0), ("repetition", 1)))
def test_assembler_runs_the_canonical_task_run_validator(role: str, index: int) -> None:
    wrong_task = _task().model_copy(update={"task_id": "task:other"})

    with pytest.raises(ValueError, match=rf"{role} task/run validation failed"):
        _evidence(task_override={index: wrong_task})


def test_assembler_rejects_validator_outside_the_case_authority_pin() -> None:
    untrusted = replace(_binding(), validator_digest=_DIGEST_A)
    with pytest.raises(ValueError, match="validator binding does not match"):
        _evidence(validator_binding=untrusted)


def test_assembler_rejects_projection_evidence_from_the_other_run() -> None:
    baseline_run = _run_and_evidence(0)[0]
    foreign_ref = _run_and_evidence(1)[1].evidence_record_id
    override = {_run_ref(baseline_run): foreign_ref}

    with pytest.raises(ValueError, match="baseline projection evidence must resolve"):
        _evidence(projection_evidence_override=override)


def test_run_pair_ids_must_match_the_case() -> None:
    case = _case()
    b_run, _ = _run_and_evidence(0)
    r_run, _ = _run_and_evidence(1)
    bad_runs = RepeatabilityRunPair(
        baseline=RepeatabilityRunInput("rep-unknown", _task(), b_run),
        repetition=RepeatabilityRunInput(case.repetition.repetition_id, _task(), r_run),
    )

    with pytest.raises(ValueError, match="run pair repetition ids must match"):
        _evidence(case=case, runs=bad_runs)


def test_assembler_rejects_verification_evidence_outside_the_pair() -> None:
    case = _case()
    records = _default_records(case, "evidence:not-in-any-run")

    with pytest.raises(ValueError, match="variation verification evidence must resolve"):
        _evidence(case=case, records=records)


def test_variation_verification_must_match_the_declared_policy() -> None:
    case = _case()
    records = _default_records(case, _run_and_evidence(0)[1].evidence_record_id)
    tampered = replace(records, variation=replace(records.variation, policy_id="variation:other"))

    with pytest.raises(ValueError, match="variation verification does not match the admitted variation policy"):
        _evidence(case=case, records=tampered)


@pytest.mark.parametrize("record_name", ("variation", "reset"))
def test_variation_and_reset_verification_must_cover_the_pair(record_name: str) -> None:
    case = _case()
    records = _default_records(case, _run_and_evidence(0)[1].evidence_record_id)
    partial = (case.baseline.run_ref,)
    tampered = replace(records, **{record_name: replace(getattr(records, record_name), pair_run_refs=partial)})

    with pytest.raises(ValueError, match="does not cover the admitted pair"):
        _evidence(case=case, records=tampered)


def test_cleanup_verification_must_match_the_admitted_subject() -> None:
    case = _case()
    records = _default_records(case, _run_and_evidence(0)[1].evidence_record_id)
    tampered = replace(records, cleanup=replace(records.cleanup, subject_ref="scenario-snapshot:other@1.0.0"))

    with pytest.raises(ValueError, match="cleanup verification does not match the admitted subject"):
        _evidence(case=case, records=tampered)


def test_evidence_records_must_use_unique_ids() -> None:
    case = _case()
    b_ev = _run_and_evidence(0)[1]
    r_ev = _run_and_evidence(1)[1]
    records = (b_ev, r_ev, b_ev)

    with pytest.raises(ValueError, match="evidence_records must use unique evidence_record_id"):
        _evidence(case=case, evidence_records=records)


def test_verification_records_must_use_unique_record_ids() -> None:
    case = _case()
    records = _default_records(case, _run_and_evidence(0)[1].evidence_record_id)
    tampered = replace(records, reset=replace(records.reset, record_id=records.variation.record_id))

    with pytest.raises(ValueError, match="verification records must use unique record_id"):
        _evidence(case=case, records=tampered)


class _BadProjectionValidator:
    def __init__(self, *, run_ref_override: str | None = None, return_non_projection: bool = False) -> None:
        self.binding = _binding()
        self._run_ref_override = run_ref_override
        self._return_non_projection = return_non_projection

    def project_outcome(self, *, role, case, run, evidence_records):  # type: ignore[no-untyped-def]
        del role, case
        if self._return_non_projection:
            return object()
        evidence_ref = next(r.evidence_record_id for r in evidence_records if r.run_ref.ref_id == run.run_id)
        return RepetitionProjection(
            run_ref=self._run_ref_override or f"experiment-run:{run.run_id}@{run.run_version}",
            outcome=ProjectionOutcome.DECIDED,
            projected_digest=_DIGEST_B,
            evidence_refs=(evidence_ref,),
        )

    def verify_variation(self, **_kwargs):  # type: ignore[no-untyped-def]
        return VerificationDisposition.VERIFIED

    def verify_reset(self, **_kwargs):  # type: ignore[no-untyped-def]
        return VerificationDisposition.VERIFIED

    def verify_cleanup(self, **_kwargs):  # type: ignore[no-untyped-def]
        return VerificationDisposition.VERIFIED


def _assemble_with_validator(validator: object) -> RepeatabilityConsistencyEvidence:
    case = _case()
    b_run, b_ev = _run_and_evidence(0)
    r_run, r_ev = _run_and_evidence(1)
    return assemble_repeatability_consistency_evidence(
        case,
        runs=RepeatabilityRunPair(
            baseline=RepeatabilityRunInput(case.baseline.repetition_id, _task(), b_run, _evidence_inputs(b_ev)),
            repetition=RepeatabilityRunInput(case.repetition.repetition_id, _task(), r_run, _evidence_inputs(r_ev)),
        ),
        evidence_records=(b_ev, r_ev),
        verification_records=_default_records(case, b_ev.evidence_record_id),
        validator=validator,  # type: ignore[arg-type]
    )


def test_assembler_requires_typed_projection_values() -> None:
    validator = _BadProjectionValidator(return_non_projection=True)
    with pytest.raises(ValueError, match="must derive typed RepetitionProjection values"):
        _assemble_with_validator(validator)


def test_assembler_requires_the_projection_to_identify_its_run() -> None:
    validator = _BadProjectionValidator(run_ref_override="experiment-run:other@1")
    with pytest.raises(ValueError, match="projection does not identify its admitted run"):
        _assemble_with_validator(validator)


def test_assembler_requires_typed_disposition_values() -> None:
    class _BadDispositionValidator(_BadProjectionValidator):
        def verify_reset(self, **_kwargs):  # type: ignore[no-untyped-def]
            return "verified"

    validator = _BadDispositionValidator()
    with pytest.raises(ValueError, match="must return VerificationDisposition values"):
        _assemble_with_validator(validator)


def test_case_requires_a_distinct_lineage_preserving_pair() -> None:
    baseline = _repetition_ref(0)
    repetition = _repetition_ref(1)
    reused_run = replace(repetition, run_ref=baseline.run_ref)
    with pytest.raises(ValueError, match="distinct run_ref"):
        _case(repetition=reused_run)
    reused_artifact = replace(repetition, projected_artifact_ref=baseline.projected_artifact_ref)
    with pytest.raises(ValueError, match="distinct projected_artifact_ref"):
        _case(repetition=reused_artifact)
    drifted_subject = replace(repetition, subject_ref="scenario-snapshot:other@1")
    with pytest.raises(ValueError, match="repeat the case subject_ref"):
        _case(repetition=drifted_subject)
    drifted_digest = replace(repetition, subject_digest=_DIGEST_C)
    with pytest.raises(ValueError, match="hold the subject fixed by digest"):
        _case(repetition=drifted_digest)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "run_ref": "",
                "outcome": ProjectionOutcome.DECIDED,
                "projected_digest": _DIGEST_B,
                "evidence_refs": ("e",),
            },
            "run_ref must be non-empty",
        ),
        (
            {"run_ref": "r", "outcome": "decided", "projected_digest": _DIGEST_B, "evidence_refs": ("e",)},
            "outcome must be a ProjectionOutcome",
        ),
        (
            {"run_ref": "r", "outcome": ProjectionOutcome.DECIDED, "projected_digest": None, "evidence_refs": ("e",)},
            "must carry a sha256 projected_digest",
        ),
        (
            {"run_ref": "r", "outcome": ProjectionOutcome.DECIDED, "projected_digest": _DIGEST_B, "evidence_refs": ()},
            "must carry run-bound evidence_refs",
        ),
        (
            {
                "run_ref": "r",
                "outcome": ProjectionOutcome.INDETERMINATE,
                "projected_digest": _DIGEST_B,
                "evidence_refs": (),
            },
            "must not carry a projected_digest",
        ),
    ],
)
def test_repetition_projection_shape_is_enforced(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RepetitionProjection(**kwargs)  # type: ignore[arg-type]


def test_case_rejects_malformed_field_types() -> None:
    with pytest.raises(ValueError, match="claim must be a BehavioralClaimBindingModel"):
        _case(claim="not-a-claim")  # type: ignore[arg-type]
    valid = _case()
    with pytest.raises(ValueError, match="variation_policy must be a VariationPolicy"):
        replace(valid, variation_policy="not-a-policy")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="verification_authority must be"):
        replace(valid, verification_authority="not-a-binding")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="baseline and repetition must be RepetitionRef"):
        replace(valid, repetition="not-a-repetition")  # type: ignore[arg-type]


def test_case_requires_at_least_one_capability() -> None:
    case = _case()
    with pytest.raises(ValueError, match="required_capability_refs must not be empty"):
        replace(case, required_capability_refs=())
    with pytest.raises(ValueError, match="required_capability_refs entries must be non-empty"):
        replace(case, required_capability_refs=("",))


def test_variation_policy_requires_and_dedupes_dimensions() -> None:
    with pytest.raises(ValueError, match="held_fixed_dimensions must not be empty"):
        VariationPolicy(policy_id="p", policy_version="1", held_fixed_dimensions=(), permitted_variation_refs=("x",))
    with pytest.raises(ValueError, match="held_fixed_dimensions entries must be unique"):
        VariationPolicy(
            policy_id="p",
            policy_version="1",
            held_fixed_dimensions=("subject", "subject"),
            permitted_variation_refs=("x",),
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("producer_id", "", "producer_id must be non-empty"),
        ("producer_digest", "not-a-digest", "producer_digest must be a sha256 digest"),
    ],
)
def test_verification_binding_shape_is_enforced(field_name: str, bad_value: str, message: str) -> None:
    binding = _binding()
    with pytest.raises(ValueError, match=message):
        replace(binding, **{field_name: bad_value})


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("repetition_id", "", "repetition_id must be non-empty"),
        ("run_digest", "not-a-digest", "run_digest must be a sha256 digest"),
    ],
)
def test_repetition_ref_shape_is_enforced(field_name: str, bad_value: str, message: str) -> None:
    rep = _repetition_ref(0)
    with pytest.raises(ValueError, match=message):
        replace(rep, **{field_name: bad_value})


def test_verification_record_header_is_enforced() -> None:
    with pytest.raises(ValueError, match="record_id must be non-empty"):
        ResetVerificationRecord(record_id="", record_version="1", pair_run_refs=("r",), evidence_record_refs=("e",))
    with pytest.raises(ValueError, match="evidence_record_refs must not be empty"):
        ResetVerificationRecord(record_id="x", record_version="1", pair_run_refs=("r",), evidence_record_refs=())
    with pytest.raises(ValueError, match="pair_run_refs entries must be unique"):
        ResetVerificationRecord(
            record_id="x", record_version="1", pair_run_refs=("r", "r"), evidence_record_refs=("e",)
        )
    with pytest.raises(ValueError, match="pair_run_refs entries must be non-empty"):
        ResetVerificationRecord(record_id="x", record_version="1", pair_run_refs=("",), evidence_record_refs=("e",))
