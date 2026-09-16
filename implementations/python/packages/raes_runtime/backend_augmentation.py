"""Pure scope admission at the common backend invocation boundary."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING

from raes_contracts.augmentation_scope import AUGMENTATION_SCOPE_CONTRACT
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.materialization import MATERIALIZATION_MAX_BYTES
from raes_processor.planner.augmentation_admission import (
    AugmentationAdmission,
    admit_augmentation_preparation,
    compose_augmentation_admission,
)

from .backend_realization_authority import _RealizationApplyContext

if TYPE_CHECKING:
    from raes_backend_protocols.capabilities import BackendManifest
    from raes_contracts.materialization import MaterializationArchive
    from raes_contracts.planning import EvaluationPlan, OrchestrationPlan, ProvisioningPlan
    from raes_contracts.runtime_state import RuntimeSnapshot

_SCOPE_ADDRESS = "/augmentation_scope"


def compose_augmentation_invocation(
    context: _RealizationApplyContext,
    previous: RuntimeSnapshot,
    archive: MaterializationArchive | None,
    *,
    preceding: AugmentationAdmission | None = None,
) -> tuple[_RealizationApplyContext, list[Diagnostic]]:
    """Retain prior producer ownership in the common cumulative SDL expectation."""
    if context.augmentation is None or not context.augmentation.is_valid:
        return context, []
    try:
        admitted = compose_augmentation_admission(
            context.augmentation,
            context.operation_plan,
            previous,
            archive,
            preceding=preceding.cumulative_content if preceding is not None else None,
        )
        return replace(context, augmentation=admitted), []
    except Exception:
        return context, [
            Diagnostic(
                code="augmentation.composition-invalid",
                domain="augmentation",
                address=_SCOPE_ADDRESS,
                message=(
                    "Prospective effects cannot be composed with authenticated prior producer effects; "
                    "this invocation attempted no mutation."
                ),
            )
        ]


def prepare_augmentation_invocation(
    method: Callable[..., object] | None, previous: RuntimeSnapshot, context: _RealizationApplyContext
) -> tuple[_RealizationApplyContext, list[Diagnostic]]:
    """No producer callback may mutate while discovering its prospective effects."""
    manifest, request = context.manifest, context.operation_plan
    if request is None or manifest is None or AUGMENTATION_SCOPE_CONTRACT not in manifest.supported_contract_versions:
        return context, []
    prepare = getattr(getattr(method, "__self__", None), "prepare_augmentation", None)
    try:
        if not callable(prepare):
            raise ValueError("missing pure augmentation preparation")
        report = prepare(deepcopy(request), deepcopy(previous))
        admitted = admit_augmentation_preparation(report, request, manifest, previous)
        expected = context.expected_augmentation
        if expected is not None and (
            report.effects != expected.effects
            or parse_bounded_json_object(report.content, max_bytes=MATERIALIZATION_MAX_BYTES)
            != parse_bounded_json_object(expected.content, max_bytes=MATERIALIZATION_MAX_BYTES)
        ):
            raise ValueError("producer changed its whole-run prospective effects")
    except Exception:
        return context, [
            Diagnostic(
                code="augmentation.preparation-invalid",
                domain="augmentation",
                address=_SCOPE_ADDRESS,
                message=(
                    "Backend cannot provide a complete, bound read-only augmentation preparation; "
                    "this invocation attempted no mutation."
                ),
            )
        ]
    return replace(context, augmentation=admitted), list(admitted.diagnostics)


def prepare_auxiliary_augmentation(
    producer: object,
    request: ProvisioningPlan | OrchestrationPlan | EvaluationPlan,
    manifest: BackendManifest | None,
    previous: RuntimeSnapshot,
) -> list[Diagnostic]:
    """Hooks without an attested materialization boundary must be out-of-world."""
    if manifest is None or AUGMENTATION_SCOPE_CONTRACT not in manifest.supported_contract_versions:
        return []
    # Only the method owner matters here; preparation never invokes collect/initialize.
    method = getattr(producer, "prepare_augmentation", None)
    context, diagnostics = prepare_augmentation_invocation(
        method, previous, _RealizationApplyContext(operation_plan=request, manifest=manifest)
    )
    if not diagnostics and context.augmentation.preparation.effects:
        diagnostics = [
            Diagnostic(
                code="augmentation.phase-unattested",
                domain="augmentation",
                address=_SCOPE_ADDRESS,
                message=(
                    "This hook needs in-world effects without an attested materialization boundary; "
                    "materialize its apparatus in an admitted plan phase first."
                ),
            )
        ]
    return diagnostics
