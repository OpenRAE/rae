"""Retained reproduction captures join one measurement, one execution, and one separate review."""

import copy
from pathlib import Path

import pytest
from raes_contracts.errors import EvidenceIntegrityError
from test_issue_973_crossing_corpus import constructed as constructed
from test_issue_974_machine_check import result as result

ROOT = Path(__file__).resolve().parents[3]
PRODUCER = "https://github.com/OpenRAE/rae/issues/976#issuecomment-6544932861"
REVIEWER = "https://github.com/OpenRAE/rae/issues/976#issuecomment-7000000001"
ACCEPTANCE = "https://github.com/OpenRAE/rae/issues/976#issuecomment-7000000002"
SOURCE = "c" * 40


def execution_document(reproduction, pin):
    from implementations.formal.participant_crossing import machine_check_publication as publication

    return {
        "schema": "participant-crossing-machine-check-execution/v1",
        "manifest_digest": pin,
        "source_revision": SOURCE,
        "host_profile": publication.HOST_PROFILE,
        "observed_base": "github-runner:ubuntu26:20261026.180.1:X64",
        "observed_repository": "github-runner-package-set:ubuntu26:20261026.180.1:X64",
        "native_packages": {"bubblewrap": "0.11.1-1ubuntu0.3"},
        "kernel": "7.0.0-1017-azure",
        "python_profile": publication.PYTHON_PROFILE,
        "observed_python": {"implementation": "CPython", "version": "3.14.7"},
        "python_lock_digest": "sha256:" + "1" * 64,
        "tool_lock_digest": "sha256:" + "2" * 64,
        "sandbox": "required-successful-native-replay",
        "non_claims": ["immutable-host", "independent-reproduction"],
    }


@pytest.fixture
def capture(monkeypatch, result):
    from implementations.formal.participant_crossing import reproduction

    pin = reproduction.digest(result["manifest.json"])
    monkeypatch.setattr(reproduction.machine, "load_retained", lambda root: (dict(result), pin))
    monkeypatch.setattr(reproduction.sandbox, "replay", lambda root: dict(result))
    # Staging integrity is covered by the sandbox tests; record admission does not read the package tree.
    monkeypatch.setattr(reproduction.sandbox, "package_source_paths", lambda root: ())
    measurement = reproduction.measure(ROOT, pin)
    execution = reproduction.encoded(
        {
            "schema": "participant-crossing-reproduction-execution/v1",
            "measurement_digest": reproduction.digest(measurement),
            "execution": execution_document(reproduction, pin),
            "review_acceptance": "required",
        }
    )
    claim = reproduction.decoded(measurement)["claim_digest"]
    review = {
        "schema": "participant-crossing-reproduction-review/v1",
        "decision": "accepted-bounded-reproduction",
        "authenticity": "unsigned",
        "scope": (
            "Complete reachable finite carrier of participant-crossing-dpbb-finite-v1@rev2; "
            "divergence-preserving-branching-bisimulation only."
        ),
        "nonclaims": [
            "runtime-realization",
            "backend-conformance",
            "noninterference",
            "opacity",
            "unbounded-proof",
            "wider-profile",
        ],
        "measurement_digest": reproduction.digest(measurement),
        "execution_digest": reproduction.digest(execution),
        "claim_digest": claim,
        "mutation_review_subject_digest": reproduction.decoded(measurement)["mutation_review_subject_digest"],
        "producer_ref": PRODUCER,
        "reviewer_ref": REVIEWER,
        "reviewer_role": "implementation-agent",
        "acceptance_record_ref": ACCEPTANCE,
        "source_revision": SOURCE,
        "qualified_run": {
            "artifact_digest": "sha256:" + "3" * 64,
            "artifact_id": 13100000001,
            "artifact_name": "participant-crossing-machine-check-" + SOURCE,
            "feature_sha": "d" * 40,
            "source_parents": ["e" * 40, "d" * 40],
            "url": "https://github.com/OpenRAE/rae/actions/runs/41300000001",
        },
    }
    return reproduction, pin, {"measurement.json": measurement, "execution.json": execution}, review


def bundle_of(reproduction, files, review):
    from implementations.formal.participant_crossing import reproduction_record

    return reproduction_record.capture_bundle({**files, "review.json": reproduction.encoded(review)})


def admit(bundle, pin):
    from implementations.formal.participant_crossing import reproduction_record

    return reproduction_record.admit_capture(ROOT, bundle, pin)


def test_separate_review_admits_a_content_addressed_capture(capture):
    reproduction, pin, files, review = capture
    bundle = bundle_of(reproduction, files, review)
    record = admit(bundle, pin)
    manifest = reproduction.decoded(bundle["manifest.json"])
    assert manifest["target_manifest_digest"] == pin
    assert manifest["authenticity"] == "unsigned"
    assert set(manifest["artifact_digests"]) == {"measurement.json", "execution.json", "review.json"}
    assert record["manifest_digest"] == reproduction.digest(bundle["manifest.json"])
    assert record["review"]["reviewer_ref"] == REVIEWER


@pytest.mark.parametrize(
    "fault",
    [
        "self-review",
        "producer-acceptance",
        "decision",
        "role",
        "comment",
        "measurement",
        "execution",
        "claim",
        "scope",
        "nonclaims",
        "source",
        "artifact-name",
        "parents",
        "run-url",
        "extra",
    ],
)
def test_review_cannot_self_approve_or_detach_from_the_measured_subject(capture, fault):
    reproduction, pin, files, review = capture
    forged = copy.deepcopy(review)
    if fault == "self-review":
        forged["reviewer_ref"] = PRODUCER
    elif fault == "producer-acceptance":
        forged["acceptance_record_ref"] = PRODUCER
    elif fault == "decision":
        forged["decision"] = "accepted"
    elif fault == "role":
        forged["reviewer_role"] = "producer"
    elif fault == "comment":
        forged["reviewer_ref"] = "https://github.com/OpenRAE/rae/issues/976"
    elif fault == "measurement":
        forged["measurement_digest"] = "sha256:" + "0" * 64
    elif fault == "execution":
        forged["execution_digest"] = "sha256:" + "0" * 64
    elif fault == "claim":
        forged["claim_digest"] = "sha256:" + "0" * 64
    elif fault == "scope":
        forged["scope"] = "Complete runtime equivalence."
    elif fault == "nonclaims":
        forged["nonclaims"] = forged["nonclaims"][:-1]
    elif fault == "source":
        forged["source_revision"] = "f" * 40
    elif fault == "artifact-name":
        forged["qualified_run"]["artifact_name"] = "candidate"
    elif fault == "parents":
        forged["qualified_run"]["source_parents"] = ["e" * 40]
    elif fault == "run-url":
        forged["qualified_run"]["url"] = "https://example.com/runs/1"
    else:
        forged["approved_by"] = "self"
    with pytest.raises(EvidenceIntegrityError):
        admit(bundle_of(reproduction, files, forged), pin)


@pytest.mark.parametrize("fault", ["target", "manifest", "inventory", "execution-subject", "execution-claim"])
def test_capture_must_measure_the_currently_selected_subject(capture, fault):
    reproduction, pin, files, review = capture
    bundle = bundle_of(reproduction, files, review)
    expected = pin
    if fault == "target":
        expected = "sha256:" + "0" * 64
    elif fault == "manifest":
        manifest = reproduction.decoded(bundle["manifest.json"])
        manifest["authenticity"] = "authenticated"
        bundle["manifest.json"] = reproduction.encoded(manifest)
    elif fault == "inventory":
        bundle["notes.json"] = b"{}\n"
    else:
        execution = reproduction.decoded(files["execution.json"])
        if fault == "execution-subject":
            execution["execution"]["manifest_digest"] = "sha256:" + "0" * 64
        else:
            execution["execution"]["non_claims"] = ["immutable-host"]
        execution_bytes = reproduction.encoded(execution)
        forged = {**review, "execution_digest": reproduction.digest(execution_bytes)}
        bundle = bundle_of(reproduction, {**files, "execution.json": execution_bytes}, forged)
    with pytest.raises(EvidenceIntegrityError):
        admit(bundle, expected)


API = "https://api.github.com/repos/OpenRAE/rae/"


def github_records(reproduction, files, review, pin):
    """Server records that a genuine separate review leaves behind."""
    run = review["qualified_run"]
    body = " ".join(
        (
            reproduction.digest(files["measurement.json"]),
            reproduction.digest(files["execution.json"]),
            review["claim_digest"],
            pin,
            run["url"],
        )
    )

    def comment(ref, created_at, text):
        issue, comment_id = ref.removeprefix("https://github.com/OpenRAE/rae/issues/").split("#issuecomment-")
        return f"issues/comments/{comment_id}", {
            "html_url": ref,
            "issue_url": API + "issues/" + issue,
            "created_at": created_at,
            "body": text,
        }

    run_id = run["url"].rsplit("/", 1)[1]
    return dict(
        (
            comment(PRODUCER, "2026-10-31T10:00:00Z", "producer run"),
            comment(REVIEWER, "2026-10-31T11:00:00Z", "reviewer run"),
            comment(ACCEPTANCE, "2026-10-31T12:00:00Z", "accepted " + body),
            (f"actions/runs/{run_id}", {"html_url": run["url"], "head_sha": run["feature_sha"]}),
            (
                f"actions/runs/{run_id}/jobs?per_page=100",
                {"jobs": [{"name": "canonical / model-check", "conclusion": "success"}]},
            ),
            (
                f"actions/artifacts/{run['artifact_id']}",
                {"name": run["artifact_name"], "digest": run["artifact_digest"], "workflow_run": {"id": int(run_id)}},
            ),
            (f"git/commits/{SOURCE}", {"parents": [{"sha": sha} for sha in run["source_parents"]]}),
        )
    )


def fetcher(records):
    from raes_contracts.errors import OperationalError

    def fetch(path):
        if path not in records:
            raise OperationalError("GitHub record lookup failed")
        return copy.deepcopy(records[path])

    return fetch


def staged_retain(monkeypatch, files, review):
    from implementations.formal.participant_crossing import reproduction, reproduction_record

    staging = ".cache/raes-sdl/test-reproduction-staging"
    stage = {**files, "review.json": reproduction.encoded(review)}
    original = reproduction_record.read_bytes
    monkeypatch.setattr(
        reproduction_record,
        "read_bytes",
        lambda root, name, **kwargs: (
            stage[name.rsplit("/", 1)[1]] if name.startswith(staging + "/") else original(root, name, **kwargs)
        ),
    )
    published = []
    monkeypatch.setattr(
        reproduction_record, "publish_bundle", lambda root, bundle, path: published.append((path, bundle))
    )
    return staging, stage, published


def test_retain_publishes_only_an_admitted_and_server_bound_capture(capture, monkeypatch):
    from implementations.formal.participant_crossing import reproduction_record

    reproduction, pin, files, review = capture
    records = github_records(reproduction, files, review, pin)
    staging, stage, published = staged_retain(monkeypatch, files, review)
    path = reproduction_record.retain(ROOT, staging, pin, fetch=fetcher(records))
    assert len(published) == 1
    assert published[0][0] == path
    manifest_digest = reproduction.digest(published[0][1]["manifest.json"])
    assert path == reproduction_record.OUTPUT_ROOT + "/capture-" + manifest_digest.split(":", 1)[1]
    stage["review.json"] = reproduction.encoded({**review, "reviewer_ref": PRODUCER})
    published.clear()
    with pytest.raises(EvidenceIntegrityError):
        reproduction_record.retain(ROOT, staging, pin, fetch=fetcher(records))
    assert published == []


@pytest.mark.parametrize(
    "fault",
    [
        "missing-reviewer",
        "unbound-acceptance",
        "acceptance-first",
        "other-issue",
        "moved-comment",
        "run-head",
        "failed-model-check",
        "artifact-digest",
        "artifact-run",
        "merge-parents",
    ],
)
def test_retain_refuses_review_references_without_matching_server_records(capture, monkeypatch, fault):
    from implementations.formal.participant_crossing import reproduction_record
    from raes_contracts.errors import OperationalError

    reproduction, pin, files, review = capture
    records = github_records(reproduction, files, review, pin)
    run = review["qualified_run"]
    run_id = run["url"].rsplit("/", 1)[1]
    reviewer = "issues/comments/" + REVIEWER.rsplit("-", 1)[1]
    acceptance = "issues/comments/" + ACCEPTANCE.rsplit("-", 1)[1]
    if fault == "missing-reviewer":
        del records[reviewer]
    elif fault == "unbound-acceptance":
        records[acceptance]["body"] = "accepted"
    elif fault == "acceptance-first":
        records[acceptance]["created_at"] = "2026-10-31T10:30:00Z"
    elif fault == "other-issue":
        records[acceptance]["issue_url"] = API + "issues/1"
    elif fault == "moved-comment":
        records[reviewer]["html_url"] = PRODUCER
    elif fault == "run-head":
        records[f"actions/runs/{run_id}"]["head_sha"] = "f" * 40
    elif fault == "failed-model-check":
        records[f"actions/runs/{run_id}/jobs?per_page=100"]["jobs"][0]["conclusion"] = "failure"
    elif fault == "artifact-digest":
        records[f"actions/artifacts/{run['artifact_id']}"]["digest"] = "sha256:" + "9" * 64
    elif fault == "artifact-run":
        records[f"actions/artifacts/{run['artifact_id']}"]["workflow_run"]["id"] = 1
    else:
        records[f"git/commits/{SOURCE}"]["parents"].reverse()
    staging, _stage, published = staged_retain(monkeypatch, files, review)
    with pytest.raises((EvidenceIntegrityError, OperationalError)):
        reproduction_record.retain(ROOT, staging, pin, fetch=fetcher(records))
    assert published == []
