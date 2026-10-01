"""T19: artifact admission fails before any publisher obtains usable output.

Every case drives the actual handoff the release workflow performs, rather than
asserting workflow YAML shape. A valid signature over the wrong repository,
workflow, run, attempt or subject is a rejection, and a missing, substituted or
malformed evidence document never becomes admission.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from tools.release_evidence_admission import (
    INDEX_FILENAME,
    REQUIRED_EVIDENCE,
    SCHEMA_VERSION,
    AdmissionError,
    ProducerIdentity,
    ReleaseIdentity,
    build_evidence_index,
    verify_admission,
)

_IDENTITY = ReleaseIdentity(
    repository="OpenRAE/rae",
    source_sha="a" * 40,
    workflow_ref="OpenRAE/rae/.github/workflows/release-please.yml@refs/heads/main",
    workflow_sha="e" * 40,
    run_id="1234567890",
    run_attempt="1",
    tag="v1.2.3",
)

_REPOSITORY = "OpenRAE/rae"
_SOURCE_SHA = "a" * 40
_WORKFLOW_REF = f"{_REPOSITORY}/.github/workflows/release-please.yml@refs/heads/main"
_RUN_ID = "1234567890"
_RUN_ATTEMPT = "1"

_APPROVED = ProducerIdentity(
    issuer="https://token.actions.githubusercontent.com",
    repository=_REPOSITORY,
    workflow_ref=_WORKFLOW_REF,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.fixture
def release(tmp_path: Path) -> dict[str, object]:
    """A complete, admissible release: one wheel, one sdist, and their evidence."""

    dist = tmp_path / "dist"
    evidence = tmp_path / "evidence"
    wheel = _write(dist / "raes-1.2.3-py3-none-any.whl", b"wheel-bytes")
    sdist = _write(dist / "raes-1.2.3.tar.gz", b"sdist-bytes")
    derived = _write(dist / "from-sdist" / "raes-1.2.3-py3-none-any.whl", b"derived-bytes")

    for subject, name in ((wheel, "wheel"), (sdist, "sdist")):
        _write(
            evidence / f"{name}.cdx.json",
            json.dumps(
                {
                    "bomFormat": "CycloneDX",
                    "specVersion": "1.6",
                    "metadata": {
                        "component": {
                            "name": "raes",
                            "version": "1.2.3",
                            "hashes": [{"alg": "SHA-256", "content": _sha256(subject.read_bytes())}],
                        }
                    },
                    "components": [{"name": "typer", "version": "0.24.1"}],
                }
            ).encode(),
        )
    _write(
        evidence / "build-inventory.json",
        json.dumps(
            {
                "schema_version": "raes-build-inventory/v1",
                "subjects": [
                    {"filename": wheel.name, "sha256": _sha256(wheel.read_bytes())},
                    {"filename": sdist.name, "sha256": _sha256(sdist.read_bytes())},
                ],
                "build_inputs": [{"name": "hatchling", "version": "1.27.0"}],
            }
        ).encode(),
    )

    index = build_evidence_index(
        distribution_dir=dist,
        evidence_dir=evidence,
        identity=_IDENTITY,
        profile_id="public-linux-x86_64-cp312-all-extras",
        policy_hashes={"tooling_policy_sha256": "b" * 64},
    )
    # `generate` writes the index into the evidence directory, where it is
    # uploaded, signed and admitted alongside the documents it describes.
    _write(evidence / INDEX_FILENAME, json.dumps(index).encode())

    # Publishers consume the uploaded distribution set, which never contains the
    # build-time from-sdist tree; model that by removing it after indexing.
    derived_digest = _sha256(derived.read_bytes())
    derived.unlink()
    derived.parent.rmdir()
    attestations = {_sha256(path.read_bytes()): _APPROVED for path in (wheel, sdist, *sorted(evidence.iterdir()))}
    return {
        "dist": dist,
        "evidence": evidence,
        "index": index,
        "attestations": attestations,
        "wheel": wheel,
        "sdist": sdist,
        "derived_digest": derived_digest,
    }


def _verify(release: dict[str, object], **overrides: object) -> None:
    kwargs: dict[str, object] = {
        "distribution_dir": release["dist"],
        "evidence_dir": release["evidence"],
        "index": release["index"],
        "attestations": release["attestations"],
        "approved_producers": (_APPROVED,),
        "expected": _IDENTITY,
        "policy_hashes": {"tooling_policy_sha256": "b" * 64},
    }
    kwargs.update(overrides)
    verify_admission(**kwargs)  # type: ignore[arg-type]


def _expect(release: dict[str, object], code: str, mutate: Callable[[], None], **overrides: object) -> None:
    mutate()
    with pytest.raises(AdmissionError) as excinfo:
        _verify(release, **overrides)
    assert excinfo.value.code == code


def test_complete_release_is_admitted(release: dict[str, object]) -> None:
    _verify(release)
    assert release["index"]["schema_version"] == SCHEMA_VERSION


def test_index_binds_the_sdist_to_its_original_archive(release: dict[str, object]) -> None:
    """The sdist-derived wheel is a separate subject, never a stand-in."""

    index = release["index"]
    subjects = {item["role"]: item for item in index["subjects"]}
    test_subjects = {item["role"]: item for item in index["test_subjects"]}
    assert set(subjects) == {"wheel", "sdist"}
    assert subjects["sdist"]["sha256"] == _sha256(release["sdist"].read_bytes())

    derived = test_subjects["derived-test-wheel"]
    assert derived["sha256"] == release["derived_digest"]
    assert derived["derived_from"] == release["sdist"].name
    # Same basename as the release wheel, deliberately a distinct identity.
    assert derived["filename"] == subjects["wheel"]["filename"]
    assert derived["sha256"] != subjects["wheel"]["sha256"]


def test_missing_wheel_is_refused(release: dict[str, object]) -> None:
    _expect(release, "admission-subject-missing", lambda: release["wheel"].unlink())


def test_missing_sdist_is_refused(release: dict[str, object]) -> None:
    _expect(release, "admission-subject-missing", lambda: release["sdist"].unlink())


def test_extra_distribution_file_is_refused(release: dict[str, object]) -> None:
    _expect(
        release,
        "admission-unexpected-distribution",
        lambda: _write(release["dist"] / "raes-9.9.9-py3-none-any.whl", b"smuggled"),
    )


def test_replaced_subject_bytes_are_refused(release: dict[str, object]) -> None:
    _expect(release, "admission-subject-digest-mismatch", lambda: release["wheel"].write_bytes(b"swapped"))


def test_missing_sbom_is_refused(release: dict[str, object]) -> None:
    _expect(release, "admission-evidence-missing", lambda: (release["evidence"] / "wheel.cdx.json").unlink())


def _rewrite_evidence(release: dict[str, object], filename: str, mutate: Callable[[dict], None]) -> None:
    """Rewrite an evidence document *and* its recorded digest.

    A bundle whose sidecar bytes disagree with the index is already caught as a
    sidecar swap. The threat these cases cover is a self-consistent bundle whose
    content is semantically wrong, so the index is kept coherent on purpose.
    """

    path = release["evidence"] / filename
    document = json.loads(path.read_text())
    mutate(document)
    payload = json.dumps(document).encode()
    path.write_bytes(payload)
    for item in release["index"]["evidence"]:
        if item["filename"] == filename:
            item["sha256"] = _sha256(payload)
            item["size"] = len(payload)
    release["attestations"][_sha256(payload)] = _APPROVED


def test_sbom_naming_a_foreign_subject_is_refused(release: dict[str, object]) -> None:
    def swap() -> None:
        _rewrite_evidence(
            release,
            "wheel.cdx.json",
            lambda document: document["metadata"]["component"].__setitem__(
                "hashes", [{"alg": "SHA-256", "content": "c" * 64}]
            ),
        )

    _expect(release, "admission-sbom-foreign-subject", swap)


def test_substituted_input_inventory_is_refused(release: dict[str, object]) -> None:
    def swap() -> None:
        def mutate(document: dict) -> None:
            document["subjects"][0]["sha256"] = "d" * 64

        _rewrite_evidence(release, "build-inventory.json", mutate)

    _expect(release, "admission-inventory-subject-mismatch", swap)


def test_sidecar_swap_is_refused(release: dict[str, object]) -> None:
    """Sidecars are authenticated too, not only the distribution subjects."""

    _expect(
        release,
        "admission-evidence-digest-mismatch",
        lambda: (release["evidence"] / "build-inventory.json").write_bytes(b'{"schema_version": "x"}'),
    )


def test_missing_attestation_is_refused(release: dict[str, object]) -> None:
    def drop() -> None:
        release["attestations"].pop(_sha256(release["wheel"].read_bytes()))

    _expect(release, "admission-attestation-missing", drop)


def test_foreign_signer_identity_is_refused(release: dict[str, object]) -> None:
    def forge() -> None:
        digest = _sha256(release["wheel"].read_bytes())
        release["attestations"][digest] = ProducerIdentity(
            issuer="https://token.actions.githubusercontent.com",
            repository="attacker/rae",
            workflow_ref="attacker/rae/.github/workflows/release-please.yml@refs/heads/main",
        )

    _expect(release, "admission-attestation-foreign-producer", forge)


def test_valid_signature_from_the_wrong_workflow_is_refused(release: dict[str, object]) -> None:
    def forge() -> None:
        digest = _sha256(release["wheel"].read_bytes())
        release["attestations"][digest] = ProducerIdentity(
            issuer=_APPROVED.issuer,
            repository=_REPOSITORY,
            workflow_ref=f"{_REPOSITORY}/.github/workflows/ci.yml@refs/heads/main",
        )

    _expect(release, "admission-attestation-foreign-producer", forge)


def test_run_attempt_replay_is_refused(release: dict[str, object]) -> None:
    expected = replace(_IDENTITY, run_attempt="2")
    with pytest.raises(AdmissionError) as excinfo:
        _verify(release, expected=expected)
    assert excinfo.value.code == "admission-run-identity-mismatch"


def test_foreign_repository_is_refused(release: dict[str, object]) -> None:
    expected = replace(_IDENTITY, repository="attacker/rae")
    with pytest.raises(AdmissionError) as excinfo:
        _verify(release, expected=expected)
    assert excinfo.value.code == "admission-run-identity-mismatch"


def test_drifted_policy_hash_is_refused(release: dict[str, object]) -> None:
    with pytest.raises(AdmissionError) as excinfo:
        _verify(release, policy_hashes={"tooling_policy_sha256": "e" * 64})
    assert excinfo.value.code == "admission-policy-hash-mismatch"


def test_malformed_evidence_document_is_refused(release: dict[str, object]) -> None:
    def corrupt() -> None:
        path = release["evidence"] / "wheel.cdx.json"
        payload = b"{not json"
        path.write_bytes(payload)
        for item in release["index"]["evidence"]:
            if item["filename"] == "wheel.cdx.json":
                item["sha256"] = _sha256(payload)

    _expect(release, "admission-evidence-unparsable", corrupt)


def test_oversized_evidence_document_is_refused(release: dict[str, object]) -> None:
    def inflate() -> None:
        path = release["evidence"] / "wheel.cdx.json"
        payload = b"[" + b"0," * 20_000_000 + b"0]"
        path.write_bytes(payload)
        for item in release["index"]["evidence"]:
            if item["filename"] == "wheel.cdx.json":
                item["sha256"] = _sha256(payload)

    _expect(release, "admission-evidence-oversized", inflate)


def test_failure_is_raised_before_any_publishable_set_is_returned(release: dict[str, object]) -> None:
    """Admission has no partial-success path a publisher could consume."""

    release["wheel"].unlink()
    with pytest.raises(AdmissionError):
        _verify(release)


def test_source_sha_from_trusted_context_must_match(release: dict[str, object]) -> None:
    """A replayed index cannot describe a different candidate source revision."""

    expected = replace(_IDENTITY, source_sha="f" * 40)
    with pytest.raises(AdmissionError) as excinfo:
        _verify(release, expected=expected)
    assert excinfo.value.code == "admission-run-identity-mismatch"


def test_index_stripped_of_required_evidence_is_refused(release: dict[str, object]) -> None:
    """The required evidence set does not come from the bundle being admitted.

    Candidate build code can rewrite the evidence directory before it is
    uploaded. An index naming only the distributions must not discharge the
    obligation to carry an SBOM per subject and a build inventory.
    """

    def strip() -> None:
        index = release["index"]
        keep = {INDEX_FILENAME}
        index["evidence"] = [i for i in index["evidence"] if i["filename"] in keep]
        for name in ("wheel.cdx.json", "sdist.cdx.json", "build-inventory.json"):
            (release["evidence"] / name).unlink()

    _expect(release, "admission-required-evidence-missing", strip)


def test_undeclared_evidence_file_is_refused(release: dict[str, object]) -> None:
    """An extra sidecar would be signed and retained without semantic admission."""

    _expect(
        release,
        "admission-unexpected-evidence",
        lambda: _write(release["evidence"] / "smuggled.json", b"{}"),
    )


def test_required_evidence_names_are_fixed_not_index_supplied() -> None:
    assert set(REQUIRED_EVIDENCE) == {
        "build-inventory.json",
        "sdist.cdx.json",
        "wheel.cdx.json",
    }
    assert INDEX_FILENAME == "release-evidence-index.json"
