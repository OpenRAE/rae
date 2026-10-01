"""Explicit, source-preserving adoption of participant relations (#1338)."""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import Field
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ArtifactTransformationPreservationModel, ArtifactTransformationReportModel

from ._base import SDLModel, is_variable_ref
from ._errors import SDLError
from ._source_profile import DEFAULT_PARSER_LIMITS, SDLParserLimits, SDLSourceParseOptions
from ._transformation_support import check, diagnostic
from ._transformation_types import SDLTransformationResult
from ._yaml_loader import load_sdl_yaml
from .canonical import canonical_sdl_digest
from .parser import parse_sdl
from .scenario import Scenario
from .semantic_revisions import source_byte_digest

PARTICIPANT_MIGRATION_PROFILE = "adopt-participant-identity/v1"


class ParticipantIdentityMigrationContext(SDLModel):
    """Exact source and owner-only (None) or explicit participant decisions.

    Keys are JSON pointers to legacy entity objectives, e.g. /objectives/goal.
    The context is an author decision, never inferred from affiliations.
    """

    source_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    entity_objectives: dict[str, str | None] = Field(default_factory=dict, max_length=10_000)


def _pointer(section: str, name: str) -> str:
    return f"/{section}/" + name.replace("~", "~0").replace("/", "~1")


def _legacy_objectives(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _pointer("objectives", name): objective
        for name, objective in payload.get("objectives", {}).items()
        if isinstance(objective, dict) and "entity" in objective
    }


def _migrate_agent(agent: dict[str, Any]) -> str | None:
    if {"affiliations", "role"}.intersection(agent):
        return "conflicting-fields"
    if not isinstance(agent["entity"], str) or not agent["entity"]:
        return "source-invalid"
    agent["affiliations"] = [agent.pop("entity")]
    return None


def _migrate_objective(objective: dict[str, Any], assignment: str | None) -> str | None:
    if {"owner", "assigned_participant"}.intersection(objective) or {"agent", "entity"}.issubset(objective):
        return "conflicting-fields"
    field = "agent" if "agent" in objective else "entity"
    value = objective.pop(field)
    if not isinstance(value, str) or not value:
        return "source-invalid"
    objective["assigned_participant" if field == "agent" else "owner"] = value
    if field == "entity" and assignment is not None:
        objective["assigned_participant"] = assignment
    return None


def _detach_declarations(payload: dict[str, Any]) -> None:
    # YAML aliases share Python objects; decisions belong to declaration keys,
    # not to alias identity. Detach each mapping before changing relation fields.
    for section in ("agents", "objectives"):
        payload[section] = {
            name: dict(value) if isinstance(value, dict) else value for name, value in payload.get(section, {}).items()
        }


def _migrate_relations(payload: dict[str, Any], decisions: dict[str, str | None]) -> tuple[str | None, str]:
    _detach_declarations(payload)
    for name, agent in payload.get("agents", {}).items():
        if not isinstance(agent, dict) or "entity" not in agent:
            continue
        if code := _migrate_agent(agent):
            return code, _pointer("agents", name)
    for name, objective in payload.get("objectives", {}).items():
        if not isinstance(objective, dict) or not {"agent", "entity"}.intersection(objective):
            continue
        pointer = _pointer("objectives", name)
        if code := _migrate_objective(objective, decisions.get(pointer)):
            return code, pointer
    _migrate_variation_slots(payload.get("variation_points", {}))
    return None, ""


def _migrate_variation_slots(points: dict[str, Any]) -> None:
    for point in points.values():
        if not isinstance(point, dict) or not isinstance(point.get("target"), dict):
            continue
        target = point["target"]
        if target.get("slot") == "objectives.agent":
            target["slot"] = "objectives.assigned_participant"
        elif target.get("slot") == "objectives.entity":
            target["slot"] = "objectives.owner"


def _unresolved_field(declaration: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = declaration.get(field)
        if any(is_variable_ref(item) for item in (value if isinstance(value, list) else [value])):
            return field
    return None


def _unresolved_relation_pointer(payload: dict[str, Any]) -> str | None:
    for section, fields in (
        ("agents", ("affiliations", "role", "actions")),
        ("objectives", ("owner", "assigned_participant", "actions")),
    ):
        for name, declaration in payload.get(section, {}).items():
            if isinstance(declaration, dict) and (field := _unresolved_field(declaration, fields)):
                return _pointer(section, name) + "/" + field
    return None


def _source_issue(payload: dict[str, Any]) -> tuple[str | None, str]:
    if payload.get("imports") or "materialization_provenance" in payload:
        return "source-unsupported", "/imports" if payload.get("imports") else "/materialization_provenance"
    if any(not isinstance(payload.get(section, {}), dict) for section in ("agents", "objectives", "variation_points")):
        return "source-invalid", ""
    return None, ""


def _decision_issue(
    payload: dict[str, Any], context: ParticipantIdentityMigrationContext | None, source_digest: str
) -> tuple[str | None, str]:
    if context is not None and context.source_digest != source_digest:
        return "source-mismatch", "/context/source_digest"
    decisions = context.entity_objectives if context else {}
    required = _legacy_objectives(payload)
    missing = required.keys() - decisions.keys()
    if missing:
        return "decision-required", min(missing)
    code = "decision-mismatch" if decisions.keys() - required.keys() else None
    return code, "/context/entity_objectives" if code else ""


def _adopt(
    payload: object, context: ParticipantIdentityMigrationContext | None, source_digest: str
) -> tuple[dict[str, Any] | None, str | None, str]:
    if not isinstance(payload, dict):
        return None, "source-invalid", ""
    code, pointer = _source_issue(payload)
    if code is None:
        code, pointer = _decision_issue(payload, context, source_digest)
    if code is None:
        code, pointer = _migrate_relations(payload, context.entity_objectives if context else {})
    if code is None and (unresolved_pointer := _unresolved_relation_pointer(payload)):
        code, pointer = "unresolved-reference", unresolved_pointer
    return payload if code is None else None, code, pointer


def migrate_participant_identity(
    content: str,
    *,
    context: ParticipantIdentityMigrationContext | None = None,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLTransformationResult:
    """Produce a new validated artifact or an atomic, bounded refusal.

    This reader supports pre-1338 authoring sources. Migrate imported modules
    independently and update their owning version/digest bindings explicitly.
    Historical compiled snapshots and runtime evidence are never rewritten.
    """
    digest = source_byte_digest(content)
    context_payload = context.model_dump(mode="json") if context else None
    policy_digest = canonical_json_digest(context_payload)
    output: Scenario | None = None
    pointer = ""
    code = None
    try:
        payload = load_sdl_yaml(content, source_options=SDLSourceParseOptions(limits=limits))
        payload, code, pointer = _adopt(payload, context, digest)
        if payload is not None:
            output = parse_sdl(yaml.safe_dump(payload, sort_keys=False), limits=limits)
    except (SDLError, ValueError, TypeError):
        code = "source-or-target-invalid"
    diagnostic_code = f"participant-migration.{code}" if code else None
    report = ArtifactTransformationReportModel(
        operation_profile=PARTICIPANT_MIGRATION_PROFILE,
        status="success" if output is not None else "refused",
        artifact_kind="sdl-authoring",
        source_profile="sdl-participant-relations/pre-1338",
        target_profile="sdl-authoring-input/v1",
        canonicalization_profile="participant-migration-digest-pair/v1",
        source_digest=digest,
        target_digest=canonical_sdl_digest(output).value if output is not None else None,
        policy_digest=policy_digest,
        derivation_digest=canonical_json_digest(
            {"operation": PARTICIPANT_MIGRATION_PROFILE, "source": digest, "policy": policy_digest}
        ),
        preconditions=(check("source-and-author-decisions", "passed" if output is not None else "failed"),),
        postconditions=(check("canonical-target-admitted", "passed"),) if output is not None else (),
        affected_identities=tuple(sorted(context.entity_objectives)) if context else (),
        preservation=ArtifactTransformationPreservationModel(
            profile="explicit-participant-relations/v1",
            outcome="not-applicable",
            limitations=(
                "Authored relation migration is not evidence of realized action or cross-version equivalence.",
            ),
        ),
        diagnostics=(
            diagnostic(
                diagnostic_code,
                "Participant migration refused; review source-bound decisions and "
                "docs/migration/participant-identity.md.",
                address=pointer,
            ),
        )
        if diagnostic_code
        else (),
    )
    return SDLTransformationResult(output, (), report)
