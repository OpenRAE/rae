"""Ed25519 signature payload construction and trusted-signer verification."""

from __future__ import annotations

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from raes_contracts.json_serialization import sorted_json_text

from .._errors import SDLParseError
from ..scenario import ModuleDescriptor
from .models import RegistryTrustPolicy


def _public_key_bytes(encoded_key: str) -> bytes:
    try:
        return base64.b64decode(encoded_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise SDLParseError("Invalid trusted signer public key") from exc


def _signable_payload(
    module_descriptor: ModuleDescriptor,
    *,
    content_digest: str,
    root_file: str,
) -> bytes:
    """Canonical bytes an Ed25519 signature binds for an OCI module (issue #14).

    The payload binds ``root_file`` alongside the module identity, exports, and
    bundle ``content_digest`` so a compromised registry cannot repoint the module
    entrypoint to a different file inside an otherwise-signed bundle. This is the
    single canonical signer-payload builder: publishing and resolving must produce
    the identical shape or verification fails closed.
    """
    return sorted_json_text(
        {
            "module_id": module_descriptor.id,
            "module_version": module_descriptor.version,
            "exports": module_descriptor.exports,
            "content_digest": content_digest,
            "root_file": root_file,
        },
    ).encode("utf-8")


def _verify_signatures(
    *,
    signatures: list[dict[str, str]],
    trust_policy: RegistryTrustPolicy,
    module_descriptor: ModuleDescriptor,
    content_digest: str,
    root_file: str,
) -> str:
    payload = _signable_payload(module_descriptor, content_digest=content_digest, root_file=root_file)
    for signature_entry in signatures:
        signer_id = str(signature_entry.get("signer_id", ""))
        signature_b64 = str(signature_entry.get("signature", ""))
        public_key = trust_policy.trusted_signers.get(signer_id)
        if not signer_id or not signature_b64 or not public_key:
            continue
        try:
            key = Ed25519PublicKey.from_public_bytes(_public_key_bytes(public_key))
            key.verify(base64.b64decode(signature_b64.encode("utf-8")), payload)
        except InvalidSignature, ValueError:
            continue
        else:
            return signer_id
    raise SDLParseError("No valid trusted signer signature found for OCI module")
