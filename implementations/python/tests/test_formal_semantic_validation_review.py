"""Evidence failures identify the exact integrity boundary that rejected them."""

import subprocess

import pytest
from evidence_test_fixtures import copy_bundle
from test_formal_semantic_validation import REPO_ROOT, _bundle
from tools.check_formal_semantic_validation import (
    load_release_bundles,
    load_retest_bundle,
    validate_bundle,
    validate_release_bundle,
    validate_retest_bundle,
)
from tools.formal_semantic_validation import _production, _retest, _snapshot


def identities(failures):
    return {(f.rule_id, f.message, f.path) for f in failures}


@pytest.mark.parametrize(
    ("field", "value", "rule", "message"),
    [
        ("raes_revision", "dev", "formal-validation-revision-pin", "retest snapshot must pin a full RAES commit"),
        (
            "versions",
            {},
            "formal-validation-version-disclosure",
            "retest snapshot must record the bounded output-affecting versions",
        ),
    ],
)
def test_retest_requires_immutable_revision_and_version_disclosure(field, value, rule, message):
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    snapshot[field] = value
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert (rule, message, release.manifest["snapshot_path"]) in identities(failures)


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize(
    ("field", "value"), [("actual_outcome", "accepted"), ("diagnostic_kind", "invented"), ("result_digest", "0" * 64)]
)
def test_unsupported_observations_cannot_fabricate_results(version, field, value):
    observation = {
        "case_id": "unsupported",
        "actual_outcome": "unsupported",
        "diagnostic_kind": None,
        "result_digest": None,
    }
    failures = []

    def validate():
        if version == 1:
            _snapshot._validate_snapshot_replay(
                REPO_ROOT, {"replay_mode": "unsupported"}, observation, failures, "snapshot.json", replay_cases=True
            )
        else:
            _retest._validate_retained_retest_observation(
                REPO_ROOT, {"replay_mode": "unsupported"}, observation, failures, "snapshot.json"
            )

    validate()
    assert failures == []
    observation[field] = value
    validate()
    message = (
        "unsupported observation 'unsupported' must not synthesize diagnostics or results"
        if version == 1
        else "historical unsupported case 'unsupported' must remain unsupported"
    )
    assert identities(failures) == {("formal-validation-unsupported-observation", message, "snapshot.json")}


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("error", [OSError, ValueError])
def test_retained_replay_exceptions_are_failures(monkeypatch, version, error):
    module = _snapshot if version == 1 else _retest

    def fail(*_args):
        raise error("seeded failure")

    monkeypatch.setattr(module, "replay_case", fail)
    case, observation = {"case_id": "control", "replay_mode": "parse"}, {"case_id": "control"}
    failures = []
    if version == 1:
        _snapshot._validate_snapshot_replay(REPO_ROOT, case, observation, failures, "snapshot.json", replay_cases=True)
        message = "could not replay 'control': seeded failure"
    else:
        _retest._validate_retained_retest_observation(REPO_ROOT, case, observation, failures, "snapshot.json")
        message = f"retained case 'control' could not replay ({error.__name__})"
    assert identities(failures) == {("formal-validation-replay-error", message, "snapshot.json")}


@pytest.mark.parametrize("case_id", ["finite-domain-satisfiable-v2", "typed-exploit-path-valid-v2"])
@pytest.mark.parametrize("error", [OSError, ValueError, RuntimeError, subprocess.SubprocessError])
def test_production_replay_exceptions_are_failures(monkeypatch, case_id, error):
    release, _protocol, corpus, snapshot, _analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    case = next(item for item in corpus["cases"] if item["case_id"] == case_id)
    observation = next(item for item in snapshot["observations"] if item["case_id"] == case_id)
    command = next(item for item in snapshot["commands"] if item["command_id"] == case_id)
    context = _production._ProductionObservationContext(
        REPO_ROOT, {item["path"]: item for item in release.manifest["artifacts"]}
    )

    def fail(*_args, **_kwargs):
        raise error("seeded failure")

    monkeypatch.setattr(_production, "_replay_production_evidence", fail)
    failures = []
    _production._validate_production_evidence_observation(
        context, case, observation, command, failures, "snapshot.json"
    )
    assert identities(failures) == {
        (
            "formal-validation-production-replay",
            f"case {case_id!r} production replay failed ({error.__name__})",
            "snapshot.json",
        )
    }


def test_retest_rejects_an_extra_atomically_selected_artifact():
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    release.manifest["artifacts"].append(
        {"artifact_id": "extra", "kind": "production-evidence", "path": "extra.json", "sha256": "0" * 64}
    )
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert (
        "formal-validation-production-evidence-join",
        "the atomic release must select exactly every production input and evidence artifact",
        release.manifest_path,
    ) in identities(failures)


def test_retest_rejects_missing_production_command_selection():
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    snapshot["commands"] = [
        item for item in snapshot["commands"] if item["command_id"] != "typed-exploit-path-valid-v2"
    ]
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert (
        "formal-validation-production-command",
        "every production evidence case needs one fixed command",
        release.manifest["snapshot_path"],
    ) in identities(failures)


@pytest.mark.parametrize(
    ("artifact", "keys", "value", "rule"),
    [
        ("corpus", ("cases", 0, "case_id"), "", "formal-validation-case-ids"),
        ("snapshot", ("observations",), {}, "formal-validation-observations"),
        ("snapshot", ("participant_observations",), {}, "formal-validation-participant-observations"),
        ("analysis", ("claim_results",), {}, "formal-validation-analysis-results"),
        ("analysis", ("claim_results", 0, "claim_class_id"), "unknown", "formal-validation-analysis-result-join"),
    ],
)
def test_historical_gate_rejects_remaining_integrity_mutations(artifact, keys, value, rule):
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    target = {"corpus": corpus, "snapshot": snapshot, "analysis": analysis}[artifact]
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis, replay_cases=False)
    assert rule in {f.rule_id for f in failures}


@pytest.mark.parametrize(
    ("keys", "value", "rule"),
    [
        (("unexpected",), True, "formal-validation-release-shape"),
        (("revision",), "dev", "formal-validation-release-revision"),
        (("artifacts",), {}, "formal-validation-release-artifacts"),
        (("artifacts", 0, "unexpected"), True, "formal-validation-release-artifact-shape"),
    ],
)
def test_release_gate_rejects_remaining_integrity_mutations(keys, value, rule):
    release = next(
        item for item in copy_bundle(load_release_bundles, REPO_ROOT) if item.manifest["revision"] == "3.0.0"
    )
    target = release.manifest
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    assert rule in {f.rule_id for f in validate_release_bundle(REPO_ROOT, release)}


@pytest.mark.parametrize(
    ("artifact", "field", "value", "rule"),
    [
        ("release", "revision", "99.0.0", "formal-validation-retest-release"),
        ("protocol", "revision", "1.0.0", "formal-validation-retest-revision"),
    ],
)
def test_retest_rejects_unsupported_release_or_protocol(artifact, field, value, rule):
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    target = release.manifest if artifact == "release" else protocol
    target[field] = value
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert rule in {f.rule_id for f in failures}


def test_retest_cannot_rewrite_a_historical_case():
    release, protocol, corpus, snapshot, analysis = copy_bundle(load_retest_bundle, REPO_ROOT)
    corpus["cases"][0]["expected_outcome"] = "invented"
    failures = validate_retest_bundle(REPO_ROOT, release, protocol, corpus, snapshot, analysis)
    assert "formal-validation-historical-retention" in {f.rule_id for f in failures}


def test_unsupported_case_cannot_acquire_a_fabricated_outcome():
    manifest, protocol, corpus, snapshot, analysis = _bundle()
    case = next(item for item in corpus["cases"] if item["replay_mode"] == "unsupported")
    case["expected_outcome"] = "accepted"
    failures = validate_bundle(REPO_ROOT, manifest, protocol, corpus, snapshot, analysis, replay_cases=False)
    assert "formal-validation-unsupported-case" in {f.rule_id for f in failures}
