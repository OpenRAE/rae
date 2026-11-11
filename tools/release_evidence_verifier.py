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
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAES_PACKAGES_ROOT = REPO_ROOT / "implementations" / "python" / "packages"
for _source_root in (REPO_ROOT, RAES_PACKAGES_ROOT):
    if str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from raes_contracts.errors import InvalidInputError, RaesError  # noqa: E402

from tools.release_evidence_admission import ProducerIdentity  # noqa: E402

# The verifier emits a small JSON array. Anything larger is malformed output or
# a hostile response rather than a verdict.
# The verifier emits a JSON document tree; naming it beats `Any`.
type JsonValue = "str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]"

MAX_VERIFIER_OUTPUT_BYTES = 1 * 1024 * 1024
_VERIFIER_TIMEOUT_SECONDS = 120

_GITHUB_PREFIX = "https://github.com/"


class VerifierError(RaesError):
    """A verification-boundary failure carrying a stable, publishable code.

    The codes cover rejected evidence and a verifier that cannot run, which
    are different categories, so the family derives from ``RaesError``. Each
    code means that no attestation was verified, and the release gate rejects
    the evidence.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _IntegerDigitLimitError(InvalidInputError):
    """A JSON integer exceeds the interpreter digit limit; it controls the flow of this module only."""


def _bounded_integer(literal: str) -> int:
    # The decoder passes only JSON integer literals, so int() fails only beyond the interpreter digit limit.
    try:
        return int(literal)
    except ValueError as exc:
        raise _IntegerDigitLimitError("JSON integer exceeds the interpreter digit limit") from exc


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


def _sole_attestation(payload: str) -> JsonValue:
    """Decode the verifier's output down to exactly one attestation."""

    if len(payload.encode("utf-8", errors="ignore")) > MAX_VERIFIER_OUTPUT_BYTES:
        raise VerifierError(
            "verifier-output-oversized",
            "attestation verifier output exceeds the reviewed size bound",
        )
    try:
        document: JsonValue = json.loads(payload, parse_int=_bounded_integer)
    except (json.JSONDecodeError, _IntegerDigitLimitError) as exc:
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
    return document[0]


def _certificate(entry: JsonValue) -> Mapping[str, JsonValue]:
    """Reach the signing certificate, refusing any shape that lacks one."""

    result = entry.get("verificationResult") if isinstance(entry, Mapping) else None
    signature = result.get("signature") if isinstance(result, Mapping) else None
    certificate = signature.get("certificate") if isinstance(signature, Mapping) else None
    if not isinstance(certificate, Mapping):
        raise VerifierError(
            "verifier-identity-absent",
            "attestation carries no certificate identity",
        )
    return certificate


def parse_verifier_output(payload: str) -> ProducerIdentity:
    """Read exactly one clean verdict out of the maintained verifier's output."""

    certificate = _certificate(_sole_attestation(payload))
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


def run_verifier(command: Sequence[str]) -> str:
    """Run the maintained verifier with a fixed argument vector and return its output."""

    try:
        # Fixed argv, no shell, closed stdin.
        completed = subprocess.run(  # noqa: S603
            list(command),
            capture_output=True,
            text=True,
            timeout=_VERIFIER_TIMEOUT_SECONDS,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerifierError("verifier-unavailable", "attestation verifier could not be executed") from exc
    except UnicodeDecodeError as exc:
        # Text mode decodes the verifier output; output that does not decode cannot be parsed.
        raise VerifierError("verifier-output-unparsable", "attestation verifier output could not be parsed") from exc
    if completed.returncode != 0:
        raise VerifierError("verifier-rejected", "attestation verifier did not return a clean verdict")
    return completed.stdout


__all__ = [
    "MAX_VERIFIER_OUTPUT_BYTES",
    "VerifierError",
    "build_verify_command",
    "parse_verifier_output",
    "run_verifier",
]
