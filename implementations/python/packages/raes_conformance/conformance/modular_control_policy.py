"""Authored recovery preservation uses the incumbent SDL compiler and planner."""

from __future__ import annotations

from raes import parse_sdl
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.plan_projection import provisioning_plan_model
from raes_contracts.errors import EvidenceIntegrityError, RaesError
from raes_contracts.execution_policy import EffectiveExecutionPolicy
from raes_contracts.operational_logging import get_logger
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_runtime.registry import RuntimeTarget

from .diagnostics import _diagnostic, sanitized_failure_message
from .modular_control_types import ModularControlEvidence
from .report import ConformanceCaseResult

_LOGGER = get_logger(__name__)
_SDL = """
name: conformance-recovery
nodes: {host: {type: compute, os: linux}}
evidence_requirements:
  continuity:
    source_class: apparatus
    scope: whole-scenario
    window: execution
    channel: log
    sensitivity: plain
    redaction: none
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required
execution_policy:
  default:
    policy_id: authored-conformance-policy
    response: RESPONSE
    evidence_refs: [continuity]
"""


def _planned_policies(target: RuntimeTarget, response: str) -> list[dict[str, object]]:
    scenario = parse_sdl(_SDL.replace("RESPONSE", response))
    execution = plan(compile_runtime_model(scenario), target.manifest)
    public = provisioning_plan_model(execution.provisioning)
    # Each finding below means that the plan for the target does not match its authored input.
    if not public.operations:
        raise EvidenceIntegrityError("authored recovery probe produced no operation")
    policies = [_policy_payload(operation.execution_policy, response) for operation in public.operations]
    if response == "resume" and not any(item.code.startswith("execution-policy.") for item in execution.diagnostics):
        raise EvidenceIntegrityError("unsupported general resume was admitted")
    return policies


def _policy_payload(effective: EffectiveExecutionPolicy | None, response: str) -> dict[str, object]:
    if (
        effective is None
        or effective.policy.response != response
        or effective.policy.policy_id != "authored-conformance-policy"
    ):
        raise EvidenceIntegrityError("authored recovery policy was lost in planning")
    if effective.governing_scope != "#/":
        raise EvidenceIntegrityError("authored recovery scope was changed")
    return effective.model_dump(mode="json")


def authored_recovery_case(
    target: RuntimeTarget, obligations: tuple[str, ...], effects: tuple[str, ...]
) -> ConformanceCaseResult:
    from .modular_control import _effect_kinds

    diagnostics = []
    policies = []
    try:
        for response in ("terminate", "resume"):
            policies.extend(_planned_policies(target, response))
    except Exception as exc:
        if not isinstance(exc, RaesError):
            # Boundary of the recovery check: an unexpected failure is logged once, then reported.
            _LOGGER.exception("authored recovery probe failed")
        diagnostics.append(
            _diagnostic("conformance.modular-recovery-policy", "authored-recovery", sanitized_failure_message(exc))
        )
    return ConformanceCaseResult(
        name="authored-recovery",
        contract_name="provisioning-plan-v1",
        valid=True,
        passed=not diagnostics,
        probe_kind="modular-control",
        probe_digest=canonical_json_digest(_SDL),
        modular_control=ModularControlEvidence(
            obligation="authored-recovery",
            selected_obligations=obligations,
            claimed_effect_kinds=effects,
            excluded_effect_kinds=tuple(kind for kind in _effect_kinds() if kind not in effects),
            artifact_digests={"policy": canonical_json_digest(policies)},
        ),
        diagnostics=tuple(diagnostics),
        limitations=("Parse/compile/plan evidence only; no native retry, checkpoint or resume claim.",),
    )
