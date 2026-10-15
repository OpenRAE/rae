"""Closed operator-installed OCI realization/input/target contracts; never HTTP selectors."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, model_validator
from raes_contracts.associated_artifacts import (
    AssociatedArtifactValidationLimits,
    require_instantiated_scenario_reference,
    validate_associated_artifact_manifest,
)
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AssociatedArtifactManifestModel,
    InjectOrderModel,
    InjectTargetBindingModel,
    InjectTriggerRequestModel,
    OperationArtifactReferenceModel,
)
from raes_contracts.contracts.backend_operation import OperationContractModel, OperationDigest
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.planning import OrchestrationPlan

from .drivers.oci_image_trust import is_image_reference


class OciInjectSourceModel(OperationContractModel):
    """Backend-private descriptor of an admitted image's authored entrypoint; no runtime parameters."""

    profile: Literal["reference-oci-entrypoint/v1"]
    image: str = Field(min_length=1, max_length=512)
    image_config_digest: OperationDigest

    @model_validator(mode="after")
    def _image_reference(self) -> Self:
        if not is_image_reference(self.image):
            raise ValueError("OCI inject source requires a valid image reference")
        return self


class OciInjectProbe(OperationContractModel):
    """Approved non-secret before/after bytes of one explicitly selected world file."""

    binding: InjectTargetBindingModel
    path: str = Field(min_length=1, max_length=256)
    before: bytes = Field(max_length=65536)
    after: bytes = Field(max_length=65536)

    @model_validator(mode="after")
    def _closed_probe(self) -> Self:
        path = PurePosixPath(self.path)
        if not path.is_absolute() or path.as_posix() != self.path or ".." in path.parts or "\0" in self.path:
            raise ValueError("OCI inject probe requires its admitted absolute target path")
        if self.before == self.after:
            raise ValueError("OCI inject readback must distinguish the authored world effect")
        return self


@dataclass(frozen=True)
class OciInjectPermit:
    """Issued by the trusted run ordering authority, never derived from arrival/lock order."""

    request: InjectTriggerRequestModel
    order: InjectOrderModel
    evidence: tuple[OperationArtifactReferenceModel, ...]

    def __post_init__(self) -> None:
        if (self.order.scope, self.order.predecessor) != (
            self.request.run_scope,
            self.request.expected_head,
        ) or not 1 <= len(self.evidence) <= 64:
            raise ValueError("OCI inject permit requires its exact ordered request and admission evidence")


@dataclass(frozen=True)
class OciInjectProgram:
    """Immutable, host-admitted source association and concrete realization pins."""

    scenario: object
    scenario_reference: OperationArtifactReferenceModel
    plan: OrchestrationPlan
    source_manifest: AssociatedArtifactManifestModel
    source_descriptor: bytes
    probes: tuple[OciInjectProbe, ...]
    permits: tuple[OciInjectPermit, ...]
    instantiated_scenario: object | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.plan, OrchestrationPlan)
            or not 1 <= len(self.probes) <= 16
            or not 1 <= len(self.permits) <= 1024
            or not isinstance(self.source_descriptor, bytes)
            or len(self.source_descriptor) > 4096
        ):
            raise ValueError("OCI inject program exceeds its admitted contract bounds")
        require_instantiated_scenario_reference(
            self.scenario, self.scenario_reference, instantiated=self.instantiated_scenario
        )
        if len(self.source_manifest.artifacts) != 1:
            raise ValueError("OCI inject source must have one exact descriptor artifact")
        artifact_id, artifact = next(iter(self.source_manifest.artifacts.items()))
        if artifact.sensitivity not in {"public", "internal"} or artifact.media_type != "application/json":
            raise ValueError("OCI inject source requires an approved non-secret descriptor")
        diagnostics = validate_associated_artifact_manifest(
            self.source_manifest,
            parent=self.scenario,
            artifact_readers={artifact_id: BytesIO(self.source_descriptor)},
            limits=AssociatedArtifactValidationLimits(max_artifacts=1, max_artifact_bytes=4096, max_total_bytes=4096),
        )
        if diagnostics:
            raise ValueError("OCI inject source association or content integrity could not be established")
        OciInjectSourceModel.model_validate(
            parse_bounded_json_object(self.source_descriptor, max_bytes=4096, max_depth=4)
        )
        pairs = [(probe.binding.binding, probe.binding.instance) for probe in self.probes]
        if len(pairs) != len(set(pairs)):
            raise ValueError("OCI inject probes require unique selected binding instances")

    @property
    def source(self) -> OciInjectSourceModel:
        return OciInjectSourceModel.model_validate(
            parse_bounded_json_object(self.source_descriptor, max_bytes=4096, max_depth=4)
        )

    @property
    def source_reference(self) -> OperationArtifactReferenceModel:
        return OperationArtifactReferenceModel(
            contract_id="associated-artifact-manifest-v1",
            artifact_id=self.source_manifest.manifest_id,
            digest=canonical_json_digest(self.source_manifest.model_dump(mode="json")),
        )
