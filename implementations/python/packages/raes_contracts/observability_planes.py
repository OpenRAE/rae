"""Observability and evidence planes of claim-bearing contracts (SEM-224, ADR-066).

ADR-066 and ``specs/formal/observability-evidence-plane.md`` define five named
planes. This module assigns exactly one primary plane to a claim-bearing
contract by its contract role, never by a free-form string (OE-11). It is the
source of the portable ``x-raes-plane`` annotation on the published contracts.
SDL sections and runtime families get their plane in
``raes.observability_plane_semantics``.
"""

from __future__ import annotations

from enum import Enum


class ObservabilityEvidencePlane(str, Enum):
    """The five named observability/evidence planes (ADR-066)."""

    SCENARIO_NATIVE_OBSERVABILITY = "scenario_native_observability"
    AUTHORED_EVIDENCE_REQUIREMENT = "authored_evidence_requirement"
    PROCESSOR_BACKEND_OPERATIONAL = "processor_backend_operational_observability"
    CAPTURED_EVIDENCE = "captured_evidence"
    DERIVED_ANALYSIS = "derived_analysis"


# Claim-bearing carriers whose contract role decides a single primary plane.
# Authored evidence requirement, captured evidence, and derived analysis are the
# three experiment-core carriers; processor/backend operational observability is
# carried by apparatus manifests, processor manifests, and apparatus context.
PLANE_BY_CONTRACT_ID: dict[str, ObservabilityEvidencePlane] = {
    "participant-control-selection-v1": ObservabilityEvidencePlane.PROCESSOR_BACKEND_OPERATIONAL,
    "participant-control-evaluation-v1": ObservabilityEvidencePlane.PROCESSOR_BACKEND_OPERATIONAL,
    "participant-control-selection-v2": ObservabilityEvidencePlane.PROCESSOR_BACKEND_OPERATIONAL,
    "participant-control-evaluation-v2": ObservabilityEvidencePlane.PROCESSOR_BACKEND_OPERATIONAL,
    "experiment-capture-spec-v1": ObservabilityEvidencePlane.AUTHORED_EVIDENCE_REQUIREMENT,
    "experiment-evidence-record-v1": ObservabilityEvidencePlane.CAPTURED_EVIDENCE,
    "experiment-derived-measure-v1": ObservabilityEvidencePlane.DERIVED_ANALYSIS,
    "backend-manifest-v2": ObservabilityEvidencePlane.PROCESSOR_BACKEND_OPERATIONAL,
    "processor-manifest-v2": ObservabilityEvidencePlane.PROCESSOR_BACKEND_OPERATIONAL,
    "experiment-apparatus-context-v1": ObservabilityEvidencePlane.PROCESSOR_BACKEND_OPERATIONAL,
}

# Contracts whose ``x-raes-plane`` annotation is published as portable
# traceability (the three experiment-core carriers that map 1:1 to a plane).
PLANE_ANNOTATED_CONTRACT_IDS: tuple[str, ...] = (
    "participant-control-selection-v1",
    "participant-control-evaluation-v1",
    "participant-control-selection-v2",
    "participant-control-evaluation-v2",
    "experiment-capture-spec-v1",
    "experiment-evidence-record-v1",
    "experiment-derived-measure-v1",
)


def classify_contract_plane(contract_id: str) -> ObservabilityEvidencePlane:
    """Return the single primary plane for a registered claim-bearing carrier.

    Raises ``ValueError`` for an unregistered carrier: plane ownership is decided
    by carrier role, never inferred.
    """

    try:
        return PLANE_BY_CONTRACT_ID[contract_id]
    except KeyError:
        raise ValueError(
            f"no observability/evidence plane is registered for carrier '{contract_id}'; "
            "plane ownership is decided by carrier role, not inferred"
        ) from None


__all__ = [
    "PLANE_ANNOTATED_CONTRACT_IDS",
    "PLANE_BY_CONTRACT_ID",
    "ObservabilityEvidencePlane",
    "classify_contract_plane",
]
