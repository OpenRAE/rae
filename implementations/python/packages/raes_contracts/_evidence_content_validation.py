"""Bounded byte and output-contract validation for experiment evidence."""

from __future__ import annotations

import hashlib
from typing import BinaryIO

from .contracts import (
    ExperimentArtifactRefModel,
    ExperimentCaptureRequirementModel,
    ExperimentEvidenceRecordModel,
)
from .evidence_output_validation import resolve_evidence_output_contract
from .json_ingress import JSONValue, parse_bounded_json, parse_bounded_json_object

_CHUNK_SIZE = 64 * 1024
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def _read_payload(reader: BinaryIO, *, size: int, algorithm: str) -> tuple[bytes, str]:
    if size > _MAX_ARTIFACT_BYTES:
        raise ValueError("evidence artifact exceeds the bounded validation limit")
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise ValueError("evidence artifact checksum algorithm is unsupported") from exc
    chunks: list[bytes] = []
    total = 0
    while total <= size:
        chunk = reader.read(min(_CHUNK_SIZE, size + 1 - total))
        if not isinstance(chunk, bytes):
            raise ValueError("evidence artifact reader must return bytes")
        if not chunk:
            break
        chunks.append(chunk)
        digest.update(chunk)
        total += len(chunk)
    if total != size:
        raise ValueError("evidence artifact bytes do not match the declared size")
    return b"".join(chunks), digest.hexdigest()


def _json_pointer_resolves(document: object, pointer: str) -> bool:
    if pointer == "":
        return True
    current = document
    for encoded in pointer.removeprefix("/").split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return False
    return True


def _parse_contract_document(payload: bytes, *, media_type: str, output_contract: str) -> JSONValue:
    contract = resolve_evidence_output_contract(output_contract)
    root = contract.root
    try:
        if media_type not in contract.media_types:
            raise ValueError("evidence media type is not supported by the declared output_contract")
        if media_type == "application/json":
            document = parse_bounded_json(payload, max_bytes=_MAX_ARTIFACT_BYTES, root=root)
        else:
            lines = payload.splitlines()
            if not lines or any(not line.strip() for line in lines):
                raise ValueError("JSON Lines evidence must contain non-empty object records")
            document = [parse_bounded_json_object(line, max_bytes=_MAX_ARTIFACT_BYTES) for line in lines]
    except ValueError as exc:
        raise ValueError("emitted evidence does not satisfy the declared output_contract") from exc
    contract.validate(document)
    return document


def _validate_artifact_content(
    requirement: ExperimentCaptureRequirementModel,
    record: ExperimentEvidenceRecordModel,
    artifact: ExperimentArtifactRefModel,
    reader: BinaryIO | None,
) -> None:
    if reader is None:
        raise ValueError("required emitted evidence has no concrete byte reader")
    _validate_artifact_metadata(requirement, record, artifact)
    payload, checksum = _read_payload(
        reader,
        size=artifact.size_bytes,
        algorithm=artifact.checksum.algorithm,
    )
    if checksum.casefold() != artifact.checksum.value.casefold():
        raise ValueError("emitted evidence checksum does not match the captured bytes")
    _validate_artifact_integrity(requirement, artifact)
    document = _parse_contract_document(
        payload,
        media_type=artifact.media_type,
        output_contract=requirement.output_contract,
    )
    _validate_field_selectors(requirement, document)


def _validate_artifact_metadata(
    requirement: ExperimentCaptureRequirementModel,
    record: ExperimentEvidenceRecordModel,
    artifact: ExperimentArtifactRefModel,
) -> None:
    if requirement.required_artifact_roles and artifact.role not in requirement.required_artifact_roles:
        raise ValueError("emitted evidence artifact role does not match the capture requirement")
    if artifact.media_type not in requirement.expected_media_types:
        raise ValueError("emitted evidence media type does not match the capture requirement")
    if artifact.sensitivity != requirement.sensitivity or artifact.sensitivity != record.sensitivity:
        raise ValueError("emitted evidence artifact sensitivity does not match the validated capture record")


def _validate_artifact_integrity(
    requirement: ExperimentCaptureRequirementModel,
    artifact: ExperimentArtifactRefModel,
) -> None:
    for integrity in requirement.integrity_requirements:
        if integrity in {"checksum", "sha256-digest"}:
            if integrity == "sha256-digest" and artifact.checksum.algorithm != "sha256":
                raise ValueError("emitted evidence does not satisfy the required sha256 integrity mode")
        else:
            raise ValueError(f"emitted evidence cannot prove integrity requirement {integrity!r}")


def _validate_field_selectors(requirement: ExperimentCaptureRequirementModel, document: JSONValue) -> None:
    missing = sorted(
        selector for selector in requirement.field_selectors if not _json_pointer_resolves(document, selector)
    )
    if missing:
        raise ValueError("emitted evidence is missing required field selector(s): " + ", ".join(missing))
