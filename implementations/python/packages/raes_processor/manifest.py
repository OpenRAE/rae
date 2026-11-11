"""Reference processor manifest declarations."""

from __future__ import annotations

from collections.abc import Collection
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from typing import Any

from raes_contracts.apparatus import ConceptBinding
from raes_contracts.contracts import (
    ApparatusIdentityModel,
    ConceptBindingEntryModel,
    ProcessorCapabilitiesV2Model,
    ProcessorCompatibilityModel,
    ProcessorManifestV2Model,
)
from raes_contracts.contracts.participant_tool_support import ProcessorParticipantToolsModel
from raes_contracts.vocabulary import ProcessorFeature

from raes_processor.capabilities import ProcessorCapabilitySet, ProcessorManifest

REFERENCE_PROCESSOR_NAME = "raes-reference-processor"
REFERENCE_SUPPORTED_CONTRACT_VERSIONS_V2 = (
    "processor-manifest-v2",
    "provisioning-plan-v1",
    "orchestration-plan-v1",
    "evaluation-plan-v1",
    "workflow-cancellation-request-v1",
    "operation-receipt-v1",
    "operation-status-v1",
    "runtime-snapshot-v1",
)
REFERENCE_CONCEPT_BINDINGS = (
    ConceptBinding(scope="capabilities.supported_sdl_versions", family="scenarios"),
    ConceptBinding(scope="capabilities.supported_features", family="apparatus-declarations"),
)


def _current_processor_version() -> str:
    try:
        return distribution_version("raes")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def create_reference_processor_manifest(
    *,
    version: str | None = None,
    compatible_backends: Collection[str] = ("stub",),
) -> ProcessorManifest:
    """Return the current repo-owned reference processor manifest."""

    return ProcessorManifest(
        name=REFERENCE_PROCESSOR_NAME,
        version=version or _current_processor_version(),
        supported_contract_versions=frozenset(REFERENCE_SUPPORTED_CONTRACT_VERSIONS_V2),
        capabilities=ProcessorCapabilitySet(
            supported_sdl_versions=frozenset({"sdl-authoring-input-v1"}),
            supported_features=frozenset(ProcessorFeature),
            participant_tools=ProcessorParticipantToolsModel(
                semantic_versions=["participant-tool-profile/v1"],
                feature_support=[
                    {"feature": feature, "support_level": "exact", "evidence_refs": ["tests:ACT-619", "tests:API-414"]}
                    for feature in ("tool_affordances", "scoped_tool_affordances")
                ],
            ),
        ),
        compatible_backends=frozenset(compatible_backends),
        concept_bindings=REFERENCE_CONCEPT_BINDINGS,
        constraints={},
    )


def reference_processor_manifest_v2_model(
    *,
    version: str | None = None,
    compatible_backends: Collection[str] = ("stub",),
) -> ProcessorManifestV2Model:
    """Return the reference processor manifest as the authoritative v2 model."""

    manifest = create_reference_processor_manifest(
        version=version,
        compatible_backends=compatible_backends,
    )
    return ProcessorManifestV2Model(
        identity=ApparatusIdentityModel(name=manifest.identity.name, version=manifest.identity.version),
        supported_contract_versions=list(REFERENCE_SUPPORTED_CONTRACT_VERSIONS_V2),
        compatibility=ProcessorCompatibilityModel(
            backends=sorted(manifest.compatible_backends),
        ),
        concept_bindings=[
            ConceptBindingEntryModel(scope=binding.scope, family=binding.family)
            for binding in manifest.concept_bindings
        ],
        constraints=dict(manifest.constraints),
        capabilities=ProcessorCapabilitiesV2Model(
            supported_sdl_versions=sorted(manifest.supported_sdl_versions),
            supported_features=[feature for feature in ProcessorFeature if feature in manifest.supported_features],
            participant_tools=manifest.capabilities.participant_tools,
        ),
    )


def reference_processor_manifest_model(
    *,
    version: str | None = None,
    compatible_backends: Collection[str] = ("stub",),
) -> ProcessorManifestV2Model:
    """Return the reference processor manifest as the authoritative v2 contract model."""

    return reference_processor_manifest_v2_model(
        version=version,
        compatible_backends=compatible_backends,
    )


def reference_processor_manifest_payload(
    *,
    version: str | None = None,
    compatible_backends: Collection[str] = ("stub",),
) -> dict[str, Any]:
    """Return the reference processor manifest as JSON-ready data."""

    return reference_processor_manifest_v2_model(
        version=version,
        compatible_backends=compatible_backends,
    ).model_dump(mode="json")
