"""Pydantic policy/lock models, the resolved-module DTO, and lockfile persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import Field, ValidationError
from raes_contracts.operational_logging import get_logger

from .._base import SDLModel
from .._errors import SDLParseDiagnostic, SDLParseError, SDLSourcePosition, SDLSourceRange
from .._source_profile import DEFAULT_PARSER_LIMITS
from .._source_validation import validate_source_graph, validate_source_tokens
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

_LOGGER = get_logger(__name__)


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
    content = _read_workspace_config(path)
    if content is None:
        return TrustPolicy()
    loader: yaml.SafeLoader | None = None
    try:
        validate_source_tokens(content, path=path, limits=DEFAULT_PARSER_LIMITS)
        loader = yaml.SafeLoader(content)
        root = loader.get_single_node()
        if root is None:
            return TrustPolicy()
        validate_source_graph(root, path=path, limits=DEFAULT_PARSER_LIMITS)
        return TrustPolicy.model_validate(loader.construct_document(root))
    except (yaml.YAMLError, ValidationError, SDLParseError, ValueError, RecursionError) as exc:
        raise _workspace_config_error(path, exc) from None
    finally:
        if loader is not None:
            loader.dispose()


def load_lockfile(base_dir: Path) -> Lockfile | None:
    path = base_dir / LOCKFILE_NAME
    content = _read_workspace_config(path)
    if content is None:
        return None
    try:
        return Lockfile.model_validate_json(content)
    except ValidationError as exc:
        raise _workspace_config_error(path, exc) from None


def _read_workspace_config(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            raw = handle.read(DEFAULT_PARSER_LIMITS.max_input_bytes + 1)
        if len(raw) > DEFAULT_PARSER_LIMITS.max_input_bytes:
            raise _workspace_config_error(path)
        return raw.decode("utf-8")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as exc:
        raise _workspace_config_error(path, exc) from None
    except OSError as exc:
        # ``from None`` keeps OS error text out of the parse error, so record the cause first (rule L3).
        _LOGGER.warning("workspace configuration %s could not be read", path.name, exc_info=True)
        raise _workspace_config_error(path, exc) from None


def _workspace_config_error(path: Path, exc: Exception | None = None) -> SDLParseError:
    """Expose source metadata without YAML/Pydantic input values or OS error prose."""

    message = f"Cannot load workspace configuration {path.name}."
    mark = getattr(exc, "problem_mark", None)
    position = SDLSourcePosition(mark.line + 1, mark.column + 1) if mark else SDLSourcePosition(1, 1)
    source_range = SDLSourceRange(start=position, end=position)
    if isinstance(exc, SDLParseError) and exc.diagnostics:
        source_range = exc.diagnostics[0].primary_range
    diagnostic = SDLParseDiagnostic(
        code="sdl.workspace-config.invalid",
        message=message,
        pointer="",
        primary_range=source_range,
        source=str(path),
    )
    return SDLParseError(message, path=path, diagnostics=(diagnostic,))


def write_lockfile(base_dir: Path, lockfile: Lockfile) -> Path:
    path = base_dir / LOCKFILE_NAME
    path.write_text(
        json.dumps(lockfile.model_dump(mode="python"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
