"""Integrity tests for the preregistered DSL language-evaluation bundle."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import tools.check_dsl_language_evaluation as evaluation_gate
from raes_contracts.errors import InvalidInputError
from tools.check_dsl_language_evaluation import (
    REQUIRED_DIMENSION_IDS,
    REQUIRED_PERSONA_IDS,
    load_bundle,
    recompute_dimension_results,
    recompute_measure_results,
    validate_bundle,
)
from tools.policy.common import load_bounded_json_object

REPO_ROOT = Path(__file__).resolve().parents[3]


def _rule_ids(failures: list[object]) -> set[str]:
    return {failure.rule_id for failure in failures}


def _bundle() -> tuple[dict, dict, dict, dict]:
    manifest, protocol, snapshot, analysis = load_bundle(REPO_ROOT)
    return (
        deepcopy(manifest),
        deepcopy(protocol),
        deepcopy(snapshot),
        deepcopy(analysis),
    )


def _full_claim_scope(protocol: dict) -> dict[str, list[str]]:
    return {
        "persona_ids": [item["persona_id"] for item in protocol["personas"]],
        "task_ids": [item["task_id"] for item in protocol["tasks"]],
        "tooling_condition_ids": [item["condition_id"] for item in protocol["tooling_conditions"]],
        "variant_ids": [item["variant_id"] for item in protocol["variants"]],
        "artifact_stage_ids": [item["stage_id"] for item in protocol["artifact_stages"]],
        "dimension_ids": [item["dimension_id"] for item in protocol["dimensions"]],
        "measure_ids": [item["measure_id"] for item in protocol["measures"]],
    }


def _refresh_analysis(
    protocol: dict,
    snapshot: dict,
    analysis: dict,
    evidence_status: str,
    *,
    claim_binding: dict | None = None,
) -> None:
    scope = analysis["claim"]["scope"]
    measure_results = recompute_measure_results(protocol, snapshot, scope=scope)
    analysis["measure_results"] = [
        {
            "measure_id": measure_id,
            "status": (
                "not_evaluated"
                if result["denominator"] == 0
                else "incomplete"
                if result["observed_count"] != result["denominator"]
                else "evaluated"
            ),
            **result,
        }
        for measure_id, result in measure_results.items()
    ]
    analysis["dimension_results"] = [
        {"dimension_id": dimension_id, **result}
        for dimension_id, result in recompute_dimension_results(
            protocol,
            measure_results,
            dimension_ids=scope["dimension_ids"],
        ).items()
    ]
    claim_id = analysis["claim"]["claim_id"]
    if claim_binding is None:
        claim_binding = next(
            entry[0]["claim_binding"]
            for entry in evaluation_gate.load_bundles(REPO_ROOT)
            if entry[0]["claim_binding"]["claim_id"] == claim_id
        )
    strata = evaluation_gate.resolve_claim_strata(protocol, analysis, claim_binding)
    analysis["stratum_results"] = (
        []
        if snapshot["execution_status"] == "not_started"
        else evaluation_gate.recompute_stratum_results(protocol, snapshot, strata)
    )
    analysis["execution_status"] = snapshot["execution_status"]
    analysis["evidence_status"] = evidence_status


def _executed_bundle(*, failing: bool = False) -> tuple[dict, dict, dict]:
    _, protocol, snapshot, analysis = _bundle()
    snapshot["execution_status"] = "complete"
    snapshot["ethics_review"] = {
        "status": "approved",
        "protocol_identifier": "ethics-approval-one",
        "approved_population": "qualified RAES author and reviewer personas",
        "approved_data_boundary": "minimized pseudonymous records",
    }
    subjects_by_persona: dict[str, list[dict]] = {}
    for persona in protocol["personas"]:
        persona_id = persona["persona_id"]
        subjects_by_persona[persona_id] = []
        for index in range(persona["minimum_completed_subjects"]):
            subject = {
                "subject_id": f"subject-{persona_id}-{index}",
                "persona_id": persona_id,
                "experience_band": protocol["sampling_plan"]["experience_bands"][0],
                "consent_status": "consented",
            }
            subjects_by_persona[persona_id].append(subject)
            snapshot["subjects"].append(subject)

    tasks_by_id = {task["task_id"]: task for task in protocol["tasks"]}
    measures = protocol["measures"]

    def append_attempt(subject: dict, task: dict, condition_id: str, variant_id: str) -> None:
        attempt_number = len(snapshot["attempts"])
        attempt_id = f"attempt-{attempt_number}"
        observation_ids: list[str] = []
        attempt_outcome = (
            "failed"
            if failing
            and any(
                measure["measure_id"] == "task-completion" and task["task_id"] in measure["task_ids"]
                for measure in measures
            )
            else "completed"
        )
        attempt = {
            "attempt_id": attempt_id,
            "study_run_id": "study-run-one",
            "task_id": task["task_id"],
            "persona_id": subject["persona_id"],
            "subject_id": subject["subject_id"],
            "tooling_condition_id": condition_id,
            "variant_id": variant_id,
            "outcome": attempt_outcome,
            "observation_ids": observation_ids,
            "started_at": "2026-07-15T09:00:00Z",
            "ended_at": "2026-07-15T10:00:00Z",
        }
        snapshot["attempts"].append(attempt)
        for measure in measures:
            if task["task_id"] not in measure["task_ids"]:
                continue
            declaration = next(
                item
                for item in measure["stage_applicability"]
                if item["task_id"] == task["task_id"] and variant_id in item["variant_ids"]
            )
            for artifact_stage in declaration["artifact_stage_ids"]:
                observation_id = f"observation-{attempt_number}-{measure['measure_id']}-{artifact_stage}"
                observation_ids.append(observation_id)
                value = 1 if measure["direction"] == "higher-is-better" else 0
                if failing and measure["measure_id"] == "task-completion":
                    value = 0
                snapshot["observations"].append(
                    {
                        "observation_id": observation_id,
                        "protocol_revision": protocol["revision"],
                        "study_run_id": attempt["study_run_id"],
                        "task_id": task["task_id"],
                        "persona_id": subject["persona_id"],
                        "subject_id": subject["subject_id"],
                        "tooling_condition_id": condition_id,
                        "attempt_id": attempt_id,
                        "variant_id": variant_id,
                        "artifact_stage": artifact_stage,
                        "dimension_ids": [
                            dimension_id
                            for dimension_id in measure["dimension_ids"]
                            if dimension_id in task["dimension_ids"]
                        ],
                        "measure_id": measure["measure_id"],
                        "value": value,
                        "outcome": attempt_outcome,
                        "evidence_refs": [],
                    }
                )
        if "review-judgment" in task["artifact_stage_ids"]:
            reviewer = next(
                candidate
                for persona_id in task["persona_ids"]
                for candidate in subjects_by_persona[persona_id]
                if candidate["subject_id"] != subject["subject_id"]
            )
            snapshot["reviews"].append(
                {
                    "review_id": f"review-{attempt_number}",
                    "attempt_id": attempt_id,
                    "reviewer_subject_id": reviewer["subject_id"],
                    "task_id": task["task_id"],
                    "variant_id": variant_id,
                    "judgment": "matches sealed intent",
                    "confidence": 1.0,
                    "rationale_code": "matches-intent",
                    "fixed_at": "2026-07-15T10:30:00Z",
                }
            )

    for subject in snapshot["subjects"]:
        for requirement in protocol["execution_plan"]["subject_task_requirements"]:
            task = next(
                task
                for task in protocol["tasks"]
                if subject["persona_id"] in task["persona_ids"] and task["kind"] in requirement["task_kinds"]
            )
            append_attempt(
                subject,
                task,
                task["tooling_condition_ids"][0],
                task["variant_ids"][0],
            )
    for task in tasks_by_id.values():
        subject = subjects_by_persona[task["persona_ids"][0]][0]
        for condition_id in task["tooling_condition_ids"]:
            for variant_id in task["variant_ids"]:
                append_attempt(subject, task, condition_id, variant_id)

    _refresh_analysis(protocol, snapshot, analysis, "refuted" if failing else "demonstrated")
    return protocol, snapshot, analysis


def _append_valid_disagreement(protocol: dict, snapshot: dict) -> dict:
    """Add a second independent review and a valid disagreement record."""
    first_review = snapshot["reviews"][0]
    attempt = next(item for item in snapshot["attempts"] if item["attempt_id"] == first_review["attempt_id"])
    task = next(item for item in protocol["tasks"] if item["task_id"] == attempt["task_id"])
    second_reviewer = next(
        subject
        for subject in snapshot["subjects"]
        if subject["subject_id"] not in {attempt["subject_id"], first_review["reviewer_subject_id"]}
        and subject["persona_id"] in task["persona_ids"]
    )
    second_review = {
        **first_review,
        "review_id": f"{first_review['review_id']}-second",
        "reviewer_subject_id": second_reviewer["subject_id"],
        "judgment": "does not match sealed intent",
        "rationale_code": "semantic-mismatch",
    }
    snapshot["reviews"].append(second_review)
    disagreement = {
        "disagreement_id": f"disagreement-{attempt['attempt_id']}",
        "review_ids": [first_review["review_id"], second_review["review_id"]],
        "status": "resolved",
        "adjudication": "original fixed judgments retained with the adjudication",
        "originals_preserved": True,
    }
    snapshot["disagreements"].append(disagreement)
    return disagreement


def test_current_bundle_declares_required_catalogs_and_an_honest_status() -> None:
    _, protocol, snapshot, analysis = _bundle()
    assert {item["dimension_id"] for item in protocol["dimensions"]} == REQUIRED_DIMENSION_IDS
    assert {item["persona_id"] for item in protocol["personas"]} == REQUIRED_PERSONA_IDS
    assert snapshot["execution_status"] == "not_started"
    assert snapshot["a" + "ces_revision"] == "38ba081714b12a4dcc7a5c527e2f1250d80a4d1b"
    assert analysis["evidence_status"] == "untested"


def test_manifest_loads_primary_and_accessibility_bundles() -> None:
    bundles = evaluation_gate.load_bundles(REPO_ROOT)

    assert [entry[0]["bundle_id"] for entry in bundles] == [
        "a" + "ces-dsl-language-evaluation",
        "a" + "ces-researcher-accessibility-evaluation",
    ]
    assert all(validate_bundle(REPO_ROOT, *entry[1:]) == [] for entry in bundles)
    _, accessibility_protocol, accessibility_snapshot, accessibility_analysis = bundles[1]
    assert accessibility_protocol["revision"] == "2.0.0"
    assert accessibility_snapshot["execution_status"] == "not_started"
    assert accessibility_analysis["evidence_status"] == "untested"
    assert accessibility_analysis["claim"]["scope"]["persona_ids"] == [
        "security-researcher",
        "benchmark-designer",
        "backend-implementer",
        "evaluator-reviewer",
    ]


def test_manifest_rejects_malformed_supplemental_bundle_entries(tmp_path: Path) -> None:
    manifest_path = tmp_path / evaluation_gate.MANIFEST_PATH
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """{
          "bundle_id": "primary-bundle",
          "revision": "1.0.0",
              "protocol_path": "protocol.json",
              "snapshot_path": "snapshot.json",
              "analysis_path": "analysis.json",
              "claim_binding": {},
              "supplemental_bundles": ["not-an-object"]
        }\n""",
        encoding="utf-8",
    )

    try:
        evaluation_gate.load_bundles(tmp_path)
    except InvalidInputError as exc:
        assert "supplemental_bundles[0] must be an object" in str(exc)
    else:
        raise AssertionError("malformed supplemental bundle entries must fail closed")


def test_claim_scope_rejects_unknown_catalog_ids() -> None:
    _, protocol, snapshot, analysis = _bundle()
    analysis["claim"]["scope"] = _full_claim_scope(protocol)
    analysis["claim"]["scope"]["task_ids"].append("missing-task")

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-claim-scope" in _rule_ids(failures)


def test_bundle_validation_reports_the_selected_analysis_path() -> None:
    _, protocol, snapshot, analysis = _bundle()
    analysis["claim"]["scope"]["task_ids"].append("missing-task")

    failures = validate_bundle(
        REPO_ROOT,
        protocol,
        snapshot,
        analysis,
        artifact_paths={"analysis_path": "docs/research/dsl-language-evaluation/custom-analysis.json"},
    )

    scope_failure = next(failure for failure in failures if failure.rule_id == "dsl-evaluation-claim-scope")
    assert scope_failure.path == "docs/research/dsl-language-evaluation/custom-analysis.json"


def test_claim_scope_ignores_frozen_records_from_another_persona() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    scope = _full_claim_scope(protocol)
    scope["persona_ids"].remove("assurance-auditor")
    next(item for item in protocol["personas"] if item["persona_id"] == "assurance-auditor")[
        "minimum_completed_subjects"
    ] = 0
    protocol["sampling_plan"]["target_total"] = 25
    analysis["claim"]["claim_id"] = "raes-language-adequacy-without-assurance-auditor"
    analysis["claim"]["scope"] = scope
    measure_results = recompute_measure_results(protocol, snapshot, scope=scope)
    analysis["measure_results"] = [
        {
            "measure_id": measure_id,
            "status": "evaluated",
            **result,
        }
        for measure_id, result in measure_results.items()
    ]
    analysis["dimension_results"] = [
        {"dimension_id": dimension_id, **result}
        for dimension_id, result in recompute_dimension_results(protocol, measure_results).items()
        if dimension_id in scope["dimension_ids"]
    ]
    claim_binding = deepcopy(load_bundle(REPO_ROOT)[0]["claim_binding"])
    claim_binding["claim_id"] = analysis["claim"]["claim_id"]
    claim_binding["scope"] = deepcopy(scope)
    claim_binding["strata"][0]["persona_ids"].remove("assurance-auditor")
    strata = evaluation_gate.resolve_claim_strata(protocol, analysis, claim_binding)
    analysis["stratum_results"] = evaluation_gate.recompute_stratum_results(protocol, snapshot, strata)

    assert (
        validate_bundle(
            REPO_ROOT,
            protocol,
            snapshot,
            analysis,
            artifact_paths={"claim_binding": claim_binding},
        )
        == []
    )


def test_analysis_cannot_narrow_the_manifest_bound_claim_scope() -> None:
    protocol, snapshot, analysis = _executed_bundle(failing=True)
    scope = _full_claim_scope(protocol)
    scope["persona_ids"] = ["evaluator-reviewer"]
    scope["task_ids"] = [
        "classify-underspecified-realization",
        "round-trip-format-equivalence",
    ]
    scope["variant_ids"] = [
        "profile-dependent-realization",
        "format-only-equivalent",
    ]
    public_tools_attempt = next(
        attempt
        for attempt in snapshot["attempts"]
        if attempt["task_id"] == "classify-underspecified-realization"
        and attempt["tooling_condition_id"] == "public-tools"
    )
    evaluator = next(subject for subject in snapshot["subjects"] if subject["persona_id"] == "evaluator-reviewer")
    public_tools_attempt["persona_id"] = "evaluator-reviewer"
    public_tools_attempt["subject_id"] = evaluator["subject_id"]
    for observation in snapshot["observations"]:
        if observation["attempt_id"] == public_tools_attempt["attempt_id"]:
            observation["persona_id"] = "evaluator-reviewer"
            observation["subject_id"] = evaluator["subject_id"]
    scope["dimension_ids"] = ["ambiguity"]
    scope["measure_ids"] = ["relation-classification-accuracy", "critical-silent-ambiguities"]
    for persona in protocol["personas"]:
        persona["minimum_completed_subjects"] = 5 if persona["persona_id"] == "evaluator-reviewer" else 0
    protocol["sampling_plan"]["target_total"] = 5
    analysis["claim"]["scope"] = scope
    measure_results = recompute_measure_results(protocol, snapshot, scope=scope)
    analysis["measure_results"] = [
        {"measure_id": measure_id, "status": "evaluated", **result} for measure_id, result in measure_results.items()
    ]
    analysis["dimension_results"] = [
        {"dimension_id": dimension_id, **result}
        for dimension_id, result in recompute_dimension_results(
            protocol,
            measure_results,
            dimension_ids=scope["dimension_ids"],
        ).items()
    ]
    analysis["evidence_status"] = "demonstrated"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-claim-binding" in _rule_ids(failures)


def test_gating_persona_failure_cannot_be_masked_by_pooled_success() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    subject_ids = {
        item["subject_id"]
        for item in snapshot["subjects"]
        if item["persona_id"] == "benchmark-designer"
        and (item["subject_id"].endswith("-1") or item["subject_id"].endswith("-2"))
    }
    failed_attempt_ids = {
        observation["attempt_id"]
        for observation in snapshot["observations"]
        if observation["subject_id"] in subject_ids and observation["measure_id"] == "task-completion"
    }
    for attempt in snapshot["attempts"]:
        if attempt["attempt_id"] in failed_attempt_ids:
            attempt["outcome"] = "failed"
    for observation in snapshot["observations"]:
        if observation["attempt_id"] in failed_attempt_ids:
            observation["outcome"] = "failed"
            if observation["measure_id"] == "task-completion":
                observation["value"] = 0

    claim_binding = deepcopy(load_bundle(REPO_ROOT)[0]["claim_binding"])
    analysis["claim"]["claim_id"] = "raes-language-adequacy-persona-gated"
    claim_binding["claim_id"] = analysis["claim"]["claim_id"]
    claim_binding["strata"][0]["group_id"] = "persona-gates"
    claim_binding["strata"][0]["partition_by"] = ["persona_id"]
    _refresh_analysis(
        protocol,
        snapshot,
        analysis,
        "demonstrated",
        claim_binding=claim_binding,
    )

    assert all(result["threshold_result"] == "pass" for result in analysis["dimension_results"])
    benchmark_result = next(
        item for item in analysis["stratum_results"] if item["stratum_id"].endswith("benchmark-designer")
    )
    assert any(result["threshold_result"] == "fail" for result in benchmark_result["dimension_results"])

    failures = validate_bundle(
        REPO_ROOT,
        protocol,
        snapshot,
        analysis,
        artifact_paths={"claim_binding": claim_binding},
    )

    assert "dsl-evaluation-evidence-status" in _rule_ids(failures)


def test_comparison_persona_is_persisted_but_cannot_decide_promotion() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    failed_attempt_ids = {
        observation["attempt_id"]
        for observation in snapshot["observations"]
        if observation["persona_id"] == "backend-implementer" and observation["measure_id"] == "task-completion"
    }
    for attempt in snapshot["attempts"]:
        if attempt["attempt_id"] in failed_attempt_ids:
            attempt["outcome"] = "failed"
    for observation in snapshot["observations"]:
        if observation["attempt_id"] in failed_attempt_ids:
            observation["outcome"] = "failed"
            if observation["measure_id"] == "task-completion":
                observation["value"] = 0

    claim_binding = deepcopy(load_bundle(REPO_ROOT)[0]["claim_binding"])
    analysis["claim"]["claim_id"] = "raes-language-adequacy-with-backend-comparison"
    claim_binding["claim_id"] = analysis["claim"]["claim_id"]
    base_group = claim_binding["strata"][0]
    claim_binding["strata"] = [
        {
            **deepcopy(base_group),
            "group_id": "target-population",
            "persona_ids": [
                persona_id for persona_id in base_group["persona_ids"] if persona_id != "backend-implementer"
            ],
        },
        {
            **deepcopy(base_group),
            "group_id": "backend-comparison",
            "role": "comparison",
            "persona_ids": ["backend-implementer"],
        },
    ]
    _refresh_analysis(
        protocol,
        snapshot,
        analysis,
        "demonstrated",
        claim_binding=claim_binding,
    )

    comparison = next(item for item in analysis["stratum_results"] if item["role"] == "comparison")
    assert any(result["threshold_result"] == "fail" for result in comparison["dimension_results"])
    assert (
        validate_bundle(
            REPO_ROOT,
            protocol,
            snapshot,
            analysis,
            artifact_paths={"claim_binding": claim_binding},
        )
        == []
    )


def test_claim_binding_rejects_an_invalid_stratum_role() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    claim_binding = deepcopy(load_bundle(REPO_ROOT)[0]["claim_binding"])
    claim_binding["strata"][0]["role"] = "observer"

    failures = validate_bundle(
        REPO_ROOT,
        protocol,
        snapshot,
        analysis,
        artifact_paths={"claim_binding": claim_binding},
    )

    assert "dsl-evaluation-claim-strata" in _rule_ids(failures)


def test_gate_rejects_stale_stratum_results() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    analysis["stratum_results"][0]["measure_results"][0]["denominator"] += 1

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-stratum-drift" in _rule_ids(failures)


def test_gate_rejects_missing_stratum_results() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    analysis["stratum_results"].clear()

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-stratum-coverage" in _rule_ids(failures)


def test_scope_completion_requires_each_subjects_in_scope_condition() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    scope = _full_claim_scope(protocol)
    scope["persona_ids"] = ["benchmark-designer"]
    scope["task_ids"] = ["author-multihost-experiment", "independent-review-change"]
    scope["tooling_condition_ids"] = ["public-docs-only"]
    scope["variant_ids"] = ["multihost-reference", "review-hidden-assumption-change"]
    scope["dimension_ids"] = ["usability-comprehension", "reviewability"]
    scope["measure_ids"] = [
        "task-completion",
        "critical-semantic-errors",
        "critical-review-items",
        "majority-missed-critical-items",
    ]
    benchmark_subjects = [subject for subject in snapshot["subjects"] if subject["persona_id"] == "benchmark-designer"]
    for persona in protocol["personas"]:
        persona["minimum_completed_subjects"] = 5 if persona["persona_id"] == "benchmark-designer" else 0
    protocol["sampling_plan"]["target_total"] = 5
    for attempt in snapshot["attempts"]:
        if (
            attempt["subject_id"] in {subject["subject_id"] for subject in benchmark_subjects[1:]}
            and attempt["task_id"] == "author-multihost-experiment"
            and attempt["tooling_condition_id"] == "public-docs-only"
        ):
            attempt["tooling_condition_id"] = "public-tools"
            for observation in snapshot["observations"]:
                if observation["attempt_id"] == attempt["attempt_id"]:
                    observation["tooling_condition_id"] = "public-tools"
    analysis["claim"]["scope"] = scope
    measure_results = recompute_measure_results(protocol, snapshot, scope=scope)
    analysis["measure_results"] = [
        {"measure_id": measure_id, "status": "evaluated", **result} for measure_id, result in measure_results.items()
    ]
    analysis["dimension_results"] = [
        {"dimension_id": dimension_id, **result}
        for dimension_id, result in recompute_dimension_results(
            protocol,
            measure_results,
            dimension_ids=scope["dimension_ids"],
        ).items()
    ]

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-subject-workload" in _rule_ids(failures)


def test_not_started_bundle_cannot_claim_observations_or_demonstration() -> None:
    _, protocol, snapshot, analysis = _bundle()
    snapshot["attempts"].append({"attempt_id": "fabricated"})
    analysis["evidence_status"] = "demonstrated"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "dsl-evaluation-not-started-observations",
        "dsl-evaluation-evidence-status",
    }.issubset(_rule_ids(failures))


def test_protocol_gate_requires_every_issue_dimension_persona_and_task_kind() -> None:
    _, protocol, snapshot, analysis = _bundle()
    protocol["dimensions"] = [item for item in protocol["dimensions"] if item["dimension_id"] != "reviewability"]
    protocol["thresholds"] = [item for item in protocol["thresholds"] if item["dimension_id"] != "reviewability"]
    protocol["personas"] = [item for item in protocol["personas"] if item["persona_id"] != "assurance-auditor"]
    protocol["tasks"] = [item for item in protocol["tasks"] if item["kind"] != "ambiguous"]

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "dsl-evaluation-dimension-coverage",
        "dsl-evaluation-persona-coverage",
        "dsl-evaluation-task-kind-coverage",
    }.issubset(_rule_ids(failures))


def test_protocol_gate_rejects_unknown_fields_and_broken_catalog_joins() -> None:
    _, protocol, snapshot, analysis = _bundle()
    protocol["tasks"][0]["backend_hint"] = "private"
    protocol["tasks"][1]["persona_ids"] = ["missing-persona"]

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "dsl-evaluation-protocol-shape",
        "dsl-evaluation-task-join",
    }.issubset(_rule_ids(failures))


def test_gate_rejects_unsafe_public_and_claim_evidence_paths() -> None:
    _, protocol, snapshot, analysis = _bundle()
    snapshot["public_surface"][0]["artifact"] = "../outside.md"
    analysis["claim"]["evidence_artifacts"][0] = "../outside.json"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "dsl-evaluation-public-surface-path",
        "dsl-evaluation-claim-evidence-path",
    }.issubset(_rule_ids(failures))


def test_repository_source_locator_must_match_its_pinned_revision() -> None:
    _, protocol, snapshot, analysis = _bundle()
    source = next(item for item in protocol["sources"] if item["kind"] == "repository-internal")
    source["locator"] = source["locator"].replace(source["revision"], "0" * 40)

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-source-pin" in _rule_ids(failures)


def test_demonstrated_status_requires_preregistered_subject_and_task_coverage() -> None:
    _, protocol, snapshot, analysis = _bundle()
    snapshot["execution_status"] = "complete"
    snapshot["ethics_review"]["status"] = "approved"
    analysis["execution_status"] = "complete"
    analysis["evidence_status"] = "demonstrated"
    for result in analysis["dimension_results"]:
        result.update(
            {
                "status": "evaluated",
                "numerator": 1,
                "denominator": 1,
                "value": 1.0,
                "threshold_result": "pass",
            }
        )

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-completion-coverage" in _rule_ids(failures)


def test_shape_valid_complete_bundles_support_passing_and_failing_results() -> None:
    passing_protocol, passing_snapshot, passing_analysis = _executed_bundle()
    failing_protocol, failing_snapshot, failing_analysis = _executed_bundle(failing=True)

    assert validate_bundle(REPO_ROOT, passing_protocol, passing_snapshot, passing_analysis) == []
    assert passing_analysis["evidence_status"] == "demonstrated"
    assert validate_bundle(REPO_ROOT, failing_protocol, failing_snapshot, failing_analysis) == []
    assert failing_analysis["evidence_status"] == "refuted"


def test_opportunity_matrix_rejects_a_self_selected_observation_subset() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    omitted = snapshot["observations"].pop()
    parent = next(item for item in snapshot["attempts"] if item["attempt_id"] == omitted["attempt_id"])
    parent["observation_ids"].remove(omitted["observation_id"])
    _refresh_analysis(protocol, snapshot, analysis, "partial")

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)
    measure = next(result for result in analysis["measure_results"] if result["measure_id"] == omitted["measure_id"])

    assert "dsl-evaluation-opportunity-coverage" in _rule_ids(failures)
    assert measure["missing_count"] == 1
    assert measure["observed_count"] + measure["missing_count"] == measure["denominator"]


def test_stage_opportunity_matrix_requires_every_preregistered_artifact_stage() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    omitted = next(
        observation
        for observation in snapshot["observations"]
        if observation["measure_id"] == "untraced-critical-changes"
        and observation["task_id"] == "author-multihost-experiment"
        and observation["artifact_stage"] == "compiled"
    )
    snapshot["observations"].remove(omitted)
    parent = next(attempt for attempt in snapshot["attempts"] if attempt["attempt_id"] == omitted["attempt_id"])
    parent["observation_ids"].remove(omitted["observation_id"])
    _refresh_analysis(protocol, snapshot, analysis, "partial")

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)
    measure = next(
        result for result in analysis["measure_results"] if result["measure_id"] == "untraced-critical-changes"
    )

    assert "dsl-evaluation-opportunity-coverage" in _rule_ids(failures)
    assert measure["missing_count"] == 1
    assert measure["observed_count"] + measure["missing_count"] == measure["denominator"]


def test_observation_stage_must_match_measure_stage_applicability() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    observation = next(
        item
        for item in snapshot["observations"]
        if item["measure_id"] == "task-completion" and item["task_id"] == "author-multihost-experiment"
    )
    observation["artifact_stage"] = "authored"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "dsl-evaluation-observation-task-join",
        "dsl-evaluation-opportunity-coverage",
    }.issubset(_rule_ids(failures))


def test_protocol_requires_closed_task_variant_stage_declarations() -> None:
    _, protocol, snapshot, analysis = _bundle()
    protocol["measures"][0]["stage_applicability"].pop()

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-measure-stage-coverage" in _rule_ids(failures)


def test_complete_status_requires_each_subjects_preregistered_workload() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    subject = next(
        item
        for item in snapshot["subjects"]
        if item["persona_id"] == "benchmark-designer" and item["subject_id"].endswith("-1")
    )
    challenge_kinds = set(protocol["execution_plan"]["subject_task_requirements"][1]["task_kinds"])
    task_kinds = {task["task_id"]: task["kind"] for task in protocol["tasks"]}
    removed_attempt_ids = {
        attempt["attempt_id"]
        for attempt in snapshot["attempts"]
        if attempt["subject_id"] == subject["subject_id"] and task_kinds[attempt["task_id"]] in challenge_kinds
    }
    snapshot["attempts"] = [
        attempt for attempt in snapshot["attempts"] if attempt["attempt_id"] not in removed_attempt_ids
    ]
    snapshot["observations"] = [
        observation for observation in snapshot["observations"] if observation["attempt_id"] not in removed_attempt_ids
    ]
    snapshot["reviews"] = [review for review in snapshot["reviews"] if review["attempt_id"] not in removed_attempt_ids]
    _refresh_analysis(protocol, snapshot, analysis, "demonstrated")

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-subject-workload" in _rule_ids(failures)


def test_protocol_requires_structured_per_subject_task_groups() -> None:
    _, protocol, snapshot, analysis = _bundle()
    protocol["execution_plan"]["subject_task_requirements"].pop()

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-subject-workload-plan" in _rule_ids(failures)


def test_execution_graph_rejects_disconnected_parent_and_task_fields() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    observation = snapshot["observations"][0]
    observation["persona_id"] = "assurance-auditor"
    observation["artifact_stage"] = "review-judgment"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "dsl-evaluation-observation-parent-join",
        "dsl-evaluation-observation-task-join",
    }.issubset(_rule_ids(failures))


def test_independent_review_gate_rejects_every_ineligible_reviewer_path() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    baseline = (protocol, snapshot, analysis)

    for case in (
        "self-review",
        "withdrawn-reviewer",
        "ineligible-persona",
        "task-without-review-stage",
        "wrong-parent-task",
        "wrong-parent-variant",
        "unknown-reviewer",
    ):
        protocol, snapshot, analysis = deepcopy(baseline)
        review = snapshot["reviews"][0]
        attempt = next(item for item in snapshot["attempts"] if item["attempt_id"] == review["attempt_id"])
        task = next(item for item in protocol["tasks"] if item["task_id"] == attempt["task_id"])

        if case == "self-review":
            review["reviewer_subject_id"] = attempt["subject_id"]
        elif case == "withdrawn-reviewer":
            reviewer = next(
                item for item in snapshot["subjects"] if item["subject_id"] == review["reviewer_subject_id"]
            )
            reviewer["consent_status"] = "withdrawn"
        elif case == "ineligible-persona":
            review["reviewer_subject_id"] = next(
                item["subject_id"]
                for item in snapshot["subjects"]
                if item["subject_id"] != attempt["subject_id"] and item["persona_id"] not in task["persona_ids"]
            )
        elif case == "task-without-review-stage":
            task["artifact_stage_ids"].remove("review-judgment")
        elif case == "wrong-parent-task":
            review["task_id"] = next(
                item["task_id"] for item in protocol["tasks"] if item["task_id"] != task["task_id"]
            )
        elif case == "wrong-parent-variant":
            review["variant_id"] = "different-variant"
        else:
            review["reviewer_subject_id"] = "unknown-reviewer"

        failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

        assert "dsl-evaluation-review-join" in _rule_ids(failures), case


def test_independent_review_gate_rejects_every_malformed_fixed_judgment_path() -> None:
    baseline = _executed_bundle()

    for field, invalid_value in (
        ("judgment", ""),
        ("confidence", True),
        ("confidence", "high"),
        ("confidence", -0.1),
        ("confidence", 1.1),
        ("rationale_code", "not a valid rationale id"),
        ("fixed_at", ""),
    ):
        protocol, snapshot, analysis = deepcopy(baseline)
        snapshot["reviews"][0][field] = invalid_value

        failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

        assert "dsl-evaluation-review-shape" in _rule_ids(failures), (field, invalid_value)


def test_disagreements_must_join_distinct_reviews_of_one_parent_attempt() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    disagreement = _append_valid_disagreement(protocol, snapshot)
    assert validate_bundle(REPO_ROOT, protocol, snapshot, analysis) == []

    other_parent_review = next(
        review for review in snapshot["reviews"] if review["attempt_id"] != snapshot["reviews"][0]["attempt_id"]
    )
    disagreement["review_ids"][1] = other_parent_review["review_id"]

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-disagreement-join" in _rule_ids(failures)


def test_disagreement_adjudication_cannot_discard_original_judgments() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    disagreement = _append_valid_disagreement(protocol, snapshot)
    disagreement["originals_preserved"] = False

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-disagreement-preservation" in _rule_ids(failures)


def test_withdrawals_are_excluded_only_through_the_closed_parent_graph() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    withdrawn_subject = snapshot["subjects"][0]
    withdrawn_subject["consent_status"] = "withdrawn"
    snapshot["withdrawals"] = [
        {
            "subject_id": withdrawn_subject["subject_id"],
            "recorded_at": "2026-07-15T11:00:00Z",
            "retained_aggregate_only": True,
        }
    ]
    withdrawn_attempt_ids = {
        attempt["attempt_id"]
        for attempt in snapshot["attempts"]
        if attempt["subject_id"] == withdrawn_subject["subject_id"]
    }
    for attempt in snapshot["attempts"]:
        if attempt["attempt_id"] in withdrawn_attempt_ids:
            attempt["outcome"] = "withdrawn"
            attempt["observation_ids"] = []
    snapshot["observations"] = [
        observation
        for observation in snapshot["observations"]
        if observation["attempt_id"] not in withdrawn_attempt_ids
    ]
    snapshot["reviews"] = [
        review
        for review in snapshot["reviews"]
        if review["attempt_id"] not in withdrawn_attempt_ids
        and review["reviewer_subject_id"] != withdrawn_subject["subject_id"]
    ]
    snapshot["execution_status"] = "in_progress"
    _refresh_analysis(protocol, snapshot, analysis, "partial")

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert failures == []
    assert any(result["withdrawn_count"] > 0 for result in analysis["measure_results"])


def test_complete_missing_outcomes_remain_explicit_partial_evidence() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    attempt = next(item for item in snapshot["attempts"] if item["task_id"] == "author-multihost-experiment")
    attempt["outcome"] = "missing"
    for observation in snapshot["observations"]:
        if observation["attempt_id"] != attempt["attempt_id"]:
            continue
        observation["outcome"] = "missing"
        observation["value"] = 0 if observation["measure_id"] == "task-completion" else None
    _refresh_analysis(protocol, snapshot, analysis, "partial")

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert failures == []
    assert any(result["missing_count"] > 0 for result in analysis["measure_results"])
    assert any(result["status"] == "incomplete" for result in analysis["measure_results"])


def test_evidence_status_is_derived_from_recomputed_dimension_results() -> None:
    protocol, snapshot, analysis = _executed_bundle()
    analysis["evidence_status"] = "refuted"
    unsupported_refutation = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    snapshot["execution_status"] = "in_progress"
    _refresh_analysis(protocol, snapshot, analysis, "partial")
    supported_partial = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)
    analysis["evidence_status"] = "untested"
    unsupported_untested = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-evidence-status" in _rule_ids(unsupported_refutation)
    assert supported_partial == []
    assert "dsl-evaluation-evidence-status" in _rule_ids(unsupported_untested)


def test_measure_results_are_recomputed_from_frozen_observations() -> None:
    protocol, snapshot, _ = _executed_bundle()
    completion_observations = [
        observation for observation in snapshot["observations"] if observation["measure_id"] == "task-completion"
    ]
    for index, observation in enumerate(completion_observations):
        observation["value"] = index % 2

    results = recompute_measure_results(protocol, snapshot)

    completion = results["task-completion"]
    assert completion["denominator"] == len(completion_observations)
    assert completion["observed_count"] == completion["opportunity_count"]
    assert completion["numerator"] == sum(index % 2 for index in range(len(completion_observations)))
    assert completion["value"] == completion["numerator"] / completion["denominator"]
    assert results["semantic-rework-cycles"]["statistic"] == "median"
    assert results["semantic-rework-cycles"]["value"] == 0.0


def test_gate_rejects_stale_measure_results() -> None:
    _, protocol, snapshot, analysis = _bundle()
    recomputed = recompute_measure_results(protocol, snapshot)
    analysis["measure_results"] = [
        {"measure_id": measure_id, "status": "not_evaluated", **result} for measure_id, result in recomputed.items()
    ]
    analysis["measure_results"][0]["value"] = 1.0

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-analysis-measure-drift" in _rule_ids(failures)


def test_gate_rejects_secret_bearing_source_locators() -> None:
    _, protocol, snapshot, analysis = _bundle()
    protocol["sources"][0]["locator"] = "https://example.test/paper?access_token=secret"

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert "dsl-evaluation-source-secret" in _rule_ids(failures)


def test_shared_json_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    artifact = tmp_path / "duplicate.json"
    artifact.write_text('{"revision": 1, "revision": 2}\n', encoding="utf-8")

    try:
        load_bounded_json_object(tmp_path, "duplicate.json", max_bytes=1024)
    except InvalidInputError as exc:
        assert "duplicate JSON key 'revision'" in str(exc)
    else:
        raise AssertionError("duplicate JSON keys must fail closed")


def test_malformed_scalar_fields_fail_closed_without_crashing() -> None:
    _, protocol, snapshot, analysis = _bundle()
    protocol["sources"][-1]["locator"] = None
    protocol["tasks"][0]["variant_ids"] = 1
    snapshot["public_surface"][0]["artifact"] = {"path": "not-text"}

    failures = validate_bundle(REPO_ROOT, protocol, snapshot, analysis)

    assert {
        "dsl-evaluation-source-locator",
        "dsl-evaluation-task-join",
        "dsl-evaluation-public-surface-path",
    }.issubset(_rule_ids(failures))


def test_dimension_thresholds_are_recomputed_from_measure_results() -> None:
    _, protocol, _, analysis = _bundle()
    measure_results = {item["measure_id"]: deepcopy(item) for item in analysis["measure_results"]}
    for result in measure_results.values():
        result.update({"status": "evaluated", "denominator": 10, "value": 1.0})
    measure_results["critical-semantic-errors"]["value"] = 0.0
    measure_results["semantic-rework-cycles"]["value"] = 1.0
    for measure_id in (
        "critical-silent-omissions",
        "silent-lossy-migrations",
        "critical-silent-ambiguities",
        "majority-missed-critical-items",
        "untraced-critical-changes",
    ):
        measure_results[measure_id]["value"] = 0

    passing = recompute_dimension_results(protocol, measure_results)
    assert all(result["threshold_result"] == "pass" for result in passing.values())

    measure_results["task-completion"]["value"] = 0.5
    failing = recompute_dimension_results(protocol, measure_results)
    assert failing["usability-comprehension"]["threshold_result"] == "fail"
    assert failing["effectiveness-productivity"]["threshold_result"] == "fail"


def test_measure_recomputation_refusal_is_an_observation_failure(monkeypatch) -> None:
    from tools.dsl_language_evaluation import _analysis

    _, protocol, snapshot, analysis = _bundle()

    def refuse(*_args, **_kwargs):
        raise InvalidInputError("seeded observation refusal")

    monkeypatch.setattr(_analysis, "recompute_measure_results", refuse)
    failures = []
    _analysis._measure_result_failures(protocol, snapshot, analysis, {"measure_ids": set()}, failures, "analysis.json")

    assert ("dsl-evaluation-observation-value", "seeded observation refusal") in {
        (failure.rule_id, failure.message) for failure in failures
    }


def test_measure_recomputation_defect_is_not_reported_as_an_observation_failure(monkeypatch) -> None:
    from tools.dsl_language_evaluation import _analysis

    _, protocol, snapshot, analysis = _bundle()

    def defect(*_args, **_kwargs):
        raise ValueError("seeded defect")

    monkeypatch.setattr(_analysis, "recompute_measure_results", defect)
    failures = []
    try:
        _analysis._measure_result_failures(
            protocol, snapshot, analysis, {"measure_ids": set()}, failures, "analysis.json"
        )
    except ValueError as exc:
        assert str(exc) == "seeded defect"
    else:
        raise AssertionError("a defect must propagate instead of becoming an evidence failure")
    assert "dsl-evaluation-observation-value" not in _rule_ids(failures)
