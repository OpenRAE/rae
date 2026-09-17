"""Portable public-seed digest generation semantics for typed private profiles."""

from ._base import ContractModel, NonEmptyString
from .canonical import canonical_json_digest
from .domain_profiles import DomainProfileSemanticContractModel

DIGEST_ARTIFACT_SEMANTICS = DomainProfileSemanticContractModel(
    authority="https://openrae.org/profiles",
    contract_id="public-seed-digest-artifact",
    revision="1",
    digest=canonical_json_digest(
        {
            "contract": "public-seed-digest-artifact/v1",
            "input": "public UTF-8 seed",
            "output": "ASCII lowercase SHA-256 hex bytes on each declared output",
            "delivery": "existing sensitivity, lifecycle and exact read-only consumer projections",
        }
    ),
)


class DigestArtifactParameters(ContractModel):
    seed: NonEmptyString
