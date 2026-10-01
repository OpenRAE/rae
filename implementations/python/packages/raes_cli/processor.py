"""Processor declaration and plan-inspection commands."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError
from raes import SDLError, SDLInstantiationError, SDLParseError, SDLValidationError
from raes_backend_protocols.manifest import (
    BackendManifest,
    BackendManifestEnvelopeUnsupportedError,
    backend_manifest_from_v2_model,
)
from raes_backend_stubs.manifest import create_stub_manifest
from raes_contracts.account_credentials import (
    account_placement_has_credential_bindings,
    value_free_account_placement_payload,
)
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.diagnostics import diagnostic_payload
from raes_contracts.plan_projection import (
    evaluation_plan_model,
    orchestration_plan_model,
    provisioning_plan_model,
)
from raes_contracts.planning import ChangeAction
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.exploit_path import (
    ANALYSIS_PROFILE as EXPLOIT_PATH_ANALYSIS_PROFILE,
)
from raes_processor.exploit_path import (
    ExploitPathOperationalError,
    analyze_exploit_path_file,
)
from raes_processor.manifest import reference_processor_manifest_payload
from raes_processor.models import ExecutionPlan
from raes_processor.reconciliation_demonstration import (
    PLANNED_STATE_PROJECTION,
    ReconciliationDemonstration,
    ReconciliationStatus,
    ScenarioVersion,
    ScenarioVersionRejected,
    reconcile_scenario_versions,
)
from raes_processor.reference import run_reference_processor
from raes_processor.satisfiability import (
    ANALYSIS_PROFILE,
    SatisfiabilityOperationalError,
    analyze_scenario_file,
)

app = typer.Typer(help="Processor declarations and compatibility surfaces.")

# Backend-manifest JSON is small; bound the read before decoding untrusted input.
_MANIFEST_MAX_BYTES = 1 * 1024 * 1024


class PlanOutputFormat(str, Enum):
    """Serialization format for the compiled plan."""

    JSON = "json"


@app.command("manifest")
def manifest() -> None:
    """Print the reference processor manifest."""

    typer.echo(json.dumps(reference_processor_manifest_payload(), indent=2, sort_keys=True))


def _manifest_validation_summary(error: ValidationError) -> str:
    # Report field paths and error kinds only -- never the offending input values.
    locations = "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or '<root>'}: {item['type']}" for item in error.errors()[:5]
    )
    return f"manifest is not a valid backend-manifest-v2: {locations}"


def _sdl_error_summary(source: Path, exc: SDLError) -> str:
    """Render a stable, sanitized SDL compilation-failure line for stderr.

    Emits only the failure kind plus safe metadata -- diagnostic codes and
    1-based line:column positions for parse failures, error counts otherwise --
    never the exception's message text, source snippets, or rejected authored
    values, which can carry untrusted SDL content or terminal control sequences.
    """

    if isinstance(exc, SDLParseError) and exc.diagnostics:
        markers = ", ".join(
            f"{diagnostic.code}@{diagnostic.primary_range.start.line}:{diagnostic.primary_range.start.column}"
            for diagnostic in exc.diagnostics[:10]
        )
        detail = f"SDL parse failed [{markers}]"
    elif isinstance(exc, SDLValidationError):
        count = len(exc.errors)
        detail = f"{count} SDL validation error{'s' if count != 1 else ''}"
    elif isinstance(exc, SDLInstantiationError):
        count = len(exc.errors)
        detail = f"{count} SDL instantiation error{'s' if count != 1 else ''}"
    else:
        detail = f"SDL compilation failed ({type(exc).__name__})"
    return f"error: could not compile {source}: {detail}"


def _load_backend_manifest(manifest_path: Path | None) -> BackendManifest:
    """Resolve the backend manifest the plan targets.

    Defaults to the reference stub dry-run manifest -- the same target the MCP
    ``sdl_plan`` surface uses, a convenience planning target rather than evidence
    a backend ran. A supplied ``--manifest`` is size-bounded, read as UTF-8 JSON,
    validated against the published ``backend-manifest-v2`` model, then adapted to
    the internal manifest (which re-runs the capability validators). It fails
    closed on realization-envelope-bearing manifests, which a v2 payload cannot
    fully carry.
    """

    if manifest_path is None:
        return create_stub_manifest()
    if manifest_path.stat().st_size > _MANIFEST_MAX_BYTES:
        raise typer.BadParameter(f"manifest exceeds the {_MANIFEST_MAX_BYTES}-byte limit")
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise typer.BadParameter("manifest must be UTF-8 encoded JSON") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"manifest is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter("manifest must be a JSON object")
    try:
        model = BackendManifestV2Model.model_validate(payload)
    except ValidationError as exc:
        raise typer.BadParameter(_manifest_validation_summary(exc)) from exc
    try:
        return backend_manifest_from_v2_model(model)
    except BackendManifestEnvelopeUnsupportedError as exc:
        raise typer.BadParameter(
            "manifest declares a realization envelope the plan CLI cannot resolve; "
            "supply an envelope-free manifest or omit --manifest"
        ) from exc
    except ValueError as exc:
        # Deeper backend-capability validators can interpolate rejected manifest
        # values into their messages; render a stable, input-free message.
        raise typer.BadParameter("manifest was rejected by backend capability validation") from exc


def _execution_plan_payload(execution_plan: ExecutionPlan) -> dict[str, Any]:
    payload = {
        "scenario_name": execution_plan.scenario_name,
        "provisioning": provisioning_plan_model(execution_plan.provisioning).model_dump(mode="json"),
        "orchestration": orchestration_plan_model(execution_plan.orchestration).model_dump(mode="json"),
        "evaluation": evaluation_plan_model(execution_plan.evaluation).model_dump(mode="json"),
        "diagnostics": [diagnostic_payload(diagnostic) for diagnostic in execution_plan.diagnostics],
    }
    for operation in payload["provisioning"]["operations"]:
        if operation["resource_type"] != "account-placement":
            continue
        operation_payload = operation["payload"]
        if account_placement_has_credential_bindings(operation_payload):
            operation["payload"] = value_free_account_placement_payload(operation_payload)
    return payload


@app.command("plan")
def plan(
    sdl: Path = typer.Argument(..., exists=True, readable=True, help="SDL scenario file to compile and plan."),
    manifest_path: Path | None = typer.Option(
        None,
        "--manifest",
        exists=True,
        readable=True,
        help="Backend-manifest-v2 JSON to plan against (defaults to the reference dry-run manifest).",
    ),
    output_format: PlanOutputFormat = typer.Option(
        ...,
        "--format",
        help="Output format for the compiled plan.",
    ),
) -> None:
    """Compile an SDL scenario and emit its execution plan as published-contract JSON.

    Plans against the reference dry-run manifest by default; ``--manifest`` targets
    an explicitly supplied backend-manifest-v2. stdout is a single JSON envelope
    whose ``provisioning`` / ``orchestration`` / ``evaluation`` members each
    validate against the published plan contracts. A plan produced with error
    diagnostics is still emitted in full, with a non-zero exit status. This is a
    read-only dry run: it does not apply, provision, or start anything.
    """

    # Only JSON is supported today; the enum reserves the seam for future formats.
    del output_format
    backend_manifest = _load_backend_manifest(manifest_path)
    try:
        result = run_reference_processor(sdl, backend_manifest)
    except SDLError as exc:
        typer.echo(_sdl_error_summary(sdl, exc), err=True)
        raise typer.Exit(code=1) from exc

    payload = _execution_plan_payload(result.execution_plan)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if not result.execution_plan.is_valid:
        raise typer.Exit(code=1)


def _snapshot_summary(snapshot: RuntimeSnapshot) -> dict[str, Any]:
    """Summarize projected state by identity and dependency, never by payload.

    Resource payloads carry authored credentials and content, and the
    reconciliation question is answered without them. Profile bindings are
    reported by binding id for the same reason -- a binding's ``value`` is
    arbitrary profile data.
    """

    entries = sorted(
        (
            {
                "address": entry.address,
                "domain": entry.domain.value,
                "resource_type": entry.resource_type,
                "ordering_dependencies": list(entry.ordering_dependencies),
                "refresh_dependencies": list(entry.refresh_dependencies),
                "profile_binding_ids": sorted(binding.binding_id for binding in entry.profile_bindings),
            }
            for entry in snapshot.entries.values()
        ),
        key=lambda entry: entry["address"],
    )
    return {"entry_count": len(entries), "entries": entries}


def _reconciliation_payload(demonstration: ReconciliationDemonstration) -> dict[str, Any]:
    baseline_snapshot = demonstration.baseline_snapshot
    counts = demonstration.action_counts
    candidate_rejected_before_planning = demonstration.status is ReconciliationStatus.BASELINE_REJECTED
    return {
        "status": demonstration.status.value,
        "snapshot_kind": PLANNED_STATE_PROJECTION,
        "baseline": {
            "scenario_name": demonstration.baseline_scenario_name,
            "diagnostics": [diagnostic_payload(diagnostic) for diagnostic in demonstration.baseline_diagnostics],
            "snapshot": None if baseline_snapshot is None else _snapshot_summary(baseline_snapshot),
        },
        "candidate": (
            None
            if candidate_rejected_before_planning
            else {
                "scenario_name": demonstration.candidate_scenario_name,
                "diagnostics": [diagnostic_payload(diagnostic) for diagnostic in demonstration.candidate_diagnostics],
            }
        ),
        # Null rather than four zeroes when nothing was reconciled, so a
        # rejected baseline cannot be misread as "no changes".
        "actions": None if counts is None else {action.value: counts[action] for action in ChangeAction},
        "operations": (
            None
            if demonstration.operations is None
            else [
                {
                    "domain": operation.domain.value,
                    "address": operation.address,
                    "resource_type": operation.resource_type,
                    "action": operation.action.value,
                }
                for operation in demonstration.operations
            ]
        ),
    }


@app.command("reconcile")
def reconcile(
    baseline: Path = typer.Argument(..., exists=True, readable=True, help="Baseline SDL scenario version."),
    candidate: Path = typer.Argument(..., exists=True, readable=True, help="Modified SDL scenario version."),
    manifest_path: Path | None = typer.Option(
        None,
        "--manifest",
        exists=True,
        readable=True,
        help="Backend-manifest-v2 JSON to plan both versions against (defaults to the reference dry-run manifest).",
    ),
    output_format: PlanOutputFormat = typer.Option(
        ...,
        "--format",
        help="Output format for the reconciliation report.",
    ),
) -> None:
    """Show how the planner reconciles one scenario version against another.

    Plans ``BASELINE``, projects its planned state into a synthetic snapshot,
    plans ``CANDIDATE`` against that snapshot, and reports every resulting
    ``create``/``update``/``delete``/``unchanged`` action. Both versions are
    planned against the same manifest, so the reported delta reflects the
    authored difference rather than a change of target.

    The projected snapshot is assumed state, not backend readback or proof of
    realization; the report summarizes resource identity and dependencies and
    deliberately omits resource payloads. This is a read-only dry run: it does
    not apply, provision, or start anything. A rejected version yields a
    non-zero exit status.
    """

    # Only JSON is supported today; the enum reserves the seam for future formats.
    del output_format
    backend_manifest = _load_backend_manifest(manifest_path)
    try:
        demonstration = reconcile_scenario_versions(baseline, candidate, backend_manifest)
    except ScenarioVersionRejected as exc:
        source = baseline if exc.version is ScenarioVersion.BASELINE else candidate
        typer.echo(_sdl_error_summary(source, exc.cause), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(_reconciliation_payload(demonstration), indent=2, sort_keys=True))
    if demonstration.status is not ReconciliationStatus.RECONCILED:
        raise typer.Exit(code=1)


@app.command("satisfiability")
def satisfiability(
    sdl: Path = typer.Argument(..., exists=True, readable=True, help="SDL scenario file to analyze."),
    profile: str = typer.Option(
        ANALYSIS_PROFILE,
        "--profile",
        help="Closed governed satisfiability-analysis profile.",
    ),
) -> None:
    """Emit replayable whole-scenario satisfiability evidence as JSON.

    Exit status 0 means satisfiable or unsatisfiable, 2 means the authored
    scenario uses a construct outside the selected theory, and 1 means the
    input or operational boundary failed. Unsupported is a typed, fail-closed
    analysis result rather than a satisfiability conclusion.
    """

    try:
        evidence = analyze_scenario_file(sdl, profile=profile)
    except SDLError as exc:
        typer.echo(
            f"error: satisfiability input was rejected ({type(exc).__name__})",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except SatisfiabilityOperationalError as exc:
        # The service deliberately exposes value-free operational messages.
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(evidence.model_dump(mode="json"), indent=2, sort_keys=True))
    if evidence.outcome.value == "unsupported":
        raise typer.Exit(code=2)


@app.command("exploit-path")
def exploit_path(
    input_json: Path = typer.Argument(..., exists=True, readable=True, help="Exploit-path analysis input JSON."),
    profile: str = typer.Option(
        EXPLOIT_PATH_ANALYSIS_PROFILE,
        "--profile",
        help="Closed governed exploit-path analysis profile.",
    ),
) -> None:
    """Emit replayable typed exploit-path analysis evidence as JSON.

    Exit status 0 means the supported query completed with a valid or invalid
    path result, 2 means typed unsupported input, and 1 means malformed input
    or operational failure.
    """

    try:
        evidence = analyze_exploit_path_file(input_json, profile=profile)
    except ExploitPathOperationalError as exc:
        typer.echo(f"error: exploit-path input was rejected ({exc})", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(evidence.model_dump(mode="json"), indent=2, sort_keys=True))
    if evidence.outcome.value == "unsupported":
        raise typer.Exit(code=2)
