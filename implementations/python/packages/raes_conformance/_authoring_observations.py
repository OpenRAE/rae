"""Admission and incumbent diagnostic projections for authoring conformance."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from pydantic_core import PydanticSerializationError
from raes import (
    RenameSDLDeclarationRequest,
    SDLParseDiagnostic,
    SDLParseError,
    SDLParserLimits,
    canonical_sdl_digest,
    parse_sdl,
    rename_sdl_declaration,
    render_sdl_source,
)
from raes.scenario import Scenario
from raes_contracts.authoring_adapters import AuthoringAdapterVectorModel, AuthoringObservationModel
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ArtifactTransformationReportModel
from raes_contracts.diagnostics import DiagnosticModel
from raes_contracts.errors import EvidenceIntegrityError, InvalidInputError
from raes_processor.semantic_comparison import coordinate_for_artifact

_VALIDATE_PROFILE = "validate-sdl/v1"
_LIMITS = SDLParserLimits(
    max_input_bytes=65536,
    max_scalar_bytes=65536,
    max_depth=32,
    max_nodes=4096,
    max_aliases=32,
    max_expanded_nodes=8192,
    max_imports=1,
    max_composed_nodes=8192,
    max_composed_bytes=65536,
    max_composition_depth=1,
    max_namespace_depth=1,
)


@dataclass(frozen=True)
class AuthoringPathOutput:
    """Untrusted path output plus original, incumbent diagnostic/provenance evidence."""

    input_source: str
    output_source: str | None
    diagnostics: tuple[DiagnosticModel | SDLParseDiagnostic, ...] = ()
    transformation_report: ArtifactTransformationReportModel | None = None


def admit_source(source: str) -> Scenario:
    scenario = parse_sdl(source, limits=_LIMITS, source_format="sdl-yaml/v1", migration_policy="reject")
    if type(scenario) is not Scenario or scenario.imports:
        raise InvalidInputError("this profile requires self-contained normalized authoring SDL")
    if scenario.advisories:
        raise InvalidInputError("this profile cannot compare unstructured advisory evidence")
    return scenario


def _utf8_size(text: str) -> int:
    try:
        return len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        # An unpaired surrogate has no UTF-8 form, so the untrusted path output is not portable text.
        raise InvalidInputError("path output text is not valid UTF-8") from exc


def _carrier_payload(carrier: DiagnosticModel | ArtifactTransformationReportModel) -> dict[str, object]:
    try:
        return carrier.model_dump(mode="json")
    except PydanticSerializationError as exc:
        # A constructed or mutated carrier can hold a value without a JSON form; it is not an incumbent carrier.
        raise InvalidInputError("path output carrier has no portable JSON form") from exc


def diagnostic_digest(diagnostics: tuple[DiagnosticModel | SDLParseDiagnostic, ...]) -> str:
    """Hash a multiset of incumbent semantic keys, preserving duplicate counts."""
    if not isinstance(diagnostics, Collection):
        raise InvalidInputError("diagnostics must use an incumbent structured carrier")
    if len(diagnostics) > 64:
        raise InvalidInputError("diagnostic count exceeds the profile limit")
    keys = [_diagnostic_key(item) for item in diagnostics]
    return canonical_json_digest({"profile": "authoring-diagnostic-semantics/v1", "keys": sorted(keys)})


def _diagnostic_key(item: object) -> tuple[str, str, str, str]:
    """Return the incumbent semantic key of one bounded diagnostic."""
    if isinstance(item, DiagnosticModel):
        item = DiagnosticModel.model_validate(_carrier_payload(item))
        key = item.domain, item.code, item.severity.value, item.address
    elif isinstance(item, SDLParseDiagnostic):
        key = item.stage, item.code, item.severity, item.pointer
        if not isinstance(item.severity, str) or item.severity not in {"error", "warning", "info"}:
            raise InvalidInputError("invalid source diagnostic severity")
    else:
        raise InvalidInputError("diagnostics must use an incumbent structured carrier")
    _require_bounded_diagnostic(key, item.message)
    return key


def _require_bounded_diagnostic(key: tuple[object, ...], message: object) -> None:
    if any(not isinstance(value, str) or _utf8_size(value) > 4096 for value in key):
        raise InvalidInputError("diagnostic key exceeds the profile limit")
    if not key[0] or not key[1] or not isinstance(message, str) or _utf8_size(message) > 512:
        raise InvalidInputError("diagnostic requires bounded code, stage and message")


def observe_output(
    vector: AuthoringAdapterVectorModel,
    output: AuthoringPathOutput,
) -> tuple[AuthoringObservationModel, Scenario | None]:
    if output.output_source is not None and not isinstance(output.output_source, str):
        raise InvalidInputError("path output source must be SDL text")
    artifact = admit_source(output.output_source) if output.output_source is not None else None
    artifact_digest = canonical_sdl_digest(artifact).value if artifact is not None else None
    diagnostics = diagnostic_digest(output.diagnostics)
    if artifact is None and not output.diagnostics:
        raise InvalidInputError("refusal requires structured diagnostics")
    transformation_digest = _transformation_digest(vector, output.transformation_report, artifact, artifact_digest)
    return AuthoringObservationModel(
        outcome="success" if artifact is not None else "refused",
        artifact_coordinate=coordinate_for_artifact(artifact) if artifact is not None else None,
        canonical_artifact_digest=artifact_digest,
        diagnostics_digest=diagnostics,
        transformation_digest=transformation_digest,
    ), artifact


def _transformation_digest(
    vector: AuthoringAdapterVectorModel,
    report: ArtifactTransformationReportModel | None,
    artifact: Scenario | None,
    artifact_digest: str | None,
) -> str | None:
    if report is None:
        if vector.operation.profile != _VALIDATE_PROFILE:
            _require_pre_operation_refusal(vector.input_source, artifact)
        return None
    if not isinstance(report, ArtifactTransformationReportModel):
        raise InvalidInputError("transformation provenance must use the incumbent report carrier")
    # Reconstruct: model_copy/model_construct and nested mutation are not admission.
    report = ArtifactTransformationReportModel.model_validate(_carrier_payload(report))
    _require_transformation_bindings(vector, report, artifact_digest)
    if vector.operation.profile == _VALIDATE_PROFILE:
        raise InvalidInputError("validation must not fabricate transformation provenance")
    return canonical_json_digest(report.model_dump(mode="json"))


def _require_transformation_bindings(
    vector: AuthoringAdapterVectorModel,
    report: ArtifactTransformationReportModel,
    artifact_digest: str | None,
) -> None:
    if len(report.model_dump_json().encode("utf-8")) > 65536:
        raise InvalidInputError("transformation report exceeds the profile byte limit")
    source_digest = canonical_sdl_digest(admit_source(vector.input_source)).value
    if (
        report.operation_profile != vector.operation.profile
        or report.source_digest != source_digest
        or report.target_digest != artifact_digest
        or report.source_profile != "sdl-authoring-input/v1"
        or report.target_profile != "sdl-authoring-input/v1"
        or report.canonicalization_profile != "raes-sdl-semantic/v2"
        or (report.status == "success") != (artifact_digest is not None)
    ):
        raise EvidenceIntegrityError("transformation evidence does not bind this operation and its artifacts")


def _require_pre_operation_refusal(source: str, artifact: Scenario | None) -> None:
    """Absent provenance is valid only when strict source admission prevented execution."""
    if artifact is None:
        try:
            admit_source(source)
        except SDLParseError as exc:
            if exc.diagnostics:
                return
    raise InvalidInputError("an admitted transformation operation requires its owning report")


def reference_authoring_output(vector: AuthoringAdapterVectorModel) -> AuthoringPathOutput:
    """Exercise the production operation; this is not the vector's expected oracle."""
    try:
        source = admit_source(vector.input_source)
    except SDLParseError as exc:
        if not exc.diagnostics:
            raise InvalidInputError("this profile requires structured parser rejection evidence") from exc
        return AuthoringPathOutput(vector.input_source, None, exc.diagnostics)
    if vector.operation.profile == _VALIDATE_PROFILE:
        return AuthoringPathOutput(vector.input_source, render_sdl_source(source).content)
    result = rename_sdl_declaration(
        source,
        RenameSDLDeclarationRequest(
            target_address=vector.operation.target_address,
            new_local_name=vector.operation.new_local_name,
        ),
    )
    content = render_sdl_source(result.output).content if result.output is not None else None
    return AuthoringPathOutput(vector.input_source, content, result.report.diagnostics, result.report)
