"""Explicit, source-preserving conversion of legacy mixed control to a rev1 finite script (#1363).

The converter accepts only source that passes legacy semantic validation and
converts only when every accepted legacy trace constraint is preserved. It
reports every applicable refusal with a JSON pointer and never emits partial
output; rev1 input comes back unchanged. Conversion to a reusable policy always
needs an author decision and is not offered.
"""

from __future__ import annotations

import re
from typing import Any

import yaml
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ArtifactTransformationPreservationModel, ArtifactTransformationReportModel

from ._errors import SDLError, SDLValidationError
from ._mapping_scopes import normalize_field_key
from ._source_profile import DEFAULT_PARSER_LIMITS, SDLParserLimits, SDLSourceParseOptions
from ._transformation_support import check, diagnostic
from ._transformation_types import SDLTransformationResult
from ._yaml_loader import load_sdl_yaml
from .canonical import canonical_sdl_digest
from .parser import parse_sdl
from .participant_behavior_specification import (
    MixedControlParticipantOperation,
    MixedControlTransitionKind,
    ParticipantBehaviorSpecification,
)
from .participant_mixed_control_policy import MIXED_CONTROL_POLICY_SEMANTICS
from .scenario import Scenario
from .semantic_revisions import source_byte_digest

MIXED_CONTROL_MIGRATION_PROFILE = "convert-mixed-control-finite-script/v1"
_SPECS = "behavior_specifications"
_MIXED_CONTROL = "mixed_control"
_TRANSITIONS = "transitions"
_INVALID = "source-or-target-invalid"
_HANDOFF = MixedControlTransitionKind.HANDOFF
_PROPOSAL_OUTSIDE_KIND_SET = frozenset(
    {MixedControlTransitionKind.INTERVENTION, MixedControlTransitionKind.HANDOFF, MixedControlTransitionKind.OVERRIDE}
)
_TRANSITION_ERROR_RE = re.compile(
    r"Behavior specification '([^']+)' mixed_control (transition|permitted transition) '([^']+)'"
)
_LIMITATIONS = (
    "Conversion preserves authored trace constraints; it is not evidence of an executed or equivalent runtime trace.",
    "Legacy proposal_revision values equal state revisions; converted proposals and decisions bind revision 1.",
)


def _pointer(*parts: str) -> str:
    return "".join("/" + part.replace("~", "~0").replace("/", "~1") for part in parts)


def _error_pointers(error: SDLValidationError) -> list[str]:
    """Point each failure at its source transition; converted edges keep the legacy transition ids."""

    pointers = []
    for message in error.errors:
        match = _TRANSITION_ERROR_RE.search(message)
        if match is None:
            pointers.append("")
            continue
        spec_name, _, transition_id = match.groups()
        pointers.append(_pointer(_SPECS, spec_name, _MIXED_CONTROL, _TRANSITIONS, transition_id))
    return pointers or [""]


def _controller(declaration: MixedControlParticipantOperation, state_ref: str) -> str:
    controller = declaration.controller_states[state_ref].controller_ref
    return declaration.participant_ref if controller == "self" else controller


def _transition_refusals(spec_name: str, declaration: MixedControlParticipantOperation) -> list[tuple[str, str]]:
    refusals: list[tuple[str, str]] = []
    established: set[tuple[str, int]] = set()
    for transition_id, transition in sorted(declaration.transitions.items(), key=lambda item: item[1].effective_order):
        pointer = _pointer(_SPECS, spec_name, _MIXED_CONTROL, _TRANSITIONS, transition_id)
        kind = MixedControlTransitionKind(transition.transition_kind)
        changes = _controller(declaration, transition.from_state_ref) != _controller(
            declaration, transition.to_state_ref
        )
        if kind is _HANDOFF and not changes:
            refusals.append(("handoff-without-controller-change", pointer))
        if kind is not _HANDOFF and changes:
            refusals.append(("controller-change-requires-handoff", pointer))
        if transition.proposal_ref is not None and kind in _PROPOSAL_OUTSIDE_KIND_SET:
            refusals.append(("proposal-target-outside-kind-set", pointer))
        if transition.completion_evidence_refs and kind is not _HANDOFF:
            refusals.append((_INVALID, pointer))
        node = (transition.from_state_ref, transition.expected_state_revision)
        if node in established:
            refusals.append(("branching-sequence", pointer))
        established.add(node)
    return refusals


def _delivery_refusals(
    spec_name: str,
    behavior_spec: ParticipantBehaviorSpecification,
    declaration: MixedControlParticipantOperation,
) -> list[tuple[str, str]]:
    refusals: list[tuple[str, str]] = []
    for binding_id, binding in sorted(behavior_spec.participant_inject_deliveries.items()):
        transition = declaration.transitions.get(binding.control_transition_ref or "")
        if transition is None:
            continue
        pointer = _pointer(_SPECS, spec_name, "participant_inject_deliveries", binding_id)
        refusals += [("order-time-mapping-required", pointer), ("policy-revision-conflated", pointer)]
        source = declaration.controller_states[transition.from_state_ref]
        destination = declaration.controller_states[transition.to_state_ref]
        if _controller(declaration, transition.from_state_ref) != _controller(
            declaration, transition.to_state_ref
        ) or set(source.scope_refs) != set(destination.scope_refs):
            refusals.append(("source-destination-authority-disagreement", pointer))
    return refusals


def _converted_policy(declaration: MixedControlParticipantOperation) -> dict[str, Any]:
    edges: dict[str, dict[str, Any]] = {}
    steps: list[dict[str, Any]] = []
    for transition_id, transition in sorted(declaration.transitions.items(), key=lambda item: item[1].effective_order):
        kind = MixedControlTransitionKind(transition.transition_kind)
        edge: dict[str, Any] = {
            "transition_kind": kind.value,
            "from_state_ref": transition.from_state_ref,
            "to_state_ref": transition.to_state_ref,
            "valid_from_order": transition.valid_from_order,
            "valid_until_order": transition.valid_until_order,
            "evidence_refs": list(transition.evidence_refs),
        }
        if kind is _HANDOFF:
            edge["completion_evidence_refs"] = list(transition.completion_evidence_refs)
        if kind is MixedControlTransitionKind.EXTERNAL_DIRECTION:
            edge["target_kinds"] = ["proposal"]
        edges[transition_id] = edge
        step: dict[str, Any] = {
            "step_id": transition_id,
            "permitted_transition_ref": transition_id,
            "expected_state_revision": transition.expected_state_revision,
            "valid_from_order": transition.effective_order,
            "valid_until_order": transition.effective_order,
        }
        if transition.proposal_ref is not None:
            if kind is MixedControlTransitionKind.CANCELLATION:
                step["target_kind"] = "proposal"
            step["target_step_ref"] = transition.proposal_ref
        steps.append(step)
    return {
        "semantics": MIXED_CONTROL_POLICY_SEMANTICS,
        "form": "finite-script",
        "participant_ref": declaration.participant_ref,
        "policy_revision": declaration.policy_revision,
        "order_strategy": declaration.order_strategy.value,
        "initial_state_ref": declaration.initial_state_ref,
        "dispositions": declaration.dispositions.model_dump(mode="json"),
        "controller_states": {
            state_id: state.model_dump(mode="json") for state_id, state in declaration.controller_states.items()
        },
        "permitted_transitions": edges,
        "script_steps": steps,
    }


def _convert(payload: object, scenario: Scenario) -> tuple[dict[str, Any] | None, list[tuple[str, str]], list[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get(_SPECS, {}), dict):
        return None, [(_INVALID, "")], []
    refusals: list[tuple[str, str]] = []
    affected: list[str] = []
    for spec_name, raw_spec in payload.get(_SPECS, {}).items():
        behavior_spec = scenario.behavior_specifications.get(spec_name)
        declaration = getattr(behavior_spec, _MIXED_CONTROL, None)
        if not isinstance(declaration, MixedControlParticipantOperation) or not isinstance(raw_spec, dict):
            continue
        refusals += _transition_refusals(spec_name, declaration)
        refusals += _delivery_refusals(spec_name, behavior_spec, declaration)
        affected += [
            _pointer(_SPECS, spec_name, _MIXED_CONTROL, _TRANSITIONS, transition_id) + "/proposal_revision"
            for transition_id, transition in declaration.transitions.items()
            if transition.proposal_revision is not None
        ]
        for key in [key for key in raw_spec if normalize_field_key(str(key)) == _MIXED_CONTROL]:
            del raw_spec[key]
        raw_spec[_MIXED_CONTROL] = _converted_policy(declaration)
    return (payload if not refusals else None), refusals, affected


def migrate_mixed_control_to_finite_script(
    content: str,
    *,
    limits: SDLParserLimits = DEFAULT_PARSER_LIMITS,
) -> SDLTransformationResult:
    """Convert each legacy ``mixed_control`` to a rev1 finite script, or refuse atomically.

    Historical occurrences, compiled snapshots and runtime evidence are never rewritten.
    """

    digest = source_byte_digest(content)
    output: Scenario | None = None
    refusals: list[tuple[str, str]] = []
    affected: list[str] = []
    try:
        scenario = parse_sdl(content, limits=limits)
        payload = load_sdl_yaml(content, source_options=SDLSourceParseOptions(limits=limits))
        converted, refusals, affected = _convert(payload, scenario)
        if converted is not None:
            output = parse_sdl(yaml.safe_dump(converted, sort_keys=False), limits=limits)
    except SDLValidationError as error:
        refusals = [(_INVALID, pointer) for pointer in _error_pointers(error)]
    except (SDLError, ValueError, TypeError):
        refusals = [(_INVALID, "")]
    codes = sorted({(f"mixed-control-migration.{code}", pointer) for code, pointer in refusals})
    policy_digest = canonical_json_digest(None)
    report = ArtifactTransformationReportModel(
        operation_profile=MIXED_CONTROL_MIGRATION_PROFILE,
        status="success" if output is not None else "refused",
        artifact_kind="sdl-authoring",
        source_profile="sdl-mixed-control/fixed-coordinate-v1",
        target_profile="sdl-authoring-input/v1",
        canonicalization_profile="mixed-control-migration-digest-pair/v1",
        source_digest=digest,
        target_digest=canonical_sdl_digest(output).value if output is not None else None,
        policy_digest=policy_digest,
        derivation_digest=canonical_json_digest(
            {"operation": MIXED_CONTROL_MIGRATION_PROFILE, "source": digest, "policy": policy_digest}
        ),
        preconditions=(check("legacy-trace-constraints-preserved", "passed" if output is not None else "failed"),),
        postconditions=(check("rev1-target-admitted", "passed"),) if output is not None else (),
        affected_identities=tuple(sorted(set(affected))) if output is not None else (),
        preservation=ArtifactTransformationPreservationModel(
            profile="legacy-mixed-control-trace-constraints/v1",
            outcome="not-applicable",
            limitations=tuple(sorted(_LIMITATIONS)),
        ),
        diagnostics=tuple(
            diagnostic(
                code,
                "Mixed-control conversion refused; see docs/migration/mixed-control-finite-script-conversion.md.",
                address=pointer,
            )
            for code, pointer in codes
        ),
    )
    return SDLTransformationResult(output, (), report)


__all__ = ["MIXED_CONTROL_MIGRATION_PROFILE", "migrate_mixed_control_to_finite_script"]
