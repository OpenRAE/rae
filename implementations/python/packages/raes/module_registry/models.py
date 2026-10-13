"""Pydantic policy/lock models, the resolved-module DTO, and lockfile persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import Field

from .._base import SDLModel
from .._errors import SDLParseError
from ..scenario import ImportDecl, ModuleDescriptor, Scenario
from ._constants import (
    LOCKFILE_NAME,
    LOCKFILE_SCHEMA_VERSION,
    TRUST_POLICY_NAME,
    TRUST_POLICY_SCHEMA_VERSION,
)

if TYPE_CHECKING:
    from ..parser import SDLSourceDocument
    from ._verified_sources import _VerifiedSourceBundle


class RegistryTrustPolicy(SDLModel):
    require_signatures: bool = True
    trusted_signers: dict[str, str] = Field(default_factory=dict)
    allow_insecure_http: bool = False


class TrustPolicy(SDLModel):
    schema_version: str = TRUST_POLICY_SCHEMA_VERSION
    allow_unsigned_local_sources: bool = True
    registries: dict[str, RegistryTrustPolicy] = Field(default_factory=dict)


class LockRecord(SDLModel):
    source: str
    namespace: str
    requested_version: str = "*"
    resolved_source: str
    module_id: str
    module_version: str
    manifest_digest: str
    content_digest: str
    export_hash: str
    signer_id: str = ""


class Lockfile(SDLModel):
    schema_version: str = LOCKFILE_SCHEMA_VERSION
    imports: list[LockRecord] = Field(default_factory=list)

    def locked_record(self, locked_ref: str) -> LockRecord | None:
        """Return the record that a ``locked:<ref>`` import names, by resolved or requested source."""

        return next((record for record in self.imports if locked_ref in {record.resolved_source, record.source}), None)


@dataclass(frozen=True)
class ResolvedModule:
    import_decl: ImportDecl
    module_descriptor: ModuleDescriptor
    root_file: Path
    source_document: SDLSourceDocument
    resolved_source: str
    manifest_digest: str = ""
    content_digest: str = ""
    export_hash: str = ""
    signer_id: str = ""
    verified_sources: _VerifiedSourceBundle | None = None


def _scenario_module_descriptor(scenario: Scenario, *, source_id: str) -> ModuleDescriptor:
    if scenario.module is not None:
        return scenario.module
    raise SDLParseError(
        "Imported SDL units require an explicit module descriptor",
        path=Path(source_id),
    )


def load_trust_policy(base_dir: Path) -> TrustPolicy:
    path = base_dir / TRUST_POLICY_NAME
    if not path.exists():
        return TrustPolicy()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return TrustPolicy.model_validate(payload)


def load_lockfile(base_dir: Path) -> Lockfile | None:
    path = base_dir / LOCKFILE_NAME
    if not path.exists():
        return None
    return Lockfile.model_validate_json(path.read_text(encoding="utf-8"))


def write_lockfile(base_dir: Path, lockfile: Lockfile) -> Path:
    path = base_dir / LOCKFILE_NAME
    path.write_text(
        json.dumps(lockfile.model_dump(mode="python"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
