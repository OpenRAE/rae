"""Closed frozen shape admission for the finite retained evidence corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field
from referencing import Registry

from tools.policy.common import safe_repo_path

from ._types import _ARCHIVAL_MANIFEST_SHA256

_ARCHIVE_ROOT = "docs/research/formal-semantic-validation/archive-contracts"


class _ArchivedContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["satisfiability", "exploit-path"]
    path: str = Field(pattern=r"^docs/research/formal-semantic-validation/archive-contracts/[a-z-]+-v1\.json$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    source_schema: str = Field(min_length=1)


class _ArchiveManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: Literal["raes-retained-production-evidence-shapes/v1"]
    contracts: tuple[_ArchivedContract, ...] = Field(min_length=2, max_length=2)


def validate_archival_evidence_shape(repo_root: Path, payload: object, replay_mode: object) -> None:
    manifest_bytes = (repo_root / _ARCHIVE_ROOT / "manifest-v1.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != _ARCHIVAL_MANIFEST_SHA256:
        raise ValueError("historical production evidence archival manifest digest mismatch")
    manifest = _ArchiveManifest.model_validate_json(manifest_bytes)
    records = [record for record in manifest.contracts if record.mode == replay_mode]
    if len(records) != 1:
        raise ValueError("historical production evidence has no archival shape contract")
    record = records[0]
    path = safe_repo_path(repo_root, record.path)
    if path is None or not path.is_file():
        raise ValueError("historical production evidence archival shape is missing")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != record.sha256:
        raise ValueError("historical production evidence archival shape digest mismatch")
    if not Draft202012Validator(json.loads(content), registry=Registry()).is_valid(payload):
        raise ValueError("historical production evidence violates its frozen archival shape")
