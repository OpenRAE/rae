"""Signature verification is delegated; release association is decided here.

The maintained `gh attestation verify` client owns signature, certificate and
issuer checking. This module owns the argv it is invoked with, the bounds on its
output, and the refusal of anything that is not a clean, parseable verdict.
A skip, a crash, malformed output or a cancelled run never becomes admission.
"""

from __future__ import annotations

import json

import pytest
from tools.release_evidence_verifier import (
    VerifierError,
    build_verify_command,
    parse_verifier_output,
)

_REPOSITORY = "OpenRAE/rae"
_WORKFLOW = "OpenRAE/rae/.github/workflows/release-please.yml@refs/heads/main"


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
    assert "--repo" in command and _REPOSITORY in command
    assert "--signer-workflow" in command
    assert "--format" in command and "json" in command


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


def test_empty_attestation_list_is_refused() -> None:
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
    with pytest.raises(VerifierError) as excinfo:
        parse_verifier_output(json.dumps([{"verificationResult": {}}]))
    assert excinfo.value.code == "verifier-identity-absent"


def test_ambiguous_multiple_attestations_are_refused() -> None:
    document = json.loads(_bundle())
    with pytest.raises(VerifierError) as excinfo:
        parse_verifier_output(json.dumps(document * 2))
    assert excinfo.value.code == "verifier-ambiguous-attestation"


def test_source_repository_uri_that_is_not_a_github_url_is_refused() -> None:
    with pytest.raises(VerifierError) as excinfo:
        parse_verifier_output(_bundle(sourceRepositoryURI="https://evil.example/OpenRAE/rae"))
    assert excinfo.value.code == "verifier-identity-untrusted-host"
