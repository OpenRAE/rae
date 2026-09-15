"""Negotiated attestation admission and protected archive publication after apply."""

from dataclasses import replace

from raes_contracts.materialization import MATERIALIZATION_ATTESTATION_CONTRACT, MaterializationArchive
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_processor.planner import admit_materialization_submission, validate_materialization_archive_record

from .backend_realization_authority import _RealizationApplyContext
from .diagnostics import _failure_diagnostic


def materialization_precondition(
    context: _RealizationApplyContext, archive: MaterializationArchive | None
) -> str | None:
    request, manifest = context.operation_plan, context.manifest
    if request is None:
        return None
    source = getattr(request, "materialization_source", None)
    negotiated = manifest is not None and MATERIALIZATION_ATTESTATION_CONTRACT in manifest.supported_contract_versions
    if not negotiated and source is None:
        return None
    if not negotiated or source is None or archive is None or manifest.realization_envelope is None:
        return "Materialization reporting requires negotiated support, trusted source context, configured identity and an archive owner."
    return None


def finalize_materialization(
    raw: ApplyResult,
    accepted: ApplyResult,
    context: _RealizationApplyContext,
    previous: RuntimeSnapshot,
    archive: MaterializationArchive | None,
) -> ApplyResult:
    """Publish bytes before accepted references; preserve valid cleanup on failure."""
    accepted = replace(accepted, materialization_attestation=None)
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
        record = archive.publish(admitted.sdl)
        validate_materialization_archive_record(admitted, record)
        snapshot = accepted.snapshot.with_entries(
            dict(accepted.snapshot.entries),
            materialization_attestations=(*previous.materialization_attestations, record),
        )
    except Exception:
        return replace(
            accepted,
            success=False,
            diagnostics=[
                *accepted.diagnostics,
                _failure_diagnostic(
                    "runtime.materialization-attestation-invalid",
                    "runtime.materialization",
                    "Materialization attestation or protected archival delivery failed; retained resources require cleanup.",
                ),
            ],
        )
    return replace(accepted, snapshot=snapshot, materialization_attestation=admitted)
