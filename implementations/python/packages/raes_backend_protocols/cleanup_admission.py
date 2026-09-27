"""Admission of trial cleanup plans and authored execution choices against backend capability."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from raes_contracts.contracts.trial_cleanup import TrialCleanupPlanModel

    from .backend_manifest import BackendManifest


def _required_cleanup_actions(plan: TrialCleanupPlanModel) -> set[str]:
    return {
        obligation.action_kind
        for obligation in plan.cleanup_obligations.values()
        if obligation.requirement == "required"
    }


def _required_cleanup_probe_methods(plan: TrialCleanupPlanModel) -> set[str]:
    probe_refs = set(plan.clean_state.verification_probe_refs)
    probe_refs.update(
        probe_ref
        for obligation in plan.cleanup_obligations.values()
        if obligation.requirement == "required"
        for probe_ref in obligation.verification_probe_refs
    )
    return {probe_ref.partition(":")[0] for probe_ref in probe_refs}


def _require_supported_cleanup_values(label: str, required: set[str], supported: frozenset[str]) -> None:
    unsupported = sorted(required - supported)
    if unsupported:
        raise ValueError(f"unsupported cleanup {label}: {', '.join(unsupported)}")


def require_cleanup_plan_capability(manifest: BackendManifest, plan: TrialCleanupPlanModel) -> None:
    """Fail admission when a backend cannot satisfy a portable cleanup plan."""

    cleanup = manifest.cleanup
    if cleanup is None:
        raise ValueError("backend does not declare cleanup capabilities")

    _require_supported_cleanup_values("action kinds", _required_cleanup_actions(plan), cleanup.supported_action_kinds)
    _require_supported_cleanup_values(
        "verification methods", _required_cleanup_probe_methods(plan), cleanup.supported_verification_methods
    )

    if plan.clean_state.mode == "declared-reusable" and not cleanup.supports_reusable_state:
        raise ValueError("backend does not support declared reusable state")
    required_cleanup = any(obligation.requirement == "required" for obligation in plan.cleanup_obligations.values())
    if required_cleanup and not cleanup.supports_residual_state_disclosure:
        raise ValueError("required cleanup needs backend residual-state disclosure")


def require_execution_authority_capability(
    manifest: BackendManifest,
    *,
    cleanup_plan: TrialCleanupPlanModel,
    required_guarantees: Iterable[str],
) -> None:
    """Fail admission when a backend cannot honour a trial's authored execution choices.

    The cleanup plan must be supported, and every operation guarantee derived
    from the choices must be declared. A missing declaration is refusal, never
    best effort. Runtime admission still rechecks the installed provider.
    """

    require_cleanup_plan_capability(manifest, cleanup_plan)
    required = set(required_guarantees)
    if not required:
        return
    supervision = manifest.operation_supervision
    declared = supervision.guarantees if supervision is not None else frozenset()
    missing = sorted(required - declared)
    if missing:
        raise ValueError(f"unsupported operation guarantees: {', '.join(missing)}")


__all__ = ["require_cleanup_plan_capability", "require_execution_authority_capability"]
