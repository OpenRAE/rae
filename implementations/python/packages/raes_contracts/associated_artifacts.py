"""Canonical identity and bounded byte binding for associated artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import BinaryIO, cast

import rfc8785
from blake3 import blake3
from raes import MaterializedScenario, canonical_materialized_sdl_digest, canonical_sdl_digest
from raes.scenario import ExpandedScenario, InstantiatedScenario, Scenario

from .contracts import (
    AssociatedArtifactManifestModel,
    ExperimentApparatusContextModel,
    ExperimentArtifactRefModel,
    ExperimentRunModel,
    ExperimentSpecModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
)
from .diagnostics import Diagnostic, Severity
from .json_ingress import parse_bounded_json_object

_DOMAIN = "associated-artifact"
_CHUNK_SIZE = 64 * 1024
_ARTIFACTS_ADDRESS = "#/artifacts"
_MAX_MANIFEST_BYTES = 16 * 1024 * 1024

JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


@dataclass(frozen=True)
class AssociatedArtifactValidationLimits:
    """Caller policy limits for one manifest validation."""

    max_artifacts: int = 1024
    max_artifact_bytes: int = 1024 * 1024 * 1024
    max_total_bytes: int = 4 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_artifacts < 1 or self.max_artifact_bytes < 0 or self.max_total_bytes < 0:
            raise ValueError("associated-artifact validation limits must be non-negative and allow an artifact")


def _normalized_canonical_value(value: JSONValue) -> JSONValue:
    if isinstance(value, dict):
        normalized = {key: _normalized_canonical_value(item) for key, item in value.items()}
        checksum = normalized.get("checksum")
        if isinstance(checksum, dict) and isinstance(checksum.get("value"), str):
            checksum["value"] = checksum["value"].casefold()
        if isinstance(normalized.get("ref_digest"), str):
            normalized["ref_digest"] = normalized["ref_digest"].casefold()
        return normalized
    if isinstance(value, list):
        return [_normalized_canonical_value(item) for item in value]
    return value


def associated_artifact_set_bytes(manifest: AssociatedArtifactManifestModel) -> bytes:
    """Return RFC 8785 bytes for the abstract parent-plus-reference set."""

    projection = {
        "profile": manifest.canonicalization_profile,
        "scope": manifest.scope,
        "parent_ref": manifest.parent_ref.model_dump(mode="json", exclude_none=True),
        "artifacts": {
            artifact_id: artifact.model_dump(mode="json", exclude_none=True)
            for artifact_id, artifact in manifest.artifacts.items()
        },
    }
    try:
        return rfc8785.dumps(_normalized_canonical_value(projection))
    except rfc8785.CanonicalizationError as exc:
        raise ValueError("associated-artifact set canonicalization failed") from exc


def associated_artifact_set_digest(manifest: AssociatedArtifactManifestModel) -> str:
    """Derive the v1 lowercase SHA-256 identity for a manifest's artifact set."""

    digest = hashlib.sha256(associated_artifact_set_bytes(manifest)).hexdigest()
    return f"sha256:{digest}"


def load_associated_artifact_manifest_json(source: str | bytes | bytearray) -> AssociatedArtifactManifestModel:
    """Parse one manifest while rejecting duplicate JSON members before construction."""

    payload = parse_bounded_json_object(source, max_bytes=_MAX_MANIFEST_BYTES)
    return AssociatedArtifactManifestModel.model_validate(payload)


def _diagnostic(code: str, address: str, message: str) -> Diagnostic:
    return Diagnostic(code=code, domain=_DOMAIN, address=address, message=message, severity=Severity.ERROR)


def _scenario_parent_matches(manifest: AssociatedArtifactManifestModel, parent: object) -> bool:
    reference = manifest.parent_ref
    if reference.ref_kind == "scenario":
        # Generic scenario association remains the incumbent id-only contract.
        return isinstance(parent, Scenario) and parent.name == reference.ref_id

    snapshot_types = (Scenario, ExpandedScenario)
    matches = (
        isinstance(parent, snapshot_types)
        and not isinstance(parent, InstantiatedScenario)
        and parent.semantic_validated
        and parent.name == reference.ref_id
    )
    if matches:
        matches = reference.ref_version is None or parent.version == reference.ref_version
    if matches and reference.ref_digest is not None:
        matches = canonical_sdl_digest(parent).value.casefold() == reference.ref_digest.casefold()
    return matches


def _experiment_parent_matches(manifest: AssociatedArtifactManifestModel, parent: object) -> bool:
    reference = manifest.parent_ref
    parent_shapes: dict[str, tuple[type[object], str, str]] = {
        "task": (ExperimentTaskModel, "task_id", "task_version"),
        "authoring-input": (ExperimentSpecModel, "spec_id", "spec_version"),
        "apparatus-context": (ExperimentApparatusContextModel, "apparatus_context_id", "context_version"),
        "run": (ExperimentRunModel, "run_id", "run_version"),
        "study": (ExperimentStudyModel, "study_id", "study_version"),
    }
    expected_type, id_field, version_field = parent_shapes[reference.ref_kind]
    matches = isinstance(parent, expected_type) and getattr(parent, id_field) == reference.ref_id
    if matches and reference.ref_version is not None:
        matches = getattr(parent, version_field) == reference.ref_version
    return matches


def _parent_matches(manifest: AssociatedArtifactManifestModel, parent: object) -> bool:
    if manifest.parent_ref.ref_kind == "materialization-attestation":
        reference = manifest.parent_ref
        return (
            isinstance(parent, MaterializedScenario)
            and parent.semantic_validated
            and parent.materialization_provenance.attestation_id == reference.ref_id
            and reference.ref_version == "raes-sdl-materialized/v1"
            and canonical_materialized_sdl_digest(parent).value == reference.ref_digest
        )
    if manifest.parent_ref.ref_kind in {"scenario", "scenario-snapshot"}:
        return _scenario_parent_matches(manifest, parent)
    return _experiment_parent_matches(manifest, parent)


def _read_and_hash(reader: BinaryIO, algorithm: str, declared_size: int) -> tuple[int, str] | None:
    if algorithm == "blake3":
        digest = blake3()
    else:
        try:
            digest = hashlib.new(algorithm)
        except ValueError:
            return None
    total = 0
    while total <= declared_size:
        chunk = reader.read(min(_CHUNK_SIZE, declared_size + 1 - total))
        if not isinstance(chunk, bytes):
            raise TypeError("artifact reader must return bytes")
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
    return total, digest.hexdigest()


def _resource_limit_diagnostics(
    manifest: AssociatedArtifactManifestModel,
    limits: AssociatedArtifactValidationLimits,
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if len(manifest.artifacts) > limits.max_artifacts:
        diagnostics.append(
            _diagnostic(
                "associated-artifact.resource-limit-exceeded",
                _ARTIFACTS_ADDRESS,
                "artifact count exceeds the caller-supplied validation limit",
            )
        )
    declared_total = sum(artifact.size_bytes for artifact in manifest.artifacts.values())
    oversized = [
        artifact_id
        for artifact_id, artifact in manifest.artifacts.items()
        if artifact.size_bytes > limits.max_artifact_bytes
    ]
    if oversized or declared_total > limits.max_total_bytes:
        diagnostics.append(
            _diagnostic(
                "associated-artifact.resource-limit-exceeded",
                _ARTIFACTS_ADDRESS,
                "declared artifact bytes exceed the caller-supplied validation limits",
            )
        )
    return tuple(diagnostics)


def _identity_diagnostics(manifest: AssociatedArtifactManifestModel, parent: object) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    if not _parent_matches(manifest, parent):
        diagnostics.append(
            _diagnostic(
                "associated-artifact.parent-mismatch",
                "#/parent_ref",
                "the supplied concrete parent does not match parent_ref",
            )
        )
    if associated_artifact_set_digest(manifest) != manifest.set_digest:
        diagnostics.append(
            _diagnostic(
                "associated-artifact.set-digest-mismatch",
                "#/set_digest",
                "set_digest does not match the canonical parent-plus-artifact-reference set",
            )
        )
    return tuple(diagnostics)


def _binding_presence_diagnostics(
    manifest_ids: set[str],
    supplied_ids: set[str],
) -> tuple[Diagnostic, ...]:
    diagnostics: list[Diagnostic] = []
    for artifact_id in sorted(manifest_ids - supplied_ids):
        diagnostics.append(
            _diagnostic(
                "associated-artifact.payload-binding-missing",
                f"#/artifacts/{artifact_id}",
                "no concrete byte reader was supplied for this artifact",
            )
        )
    for artifact_id in sorted(supplied_ids - manifest_ids):
        diagnostics.append(
            _diagnostic(
                "associated-artifact.payload-binding-unexpected",
                _ARTIFACTS_ADDRESS,
                f"a byte reader was supplied for undeclared artifact id {artifact_id!r}",
            )
        )
    return tuple(diagnostics)


def _read_payload(
    artifact_id: str,
    artifact: ExperimentArtifactRefModel,
    reader: object,
) -> tuple[tuple[int, str] | None, Diagnostic | None]:
    address = f"#/artifacts/{artifact_id}"
    result: tuple[int, str] | None = None
    diagnostic: Diagnostic | None = None
    if not hasattr(reader, "read"):
        diagnostic = _diagnostic(
            "associated-artifact.payload-binding-invalid",
            address,
            "the supplied binding is not a concrete byte reader",
        )
    else:
        try:
            result = _read_and_hash(cast(BinaryIO, reader), artifact.checksum.algorithm, artifact.size_bytes)
        except (OSError, TypeError, ValueError):
            diagnostic = _diagnostic(
                "associated-artifact.payload-binding-invalid",
                address,
                "the concrete byte reader failed without yielding a valid bounded byte stream",
            )
        if result is None and diagnostic is None:
            diagnostic = _diagnostic(
                "associated-artifact.checksum-algorithm-unsupported",
                f"{address}/checksum/algorithm",
                "the checksum algorithm is unavailable to this validator",
            )
    return result, diagnostic


def _payload_diagnostics(
    artifact_id: str,
    artifact: ExperimentArtifactRefModel,
    reader: object,
) -> tuple[Diagnostic, ...]:
    address = f"#/artifacts/{artifact_id}"
    result, read_diagnostic = _read_payload(artifact_id, artifact, reader)
    if read_diagnostic is not None:
        return (read_diagnostic,)

    diagnostics: list[Diagnostic] = []
    assert result is not None
    actual_size, actual_checksum = result
    if actual_size != artifact.size_bytes:
        diagnostics.append(
            _diagnostic(
                "associated-artifact.payload-size-mismatch",
                f"{address}/size_bytes",
                "concrete payload size does not match size_bytes",
            )
        )
    if actual_checksum.casefold() != artifact.checksum.value.casefold():
        diagnostics.append(
            _diagnostic(
                "associated-artifact.payload-checksum-mismatch",
                f"{address}/checksum",
                "concrete payload bytes do not match the declared checksum",
            )
        )
    return tuple(diagnostics)


def validate_associated_artifact_manifest(
    manifest: AssociatedArtifactManifestModel,
    *,
    parent: object,
    artifact_readers: Mapping[str, BinaryIO],
    limits: AssociatedArtifactValidationLimits | None = None,
) -> tuple[Diagnostic, ...]:
    """Validate parent/set identity and every payload through bounded readers.

    Scenario snapshots accept only semantically validated ``Scenario`` or
    ``ExpandedScenario`` authoring parents. Generic scenario association keeps
    its id-only ``Scenario`` behavior; instantiated scenarios are never
    canonical authoring snapshot parents.

    The caller acquires and immutably stages payloads. This function performs no
    URI fetching, directory traversal, archive extraction, or ambient lookup.
    """

    limit_diagnostics = _resource_limit_diagnostics(
        manifest,
        limits or AssociatedArtifactValidationLimits(),
    )
    if limit_diagnostics:
        return limit_diagnostics

    diagnostics = list(_identity_diagnostics(manifest, parent))
    manifest_ids = set(manifest.artifacts)
    supplied_ids = set(artifact_readers)
    diagnostics.extend(_binding_presence_diagnostics(manifest_ids, supplied_ids))
    for artifact_id in sorted(manifest_ids & supplied_ids):
        diagnostics.extend(
            _payload_diagnostics(
                artifact_id,
                manifest.artifacts[artifact_id],
                artifact_readers[artifact_id],
            )
        )
    return tuple(diagnostics)


__all__ = [
    "AssociatedArtifactValidationLimits",
    "associated_artifact_set_bytes",
    "associated_artifact_set_digest",
    "load_associated_artifact_manifest_json",
    "validate_associated_artifact_manifest",
]
