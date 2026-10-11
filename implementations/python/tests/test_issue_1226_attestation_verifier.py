"""Signature verification is delegated; release association is decided here.

The maintained `gh attestation verify` client owns signature, certificate and
issuer checking. This module owns the argv it is invoked with, the bounds on its
output, and the refusal of anything that is not a clean, parseable verdict.
A skip, a crash, malformed output or a cancelled run never becomes admission.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.release_evidence import collect_attestations
from tools.release_evidence_verifier import (
    VerifierError,
    build_verify_command,
    parse_verifier_output,
)

_REPOSITORY = "OpenRAE/rae"
_WORKFLOW = "OpenRAE/rae/.github/workflows/release-please.yml@refs/heads/main"
# `gh attestation verify` 2.101.0, run on 2026-10-11 with the production argv
# against a file that has no attestation, printed nothing on stdout, printed
# this on stderr and exited 1. The digest is that of the probed file.
_NO_ATTESTATION_STDERR = (
    "\nError: HTTP 404: Not Found (https://api.github.com/repos/OpenRAE/rae/attestations/"
    "sha256:9b5841449ee6ea2f6d063746c9828605acb3b8f55172729f0470c14b8308da4c"
    "?per_page=30&predicate_type=https%3A%2F%2Fslsa.dev%2Fprovenance%2Fv1)\n"
)


def _bundle(**overrides: object) -> str:
    attestation = {
        "verificationResult": {
            "signature": {
                "certificate": {
                    "issuer": "https://token.actions.githubusercontent.com",
                    "sourceRepositoryURI": "https://github.com/OpenRAE/rae",
                    "buildSignerURI": f"https://github.com/{_WORKFLOW}",
                }
            }
        }
    }
    certificate = attestation["verificationResult"]["signature"]["certificate"]
    certificate.update(overrides)  # type: ignore[arg-type]
    return json.dumps([attestation])


def test_command_pins_repository_and_signer_workflow() -> None:
    command = build_verify_command(
        artifact_path="/tmp/raes-1.2.3-py3-none-any.whl",
        repository=_REPOSITORY,
        signer_workflow="OpenRAE/rae/.github/workflows/release-please.yml",
    )
    assert command[0] == "gh"
    assert command[1:3] == ["attestation", "verify"]
    assert "--repo" in command
    assert _REPOSITORY in command
    assert "--signer-workflow" in command
    assert "--format" in command
    assert "json" in command


def test_command_is_fixed_argv_without_shell_interpolation() -> None:
    command = build_verify_command(
        artifact_path="/tmp/a b;rm -rf /",
        repository=_REPOSITORY,
        signer_workflow="OpenRAE/rae/.github/workflows/release-please.yml",
    )
    assert "/tmp/a b;rm -rf /" in command
    assert all(isinstance(part, str) for part in command)
    assert not any(part.startswith("sh ") or "&&" in part for part in command)


def test_clean_verdict_yields_the_producer_identity() -> None:
    producer = parse_verifier_output(_bundle())
    assert producer.issuer == "https://token.actions.githubusercontent.com"
    assert producer.repository == _REPOSITORY
    assert producer.workflow_ref == _WORKFLOW


def test_missing_attestation_reply_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """gh reports a missing attestation through its exit status, not its output."""

    # The fake uses shell builtins only, so PATH can hold nothing else and the
    # real gh, which would query GitHub, cannot be reached instead.
    gh = tmp_path / "gh"
    gh.write_text(f"#!/bin/sh\nprintf '%s' '{_NO_ATTESTATION_STDERR}' >&2\nexit 1\n", encoding="utf-8")
    gh.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path))
    wheel = tmp_path / "raes-1.2.3-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    with pytest.raises(VerifierError) as excinfo:
        collect_attestations(
            distribution_dir=tmp_path,
            evidence_dir=tmp_path,
            index={"subjects": [{"path": wheel.name, "sha256": "0" * 64}], "evidence": []},
            repository=_REPOSITORY,
            signer_workflow="OpenRAE/rae/.github/workflows/release-please.yml",
        )
    assert excinfo.value.code == "verifier-rejected"


def test_empty_attestation_list_is_refused() -> None:
    """A clean exit with an empty list is refused, though gh reports no attestation by exiting 1."""

    with pytest.raises(VerifierError) as excinfo:
        parse_verifier_output("[]")
    assert excinfo.value.code == "verifier-no-attestation"


def test_malformed_verifier_output_is_refused() -> None:
    with pytest.raises(VerifierError) as excinfo:
        parse_verifier_output("not json")
    assert excinfo.value.code == "verifier-output-unparsable"


def test_oversized_verifier_output_is_refused() -> None:
    with pytest.raises(VerifierError) as excinfo:
        parse_verifier_output("[" + "0," * 5_000_000 + "0]")
    assert excinfo.value.code == "verifier-output-oversized"


def test_missing_certificate_identity_is_refused() -> None:
    payload = json.dumps([{"verificationResult": {}}])
    with pytest.raises(VerifierError) as excinfo:
        parse_verifier_output(payload)
    assert excinfo.value.code == "verifier-identity-absent"


def test_ambiguous_multiple_attestations_are_refused() -> None:
    payload = json.dumps(json.loads(_bundle()) * 2)
    with pytest.raises(VerifierError) as excinfo:
        parse_verifier_output(payload)
    assert excinfo.value.code == "verifier-ambiguous-attestation"


def test_source_repository_uri_that_is_not_a_github_url_is_refused() -> None:
    payload = _bundle(sourceRepositoryURI="https://evil.example/OpenRAE/rae")
    with pytest.raises(VerifierError) as excinfo:
        parse_verifier_output(payload)
    assert excinfo.value.code == "verifier-identity-untrusted-host"
