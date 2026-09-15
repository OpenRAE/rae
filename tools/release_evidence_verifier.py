#!/usr/bin/env python3
"""Drive the maintained attestation verifier and read back a producer identity.

Signature, certificate chain and issuer verification belong to `gh attestation
verify`; reimplementing cryptography or certificate handling here is explicitly
out of scope. What this module owns is the boundary around that client:

* a fixed argument vector, so no candidate-controlled value is ever interpolated
  into shell source;
* the expected identity, which is supplied by the trusted calling context rather
  than read out of the bundle being verified;
* bounded, strict parsing of the verifier's output, so a crash, a skip, an empty
  result or malformed JSON fails rather than being read as a pass.
"""

from __future__ import annotations

import json
from typing import Any

from tools.release_evidence_admission import ProducerIdentity

# The verifier emits a small JSON array. Anything larger is malformed output or
# a hostile response rather than a verdict.
MAX_VERIFIER_OUTPUT_BYTES = 1 * 1024 * 1024

_GITHUB_PREFIX = "https://github.com/"


class VerifierError(Exception):
    """A verification-boundary failure carrying a stable, publishable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def build_verify_command(
    *,
    artifact_path: str,
    repository: str,
    signer_workflow: str,
) -> list[str]:
    """Build the fixed argument vector for one artifact verification.

    The expected repository and signer workflow are pinned from reviewed policy,
    so a bundle signed for a different repository or workflow cannot satisfy this
    invocation even when its signature is cryptographically valid.
    """

    return [
        "gh",
        "attestation",
        "verify",
        artifact_path,
        "--repo",
        repository,
        "--signer-workflow",
        signer_workflow,
        "--format",
        "json",
    ]


def _repository_from_uri(value: object) -> str:
    if not isinstance(value, str) or not value.startswith(_GITHUB_PREFIX):
        raise VerifierError(
            "verifier-identity-untrusted-host",
            "attestation source repository is not a github.com URI",
        )
    return value[len(_GITHUB_PREFIX) :]


def _workflow_from_uri(value: object) -> str:
    if not isinstance(value, str) or not value.startswith(_GITHUB_PREFIX):
        raise VerifierError(
            "verifier-identity-untrusted-host",
            "attestation build signer is not a github.com URI",
        )
    return value[len(_GITHUB_PREFIX) :]


def parse_verifier_output(payload: str) -> ProducerIdentity:
    """Read exactly one clean verdict out of the maintained verifier's output."""

    if len(payload.encode("utf-8", errors="ignore")) > MAX_VERIFIER_OUTPUT_BYTES:
        raise VerifierError(
            "verifier-output-oversized",
            "attestation verifier output exceeds the reviewed size bound",
        )
    try:
        document: Any = json.loads(payload)
    except ValueError as exc:
        raise VerifierError(
            "verifier-output-unparsable",
            "attestation verifier output could not be parsed",
        ) from exc

    if not isinstance(document, list) or not document:
        raise VerifierError(
            "verifier-no-attestation",
            "attestation verifier returned no attestation",
        )
    if len(document) != 1:
        raise VerifierError(
            "verifier-ambiguous-attestation",
            "attestation verifier returned more than one attestation for one subject",
        )

    entry = document[0]
    certificate = None
    if isinstance(entry, dict):
        result = entry.get("verificationResult")
        signature = result.get("signature") if isinstance(result, dict) else None
        certificate = signature.get("certificate") if isinstance(signature, dict) else None
    if not isinstance(certificate, dict):
        raise VerifierError(
            "verifier-identity-absent",
            "attestation carries no certificate identity",
        )

    issuer = certificate.get("issuer")
    if not isinstance(issuer, str) or not issuer:
        raise VerifierError(
            "verifier-identity-absent",
            "attestation carries no issuer identity",
        )
    return ProducerIdentity(
        issuer=issuer,
        repository=_repository_from_uri(certificate.get("sourceRepositoryURI")),
        workflow_ref=_workflow_from_uri(certificate.get("buildSignerURI")),
    )


__all__ = [
    "MAX_VERIFIER_OUTPUT_BYTES",
    "VerifierError",
    "build_verify_command",
    "parse_verifier_output",
]
