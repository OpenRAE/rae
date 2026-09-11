"""Integrity tests for the formal semantic-validation evidence bundle."""

from __future__ import annotations

import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import tools.check_formal_semantic_validation as formal_validation
from tools.check_formal_semantic_validation import (
    REQUIRED_CLAIM_CLASS_IDS,
    REQUIRED_PARTICIPANT_OBLIGATION_IDS,
    _replay_participant_tests,
    evaluate,
    load_bundle,
    load_release_bundles,
    load_retest_bundle,
    load_satisfiability_analysis,
    validate_bundle,
    validate_release_bundle,
    validate_retest_bundle,
    validate_satisfiability_analysis,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _rule_ids(failures: list[object]) -> set[str]:
    return {failure.rule_id for failure in failures}


def _bundle() -> tuple[dict, dict, dict, dict, dict]:
    return tuple(deepcopy(item) for item in load_bundle(REPO_ROOT))  # type: ignore[return-value]


def test_historical_bundle_integrity_is_clean() -> None:
    assert validate_bundle(REPO_ROOT, *_bundle(), replay_cases=False) == []


def test_atomic_release_index_validates_every_historical_bundle() -> None:
    releases = load_release_bundles(REPO_ROOT)

    assert [release.manifest["revision"] for release in releases] == [
        "1.0.0",
        "1.1.0",
        "1.2.0",
        "2.0.0",
        "3.0.0",
        "4.0.0",
        "5.0.0",
        "6.0.0",
        "7.0.0",
    ]
    assert all(validate_release_bundle(REPO_ROOT, release) == [] for release in releases)


def test_current_retest_bundle_is_coherent_and_clean() -> None:
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(REPO_ROOT)

    assert release.manifest["revision"] == "7.0.0"
    assert protocol["revision"] == corpus["revision"] == "2.0.0"
    assert snapshot["baseline"]["release_revision"] == "6.0.0"
    assert snapshot["deviations"] == []
    assert validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis) == []


def test_historical_release_validation_does_not_replay_current_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = deepcopy(load_release_bundles(REPO_ROOT)[2])

    def fail_if_replayed(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("historical evidence must not replay current code")

    from tools.formal_semantic_validation import _retest, _snapshot

    monkeypatch.setattr(_snapshot, "replay_case", fail_if_replayed)
    monkeypatch.setattr(_retest, "replay_case", fail_if_replayed)

    assert validate_release_bundle(REPO_ROOT, release) == []


def test_unlisted_current_replay_does_not_enable_legacy_sdl_migration() -> None:
    result = formal_validation.replay_case(
        REPO_ROOT,
        {
            "case_id": "current-unpinned-case",
            "fixture_path": "docs/research/formal-semantic-validation/corpus/semantic-valid.sdl.yaml",
            "replay_mode": "parse",
        },
    )

    assert result["actual_outcome"] == "rejected"
    assert result["diagnostic_kind"] == "SDLParseError"


@pytest.mark.parametrize(
    ("case_id", "recorded", "changed"),
    [
        (
            "schema-valid-control",
            "8d7592f5631ea6748a8ad2b482fb431839cc1eb74d79db24d0e6d159a7f1dddc",
            "f7d364ef384df8a1526b489501835b635021c860793b5764f91d956710d2250c",
        ),
        (
            "semantic-resolved-objective",
            "8291a196859dbb09e9b2ef586ce179f1138139f469b92f03f16afb35877461a1",
            "fadacf4359c97415f5433563e675d454c587917c85064b625d9756e4da1c4967",
        ),
        (
            "workflow-reachable-control",
            "9d1d9d8bbaec15c6419a9a0665e148cfdfa3048af5a61d71c3fa2bfd742929b9",
            "b1b49649b54bd59d4ef357b39cf9158da90f4eae560f8dd756acf97bd0827a06",
        ),
        (
            "compile-repeatability-control",
            "a7a03db548d2a62214567834da0876609f9ff64f988878f719f846e6c5218f31",
            "16cc92b2743538f193c9248dd5b5b8eca39787566a59d5ac3125923d41da6a38",
        ),
        (
            "compile-non-vacuity-control",
            "a9705de7191f3d2a76bd7aa53a1da0603c1cdc60f154a90c4e9cba6bf4d37e76",
            "c4dc90b8056de2a3f41012c181bb4a611045d5d042503c7ea71fcf86ea5e926b",
        ),
    ],
)
def test_classification_replay_drift_is_not_accepted_by_a_digest_pair(case_id, recorded, changed) -> None:
    from tools.formal_semantic_validation._replay import _replay_observation_matches

    observation = {"actual_outcome": "accepted", "diagnostic_kind": None, "result_digest": recorded}
    replayed = {**observation, "result_digest": changed}
    assert not _replay_observation_matches(observation, replayed)


def test_retest_gate_requires_explicit_baseline_drift_disposition() -> None:
    release = next(item for item in load_release_bundles(REPO_ROOT) if item.manifest["revision"] == "5.0.0")
    protocol, corpus, snapshot, analysis = (
        deepcopy(release.protocol),
        deepcopy(release.corpus),
        deepcopy(release.snapshot),
        deepcopy(release.analysis),
    )
    snapshot["deviations"] = snapshot["deviations"][1:]

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis, replay_current=False)

    assert "formal-validation-baseline-drift" in _rule_ids(failures)


def test_retest_gate_rejects_stale_baseline_observation_value() -> None:
    release = next(item for item in load_release_bundles(REPO_ROOT) if item.manifest["revision"] == "5.0.0")
    protocol, corpus, snapshot, analysis = (
        deepcopy(release.protocol),
        deepcopy(release.corpus),
        deepcopy(release.snapshot),
        deepcopy(release.analysis),
    )
    snapshot["deviations"][0]["baseline"]["result_digest"] = "0" * 64

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis, replay_current=False)

    assert "formal-validation-baseline-drift" in _rule_ids(failures)


def test_retest_gate_rejects_changed_baseline_release_digest() -> None:
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(REPO_ROOT)
    snapshot = deepcopy(snapshot)
    snapshot["baseline"]["release_sha256"] = "0" * 64

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)

    assert "formal-validation-baseline-selection" in _rule_ids(failures)


def test_current_retest_requires_drift_disposition_for_production_evidence_cases() -> None:
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(REPO_ROOT)
    snapshot = deepcopy(snapshot)
    observation = next(item for item in snapshot["observations"] if item["case_id"] == "finite-domain-satisfiable-v2")
    observation["result_digest"] = "0" * 64

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)

    assert "formal-validation-baseline-drift" in _rule_ids(failures)


def test_retest_production_evidence_contains_governed_payloads() -> None:
    from raes_contracts.exploit_path import ExploitPathAnalysisEvidenceModel
    from raes_contracts.satisfiability import ScenarioSatisfiabilityEvidenceModel

    evidence_root = REPO_ROOT / "docs/research/formal-semantic-validation/evidence"
    satisfiable = ScenarioSatisfiabilityEvidenceModel.model_validate_json(
        (evidence_root / "finite-domain-satisfiable-v2.json").read_text(encoding="utf-8")
    )
    unsatisfiable = ScenarioSatisfiabilityEvidenceModel.model_validate_json(
        (evidence_root / "finite-domain-unsatisfiable-v2.json").read_text(encoding="utf-8")
    )
    valid_path = ExploitPathAnalysisEvidenceModel.model_validate_json(
        (evidence_root / "typed-exploit-path-valid-v2.json").read_text(encoding="utf-8")
    )
    invalid_path = ExploitPathAnalysisEvidenceModel.model_validate_json(
        (evidence_root / "typed-exploit-path-invalid-v2.json").read_text(encoding="utf-8")
    )

    assert satisfiable.witness is not None
    assert unsatisfiable.unsat_core is not None
    assert unsatisfiable.unsat_core.minimality == "subset-minimal"
    assert valid_path.witness is not None and valid_path.witness.steps
    assert invalid_path.failure is not None
    assert invalid_path.failure.unsatisfied_goal


def test_atomic_release_rejects_changed_snapshot_digest() -> None:
    release = deepcopy(load_release_bundles(REPO_ROOT)[0])
    release.manifest["snapshot_sha256"] = "0" * 64

    failures = validate_release_bundle(REPO_ROOT, release)

    assert "formal-validation-release-digest" in _rule_ids(failures)


def test_retest_gate_rejects_missing_production_evidence_join() -> None:
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(REPO_ROOT)
    snapshot = deepcopy(snapshot)
    observation = next(item for item in snapshot["observations"] if item["case_id"] == "finite-domain-satisfiable-v2")
    observation["evidence_artifact_path"] = None

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)

    assert "formal-validation-production-evidence-join" in _rule_ids(failures)


def test_retest_gate_rejects_forged_production_configuration_digest() -> None:
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(REPO_ROOT)
    snapshot = deepcopy(snapshot)
    observation = next(item for item in snapshot["observations"] if item["case_id"] == "finite-domain-satisfiable-v2")
    observation["configuration_digest"] = f"sha256:{'0' * 64}"

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)

    assert "formal-validation-production-evidence-join" in _rule_ids(failures)


def test_retest_gate_authenticates_immutable_evidence_payload_before_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from raes_processor.satisfiability import analyze_scenario_file

    release = next(item for item in load_release_bundles(REPO_ROOT) if item.manifest["revision"] == "3.0.0")
    protocol, corpus, snapshot, analysis = release.protocol, release.corpus, release.snapshot, release.analysis
    evidence_path = "docs/research/formal-semantic-validation/evidence/finite-domain-satisfiable-v2.json"
    fixture_path = REPO_ROOT / "docs/research/formal-semantic-validation/corpus/satisfiable-control.sdl.yaml"
    replacement = analyze_scenario_file(
        fixture_path,
        profile="raes-finite-domain-satisfiability-v1",
    ).model_dump(mode="json")
    original_loader = formal_validation.load_bounded_json_object

    def replace_stored_evidence(repo_root: Path, relative_path: str, *, max_bytes: int):
        if relative_path == evidence_path:
            return replacement
        return original_loader(repo_root, relative_path, max_bytes=max_bytes)

    from tools.formal_semantic_validation import _production

    monkeypatch.setattr(_production, "load_bounded_json_object", replace_stored_evidence)

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis, replay_current=False)

    assert "formal-validation-production-evidence-join" in _rule_ids(failures)


def test_retest_gate_rejects_test_local_substitute_command() -> None:
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(REPO_ROOT)
    snapshot = deepcopy(snapshot)
    command = next(item for item in snapshot["commands"] if item["command_id"] == "finite-domain-satisfiable-v2")
    command["argv"][0] = "implementations/python/tests/fake-analyzer.py"

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)

    assert "formal-validation-production-command" in _rule_ids(failures)


def test_retest_analysis_status_is_derived_not_copied_from_ceiling() -> None:
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(REPO_ROOT)
    snapshot = deepcopy(snapshot)
    analysis = deepcopy(analysis)
    observation = next(item for item in snapshot["observations"] if item["case_id"] == "finite-domain-unsatisfiable-v2")
    observation["actual_outcome"] = "satisfiable"
    result = next(item for item in analysis["claim_results"] if item["claim_class_id"] == "constraint-satisfiability")
    result["evidence_status"] = "demonstrated"

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)

    assert "formal-validation-analysis-drift" in _rule_ids(failures)
    assert "formal-validation-unsupported-overclaim" in _rule_ids(failures)


def test_retest_gate_rejects_promotion_from_historical_unsupported_cases() -> None:
    release, protocol, corpus, snapshot, analysis = load_retest_bundle(REPO_ROOT)
    corpus = deepcopy(corpus)
    snapshot = deepcopy(snapshot)
    removed_ids = {"typed-exploit-path-valid-v2", "typed-exploit-path-invalid-v2"}
    corpus["cases"] = [item for item in corpus["cases"] if item["case_id"] not in removed_ids]
    snapshot["observations"] = [item for item in snapshot["observations"] if item["case_id"] not in removed_ids]
    snapshot["commands"] = [item for item in snapshot["commands"] if item["command_id"] not in removed_ids]

    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)

    assert "formal-validation-unsupported-overclaim" in _rule_ids(failures)


def test_protocol_keeps_all_literature_claim_classes_distinct() -> None:
    _, protocol, _, _, _ = _bundle()

    assert {item["claim_class_id"] for item in protocol["claim_classes"]} == REQUIRED_CLAIM_CLASS_IDS


def test_historical_satisfiability_release_remains_atomically_selected() -> None:
    manifest, _protocol, _corpus, _snapshot, _analysis = _bundle()
    assert manifest["revision"] == "2.0.0"
    assert manifest["snapshot_path"].endswith("execution-snapshot-v1.2.json")
    assert manifest["satisfiability_snapshot_path"].endswith("satisfiability-execution-snapshot-v1.json")


def test_gate_requires_positive_and_negative_cases_for_every_claim_class() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    corpus["cases"] = [
        case
        for case in corpus["cases"]
        if not (case["claim_class_id"] == "graph-reachability" and case["polarity"] == "negative")
    ]

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-case-polarity" in _rule_ids(failures)


def test_gate_rejects_dangling_case_observations() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    snapshot["observations"][0]["case_id"] = "missing-case"

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-observation-case" in _rule_ids(failures)


def test_gate_rejects_unsafe_fixture_paths() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    case = next(item for item in corpus["cases"] if item["fixture_path"] is not None)
    case["fixture_path"] = "../outside.sdl.yaml"

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-case-path" in _rule_ids(failures)


def test_gate_rejects_observations_that_drift_from_executable_cases() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    observation = next(item for item in snapshot["observations"] if item["replayable"])
    observation["actual_outcome"] = "unexpected-outcome"

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-replay-drift" in _rule_ids(failures)


def test_gate_rejects_promotion_of_unsupported_solver_level_claims() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    result = next(item for item in analysis["claim_results"] if item["claim_class_id"] == "exploit-path-validity")
    result["evidence_status"] = "demonstrated"

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-unsupported-overclaim" in _rule_ids(failures)


def test_gate_requires_every_participant_semantics_obligation() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    protocol["participant_obligations"] = protocol["participant_obligations"][:-1]

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-participant-coverage" in _rule_ids(failures)
    assert {
        item["obligation_id"] for item in protocol["participant_obligations"]
    } != REQUIRED_PARTICIPANT_OBLIGATION_IDS


def test_gate_requires_positive_and_negative_participant_fixture_refs() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    protocol["participant_obligations"][0]["negative_test_ref"] = protocol["participant_obligations"][0][
        "positive_test_ref"
    ]

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-participant-fixtures" in _rule_ids(failures)


def test_gate_binds_participant_observations_to_the_declared_test_refs() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    snapshot["participant_observations"][0]["evidence_refs"].reverse()

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-participant-observation-evidence" in _rule_ids(failures)


def test_gate_replays_participant_tests_instead_of_trusting_pass_labels() -> None:
    def failed_replay(_repo_root: Path, _test_refs: list[str]) -> tuple[bool, str]:
        return False, "seeded participant fixture failure"

    failures = evaluate(REPO_ROOT, participant_test_runner=failed_replay)

    assert "formal-validation-participant-replay" in _rule_ids(failures)


@pytest.mark.parametrize(
    ("returncode", "expected"),
    [(0, (True, "")), (3, (False, "participant fixture replay exited with status 3"))],
)
def test_participant_test_replay_maps_pytest_status(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    expected: tuple[bool, str],
) -> None:
    monkeypatch.setattr(
        "tools.formal_semantic_validation._replay.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=returncode),
    )

    assert _replay_participant_tests(REPO_ROOT, ["tests/test_example.py::test_case"]) == expected


def test_participant_test_replay_fails_closed_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def timed_out(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=600)

    monkeypatch.setattr("tools.formal_semantic_validation._replay.subprocess.run", timed_out)

    ok, message = _replay_participant_tests(REPO_ROOT, ["tests/test_example.py::test_case"])

    assert not ok
    assert message.startswith("participant fixture replay could not complete:")


def test_gate_recomputes_claim_statuses_from_frozen_observations() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    result = next(item for item in analysis["claim_results"] if item["claim_class_id"] == "schema-validity")
    result["evidence_status"] = "untested"

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-analysis-drift" in _rule_ids(failures)


def test_gate_rejects_mutable_or_unpinned_historical_revision() -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    snapshot["a" + "ces_revision"] = "dev"

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert "formal-validation-revision-pin" in _rule_ids(failures)


@pytest.mark.parametrize(
    ("artifact_name", "target_path", "expected_rule"),
    [
        ("manifest", (), "formal-validation-manifest-shape"),
        ("protocol", (), "formal-validation-protocol-shape"),
        ("protocol", ("analysis_rules",), "formal-validation-analysis-rules"),
        ("protocol", ("claim_classes", 0), "formal-validation-claim-shape"),
        ("protocol", ("participant_obligations", 0), "formal-validation-participant-shape"),
        ("corpus", (), "formal-validation-corpus-shape"),
        ("corpus", ("cases", 0), "formal-validation-case-shape"),
        ("snapshot", (), "formal-validation-snapshot-shape"),
        ("snapshot", ("commands", 0), "formal-validation-command-shape"),
        ("snapshot", ("observations", 0), "formal-validation-observation-shape"),
        (
            "snapshot",
            ("participant_observations", 0),
            "formal-validation-participant-observation-shape",
        ),
        ("analysis", (), "formal-validation-analysis-shape"),
        ("analysis", ("claim_results", 0), "formal-validation-claim-result-shape"),
        ("analysis", ("claim",), "formal-validation-claim-record"),
    ],
)
def test_gate_rejects_unknown_fields_at_every_closed_artifact_boundary(
    artifact_name: str,
    target_path: tuple[str | int, ...],
    expected_rule: str,
) -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    artifacts = {
        "manifest": manifest,
        "protocol": protocol,
        "corpus": corpus,
        "snapshot": snapshot,
        "analysis": analysis,
    }
    target = artifacts[artifact_name]
    for key in target_path:
        target = target[key]
    target["unexpected_field"] = True

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert expected_rule in _rule_ids(failures)


@pytest.mark.parametrize(
    ("artifact_name", "target_path", "replacement", "expected_rule"),
    [
        ("protocol", ("issue_number",), 999, "formal-validation-protocol-scope"),
        ("protocol", ("evidence_status_values",), [], "formal-validation-evidence-status"),
        ("protocol", ("claim_classes",), [], "formal-validation-claim-coverage"),
        (
            "protocol",
            ("claim_classes", 0, "expected_evidence_status"),
            "unsupported",
            "formal-validation-evidence-status",
        ),
        ("protocol", ("claim_classes", 0, "allowed_evidence"), [], "formal-validation-claim-evidence"),
        ("corpus", ("cases",), [], "formal-validation-case-count"),
        ("corpus", ("cases", 0, "claim_class_id"), "unknown-class", "formal-validation-case-claim"),
        ("corpus", ("cases", 0, "replay_mode"), "unknown-mode", "formal-validation-replay-mode"),
        ("corpus", ("cases", 0, "limitation"), "", "formal-validation-case-limit"),
        ("snapshot", ("protocol_revision",), "wrong-revision", "formal-validation-snapshot-revision"),
        ("snapshot", ("execution_status",), "incomplete", "formal-validation-execution-status"),
        ("snapshot", ("commands",), [], "formal-validation-commands"),
        ("snapshot", ("commands", 0, "network"), "enabled", "formal-validation-commands"),
        ("snapshot", ("commands", 1, "argv"), [], "formal-validation-participant-command"),
        ("snapshot", ("observations",), [], "formal-validation-observation-coverage"),
        ("snapshot", ("observations", 0, "execution_id"), "wrong-execution", "formal-validation-observation-join"),
        ("snapshot", ("observations", 0, "replayable"), False, "formal-validation-observation-replayable"),
        ("snapshot", ("observations", 0, "evidence_refs"), [], "formal-validation-observation-evidence"),
        (
            "snapshot",
            ("participant_observations",),
            [],
            "formal-validation-participant-observation-coverage",
        ),
        (
            "snapshot",
            ("participant_observations", 0, "execution_id"),
            "wrong-execution",
            "formal-validation-participant-observation-join",
        ),
        (
            "snapshot",
            ("participant_observations", 0, "positive_outcome"),
            "failed",
            "formal-validation-participant-result",
        ),
        (
            "snapshot",
            ("participant_observations", 0, "limitations"),
            [],
            "formal-validation-participant-observation-evidence",
        ),
        ("analysis", ("protocol_revision",), "wrong-revision", "formal-validation-analysis-join"),
        ("analysis", ("claim_results",), [], "formal-validation-analysis-result-coverage"),
        ("analysis", ("claim_results", 0, "limitations"), [], "formal-validation-claim-limitations"),
        ("analysis", ("claim", "evidence_artifacts"), ["../unsafe"], "formal-validation-claim-artifact"),
        ("analysis", ("claim", "threats_to_validity"), [], "formal-validation-claim-record"),
        ("analysis", ("limitations",), [], "formal-validation-analysis-disclosure"),
    ],
)
def test_gate_rejects_mutations_of_every_semantic_integrity_rule_family(
    artifact_name: str,
    target_path: tuple[str | int, ...],
    replacement: object,
    expected_rule: str,
) -> None:
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    artifacts = {
        "protocol": protocol,
        "corpus": corpus,
        "snapshot": snapshot,
        "analysis": analysis,
    }
    target = artifacts[artifact_name]
    for key in target_path[:-1]:
        target = target[key]
    target[target_path[-1]] = replacement

    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis)

    assert expected_rule in _rule_ids(failures)


def test_satisfiability_supplement_has_complete_replayable_control_matrix() -> None:
    manifest, snapshot, analysis = load_satisfiability_analysis(REPO_ROOT)

    assert manifest["revision"] == "2.0.0"
    assert analysis["evidence_status"] == "demonstrated"
    assert {item["control"] for item in analysis["cases"]} == {
        "positive",
        "negative",
        "unsupported",
    }
    assert analysis["execution_id"] == snapshot["execution_id"]
    assert validate_satisfiability_analysis(REPO_ROOT, manifest, snapshot, analysis, replay_current=False) == []


def test_satisfiability_gate_rejects_missing_unsupported_control() -> None:
    manifest, snapshot, analysis = load_satisfiability_analysis(REPO_ROOT)
    analysis = deepcopy(analysis)
    analysis["cases"] = [item for item in analysis["cases"] if item["control"] != "unsupported"]

    failures = validate_satisfiability_analysis(REPO_ROOT, manifest, snapshot, analysis)

    assert "formal-satisfiability-control-coverage" in _rule_ids(failures)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("expected_outcome", "satisfiable"),
        (
            "expected_normalized_model_digest",
            "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        ),
    ],
)
def test_satisfiability_gate_rejects_mutated_frozen_observations(
    field: str,
    replacement: str,
) -> None:
    manifest, snapshot, analysis = load_satisfiability_analysis(REPO_ROOT)
    analysis = deepcopy(analysis)
    unsupported = next(item for item in analysis["cases"] if item["control"] == "unsupported")
    unsupported[field] = replacement

    failures = validate_satisfiability_analysis(REPO_ROOT, manifest, snapshot, analysis)

    assert "formal-satisfiability-replay-drift" in _rule_ids(failures)


def test_satisfiability_gate_rejects_unsafe_fixture_and_unknown_fields() -> None:
    manifest, snapshot, analysis = load_satisfiability_analysis(REPO_ROOT)
    unsafe = deepcopy(analysis)
    unsafe["cases"][0]["fixture_path"] = "../outside.sdl.yaml"
    unknown = deepcopy(analysis)
    unknown["unexpected"] = True

    assert "formal-satisfiability-case-path" in _rule_ids(
        validate_satisfiability_analysis(REPO_ROOT, manifest, snapshot, unsafe)
    )
    assert "formal-satisfiability-analysis-shape" in _rule_ids(
        validate_satisfiability_analysis(REPO_ROOT, manifest, snapshot, unknown)
    )


def test_satisfiability_gate_rejects_mutated_execution_snapshot() -> None:
    manifest, snapshot, analysis = load_satisfiability_analysis(REPO_ROOT)
    snapshot = deepcopy(snapshot)
    snapshot["observations"][0]["actual_outcome"] = "unsatisfiable"

    failures = validate_satisfiability_analysis(REPO_ROOT, manifest, snapshot, analysis)

    assert "formal-satisfiability-snapshot-drift" in _rule_ids(failures)
