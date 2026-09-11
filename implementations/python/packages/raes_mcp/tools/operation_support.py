"""Support helpers for RAES MCP operation tools."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

_MAX_INPUT_BYTES = 64 * 1024

_SECTION_FIELDS = [
    "nodes",
    "infrastructure",
    "features",
    "conditions",
    "entities",
    "injects",
    "events",
    "scripts",
    "stories",
    "content",
    "accounts",
    "relationships",
    "agents",
    "action_contracts",
    "observation_boundaries",
    "outcome_interpretation_rules",
    "objectives",
    "workflows",
]


def compile_pipeline(
    sdl_content: str,
    parameters_json: str,
    *,
    accept_migration_syntax: bool = False,
) -> dict[str, Any]:
    size_error = size_error_payload(sdl_content, parameters_json)
    if size_error is not None:
        return {"error": json.loads(size_error), "stages": [], "scenario": None, "model": None}

    from raes import (
        SDLInstantiationError,
        SDLMigrationPolicy,
        SDLParseError,
        SDLValidationError,
        instantiate_scenario,
        parse_sdl,
    )
    from raes_processor.compiler import compile_runtime_model

    params, parameter_error = parse_parameters(parameters_json)
    if parameter_error is not None:
        return {"error": parameter_error, "stages": [], "scenario": None, "model": None}

    stages: list[dict[str, str]] = []
    try:
        scenario = parse_sdl(
            sdl_content,
            migration_policy=(SDLMigrationPolicy.ACCEPT if accept_migration_syntax else SDLMigrationPolicy.REJECT),
        )
    except SDLParseError as exc:
        return {"error": stage_error("parse", exc), "stages": stages, "scenario": None, "model": None}
    except SDLValidationError as exc:
        return {
            "error": {
                "status": "invalid",
                "stage": "semantic_validation",
                "diagnostics": text_diagnostics("semantic_validation", exc.errors),
            },
            "stages": stages,
            "scenario": None,
            "model": None,
        }
    stages.extend([stage_ok("parse"), stage_ok("semantic_validation")])

    try:
        concrete = instantiate_scenario(scenario, parameters=params)
    except SDLInstantiationError as exc:
        return {
            "error": {
                "status": "invalid",
                "stage": "instantiation",
                "diagnostics": text_diagnostics("instantiation", exc.errors),
            },
            "stages": stages,
            "scenario": scenario,
            "model": None,
        }
    stages.append(stage_ok("instantiation"))

    model = compile_runtime_model(concrete)
    stages.append(stage_ok("compilation"))
    return {
        "error": None,
        "stages": stages,
        "scenario": concrete,
        "model": model,
        "source_diagnostics": [item.as_dict() for item in scenario.source_diagnostics],
        "instantiation": {
            "binding_count": len(concrete.instantiation_provenance.bindings)
            + sum(len(item.bindings) for item in concrete.instantiation_provenance.imports),
            "import_count": len(concrete.instantiation_provenance.imports),
            "profile": concrete.instantiation_provenance.selected_profile,
        },
    }


def parse_parameters(parameters_json: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        parsed = json.loads(parameters_json)
    except json.JSONDecodeError as exc:
        return (
            {},
            {
                "status": "invalid",
                "stage": "parameter_parsing",
                "diagnostics": text_diagnostics("parameter_parsing", [f"Invalid JSON in parameters_json: {exc}"]),
            },
        )
    if not isinstance(parsed, dict):
        return (
            {},
            {
                "status": "invalid",
                "stage": "parameter_parsing",
                "diagnostics": text_diagnostics("parameter_parsing", ["parameters_json must be a JSON object."]),
            },
        )
    return parsed, None


def json_response(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def size_error_payload(*values: str) -> str | None:
    size = sum(len(value.encode("utf-8", errors="replace")) for value in values)
    if size <= _MAX_INPUT_BYTES:
        return None
    return json_response(
        {
            "status": "invalid",
            "stage": "input",
            "diagnostics": text_diagnostics("input", [f"INPUT TOO LARGE - limit is {_MAX_INPUT_BYTES} bytes."]),
        }
    )


def stage_ok(stage: str, *, detail: str = "ok") -> dict[str, str]:
    return {"stage": stage, "status": "ok", "detail": detail}


def stage_error(stage: str, error: object) -> dict[str, Any]:
    structured = getattr(error, "diagnostics", ())
    if structured:
        return {
            "status": "invalid",
            "stage": stage,
            "diagnostics": [item.as_dict() for item in structured],
        }
    message = getattr(error, "details", str(error))
    return {
        "status": "invalid",
        "stage": stage,
        "diagnostics": text_diagnostics(stage, [message]),
    }


def text_diagnostics(stage: str, messages: list[str], *, severity: str = "error") -> list[dict[str, str]]:
    return [
        {
            "stage": stage,
            "severity": severity,
            "message": message,
        }
        for message in messages
    ]


def diagnostics(diagnostics: list[Any], *, stage: str) -> list[dict[str, str]]:
    rendered: list[dict[str, str]] = []
    for diagnostic in diagnostics:
        severity = getattr(diagnostic, "severity", "error")
        severity_value = getattr(severity, "value", str(severity))
        rendered.append(
            {
                "stage": stage,
                "severity": severity_value,
                "code": getattr(diagnostic, "code", ""),
                "domain": getattr(diagnostic, "domain", ""),
                "address": getattr(diagnostic, "address", ""),
                "message": getattr(diagnostic, "message", str(diagnostic)),
            }
        )
    return rendered


def has_errors(diagnostics: list[Any]) -> bool:
    return any(bool(getattr(diagnostic, "is_error", True)) for diagnostic in diagnostics)


def section_counts(scenario: object) -> dict[str, int]:
    return {field: len(data) for field in _SECTION_FIELDS if (data := getattr(scenario, field, None))}


def runtime_model_summary(model: Any) -> dict[str, Any]:
    return {
        "templates": {
            "features": len(model.feature_templates),
            "conditions": len(model.condition_templates),
            "injects": len(model.inject_templates),
        },
        "metadata": {
            "entities": len(model.entity_specs),
            "agents": len(model.agent_specs),
            "relationships": len(model.relationship_specs),
            "capability_constraints": len(model.capability_constraints),
        },
        "domains": {
            "provisioning": {
                "networks": len(model.networks),
                "nodes": len(model.node_deployments),
                "feature_bindings": len(model.feature_bindings),
                "content_placements": len(model.content_placements),
                "account_placements": len(model.account_placements),
            },
            "orchestration": {
                "injects": len(model.injects),
                "inject_bindings": len(model.inject_bindings),
                "events": len(model.events),
                "scripts": len(model.scripts),
                "stories": len(model.stories),
                "workflows": len(model.workflows),
            },
            "evaluation": {
                "condition_bindings": len(model.condition_bindings),
                "objectives": len(model.objectives),
            },
            "participant": {
                "action_contracts": len(model.action_contracts),
                "observation_boundaries": len(model.observation_boundaries),
                "outcome_interpretation_rules": len(model.outcome_interpretation_rules),
                "participant_behaviors": len(model.participant_behaviors),
            },
        },
        "diagnostic_count": len(model.diagnostics),
    }


def execution_plan_summary(execution_plan: Any) -> dict[str, Any]:
    return {
        "is_valid": execution_plan.is_valid,
        "resources": {
            "provisioning": len(execution_plan.provisioning.resources),
            "orchestration": len(execution_plan.orchestration.resources),
            "evaluation": len(execution_plan.evaluation.resources),
        },
        "operations": {
            "provisioning": operation_counts(execution_plan.provisioning.operations),
            "orchestration": operation_counts(execution_plan.orchestration.operations),
            "evaluation": operation_counts(execution_plan.evaluation.operations),
        },
        "startup_order": {
            "orchestration": list(execution_plan.orchestration.startup_order),
            "evaluation": list(execution_plan.evaluation.startup_order),
        },
        "diagnostic_count": len(execution_plan.diagnostics),
    }


def operation_counts(operations: list[Any]) -> dict[str, int]:
    return dict(
        sorted(Counter(str(op.action.value if hasattr(op.action, "value") else op.action) for op in operations).items())
    )


def manifest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    capabilities = payload.get("capabilities") or {}
    return {
        "identity": payload.get("identity"),
        "supported_contract_versions": payload.get("supported_contract_versions") or [],
        "compatibility": payload.get("compatibility") or {},
        "capability_sections": sorted(capabilities),
        "realization_support": payload.get("realization_support") or [],
        "concept_bindings": payload.get("concept_bindings") or [],
    }


def design_notes(scenario: Any, model: Any, execution_plan: Any) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    if not scenario.objectives:
        notes.append(
            note(
                "objectives",
                "warning",
                "No objectives are authored; range intent and success criteria may be hard to assess.",
            )
        )
    if scenario.objectives and not any(objective.success.assertions for objective in scenario.objectives.values()):
        notes.append(
            note(
                "assessment",
                "warning",
                "Objectives exist without any backend-neutral success assertions; objective truth is under-specified.",
            )
        )
    if scenario.agents and not scenario.action_contracts:
        notes.append(
            note(
                "participant_actions",
                "warning",
                "Agents declare action names without action contracts; do not treat action names as behavior semantics.",
            )
        )
    if scenario.agents and not scenario.observation_boundaries:
        notes.append(
            note(
                "participant_visibility",
                "warning",
                "Agents are present without observation boundaries; participant-visible state claims are limited.",
            )
        )
    if scenario.workflows and not execution_plan.orchestration.startup_order:
        notes.append(
            note(
                "workflow",
                "info",
                "Workflows are authored; inspect planning diagnostics if no orchestration startup order is emitted.",
            )
        )
    if model.action_contracts and model.observation_boundaries:
        notes.append(
            note(
                "participant_semantics",
                "info",
                "Participant action and observation contract surfaces are present for semantic review.",
            )
        )
    if execution_plan.is_valid:
        notes.append(
            note(
                "planning",
                "info",
                "The scenario plans against the reference backend manifest; live execution still requires a concrete target and run evidence.",
            )
        )
    return notes


def claim_assessment(scenario: Any, model: Any, execution_plan: Any) -> dict[str, list[dict[str, str]]]:
    supported = [
        claim(
            "authoring-syntax", "SDL YAML parses into the closed RAES SDL model.", "parse_sdl completed successfully."
        ),
        claim(
            "semantic-validation",
            "Static SDL semantic validation passed.",
            "parse_sdl completed with semantic validation enabled.",
        ),
        claim(
            "instantiation",
            "Variables/defaults can be resolved into a concrete scenario.",
            "instantiate_scenario completed successfully.",
        ),
        claim(
            "runtime-compilation",
            "The scenario can be compiled into the RAES runtime model.",
            "compile_runtime_model completed successfully.",
        ),
    ]
    conditional = [
        claim(
            "reference-planning",
            "The scenario can be planned against the reference stub backend manifest.",
            "sdl_plan dry-run is valid."
            if execution_plan.is_valid
            else "Planning produced diagnostics that must be resolved.",
        )
    ]
    unsupported = [
        claim(
            "live-execution",
            "The scenario has run successfully in a real range.",
            "Requires control-plane operation results, runtime snapshots, and backend provenance.",
        ),
        claim(
            "causal-attribution",
            "A participant action caused a detection, state change, or outcome.",
            "Requires evidence-labeled attribution, ordering support, observation support, and run evidence.",
        ),
        claim(
            "participant-skill",
            "A participant or agent demonstrated portable cyber skill.",
            "Requires participant action/observation contracts, scaffold disclosure, trajectory/history, and evaluation evidence.",
        ),
    ]

    unsupported.append(
        claim(
            "assessment-result",
            "The scenario supports scoring or assessment-result claims.",
            "Per ADR-073 the SDL no longer authors scoring/reward surfaces; graded scoring and "
            "evaluation results live in the experiment/evaluator plane (ADR-055/064/069).",
        )
    )

    if model.action_contracts and model.observation_boundaries and model.participant_behaviors:
        supported.append(
            claim(
                "participant-contract-review",
                "Participant actions and observations can be reviewed as semantic contracts.",
                "Action contracts, observation boundaries, and participant behavior bindings are compiled.",
            )
        )
    elif scenario.agents:
        conditional.append(
            claim(
                "participant-behavior",
                "Participant behavior can be interpreted beyond authored action names.",
                "Agents are present, but action contracts, observation boundaries, or participant behavior bindings are incomplete.",
            )
        )

    if model.outcome_interpretation_rules:
        conditional.append(
            claim(
                "outcome-interpretation",
                "Participant-local outcomes can be mapped into scenario/evaluation/evidence layers.",
                "Outcome interpretation rules are present; run evidence is still required for realized outcomes.",
            )
        )

    return {
        "supported": supported,
        "conditional": conditional,
        "unsupported_without_more_evidence": unsupported,
        "missing_evidence_for_stronger_claims": [
            claim(
                "backend-provenance",
                "Concrete backend identity, manifest, realization support, and runtime result envelopes.",
                "Needed for live execution and backend compatibility claims beyond the reference dry run.",
            ),
            claim(
                "participant-history",
                "Participant episode history, behavior history, observations, and scaffold exposure record.",
                "Needed for participant behavior, visibility, and skill claims.",
            ),
            claim(
                "evidence-record",
                "Observation/evidence references with capture basis, loss/redaction, ordering, and observer effects.",
                "Needed for defensible outcome and causality claims.",
            ),
        ],
    }


def note(topic: str, severity: str, message: str) -> dict[str, str]:
    return {"topic": topic, "severity": severity, "message": message}


def claim(identifier: str, claim_text: str, basis: str) -> dict[str, str]:
    return {"id": identifier, "claim": claim_text, "basis": basis}
