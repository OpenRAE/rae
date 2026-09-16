"""Negotiated attestation admission and protected archive publication after apply."""

from dataclasses import replace
from typing import cast

from raes_contracts.augmentation_scope import AUGMENTATION_SCOPE_CONTRACT
from raes_contracts.materialization import (
    MATERIALIZATION_ATTESTATION_CONTRACT,
    MaterializationArchive,
    MaterializationSource,
)
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.planner import admit_materialization_submission, validate_materialization_archive_record
from raes_processor.planner.augmentation_admission import validate_actual_augmentation

from .backend_realization_authority import _RealizationApplyContext
from .diagnostics import _failure_diagnostic


def materialization_precondition(
    context: _RealizationApplyContext, archive: MaterializationArchive | None
) -> str | None:
    request, manifest = context.operation_plan, context.manifest
    if request is None:
        return None
    source = getattr(request, "materialization_source", None)
    required = getattr(request, "augmentation_scope_required", False)
    if source is not None:
        try:
            source = MaterializationSource.model_validate(source.model_dump(mode="json"))
            required = required or source.augmentation_scope_required
        except (AttributeError, TypeError, ValueError):
            return "Materialization reporting requires valid bound source context."
    if required and (
        manifest is None
        or source is None
        or not {AUGMENTATION_SCOPE_CONTRACT, MATERIALIZATION_ATTESTATION_CONTRACT}.issubset(
            manifest.supported_contract_versions
        )
    ):
        return "Explicit augmentation permission requires negotiated enforcement and bound source context."
    negotiated = manifest is not None and MATERIALIZATION_ATTESTATION_CONTRACT in manifest.supported_contract_versions
    if not negotiated and source is None:
        return None
    error = None
    if not negotiated or source is None or archive is None or manifest.realization_envelope is None:
        error = (
            "Materialization reporting requires negotiated support, trusted source context, "
            "configured identity and an archive owner."
        )
    return error


def finalize_materialization(
    raw: ApplyResult,
    accepted: ApplyResult,
    context: _RealizationApplyContext,
    previous: RuntimeSnapshot,
    archive: MaterializationArchive | None,
) -> ApplyResult:
    """Publish bytes before accepted references; preserve valid cleanup on failure."""
    accepted = cast(ApplyResult, replace(accepted, materialization_attestation=None))
    if not accepted.success:
        return accepted
    request = context.operation_plan
    source = getattr(request, "materialization_source", None)
    if source is None and raw.materialization_attestation is None:
        return accepted
    try:
        if source is None or raw.materialization_attestation is None or archive is None or context.manifest is None:
            raise ValueError("missing negotiated materialization result")
        admitted = admit_materialization_submission(
            raw.materialization_attestation, request, context.manifest, previous, raw.snapshot
        )
        validate_actual_augmentation(admitted, context.augmentation)
        record = archive.publish(admitted.sdl)
        validate_materialization_archive_record(admitted, record)
        snapshot = accepted.snapshot.with_entries(
            dict(accepted.snapshot.entries),
            materialization_attestations=(*previous.materialization_attestations, record),
        )
    except Exception:
        accepted = cast(
            ApplyResult,
            replace(
                accepted,
                success=False,
                diagnostics=[
                    *accepted.diagnostics,
                    _failure_diagnostic(
                        "runtime.materialization-attestation-invalid",
                        "runtime.materialization",
                        "Materialization attestation or protected archival delivery failed; "
                        "retained resources require cleanup.",
                    ),
                ],
            ),
        )
    else:
        accepted = cast(ApplyResult, replace(accepted, snapshot=snapshot, materialization_attestation=admitted))
    return accepted
