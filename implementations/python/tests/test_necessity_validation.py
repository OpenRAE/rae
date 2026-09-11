"""ASR-513 bounded counterfactual and necessity validation."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, fields, replace
from functools import cache
from pathlib import Path

import pytest
from raes_conformance.necessity_evidence import (
    CleanupVerificationRecord,
    InterventionVerificationRecord,
    MatchingVerificationRecord,
    NecessityRunPair,
    NecessityVerificationRecords,
    VerificationBinding,
    VerificationDisposition,
    assemble_bounded_but_for_evidence,
)
from raes_conformance.necessity_types import _ASSEMBLY_TOKEN
from raes_conformance.necessity_validation import (
    BOUNDED_BUT_FOR_RELATION_ID,
    BoundedButForCase,
    BoundedButForEvidence,
    InterventionKind,
    NecessityComparisonOutcome,
    NecessityMatchingPolicy,
    NecessityVerificationAuthority,
    NecessityWorldRef,
    compare_bounded_but_for,
)
from raes_contracts.contracts import (
    BehavioralClaimBindingModel,
    ExperimentCaptureSpecModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunEvidenceInputs,
    ExperimentRunModel,
    ExperimentTaskModel,
    PropositionTruthResultModel,
)
from raes_contracts.satisfiability import canonical_contract_digest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64
_DIGEST_D = "sha256:" + "d" * 64
_PROPOSITION = "evaluation.proposition.service-compromised"
_ASSERTION = "evaluation.assertion.service-compromised"
_EVIDENCE_BYTES = (
    _REPO_ROOT
    / "contracts/fixtures/control-plane/participant-behavior-history-event-stream-v1/valid/terminal-observation.json"
).read_bytes()


@cache
def _artifacts(role: str) -> tuple[ExperimentTaskModel, ExperimentRunModel, ExperimentEvidenceRecordModel]:
    suffix = "baseline" if role == "baseline" else "counterfactual"
    snapshot_digest = _DIGEST_A if role == "baseline" else _DIGEST_B
    task_id = f"task-techvault-{suffix}"
    run_id = f"run-techvault-{suffix}"
    evidence_id = f"evidence-techvault-{suffix}"

    task_payload = json.loads(
        (_REPO_ROOT / "contracts/fixtures/experiment-core/experiment-task-v1/valid/reference.json").read_text()
    )
    task_payload["task_id"] = task_id
    task_payload["scenario_ref"].update(
        ref_id=f"scenario-techvault-{suffix}",
        ref_version="1.0.0",
        ref_digest=snapshot_digest,
    )
    task = ExperimentTaskModel.model_validate(task_payload)

    run_payload = json.loads(
        (_REPO_ROOT / "contracts/fixtures/experiment-core/experiment-run-v1/valid/reference.json").read_text()
    )
    run_payload["run_id"] = run_id
    run_payload["participant_implementation_provenance"]["run_id"] = run_id
    run_payload["task_ref"].update(ref_id=task_id, ref_version=task.task_version)
    run_payload["scenario_snapshot_ref"] = task.scenario_ref.model_dump(mode="json")
    run_payload["traceability"]["evidence_record_refs"] = [
        {
            "ref_kind": "evidence-record",
            "ref_id": evidence_id,
            "ref_version": "1.0.0",
        }
    ]
    for disclosure in run_payload["realized_form_disclosures"]:
        for reference in disclosure["evidence_refs"]:
            reference["ref_id"] = evidence_id
    artifact = run_payload["evidence_artifacts"][0]
    artifact["checksum"] = {"algorithm": "sha256", "value": hashlib.sha256(_EVIDENCE_BYTES).hexdigest()}
    artifact["size_bytes"] = len(_EVIDENCE_BYTES)
    run = ExperimentRunModel.model_validate(run_payload)

    evidence_payload = json.loads(
        (
            _REPO_ROOT / "contracts/fixtures/experiment-core/experiment-evidence-record-v1/valid/reference.json"
        ).read_text()
    )
    evidence_payload["evidence_record_id"] = evidence_id
    evidence_payload["run_ref"].update(ref_id=run_id, ref_version=run.run_version)
    evidence_payload["task_ref"].update(ref_id=task_id, ref_version=task.task_version)
    evidence_payload["capture_requirement_ref"] = "auth-log-evidence"
    evidence_payload["raw_content"] = {
        "content_uri": run.evidence_artifacts[0].uri,
        "content_checksum": run.evidence_artifacts[0].checksum.model_dump(mode="json"),
    }
    evidence = ExperimentEvidenceRecordModel.model_validate(evidence_payload)
    return task, run, evidence


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


def _claim(
    relation_id: str = BOUNDED_BUT_FOR_RELATION_ID,
    *,
    taxonomy_revision: str = "rev8",
) -> BehavioralClaimBindingModel:
    return BehavioralClaimBindingModel(
        taxonomy_id="raes-behavioral-relations",
        taxonomy_revision=taxonomy_revision,
        relation_id=relation_id,
        subject="The named weakness is necessary for the recorded compromise outcome.",
        left_carrier_ref="scenario.techvault.weakness.cve-2025-0001",
        right_carrier_ref=_PROPOSITION,
        observation_projection_ref="necessity-comparison-result",
        observation_projection_revision="rev1",
        quantifier_scope="finite-cases",
        evidence_scope="finite",
        evidence_boundary="One admitted baseline and intervention-world comparison.",
        assurance_status="tested",
        evidence_refs=[],
        limitations=["The result covers only the named worlds, apparatus, and matching policy."],
        explicit_non_claims=["Does not establish universal, actual, or sufficient causation."],
    )


def _world(role: str) -> NecessityWorldRef:
    _, run, _ = _artifacts(role)
    snapshot = run.scenario_snapshot_ref
    assert snapshot.ref_digest is not None
    return NecessityWorldRef(
        world_id=f"world:{role}",
        run_ref=_run_ref(run),
        run_digest=canonical_contract_digest(run),
        subject_ref=_snapshot_ref(run),
        subject_digest=snapshot.ref_digest,
        family_ref="scenario-family:techvault@1",
        baseline_lineage_ref="scenario-snapshot:techvault-source@1",
    )


def _truth(outcome: str, role: str) -> PropositionTruthResultModel:
    decided = outcome in {"true", "false"}
    _, _, evidence = _artifacts(role)
    payload: dict[str, object] = {
        "schema_version": "proposition-truth-result/v1",
        "result_id": f"truth:{role}",
        "proposition_address": _PROPOSITION,
        "assertion_address": _ASSERTION,
        "assertion_polarity": "positive",
        "proposition_outcome": outcome,
        "assertion_outcome": outcome,
        "evaluation_basis": "observed_state",
        "indeterminacy_reason": "missing_evidence" if outcome == "unknown" else None,
        "probe_binding": (
            {
                "binding_id": f"probe:{role}",
                "implementation_id": "example/compromise-observer",
                "implementation_version": "1.0.0",
                "artifact_digest": _DIGEST_C,
                "backend_manifest_ref": "backend-manifest:range",
                "proposition_address": _PROPOSITION,
                "capability_refs": ["observation.outcome"],
            }
            if decided
            else None
        ),
        "evidence_refs": [evidence.evidence_record_id] if decided else [],
        "declared_artifact_digest": None,
        "temporal_context": (
            {
                "boundary_ref": "workflow:terminal",
                "time_domain": "scenario_time",
                "clock_authority": f"experiment-clock:{role}",
            }
            if decided
            else None
        ),
        "loss_disclosures": ([{"kind": "missing", "within_admissible_bound": False}] if outcome == "unknown" else []),
        "unsupported_capability_refs": ["observation.outcome"] if outcome == "unsupported" else [],
    }
    return PropositionTruthResultModel.model_validate(payload)


def _binding() -> VerificationBinding:
    return VerificationBinding(
        producer_id="example/necessity-verifier",
        producer_version="1.0.0",
        producer_digest=_DIGEST_C,
        validator_id="raes/necessity-verification-validator",
        validator_version="1.0.0",
        validator_digest=_DIGEST_D,
    )


@dataclass(frozen=True)
class _FixtureEvidenceValidator:
    binding: VerificationBinding
    baseline_outcome: str = "true"
    counterfactual_outcome: str = "false"
    intervention_disposition: VerificationDisposition = VerificationDisposition.VERIFIED
    matching_disposition: VerificationDisposition = VerificationDisposition.VERIFIED
    cleanup_disposition: VerificationDisposition = VerificationDisposition.VERIFIED
    baseline_truth_override: PropositionTruthResultModel | None = None
    counterfactual_truth_override: PropositionTruthResultModel | None = None

    def derive_truth(
        self,
        *,
        role: str,
        case: BoundedButForCase,
        run: ExperimentRunModel,
        evidence_records: tuple[ExperimentEvidenceRecordModel, ...],
    ) -> PropositionTruthResultModel:
        del case, run, evidence_records
        override = self.baseline_truth_override if role == "baseline" else self.counterfactual_truth_override
        if override is not None:
            return override
        outcome = self.baseline_outcome if role == "baseline" else self.counterfactual_outcome
        return _truth(outcome, role)

    def verify_intervention(self, **_kwargs: object) -> VerificationDisposition:
        return self.intervention_disposition

    def verify_matching(self, **_kwargs: object) -> VerificationDisposition:
        return self.matching_disposition

    def verify_cleanup(self, **_kwargs: object) -> VerificationDisposition:
        return self.cleanup_disposition


def _case(
    *,
    claim: BehavioralClaimBindingModel | None = None,
    baseline_world: NecessityWorldRef | None = None,
    counterfactual_world: NecessityWorldRef | None = None,
) -> BoundedButForCase:
    return BoundedButForCase(
        case_id="necessity:weakness-removal",
        claim=claim or _claim(),
        candidate_ref="scenario.techvault.weakness.cve-2025-0001",
        outcome_proposition_address=_PROPOSITION,
        outcome_assertion_address=_ASSERTION,
        baseline_world=baseline_world or _world("baseline"),
        counterfactual_world=counterfactual_world or _world("counterfactual"),
        intervention_kind=InterventionKind.REMOVE,
        intervention_ref="intervention:remove-cve-2025-0001",
        intervention_version="1.0.0",
        intervention_digest=_DIGEST_C,
        criterion_id="binary-but-for",
        criterion_version="1.0.0",
        matching_policy=NecessityMatchingPolicy(
            policy_id="matching:techvault",
            policy_version="1.0.0",
            held_fixed_dimensions=("apparatus", "participants", "randomness", "time-model"),
            permitted_difference_refs=("scenario.techvault.weakness.cve-2025-0001",),
        ),
        required_capability_refs=(
            "intervention.remove",
            "observation.outcome",
            "reset.verified",
        ),
        verification_authority=NecessityVerificationAuthority(**_binding().__dict__),
        input_digest=_DIGEST_D,
    )


def _evidence(
    *,
    case: BoundedButForCase | None = None,
    baseline_outcome: str = "true",
    counterfactual_outcome: str = "false",
    intervention_verified: bool = True,
    matching_policy_satisfied: bool = True,
    cleanup_verified: bool = True,
    unmatched_dimension_refs: tuple[str, ...] = (),
    residual_state: tuple[str, ...] = (),
    baseline_truth_evidence_role: str = "baseline",
    intervention_run_ref: str | None = None,
    baseline_task_override: ExperimentTaskModel | None = None,
    baseline_run_override: ExperimentRunModel | None = None,
    counterfactual_task_override: ExperimentTaskModel | None = None,
    counterfactual_run_override: ExperimentRunModel | None = None,
    baseline_truth_override: PropositionTruthResultModel | None = None,
    counterfactual_truth_override: PropositionTruthResultModel | None = None,
    intervention_disposition: VerificationDisposition | None = None,
    matching_disposition: VerificationDisposition | None = None,
    cleanup_disposition: VerificationDisposition | None = None,
    verification_evidence_ref: str | None = None,
    validator_binding: VerificationBinding | None = None,
) -> BoundedButForEvidence:
    case = case or _case()
    baseline_task, baseline_run, baseline_record = _artifacts("baseline")
    baseline_task = baseline_task_override or baseline_task
    baseline_run = baseline_run_override or baseline_run
    counterfactual_task, counterfactual_run, counterfactual_record = _artifacts("counterfactual")
    counterfactual_task = counterfactual_task_override or counterfactual_task
    counterfactual_run = counterfactual_run_override or counterfactual_run
    verification_ref = verification_evidence_ref or counterfactual_record.evidence_record_id
    intervention = InterventionVerificationRecord(
        record_id="verification:intervention",
        record_version="1.0.0",
        world_id=case.counterfactual_world.world_id,
        run_ref=intervention_run_ref or case.counterfactual_world.run_ref,
        intervention_ref=case.intervention_ref,
        intervention_version=case.intervention_version,
        evidence_record_refs=(verification_ref,),
    )
    matching = MatchingVerificationRecord(
        record_id="verification:matching",
        record_version="1.0.0",
        baseline_world_id=case.baseline_world.world_id,
        baseline_run_ref=case.baseline_world.run_ref,
        counterfactual_world_id=case.counterfactual_world.world_id,
        counterfactual_run_ref=case.counterfactual_world.run_ref,
        policy_id=case.matching_policy.policy_id,
        policy_version=case.matching_policy.policy_version,
        observed_difference_refs=(case.candidate_ref, *unmatched_dimension_refs),
        evidence_record_refs=(verification_ref,),
    )
    cleanup = CleanupVerificationRecord(
        record_id="verification:cleanup",
        record_version="1.0.0",
        world_id=case.counterfactual_world.world_id,
        run_ref=case.counterfactual_world.run_ref,
        subject_ref=case.counterfactual_world.subject_ref,
        residual_state=residual_state,
        evidence_record_refs=(verification_ref,),
    )
    baseline_truth = baseline_truth_override or _truth(baseline_outcome, "baseline")
    if baseline_truth.evidence_refs and baseline_truth_evidence_role != "baseline":
        _, _, truth_record = _artifacts(baseline_truth_evidence_role)
        baseline_truth = baseline_truth.model_copy(update={"evidence_refs": [truth_record.evidence_record_id]})
    counterfactual_truth = counterfactual_truth_override or _truth(counterfactual_outcome, "counterfactual")
    validator = _FixtureEvidenceValidator(
        binding=validator_binding or _binding(),
        baseline_outcome=baseline_outcome,
        counterfactual_outcome=counterfactual_outcome,
        intervention_disposition=intervention_disposition
        or (VerificationDisposition.VERIFIED if intervention_verified else VerificationDisposition.FAILED),
        matching_disposition=matching_disposition
        or (VerificationDisposition.VERIFIED if matching_policy_satisfied else VerificationDisposition.FAILED),
        cleanup_disposition=cleanup_disposition
        or (VerificationDisposition.VERIFIED if cleanup_verified else VerificationDisposition.FAILED),
        baseline_truth_override=baseline_truth,
        counterfactual_truth_override=counterfactual_truth,
    )
    return assemble_bounded_but_for_evidence(
        case,
        runs=NecessityRunPair(
            baseline_task=baseline_task,
            baseline_run=baseline_run,
            counterfactual_task=counterfactual_task,
            counterfactual_run=counterfactual_run,
            baseline_evidence=_evidence_inputs(baseline_record),
            counterfactual_evidence=_evidence_inputs(counterfactual_record),
        ),
        evidence_records=(baseline_record, counterfactual_record),
        verification_records=NecessityVerificationRecords(
            intervention=intervention,
            matching=matching,
            cleanup=cleanup,
        ),
        validator=validator,
    )


_CAPABILITIES = frozenset(
    {
        "intervention.remove",
        "observation.outcome",
        "reset.verified",
    }
)


def _codes(result) -> set[str]:
    return {diagnostic.code for diagnostic in result.diagnostics}


def test_verified_true_to_false_comparison_supports_only_the_bounded_claim() -> None:
    case = _case()

    result = compare_bounded_but_for(case, _evidence(), available_capability_refs=_CAPABILITIES)

    assert result.outcome is NecessityComparisonOutcome.SUPPORTED
    assert result.supported
    assert result.case_id == case.case_id
    assert result.case_digest == case.digest
    assert result.claim == case.claim
    assert result.baseline_world == case.baseline_world
    assert result.counterfactual_world == case.counterfactual_world
    assert set(result.evidence_refs) == {
        "evidence-techvault-baseline",
        "evidence-techvault-counterfactual",
    }
    assert {identity.record_id for identity in result.verification_identities} == {
        "verification:intervention",
        "verification:matching",
        "verification:cleanup",
    }
    assert {identity.producer_id for identity in result.verification_identities} == {"example/necessity-verifier"}
    assert {identity.validator_id for identity in result.verification_identities} == {
        "raes/necessity-verification-validator"
    }
    assert not result.diagnostics


def test_comparison_evidence_cannot_be_constructed_from_caller_booleans() -> None:
    with pytest.raises(TypeError, match="assemble_bounded_but_for_evidence"):
        BoundedButForEvidence()


@pytest.mark.parametrize(
    "record_type",
    (InterventionVerificationRecord, MatchingVerificationRecord, CleanupVerificationRecord),
)
def test_verification_inputs_cannot_assert_disposition_binding_or_digest(record_type: type[object]) -> None:
    field_names = {item.name for item in fields(record_type)}

    assert field_names.isdisjoint({"disposition", "binding", "record_digest"})


def test_comparator_rejects_an_unsealed_copy_of_assembled_evidence() -> None:
    assembled = _evidence()
    unsealed = object.__new__(BoundedButForEvidence)
    for field_name in BoundedButForEvidence.__dataclass_fields__:
        value = object() if field_name == "_assembly_token" else getattr(assembled, field_name)
        object.__setattr__(unsealed, field_name, value)

    result = compare_bounded_but_for(_case(), unsealed, available_capability_refs=_CAPABILITIES)

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.necessity-evidence-unauthenticated"}


def _tampered_evidence(**overrides: object) -> BoundedButForEvidence:
    assembled = _evidence()
    tampered = object.__new__(BoundedButForEvidence)
    for field_name in BoundedButForEvidence.__dataclass_fields__:
        if field_name == "_assembly_token":
            value: object = _ASSEMBLY_TOKEN
        elif field_name in overrides:
            value = overrides[field_name]
        else:
            value = getattr(assembled, field_name)
        object.__setattr__(tampered, field_name, value)
    return tampered


def test_comparator_rejects_authority_mismatch_in_sealed_evidence() -> None:
    tampered = _tampered_evidence(
        verification_binding=replace(_binding(), validator_digest=_DIGEST_A),
    )

    result = compare_bounded_but_for(_case(), tampered, available_capability_refs=_CAPABILITIES)

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.necessity-verification-authority-mismatch"}


def test_case_digest_changes_for_every_causal_join_identity() -> None:
    case = _case()
    variants = (
        replace(case, case_id="necessity:other"),
        replace(
            case,
            candidate_ref="scenario.techvault.weakness.other",
            matching_policy=replace(
                case.matching_policy,
                permitted_difference_refs=("scenario.techvault.weakness.other",),
            ),
        ),
        replace(case, outcome_proposition_address="evaluation.proposition.other"),
        replace(case, outcome_assertion_address="evaluation.assertion.other"),
        replace(case, baseline_world=replace(case.baseline_world, run_digest=_DIGEST_C)),
        replace(case, counterfactual_world=replace(case.counterfactual_world, run_digest=_DIGEST_C)),
        replace(case, intervention_kind=InterventionKind.DISABLE),
        replace(case, intervention_ref="intervention:disable-cve"),
        replace(case, intervention_version="1.0.1"),
        replace(case, intervention_digest=_DIGEST_D),
        replace(case, criterion_id="other-criterion"),
        replace(case, criterion_version="2.0.0"),
        replace(
            case,
            matching_policy=replace(case.matching_policy, policy_version="1.0.1"),
        ),
        replace(case, required_capability_refs=("observation.outcome",)),
        replace(
            case,
            verification_authority=replace(
                case.verification_authority,
                validator_digest=_DIGEST_A,
            ),
        ),
        replace(case, input_digest=_DIGEST_A),
    )

    assert all(case.digest != variant.digest for variant in variants)


def test_both_worlds_true_refutes_the_claim_without_reporting_execution_failure() -> None:
    result = compare_bounded_but_for(
        _case(),
        _evidence(counterfactual_outcome="true"),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is NecessityComparisonOutcome.REFUTED
    assert not result.supported
    assert not result.diagnostics


@pytest.mark.parametrize(
    ("baseline", "counterfactual", "expected_code"),
    [
        ("false", "false", "conformance.necessity-baseline-nonvacuity-failed"),
        ("unknown", "false", "conformance.necessity-outcome-inconclusive"),
        ("true", "unknown", "conformance.necessity-outcome-inconclusive"),
    ],
)
def test_false_baseline_or_unknown_truth_is_inconclusive(
    baseline: str,
    counterfactual: str,
    expected_code: str,
) -> None:
    result = compare_bounded_but_for(
        _case(),
        _evidence(baseline_outcome=baseline, counterfactual_outcome=counterfactual),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is NecessityComparisonOutcome.INCONCLUSIVE
    assert expected_code in _codes(result)


def test_unsupported_truth_remains_unsupported_instead_of_becoming_false() -> None:
    result = compare_bounded_but_for(
        _case(),
        _evidence(counterfactual_outcome="unsupported"),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.necessity-outcome-unsupported"}


@pytest.mark.parametrize(
    "disposition_field",
    ("intervention_disposition", "matching_disposition", "cleanup_disposition"),
)
def test_unsupported_verification_disposition_remains_unsupported(disposition_field: str) -> None:
    result = compare_bounded_but_for(
        _case(),
        _evidence(**{disposition_field: VerificationDisposition.UNSUPPORTED}),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.necessity-verification-unsupported"}


@pytest.mark.parametrize(
    ("evidence", "expected_code"),
    [
        (
            _evidence(intervention_verified=False),
            "conformance.necessity-intervention-unverified",
        ),
        (
            _evidence(
                matching_policy_satisfied=False,
                unmatched_dimension_refs=("apparatus",),
            ),
            "conformance.necessity-worlds-incomparable",
        ),
        (
            _evidence(cleanup_verified=False),
            "conformance.necessity-cleanup-unverified",
        ),
        (
            _evidence(residual_state=("resource:leaked",)),
            "conformance.necessity-residual-state",
        ),
    ],
)
def test_intervention_comparability_and_cleanup_gates_fail_closed(
    evidence: BoundedButForEvidence,
    expected_code: str,
) -> None:
    result = compare_bounded_but_for(
        _case(),
        evidence,
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is NecessityComparisonOutcome.INCONCLUSIVE
    assert expected_code in _codes(result)


@pytest.mark.parametrize(
    ("claim", "expected_code"),
    [
        (
            _claim("bounded-probe-success"),
            "conformance.necessity-claim-relation-invalid",
        ),
        (
            _claim(taxonomy_revision="rev3"),
            "conformance.necessity-claim-invalid",
        ),
    ],
)
def test_wrong_relation_or_stale_catalog_coordinate_fails_before_comparison(
    claim: BehavioralClaimBindingModel,
    expected_code: str,
) -> None:
    case = _case(claim=claim)
    result = compare_bounded_but_for(
        case,
        _evidence(case=case),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {expected_code}


def test_non_finite_claim_boundary_is_not_interpreted_by_binary_comparator() -> None:
    claim = _claim().model_copy(
        update={
            "quantifier_scope": "sampled-population",
            "evidence_scope": "statistical",
        }
    )

    case = _case(claim=claim)
    result = compare_bounded_but_for(case, _evidence(case=case), available_capability_refs=_CAPABILITIES)

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.necessity-claim-boundary-invalid"}


def test_claim_candidate_and_outcome_identities_must_match_the_case() -> None:
    candidate_mismatch = _claim().model_copy(update={"left_carrier_ref": "scenario.techvault.weakness.other"})
    outcome_mismatch = _claim().model_copy(update={"right_carrier_ref": "evaluation.proposition.other"})

    for claim in (candidate_mismatch, outcome_mismatch):
        case = _case(claim=claim)
        result = compare_bounded_but_for(
            case,
            _evidence(case=case),
            available_capability_refs=_CAPABILITIES,
        )
        assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
        assert _codes(result) == {"conformance.necessity-claim-case-mismatch"}


@pytest.mark.parametrize("role", ("baseline", "counterfactual"))
def test_assembler_rejects_case_world_that_does_not_match_the_typed_run(role: str) -> None:
    mismatched_world = replace(
        _world(role),
        run_ref="experiment-run:other@1",
    )
    case = _case(
        baseline_world=mismatched_world if role == "baseline" else None,
        counterfactual_world=mismatched_world if role == "counterfactual" else None,
    )

    with pytest.raises(ValueError, match=rf"{role} world does not match"):
        _evidence(case=case)


@pytest.mark.parametrize("role", ("baseline", "counterfactual"))
def test_assembler_runs_the_canonical_task_run_validator(role: str) -> None:
    task, _, _ = _artifacts(role)
    wrong_task = task.model_copy(update={"task_id": "task:other"})
    overrides = (
        {"baseline_task_override": wrong_task} if role == "baseline" else {"counterfactual_task_override": wrong_task}
    )

    with pytest.raises(ValueError, match=rf"{role} task/run validation failed"):
        _evidence(**overrides)


def test_assembler_rejects_validator_outside_the_case_authority_pin() -> None:
    untrusted_binding = replace(_binding(), validator_digest=_DIGEST_A)

    with pytest.raises(ValueError, match="validator binding does not match"):
        _evidence(validator_binding=untrusted_binding)


def test_assembler_rejects_truth_evidence_from_the_other_world_run() -> None:
    with pytest.raises(ValueError, match="truth evidence must resolve through its exact run"):
        _evidence(baseline_truth_evidence_role="counterfactual")


def test_assembler_requires_truth_evidence_in_run_traceability() -> None:
    baseline_task, baseline_run, _ = _artifacts("baseline")
    _, counterfactual_run, _ = _artifacts("counterfactual")
    bad_traceability = baseline_run.traceability.model_copy(
        update={"evidence_record_refs": counterfactual_run.traceability.evidence_record_refs}
    )
    bad_run = baseline_run.model_copy(update={"traceability": bad_traceability})
    case = _case()
    case = replace(
        case,
        baseline_world=replace(
            case.baseline_world,
            run_digest=canonical_contract_digest(bad_run),
        ),
    )

    with pytest.raises(ValueError, match="task/run validation failed"):
        _evidence(
            case=case,
            baseline_task_override=baseline_task,
            baseline_run_override=bad_run,
        )


def test_assembler_rejects_verification_record_for_another_run() -> None:
    with pytest.raises(ValueError, match="intervention verification does not match"):
        _evidence(intervention_run_ref="experiment-run:other@1")


def test_case_digest_mismatch_is_rejected_before_comparison() -> None:
    evidence = _evidence()
    other_case = replace(_case(), input_digest=_DIGEST_A)

    result = compare_bounded_but_for(other_case, evidence, available_capability_refs=_CAPABILITIES)

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.necessity-case-evidence-mismatch"}


def test_unsupported_criterion_is_rejected_before_comparison() -> None:
    case = replace(_case(), criterion_id="other-criterion", criterion_version="2.0.0")

    result = compare_bounded_but_for(case, _evidence(case=case), available_capability_refs=_CAPABILITIES)

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.necessity-criterion-unsupported"}


def test_truth_for_another_outcome_is_rejected_before_comparison() -> None:
    wrong_truth = _truth("true", "baseline").model_copy(
        update={
            "proposition_address": "evaluation.proposition.other",
            "assertion_address": "evaluation.assertion.other",
            "probe_binding": _truth("true", "baseline").probe_binding.model_copy(
                update={"proposition_address": "evaluation.proposition.other"}
            ),
        }
    )

    result = compare_bounded_but_for(
        _case(),
        _evidence(baseline_truth_override=wrong_truth),
        available_capability_refs=_CAPABILITIES,
    )

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.necessity-world-evidence-mismatch"}


def test_verification_evidence_must_resolve_through_counterfactual_run() -> None:
    with pytest.raises(ValueError, match="verification evidence must resolve"):
        _evidence(verification_evidence_ref="evidence:not-in-run")


def test_missing_comparator_capability_fails_before_evidence_interpretation() -> None:
    result = compare_bounded_but_for(
        _case(),
        _evidence(),
        available_capability_refs=frozenset({"observation.outcome"}),
    )

    assert result.outcome is NecessityComparisonOutcome.UNSUPPORTED
    assert _codes(result) == {"conformance.necessity-capability-unsupported"}


def test_case_rejects_reused_run_identity_and_unrelated_world_lineage() -> None:
    baseline = _world("baseline")
    counterfactual = _world("counterfactual")
    reused_world_id = replace(counterfactual, world_id=baseline.world_id)
    reused_run = replace(counterfactual, run_ref=baseline.run_ref)
    unrelated = replace(counterfactual, family_ref="scenario-family:other@1")
    unrelated_lineage = replace(counterfactual, baseline_lineage_ref="scenario-snapshot:other-source@1")

    with pytest.raises(ValueError, match="distinct world_id"):
        _case(counterfactual_world=reused_world_id)
    with pytest.raises(ValueError, match="distinct run_ref"):
        _case(counterfactual_world=reused_run)
    with pytest.raises(ValueError, match="same family_ref"):
        _case(counterfactual_world=unrelated)
    with pytest.raises(ValueError, match="same baseline_lineage_ref"):
        _case(counterfactual_world=unrelated_lineage)


@pytest.mark.parametrize(
    ("field_name", "bad_value", "message"),
    [
        ("world_id", "", "world_id must be non-empty"),
        ("run_digest", "not-a-digest", "run_digest must be a sha256 digest"),
    ],
)
def test_necessity_world_ref_shape_is_enforced(field_name: str, bad_value: str, message: str) -> None:
    world = _world("baseline")

    with pytest.raises(ValueError, match=message):
        replace(world, **{field_name: bad_value})


def test_matching_policy_requires_unique_nonempty_dimensions_and_differences() -> None:
    with pytest.raises(ValueError, match="held_fixed_dimensions must not be empty"):
        NecessityMatchingPolicy(
            policy_id="p",
            policy_version="1",
            held_fixed_dimensions=(),
            permitted_difference_refs=("candidate",),
        )
    with pytest.raises(ValueError, match="held_fixed_dimensions entries must be unique"):
        NecessityMatchingPolicy(
            policy_id="p",
            policy_version="1",
            held_fixed_dimensions=("subject", "subject"),
            permitted_difference_refs=("candidate",),
        )
    with pytest.raises(ValueError, match="permitted_difference_refs must not be empty"):
        NecessityMatchingPolicy(
            policy_id="p",
            policy_version="1",
            held_fixed_dimensions=("subject",),
            permitted_difference_refs=(),
        )
    with pytest.raises(ValueError, match="permitted_difference_refs entries must be unique"):
        NecessityMatchingPolicy(
            policy_id="p",
            policy_version="1",
            held_fixed_dimensions=("subject",),
            permitted_difference_refs=("candidate", "candidate"),
        )


def test_case_rejects_malformed_field_types() -> None:
    with pytest.raises(ValueError, match="claim must be a BehavioralClaimBindingModel"):
        _case(claim="not-a-claim")  # type: ignore[arg-type]
    valid = _case()
    with pytest.raises(ValueError, match="baseline_world must be a NecessityWorldRef"):
        replace(valid, baseline_world="not-a-world")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="counterfactual_world must be a NecessityWorldRef"):
        replace(valid, counterfactual_world="not-a-world")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="intervention_kind must be an InterventionKind"):
        replace(valid, intervention_kind="remove")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="matching_policy must be a NecessityMatchingPolicy"):
        replace(valid, matching_policy="not-a-policy")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="verification_authority must be"):
        replace(valid, verification_authority="not-an-authority")  # type: ignore[arg-type]


def test_case_requires_unique_nonempty_capabilities() -> None:
    case = _case()
    with pytest.raises(ValueError, match="required_capability_refs must not be empty"):
        replace(case, required_capability_refs=())
    with pytest.raises(ValueError, match="required_capability_refs entries must be non-empty"):
        replace(case, required_capability_refs=("",))
    with pytest.raises(ValueError, match="required_capability_refs entries must be unique"):
        replace(case, required_capability_refs=("observation.outcome", "observation.outcome"))


def test_verification_record_header_is_enforced() -> None:
    with pytest.raises(ValueError, match="record_id must be non-empty"):
        InterventionVerificationRecord(
            record_id="",
            record_version="1",
            world_id="world",
            run_ref="run",
            intervention_ref="intervention",
            intervention_version="1",
            evidence_record_refs=("e",),
        )
    with pytest.raises(ValueError, match="evidence_record_refs must not be empty"):
        InterventionVerificationRecord(
            record_id="record",
            record_version="1",
            world_id="world",
            run_ref="run",
            intervention_ref="intervention",
            intervention_version="1",
            evidence_record_refs=(),
        )
    with pytest.raises(ValueError, match="evidence_record_refs entries must be unique"):
        InterventionVerificationRecord(
            record_id="record",
            record_version="1",
            world_id="world",
            run_ref="run",
            intervention_ref="intervention",
            intervention_version="1",
            evidence_record_refs=("e", "e"),
        )


def test_diagnostics_are_stable_and_do_not_echo_untrusted_values() -> None:
    secret_like = "secret-token-do-not-render"
    evidence = _evidence(
        matching_policy_satisfied=False,
        unmatched_dimension_refs=(secret_like,),
    )

    result = compare_bounded_but_for(
        _case(),
        evidence,
        available_capability_refs=_CAPABILITIES,
    )

    rendered = " ".join(
        f"{diagnostic.code} {diagnostic.address} {diagnostic.message}" for diagnostic in result.diagnostics
    )
    assert secret_like not in rendered
