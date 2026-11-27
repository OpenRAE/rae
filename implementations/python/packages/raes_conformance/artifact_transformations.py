"""Focused conformance runner for checked-in artifact-transformation cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from raes import (
    ArtifactTransformationPolicy,
    RemoveSDLDeclarationRequest,
    RenameSDLDeclarationRequest,
    canonicalize_portable_contract,
    parse_sdl_file,
    remove_sdl_declaration,
    rename_sdl_declaration,
)
from raes_contracts.contracts import (
    ArtifactTransformationLossKind,
    ArtifactTransformationStatus,
    ExternalConceptBindingDocumentModel,
)
from raes_contracts.corpus import FIXTURES, corpus_family_root
from raes_contracts.errors import InvalidInputError, OperationalError
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.operational_logging import get_logger

from raes_conformance.conformance.diagnostics import sanitized_failure_message

_LOGGER = get_logger(__name__)
_MAX_CASE_BYTES = 32 * 1024
_MAX_PORTABLE_CONTRACT_BYTES = 1024 * 1024


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_address: str | None = Field(default=None, min_length=1, max_length=4096)
    new_local_name: str | None = Field(default=None, min_length=1, max_length=128)


class _PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_loss_kinds: tuple[ArtifactTransformationLossKind, ...] = ()


class _ExpectedIdentityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    before: str = Field(min_length=1, max_length=4096)
    after: str = Field(min_length=1, max_length=4096)


class _ExpectedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ArtifactTransformationStatus
    identity_map: tuple[_ExpectedIdentityModel, ...] = ()


class ArtifactTransformationFixtureCaseModel(BaseModel):
    """Closed checked-in transformation case descriptor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)
    operation: Literal[
        "rename-sdl-declaration/v1",
        "remove-sdl-declaration/v1",
        "canonicalize-portable-contract/v1",
    ]
    source_contract: Literal["sdl-authoring-input/v1", "external-concept-bindings/v1"]
    source_path: str = Field(pattern=r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$", max_length=512)
    request: _RequestModel
    policy: _PolicyModel
    expected: _ExpectedModel

    @model_validator(mode="after")
    def _validate_operation_shape(self) -> ArtifactTransformationFixtureCaseModel:
        if self.operation == "rename-sdl-declaration/v1":
            if self.source_contract != "sdl-authoring-input/v1":
                raise ValueError("rename cases require an SDL source")
            if self.request.target_address is None or self.request.new_local_name is None:
                raise ValueError("rename cases require target_address and new_local_name")
        elif self.operation == "remove-sdl-declaration/v1":
            if self.source_contract != "sdl-authoring-input/v1":
                raise ValueError("removal cases require an SDL source")
            if self.request.target_address is None or self.request.new_local_name is not None:
                raise ValueError("removal cases require only target_address")
        elif (
            self.source_contract != "external-concept-bindings/v1"
            or self.request.target_address is not None
            or self.request.new_local_name is not None
        ):
            raise ValueError("portable canonicalization cases require an empty request")
        return self


@dataclass(frozen=True, slots=True)
class ArtifactTransformationConformanceCaseResult:
    case_id: str
    passed: bool
    status: ArtifactTransformationStatus | None
    report_digest: str | None
    diagnostic: str | None = None


@dataclass(frozen=True, slots=True)
class ArtifactTransformationConformanceReport:
    profile: str
    passed: bool
    cases: tuple[ArtifactTransformationConformanceCaseResult, ...]


def _confined_fixture_path(fixtures: Path, relative: str) -> Path:
    root = fixtures.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise InvalidInputError("transformation fixture source resolves outside the fixture corpus") from exc
    return candidate


def _load_case(path: Path) -> ArtifactTransformationFixtureCaseModel:
    payload = parse_bounded_json_object(path.read_bytes(), max_bytes=_MAX_CASE_BYTES)
    return ArtifactTransformationFixtureCaseModel.model_validate(payload)


def _execute_case(
    case: ArtifactTransformationFixtureCaseModel,
    *,
    fixtures: Path,
) -> ArtifactTransformationConformanceCaseResult:
    source_path = _confined_fixture_path(fixtures, case.source_path)
    if case.operation == "canonicalize-portable-contract/v1":
        payload = parse_bounded_json_object(
            source_path.read_bytes(),
            max_bytes=_MAX_PORTABLE_CONTRACT_BYTES,
        )
        source = ExternalConceptBindingDocumentModel.model_validate(payload)
        transformed = canonicalize_portable_contract(source)
        output_present = transformed.output is not None
        report = transformed.report
    else:
        source = parse_sdl_file(source_path)
        if case.operation == "rename-sdl-declaration/v1":
            if case.request.target_address is None or case.request.new_local_name is None:
                raise ValueError("admitted rename case is missing its request fields")
            transformed = rename_sdl_declaration(
                source,
                RenameSDLDeclarationRequest(
                    target_address=case.request.target_address,
                    new_local_name=case.request.new_local_name,
                ),
            )
        else:
            if case.request.target_address is None:
                raise ValueError("admitted removal case is missing target_address")
            transformed = remove_sdl_declaration(
                source,
                RemoveSDLDeclarationRequest(target_address=case.request.target_address),
                policy=ArtifactTransformationPolicy(case.policy.allowed_loss_kinds),
            )
        output_present = transformed.output is not None
        report = transformed.report

    actual_identity_map = tuple((item.before, item.after) for item in report.identity_map)
    expected_identity_map = tuple((item.before, item.after) for item in case.expected.identity_map)
    all_or_none = output_present == (report.status == ArtifactTransformationStatus.SUCCESS)
    passed = (
        report.operation_profile == case.operation
        and report.status == case.expected.status
        and actual_identity_map == expected_identity_map
        and all_or_none
    )
    return ArtifactTransformationConformanceCaseResult(
        case_id=case.case_id,
        passed=passed,
        status=report.status,
        report_digest=report.derivation_digest,
        diagnostic=None if passed else "transformation result did not match the closed expected outcome",
    )


def _failed_case(case_path: Path, exc: Exception) -> ArtifactTransformationConformanceCaseResult:
    return ArtifactTransformationConformanceCaseResult(
        case_id=case_path.stem,
        passed=False,
        status=None,
        report_digest=None,
        diagnostic=sanitized_failure_message(exc),
    )


def run_artifact_transformation_fixture_suite(
    *,
    root: Path | None = None,
) -> ArtifactTransformationConformanceReport:
    """Execute transformation cases in stable order against the production APIs."""

    fixtures = corpus_family_root(FIXTURES) if root is None else root
    cases_root = fixtures / "artifact-transformations-v1" / "cases"
    results: list[ArtifactTransformationConformanceCaseResult] = []
    for case_path in sorted(cases_root.glob("*.json")):
        try:
            case = _load_case(case_path)
            results.append(_execute_case(case, fixtures=fixtures))
        # A missing or invalid case, source or module import fails only this case.
        except (OSError, InvalidInputError, OperationalError, ValidationError) as exc:
            results.append(_failed_case(case_path, exc))
        except Exception as exc:
            # Boundary of one fixture case: the case fails with a sanitized diagnostic; log the unexpected cause once.
            _LOGGER.exception("artifact transformation conformance case failed unexpectedly")
            results.append(_failed_case(case_path, exc))
    case_tuple = tuple(results)
    return ArtifactTransformationConformanceReport(
        profile="artifact-transformations/v1",
        passed=bool(case_tuple) and all(case.passed for case in case_tuple),
        cases=case_tuple,
    )


__all__ = [
    "ArtifactTransformationConformanceCaseResult",
    "ArtifactTransformationConformanceReport",
    "ArtifactTransformationFixtureCaseModel",
    "run_artifact_transformation_fixture_suite",
]
