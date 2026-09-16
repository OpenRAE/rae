"""Pure scope admission at the common backend invocation boundary."""

from copy import deepcopy
from dataclasses import replace

from raes_contracts.augmentation_scope import AUGMENTATION_SCOPE_CONTRACT
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.json_ingress import parse_bounded_json_object
from raes_contracts.materialization import MATERIALIZATION_MAX_BYTES
from raes_processor.planner.augmentation_admission import admit_augmentation_preparation, compose_augmentation_admission


def compose_augmentation_invocation(context, previous, archive, *, preceding=None):
    """Retain prior producer ownership in the common cumulative SDL expectation."""
    if context.augmentation is None or not context.augmentation.is_valid:
        return context, []
    try:
        admitted = compose_augmentation_admission(
            context.augmentation, context.operation_plan, previous, archive, preceding=preceding
        )
        return replace(context, augmentation=admitted), []
    except Exception:
        return context, [
            Diagnostic(
                code="augmentation.composition-invalid",
                domain="augmentation",
                address="/augmentation_scope",
                message="Prospective effects cannot be composed with authenticated prior producer effects; this invocation attempted no mutation.",
            )
        ]


def prepare_augmentation_invocation(method, previous, context):
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
                address="/augmentation_scope",
                message="Backend cannot provide a complete, bound read-only augmentation preparation; this invocation attempted no mutation.",
            )
        ]
    return replace(context, augmentation=admitted), list(admitted.diagnostics)


def prepare_auxiliary_augmentation(producer, request, manifest, previous):
    """Hooks without an attested materialization boundary must be out-of-world."""
    from .backend_realization_authority import _RealizationApplyContext

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
                address="/augmentation_scope",
                message="This hook needs in-world effects without an attested materialization boundary; materialize its apparatus in an admitted plan phase first.",
            )
        ]
    return diagnostics
