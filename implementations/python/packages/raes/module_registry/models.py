"""Pydantic policy/lock models, the resolved-module DTO, and lockfile persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import Field, ValidationError

from .._base import SDLModel
from .._errors import SDLParseError
from .._model_diagnostics import _model_parse_error
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


def _read_policy_file(path: Path) -> str:
    """Read a lockfile or trust policy, failing closed without OS error text."""

    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SDLParseError(f"{path.name} could not be read as a UTF-8 file", path=path) from exc


def _policy_model_error(error: ValidationError, *, path: Path) -> SDLParseError:
    """Render a policy-file model failure through the bounded SDL envelope, naming the file."""

    rendered = _model_parse_error(error, path=path, source_ranges={})
    return SDLParseError(f"{path.name}: {rendered.details}", path=path, diagnostics=rendered.diagnostics)


def load_trust_policy(base_dir: Path) -> TrustPolicy:
    path = base_dir / TRUST_POLICY_NAME
    if not path.exists():
        return TrustPolicy()
    text = _read_policy_file(path)
    try:
        payload = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
        raise SDLParseError(f"{path.name} is not valid YAML{where}", path=path) from exc
    try:
        return TrustPolicy.model_validate(payload)
    except ValidationError as exc:
        raise _policy_model_error(exc, path=path) from exc


def load_lockfile(base_dir: Path) -> Lockfile | None:
    path = base_dir / LOCKFILE_NAME
    if not path.exists():
        return None
    text = _read_policy_file(path)
    try:
        return Lockfile.model_validate_json(text)
    except ValidationError as exc:
        raise _policy_model_error(exc, path=path) from exc


def write_lockfile(base_dir: Path, lockfile: Lockfile) -> Path:
    path = base_dir / LOCKFILE_NAME
    path.write_text(
        json.dumps(lockfile.model_dump(mode="python"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
