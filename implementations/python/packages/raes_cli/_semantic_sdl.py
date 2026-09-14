"""SDL phase adapters for the semantic CLI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from raes import (
    SDL_SOURCE_FORMAT,
    Scenario,
    SDLError,
    SDLInstantiationError,
    SDLMigrationPolicy,
    SDLParseError,
    SDLValidationError,
    build_declaration_index,
    canonical_sdl_bytes,
    canonical_sdl_digest,
    format_sdl_source,
    parse_sdl,
)
from raes_processor.compiler import compile_scenario_runtime_model
from raes_processor.models import RuntimeModel

from ._semantic_result import (
    CommandDiagnostic,
    CommandStatus,
    ResultMetadata,
    SemanticCommandResult,
    command_diagnostic,
    command_result,
)


class TransformProfile(str, Enum):
    """Closed transformations owned by the RAES semantic layer."""

    CANONICAL = "canonical"
    FORMAT = "format"


@dataclass(frozen=True)
class _SdlContext:
    operation: str
    text: str
    scenario: Scenario
    advisories: tuple[CommandDiagnostic, ...]
    migration_policy: SDLMigrationPolicy
    transform: TransformProfile | None


def _metadata(
    context: _SdlContext,
    *,
    validation_strength: str | None = None,
    processor_profile: str | None = None,
    transform_profile: str | None = None,
) -> ResultMetadata:
    return ResultMetadata(
        migration_policy=context.migration_policy,
        validation_strength=validation_strength,
        processor_profile=processor_profile,
        transform_profile=transform_profile,
    )


def _sdl_diagnostics(exc: SDLError) -> tuple[CommandDiagnostic, ...]:
    if isinstance(exc, SDLParseError) and exc.diagnostics:
        diagnostics = tuple(
            command_diagnostic(
                diagnostic.code,
                "sdl-parse",
                "SDL input was rejected at the parse stage.",
                address=diagnostic.pointer,
                severity=diagnostic.severity,
            )
            for diagnostic in exc.diagnostics[:20]
        )
    elif isinstance(exc, SDLParseError):
        diagnostics = (
            command_diagnostic(
                "sdl.parse",
                "sdl-parse",
                "SDL input was rejected at the parse stage.",
            ),
        )
    elif isinstance(exc, SDLValidationError):
        diagnostics = (
            command_diagnostic(
                "sdl.validation",
                "sdl-validation",
                f"SDL semantic validation reported {len(exc.errors)} error(s).",
            ),
        )
    elif isinstance(exc, SDLInstantiationError):
        diagnostics = (
            command_diagnostic(
                "sdl.instantiation",
                "sdl-instantiation",
                f"SDL instantiation reported {len(exc.errors)} error(s).",
            ),
        )
    else:
        diagnostics = (
            command_diagnostic(
                "sdl.invalid",
                "sdl",
                "SDL input was rejected.",
            ),
        )
    return diagnostics


def _parse_sdl_input(
    raw: bytes,
    *,
    semantic_validation: bool,
    migration_policy: SDLMigrationPolicy,
) -> tuple[str, Scenario]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SDLParseError("SDL source must be valid UTF-8.") from exc
    scenario = parse_sdl(
        text,
        skip_semantic_validation=not semantic_validation,
        source_format=SDL_SOURCE_FORMAT,
        migration_policy=migration_policy,
    )
    return text, scenario


def _build_context(
    operation: str,
    raw: bytes,
    migration_policy: SDLMigrationPolicy,
    transform: TransformProfile | None,
) -> _SdlContext:
    text, scenario = _parse_sdl_input(
        raw,
        semantic_validation=operation != "parse",
        migration_policy=migration_policy,
    )
    advisories = tuple(
        command_diagnostic(
            diagnostic.code,
            "sdl-parse",
            diagnostic.message,
            address=diagnostic.pointer,
            severity=diagnostic.severity,
        )
        for diagnostic in scenario.source_diagnostics
    )
    return _SdlContext(
        operation=operation,
        text=text,
        scenario=scenario,
        advisories=advisories,
        migration_policy=migration_policy,
        transform=transform,
    )


def _scenario_summary(scenario: Scenario, *, phase: str) -> dict[str, object]:
    fields = scenario.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return {
        "phase": phase,
        "root_type": "object",
        "scenario_name": scenario.name,
        "field_count": len(fields),
        "semantic_validated": scenario.semantic_validated,
    }


def _inspection_payload(scenario: Scenario) -> dict[str, object]:
    index = build_declaration_index(scenario)
    declarations = [
        {
            "address": declaration.address,
            "kind": declaration.kind,
            "model_path": declaration.model_path,
            "referenceable": declaration.referenceable,
            "targetable": declaration.targetable,
        }
        for declaration in index.declarations
    ]
    return {
        "phase": "inspection",
        "root_type": "object",
        "scenario_name": scenario.name,
        "declaration_count": len(declarations),
        "declarations": declarations,
        "semantic_axes": _semantic_axes(scenario),
    }


def _semantic_axes(scenario: Scenario) -> dict[str, object]:
    """Present authoring planes without inventing implementation or evidence."""
    metadata = {
        "name",
        "version",
        "description",
        "semantic_revision",
        "module",
        "imports",
        "realization",
        "evidence_requirements",
    }
    delegation = (
        scenario.realization.model_dump(mode="json", exclude_unset=True) if scenario.realization is not None else {}
    )
    delegation["omission_policy"] = (
        "inherit-selected-scope" if scenario.realization is not None else "legacy-closed-default"
    )
    return {
        "constraints": {"authored_sections": sorted(scenario.model_fields_set - metadata)},
        "delegation": delegation,
        "observation": {
            name: (
                requirement.observation_demand.model_dump(mode="json", exclude_unset=True)
                if requirement.observation_demand is not None
                else {"source": "legacy-evidence-requirement"}
            )
            for name, requirement in sorted(scenario.evidence_requirements.items())
        },
    }


def _resolution_payload(scenario: Scenario) -> dict[str, object]:
    aliases = build_declaration_index(scenario).reference_aliases()
    return {
        "phase": "resolved-references",
        "root_type": "object",
        "scenario_name": scenario.name,
        "reference_binding_count": len(aliases),
        "reference_bindings": {alias: sorted(addresses) for alias, addresses in sorted(aliases.items())},
    }


def _runtime_summary(runtime_model: RuntimeModel) -> dict[str, object]:
    return {
        "phase": "compiled-runtime-summary",
        "root_type": "object",
        "scenario_name": runtime_model.scenario_name,
        "resource_counts": {
            "networks": len(runtime_model.networks),
            "node_deployments": len(runtime_model.node_deployments),
            "feature_bindings": len(runtime_model.feature_bindings),
            "propositions": len(runtime_model.propositions),
            "assertions": len(runtime_model.assertions),
            "injects": len(runtime_model.injects),
            "events": len(runtime_model.events),
            "scripts": len(runtime_model.scripts),
            "stories": len(runtime_model.stories),
            "workflows": len(runtime_model.workflows),
            "objectives": len(runtime_model.objectives),
        },
        "diagnostic_count": len(runtime_model.diagnostics),
    }


def _execute_admission(context: _SdlContext) -> SemanticCommandResult:
    is_parse = context.operation == "parse"
    return command_result(
        context.operation,
        contract_id=SDL_SOURCE_FORMAT,
        payload=_scenario_summary(
            context.scenario,
            phase="parsed-authoring" if is_parse else "validated-authoring",
        ),
        diagnostics=context.advisories,
        metadata=_metadata(
            context,
            validation_strength="structural" if is_parse else "semantic",
        ),
    )


def _execute_normalize(context: _SdlContext) -> SemanticCommandResult:
    formatted = format_sdl_source(context.text)
    return command_result(
        context.operation,
        contract_id=SDL_SOURCE_FORMAT,
        payload={
            **_scenario_summary(
                context.scenario,
                phase="normalized-authoring",
            ),
            "content": formatted.content,
            "digest": canonical_sdl_digest(context.scenario).as_dict(),
        },
        diagnostics=context.advisories,
        metadata=_metadata(context, validation_strength="semantic"),
    )


def _execute_resolve(context: _SdlContext) -> SemanticCommandResult:
    return command_result(
        context.operation,
        contract_id=SDL_SOURCE_FORMAT,
        payload=_resolution_payload(context.scenario),
        diagnostics=context.advisories,
        metadata=_metadata(context, validation_strength="semantic"),
    )


def _execute_compile(context: _SdlContext) -> SemanticCommandResult:
    runtime_model = compile_scenario_runtime_model(context.scenario)
    compiler_diagnostics = tuple(
        command_diagnostic(
            item.code,
            item.domain,
            "The compiler reported a diagnostic.",
            address=item.address,
            severity=item.severity.value,
        )
        for item in runtime_model.diagnostics
    )
    return command_result(
        context.operation,
        contract_id=SDL_SOURCE_FORMAT,
        payload=_runtime_summary(runtime_model),
        diagnostics=(*context.advisories, *compiler_diagnostics),
        metadata=_metadata(
            context,
            validation_strength="semantic",
            processor_profile="raes-compiler/default",
        ),
    )


def _execute_transform(context: _SdlContext) -> SemanticCommandResult:
    selected = context.transform or TransformProfile.CANONICAL
    digest: dict[str, str] | None = None
    if selected is TransformProfile.FORMAT:
        content = format_sdl_source(context.text).content
    else:
        content = canonical_sdl_bytes(context.scenario).decode("utf-8")
        digest = canonical_sdl_digest(context.scenario).as_dict()
    payload: dict[str, object] = {
        "phase": "transformed",
        "root_type": "object",
        "content": content,
    }
    if digest is not None:
        payload["digest"] = digest
    return command_result(
        context.operation,
        contract_id=SDL_SOURCE_FORMAT,
        payload=payload,
        diagnostics=context.advisories,
        metadata=_metadata(
            context,
            validation_strength="semantic",
            transform_profile=selected.value,
        ),
    )


def _execute_inspect(context: _SdlContext) -> SemanticCommandResult:
    return command_result(
        context.operation,
        contract_id=SDL_SOURCE_FORMAT,
        payload=_inspection_payload(context.scenario),
        diagnostics=context.advisories,
        metadata=_metadata(context, validation_strength="semantic"),
    )


_SDL_HANDLERS: dict[
    str,
    Callable[[_SdlContext], SemanticCommandResult],
] = {
    "parse": _execute_admission,
    "validate": _execute_admission,
    "normalize": _execute_normalize,
    "resolve": _execute_resolve,
    "compile": _execute_compile,
    "transform": _execute_transform,
    "inspect": _execute_inspect,
}


def execute_sdl(
    operation: str,
    raw: bytes,
    *,
    migration_policy: SDLMigrationPolicy,
    transform: TransformProfile | None,
) -> SemanticCommandResult:
    """Dispatch one SDL artifact to its owning semantic phase."""

    if operation == "conformance":
        result = command_result(
            operation,
            status=CommandStatus.UNSUPPORTED,
            contract_id=SDL_SOURCE_FORMAT,
            metadata=ResultMetadata(migration_policy=migration_policy),
        )
    else:
        try:
            context = _build_context(
                operation,
                raw,
                migration_policy,
                transform,
            )
        except SDLError as exc:
            result = command_result(
                operation,
                status=CommandStatus.INVALID,
                contract_id=SDL_SOURCE_FORMAT,
                diagnostics=_sdl_diagnostics(exc),
                metadata=ResultMetadata(migration_policy=migration_policy),
            )
        else:
            handler = _SDL_HANDLERS.get(operation)
            if handler is None:
                result = command_result(
                    operation,
                    status=CommandStatus.INTERNAL,
                    contract_id=SDL_SOURCE_FORMAT,
                    diagnostics=(
                        command_diagnostic(
                            "cli.internal",
                            "cli",
                            "The semantic operation did not produce a result.",
                        ),
                    ),
                    metadata=ResultMetadata(
                        migration_policy=migration_policy,
                    ),
                )
            else:
                result = handler(context)
    return result
