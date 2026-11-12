"""Stub manifests bound to published realization envelope fixtures.

Processor and runtime tests need apparatus declarations for more than one
compute substrate. The published envelopes under ``contracts/realization-envelopes``
are RAES-owned dry fixtures, so these helpers bind one of them to the stub
manifest instead of importing a concrete backend.
"""

from __future__ import annotations

import json
from dataclasses import replace

from raes_backend_protocols.capabilities import BackendCapabilitySet, BackendManifest
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.corpus import REALIZATION_ENVELOPES, corpus_family_root
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel, RealizationConcern
from raes_contracts.vocabulary import RealizationVerificationScope

VIRTUAL_MACHINE_ENVELOPE = "libvirt-qemu/generic-v1.json"
OS_CONTAINER_ENVELOPE = "reference-emulation/oci-container-v1.json"


def published_envelope(relative: str) -> BackendRealizationEnvelopeModel:
    """Load one published realization envelope fixture by its corpus-relative path."""

    path = corpus_family_root(REALIZATION_ENVELOPES) / relative
    return BackendRealizationEnvelopeModel.model_validate(json.loads(path.read_text(encoding="utf-8")))


_PROVISIONING_CONTRACT_VERSIONS = frozenset(
    {
        "backend-manifest-v2",
        "realization-envelope-v1",
        "operation-receipt-v1",
        "operation-status-v1",
        "provisioning-plan-v1",
        "runtime-snapshot-v1",
    }
)


def _with_substrate_capability(support, envelope: BackendRealizationEnvelopeModel):
    claim = next(item for item in envelope.concerns if item.concern is RealizationConcern.COMPUTE_SUBSTRATE)
    return replace(
        support,
        observation_capabilities={
            **support.observation_capabilities,
            "compute-substrate": RealizationObservationCapability(
                verification_scope=RealizationVerificationScope.PRESENCE,
                observation_strength=claim.observation_strength,
            ),
        },
    )


def provisioning_only_manifest(envelope: BackendRealizationEnvelopeModel) -> BackendManifest:
    """Return a provisioner-only stub manifest that declares ``envelope``."""

    base = create_stub_manifest(with_realization_envelope=True)
    return BackendManifest(
        name="provisioning-only-double",
        version=base.version,
        supported_contract_versions=_PROVISIONING_CONTRACT_VERSIONS,
        compatible_processors=base.compatible_processors,
        concept_bindings=tuple(
            binding for binding in base.concept_bindings if binding.scope.startswith("capabilities.provisioner.")
        ),
        realization_support=(_with_substrate_capability(base.realization_support[0], envelope),),
        capabilities=BackendCapabilitySet(provisioner=base.provisioner),
        realization_envelope=envelope,
    )


def stub_manifest_with_envelope(relative: str, *, with_time: bool = False) -> BackendManifest:
    """Return the stub manifest declaring the substrate of a published envelope."""

    base = create_stub_manifest(with_time=with_time, with_realization_envelope=True)
    envelope = published_envelope(relative)
    support = _with_substrate_capability(base.realization_support[0], envelope)
    return replace(base, realization_support=(support,), realization_envelope=envelope)
