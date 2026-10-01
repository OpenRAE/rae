"""Validation helpers for realization-honesty evidence."""

from __future__ import annotations

from raes_contracts.diagnostics import Diagnostic, Severity
from raes_contracts.planning import ProvisioningPlan
from raes_contracts.realization_envelope import (
    BackendRealizationEnvelopeModel,
    ConcernDisposition,
    ObservationStrength,
    RealizationConcern,
)
from raes_contracts.realization_observation import RealizationObservation
from raes_contracts.vocabulary import RealizationVerificationScope, observation_requirement_satisfied

from ._realization_models import (
    ExpectedRealizationObservation,
    RealizationProbeEvidence,
    RealizationProbeRequest,
)

_DOMAIN = "conformance"
_RESOURCE_CONCERNS: dict[str, frozenset[RealizationConcern]] = {
    "network": frozenset({RealizationConcern.TOPOLOGY, RealizationConcern.NETWORK}),
    "node": frozenset(
        {
            RealizationConcern.TOPOLOGY,
            RealizationConcern.ARCHITECTURE,
            RealizationConcern.IMAGE,
            RealizationConcern.RESOURCE_ALLOCATION,
            RealizationConcern.NETWORK,
            RealizationConcern.SERVICE,
            RealizationConcern.ACL,
        }
    ),
    "content-placement": frozenset({RealizationConcern.CONTENT_PLACEMENT}),
    "account-placement": frozenset({RealizationConcern.ACCOUNT_PLACEMENT}),
    "domain-controller-placement": frozenset({RealizationConcern.TOPOLOGY}),
    "feature-binding": frozenset({RealizationConcern.FEATURE_BINDING}),
}


def diagnostic(code: str, address: str, message: str) -> Diagnostic:
    """Return a sanitized conformance error diagnostic."""

    return Diagnostic(code=code, domain=_DOMAIN, address=address, message=message, severity=Severity.ERROR)


def required_strengths(
    envelope: BackendRealizationEnvelopeModel,
) -> dict[RealizationConcern, ObservationStrength]:
    """Return required observation strength by supported concern."""

    return {
        disclosure.concern: disclosure.observation_strength
        for disclosure in envelope.concerns
        if disclosure.disposition is not ConcernDisposition.UNSUPPORTED
    }


def operation_inventory_diagnostics(
    plan: ProvisioningPlan,
    evidence: RealizationProbeEvidence,
    strengths: dict[RealizationConcern, ObservationStrength],
) -> list[Diagnostic]:
    """Check exact operation accounting and expected-observation coverage."""

    expected_operations = {operation.address for operation in plan.actionable_operations}
    accounted = set(evidence.accounted_operations)
    diagnostics: list[Diagnostic] = []
    if accounted != expected_operations or set(evidence.changed_addresses) != expected_operations:
        diagnostics.append(
            diagnostic(
                "conformance.operation-accounting-incomplete",
                "runtime.provisioning.operations",
                "Every actionable provisioning operation must have exactly one terminal accounting result.",
            )
        )
    inventory = {(item.address, item.concern) for item in evidence.expected_observations}
    for operation in plan.actionable_operations:
        required = _RESOURCE_CONCERNS.get(operation.resource_type, frozenset()) & strengths.keys()
        if any((operation.address, concern) not in inventory for concern in required):
            diagnostics.append(
                diagnostic(
                    "conformance.observation-inventory-incomplete",
                    operation.address,
                    "The independent expected-observation inventory omits a required realization concern.",
                )
            )
    return diagnostics


def observation_diagnostics(
    request: RealizationProbeRequest,
    evidence: RealizationProbeEvidence,
    strengths: dict[RealizationConcern, ObservationStrength],
) -> list[Diagnostic]:
    """Check observation value, strength, binding, provenance, and freshness."""

    observed: dict[tuple[str, str, RealizationConcern], list[RealizationObservation]] = {}
    for item in evidence.observations:
        observed.setdefault((item.address, item.field_path, item.concern), []).append(item)
    diagnostics: list[Diagnostic] = []
    for expected in evidence.expected_observations:
        diagnostics.extend(
            _expected_observation_diagnostics(
                expected,
                observed.get((expected.address, expected.field_path, expected.concern), []),
                request,
                evidence.baseline_sequence,
                strengths,
            )
        )
    return diagnostics


def _expected_observation_diagnostics(
    expected: ExpectedRealizationObservation,
    candidates: list[RealizationObservation],
    request: RealizationProbeRequest,
    baseline_sequence: int,
    strengths: dict[RealizationConcern, ObservationStrength],
) -> list[Diagnostic]:
    address = expected.address
    if len(candidates) != 1 or candidates[0].value != expected.value:
        return [
            diagnostic(
                "conformance.observation-missing",
                address,
                "A required addressed realization observation is missing, duplicated, or mismatched.",
            )
        ]
    item = candidates[0]
    diagnostics: list[Diagnostic] = []
    if not observation_requirement_satisfied(
        actual_scope=RealizationVerificationScope.PRESENCE,
        actual_source=item.source,
        required_scope=None,
        required_source=strengths.get(expected.concern),
    ):
        diagnostics.append(
            diagnostic(
                "conformance.observation-strength-insufficient",
                address,
                "The realization observation source does not match the configuration requirement.",
            )
        )
    if not _observation_binding_valid(item, address, request):
        diagnostics.append(
            diagnostic(
                "conformance.observation-binding-invalid",
                address,
                "The realization observation is not bound to this operation, probe, envelope, and observer.",
            )
        )
    if item.origin != "observed":
        diagnostics.append(
            diagnostic(
                "conformance.observation-not-independent",
                address,
                "Planned or echoed state cannot satisfy an independent realization observation.",
            )
        )
    if item.sequence is None or item.sequence <= baseline_sequence:
        diagnostics.append(
            diagnostic(
                "conformance.observation-stale",
                address,
                "The realization observation is not fresh for this probe execution.",
            )
        )
    return diagnostics


def _observation_binding_valid(
    item: RealizationObservation,
    address: str,
    request: RealizationProbeRequest,
) -> bool:
    return (
        item.operation_id == address
        and item.probe_digest == request.probe_digest
        and item.envelope_digest == request.envelope_digest
        and item.configuration_digest == request.configuration_digest
        and item.observer_version == request.observer_version
        and item.binding_verified
    )


def transformation_diagnostics(evidence: RealizationProbeEvidence) -> list[Diagnostic]:
    """Reject all material transformations lacking executable governed evidence."""

    diagnostics: list[Diagnostic] = []
    for transformation in evidence.transformations:
        code = (
            "conformance.transformation-undisclosed"
            if not transformation.disclosed
            else "conformance.transformation-unverified"
        )
        diagnostics.append(
            diagnostic(
                code,
                transformation.address,
                "A material realization transformation lacks a governed executable rule and exact evidence.",
            )
        )
    return diagnostics
