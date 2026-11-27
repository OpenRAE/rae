"""Observability/evidence conformance diagnostics (issue #128 / ASR-525)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from raes_contracts.contracts import ExperimentRunModel
from raes_contracts.diagnostics import Diagnostic

from raes_conformance.conformance.diagnostics import (
    _OBSERVABILITY_EVIDENCE_INVALID_DIAGNOSTIC_CODE,
    conformance_diagnostic,
)

_PORTABLE_AUGMENTATION_CARRIER_KINDS = frozenset(
    {
        "apparatus-context",
        "capture-spec",
        "derived-measure",
        "evidence-record",
        "manifest",
        "measurement-channel",
        "profile",
        "run",
        "scenario-snapshot",
    }
)


_RUN_REFINEMENT_CONCERN_KINDS = frozenset({"capture-window", "measurement-channel"})


def observability_evidence_conformance_diagnostics(
    payload: ExperimentRunModel | Mapping[str, Any],
) -> tuple[Diagnostic, ...]:
    """Return ASR-525 diagnostics for issue #128 observability/evidence semantics.

    The individual contract models already enforce the closed-world shape and
    SEM-225 baseline rules. This helper adds the conformance-level checks that
    tie the existing carriers together for issue #128: augmentation reports
    must name their portable affected carriers, and run-scoped capture
    refinements must preserve the authored/base requirement plus evidence.
    """

    run = payload if isinstance(payload, ExperimentRunModel) else ExperimentRunModel.model_validate(payload)
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_augmentation_conformance_diagnostics(run))
    diagnostics.extend(_run_refinement_conformance_diagnostics(run))
    return tuple(diagnostics)


def _augmentation_conformance_diagnostics(run: ExperimentRunModel) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for disclosure in run.augmentation_disclosures:
        address = f"experiment-run-v1.augmentation_disclosures.{disclosure.augmentation_id}"
        if not disclosure.affected_refs:
            diagnostics.append(
                conformance_diagnostic(
                    _OBSERVABILITY_EVIDENCE_INVALID_DIAGNOSTIC_CODE,
                    f"{address}.affected_refs",
                    (
                        "augmentation disclosures must name affected_refs so added capture surfaces, apparatus, "
                        "constraints, side effects, and comparability implications are portable"
                    ),
                )
            )
        if not any(ref.ref_kind in _PORTABLE_AUGMENTATION_CARRIER_KINDS for ref in disclosure.carrier_refs):
            diagnostics.append(
                conformance_diagnostic(
                    _OBSERVABILITY_EVIDENCE_INVALID_DIAGNOSTIC_CODE,
                    f"{address}.carrier_refs",
                    "augmentation disclosures must cite at least one portable carrier_ref",
                )
            )
        if disclosure.purpose in {"evidence", "evaluation", "comparability"} and not disclosure.evidence_refs:
            diagnostics.append(
                conformance_diagnostic(
                    _OBSERVABILITY_EVIDENCE_INVALID_DIAGNOSTIC_CODE,
                    f"{address}.evidence_refs",
                    f"{disclosure.purpose} augmentation disclosures must preserve supporting evidence_refs",
                )
            )
    return diagnostics


def _run_refinement_conformance_diagnostics(run: ExperimentRunModel) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for disclosure in run.realized_form_disclosures:
        if disclosure.concern_kind not in _RUN_REFINEMENT_CONCERN_KINDS:
            continue
        address = f"experiment-run-v1.realized_form_disclosures.{disclosure.concern_id}"
        if disclosure.authored_ref is None:
            diagnostics.append(
                conformance_diagnostic(
                    _OBSERVABILITY_EVIDENCE_INVALID_DIAGNOSTIC_CODE,
                    f"{address}.authored_ref",
                    (
                        "run-level evidence requirement refinements must preserve authored_ref instead of "
                        "rewriting authored scenario meaning"
                    ),
                )
            )
        if not disclosure.evidence_refs:
            diagnostics.append(
                conformance_diagnostic(
                    _OBSERVABILITY_EVIDENCE_INVALID_DIAGNOSTIC_CODE,
                    f"{address}.evidence_refs",
                    "run-level evidence requirement refinements must preserve supporting evidence_refs",
                )
            )
    return diagnostics
