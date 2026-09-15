"""The CLI generates admissible evidence and refuses anything else.

The approved-producer set is the security-critical input here: if it were
derived from the bundle under verification, any valid signature would approve
itself. It comes from the reviewed admission policy instead.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path

import pytest
from tools import release_evidence
from tools.release_evidence import (
    ReleaseEvidenceError,
    approved_producers,
    collect_attestations,
    release_identity,
)
from tools.release_evidence_admission import ProducerIdentity
from tools.release_evidence_sbom import RuntimeClosureError, observed_installation

REPO_ROOT = Path(__file__).resolve().parents[3]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _recording_runner(seen: list[list[str]]):
    def runner(command: list[str]) -> str:
        seen.append(command)
        return json.dumps(
            [
                {
                    "verificationResult": {
                        "signature": {
                            "certificate": {
                                "issuer": "https://token.actions.githubusercontent.com",
                                "sourceRepositoryURI": "https://github.com/OpenRAE/rae",
                                "buildSignerURI": "https://github.com/OpenRAE/rae/.github/workflows/release-please.yml@refs/heads/main",
                            }
                        }
                    }
                }
            ]
        )

    return runner


_ENVIRONMENT = {
    "GITHUB_REPOSITORY": "OpenRAE/rae",
    "GITHUB_SHA": "a" * 40,
    "GITHUB_WORKFLOW_REF": "OpenRAE/rae/.github/workflows/release-please.yml@refs/heads/main",
    "GITHUB_WORKFLOW_SHA": "b" * 40,
    "GITHUB_RUN_ID": "42",
    "GITHUB_RUN_ATTEMPT": "1",
}


def test_release_identity_reads_named_environment_fields() -> None:
    identity = release_identity(_ENVIRONMENT)
    assert identity["repository"] == "OpenRAE/rae"
    assert identity["run_attempt"] == "1"
    assert identity["source_sha"] != identity["workflow_sha"]


@pytest.mark.parametrize("missing", sorted(_ENVIRONMENT))
def test_incomplete_release_identity_is_refused(missing: str) -> None:
    environment = {key: value for key, value in _ENVIRONMENT.items() if key != missing}
    with pytest.raises(ReleaseEvidenceError) as excinfo:
        release_identity(environment)
    assert excinfo.value.code == "release-identity-incomplete"


def test_release_identity_records_no_credential_material() -> None:
    polluted = {**_ENVIRONMENT, "GITHUB_TOKEN": "ghp_secret", "PYPI_PASSWORD": "hunter2"}
    serialized = json.dumps(release_identity(polluted))
    assert "ghp_secret" not in serialized
    assert "hunter2" not in serialized


def test_approved_producers_come_from_the_reviewed_admission_policy() -> None:
    """The repository's own policy is the only source of approved identities."""

    producers = approved_producers(REPO_ROOT)
    assert producers
    assert all(isinstance(item, ProducerIdentity) for item in producers)
    assert all(item.repository == "OpenRAE/rae" for item in producers)
    assert all(item.issuer == "https://token.actions.githubusercontent.com" for item in producers)
    assert all("release-please.yml" in item.workflow_ref for item in producers)


def test_approved_producers_are_not_derived_from_observed_attestations() -> None:
    """A foreign signer must not become approved merely by appearing in a bundle."""

    foreign = ProducerIdentity(
        issuer="https://token.actions.githubusercontent.com",
        repository="attacker/rae",
        workflow_ref="attacker/rae/.github/workflows/release-please.yml@refs/heads/main",
    )
    assert foreign not in approved_producers(REPO_ROOT)


def test_missing_admission_policy_is_refused(tmp_path: Path) -> None:
    (tmp_path / "implementations" / "tooling").mkdir(parents=True)
    (tmp_path / "implementations" / "tooling" / "admission-policy.json").write_text(
        json.dumps({"release_producers": []}), encoding="utf-8"
    )
    with pytest.raises(ReleaseEvidenceError) as excinfo:
        approved_producers(tmp_path)
    assert excinfo.value.code == "approved-producers-absent"


def _venv(tmp_path: Path, **distributions: str) -> Path:
    site = tmp_path / "venv" / "lib" / "python3.12" / "site-packages"
    site.mkdir(parents=True)
    for name, version in distributions.items():
        (site / f"{name}-{version}.dist-info").mkdir()
    return tmp_path / "venv"


def test_observed_installation_reads_dist_info_without_importing(tmp_path: Path) -> None:
    environment = _venv(tmp_path, typer="0.24.1", click="8.4.2")
    assert observed_installation(environment) == {"typer": "0.24.1", "click": "8.4.2"}


def test_observed_installation_requires_a_site_packages_directory(tmp_path: Path) -> None:
    with pytest.raises(RuntimeClosureError) as excinfo:
        observed_installation(tmp_path)
    assert excinfo.value.code == "observed-installation-absent"


def test_observed_installation_refuses_an_empty_environment(tmp_path: Path) -> None:
    (tmp_path / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    with pytest.raises(RuntimeClosureError) as excinfo:
        observed_installation(tmp_path)
    assert excinfo.value.code == "observed-installation-empty"


def test_every_admitted_artifact_is_sent_to_the_verifier(tmp_path: Path) -> None:
    """Subjects and sidecars are both verified, not only the distributions.

    Attestations are keyed by the digest of the bytes actually on disk, so a
    record claiming a digest it does not have cannot satisfy admission.
    """

    dist = tmp_path / "dist"
    evidence = tmp_path / "evidence"
    (dist / "from-sdist").mkdir(parents=True)
    evidence.mkdir()
    wheel = dist / "raes-1.0.0-py3-none-any.whl"
    derived = dist / "from-sdist" / "raes-1.0.0-py3-none-any.whl"
    inventory = evidence / "build-inventory.json"
    index_file = evidence / "release-evidence-index.json"
    wheel.write_bytes(b"wheel")
    derived.write_bytes(b"derived")
    inventory.write_bytes(b"{}")
    index_file.write_bytes(b'{"schema_version":"x"}')

    index = {
        "subjects": [
            {"path": "raes-1.0.0-py3-none-any.whl", "sha256": _digest(wheel)},
            {"path": "from-sdist/raes-1.0.0-py3-none-any.whl", "sha256": _digest(derived)},
        ],
        "evidence": [{"filename": "build-inventory.json", "sha256": _digest(inventory)}],
    }
    seen: list[list[str]] = []

    attestations = collect_attestations(
        distribution_dir=dist,
        evidence_dir=evidence,
        index=index,
        repository="OpenRAE/rae",
        signer_workflow="OpenRAE/rae/.github/workflows/release-please.yml",
        runner=_recording_runner(seen),
    )
    assert len(seen) == 4
    assert set(attestations) == {
        _digest(wheel),
        _digest(derived),
        _digest(inventory),
        _digest(index_file),
    }
    # The two wheels share a basename, so their distinct paths must be verified.
    assert len({command[3] for command in seen}) == 4


def test_expected_identity_is_never_sourced_from_the_evidence_index() -> None:
    """The verifier must not compare the bundle against itself.

    Passing the index's own run id or attempt back as the expected value makes
    those comparisons tautological, so a replayed or substituted index satisfies
    them. Expected identity comes from the trusted workflow context only.
    """

    tree = ast.parse(inspect.getsource(release_evidence))
    call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "verify_admission"
    )
    guarded = {
        "expected_repository",
        "expected_run_id",
        "expected_run_attempt",
        "expected_source_sha",
    }
    seen = set()
    for keyword in call.keywords:
        if keyword.arg not in guarded:
            continue
        seen.add(keyword.arg)
        source = ast.dump(keyword.value)
        assert "'index'" not in source, f"{keyword.arg} is derived from the evidence index"
        assert "'identity'" in source, f"{keyword.arg} must come from the trusted context"
    assert seen == guarded


def test_the_evidence_index_is_itself_verified_as_an_attested_subject(tmp_path: Path) -> None:
    """An index whose attestation was never checked cannot govern publication."""

    dist = tmp_path / "dist"
    evidence = tmp_path / "evidence"
    for directory in (dist, evidence):
        directory.mkdir()
    inventory = evidence / "build-inventory.json"
    inventory.write_bytes(b"{}")
    (evidence / "release-evidence-index.json").write_bytes(b'{"schema_version":"x"}')

    index = {
        "subjects": [],
        "evidence": [{"filename": "build-inventory.json", "sha256": _digest(inventory)}],
    }
    seen: list[list[str]] = []
    collect_attestations(
        distribution_dir=dist,
        evidence_dir=evidence,
        index=index,
        repository="OpenRAE/rae",
        signer_workflow="OpenRAE/rae/.github/workflows/release-please.yml",
        runner=_recording_runner(seen),
    )
    assert "release-evidence-index.json" in {Path(command[3]).name for command in seen}
