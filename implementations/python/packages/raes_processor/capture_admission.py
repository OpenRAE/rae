"""Deterministic required-capture projection and backend admission."""

from __future__ import annotations

from dataclasses import dataclass

from raes.evidence_requirements import EvidenceRequirement
from raes.scenario import ScenarioContent
from raes_backend_protocols.capabilities import ObservationCapabilities, ObservationCaptureOffer
from raes_contracts.contracts import ExperimentCaptureSpecModel
from raes_contracts.diagnostics import Diagnostic, Severity

_CHANNEL_CAPTURE_KIND = {
    "packet_capture": "packet-capture",
    "log": "log",
    "trace": "trace",
    "metric": "telemetry",
    "file_artifact": "artifact",
    "screen_capture": "artifact",
    "api_response": "observation",
    "database_record": "observation",
    "participant_output": "observation",
    "other": "other",
}
_CHANNEL_MANIFEST_KIND = {
    "packet_capture": "packet-capture",
    "log": "backend-log",
    "trace": "backend-log",
    "metric": "runtime-snapshot",
    "file_artifact": "file-artifact",
    "screen_capture": "file-artifact",
    "api_response": "participant-observation",
    "database_record": "file-artifact",
    "participant_output": "participant-observation",
    "other": "backend-log",
}


def _value(value: object | None) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))


@dataclass(frozen=True)
class CaptureDemand:
    """One normalized required capture atom retained through planning."""

    demand_id: str
    address: str
    output_contract: str
    field_selectors: tuple[str, ...]
    artifact_roles: tuple[str, ...]
    media_types: tuple[str, ...]
    capture_kind: str
    source_classes: tuple[str, ...]
    source_refs: tuple[str, ...]
    scopes: tuple[str, ...]
    scope_refs: tuple[str, ...]
    channel_kinds: tuple[str, ...]
    channel_refs: tuple[str, ...]
    window_kinds: tuple[str, ...]
    integrity_modes: tuple[str, ...]
    sensitivity: str
    disclosure: str
    retention_policy_refs: tuple[str, ...]
    export_policy: str = "not-required"
    redaction_policy: str | None = None
    capture_spec_ref: str = ""
    capture_requirement_ref: str = ""


def _sdl_capture_demand(name: str, requirement: EvidenceRequirement) -> CaptureDemand:
    channel = _value(requirement.channel)
    window_kinds = tuple(
        value
        for value in (
            requirement.window,
            "event" if requirement.trigger_ref else "",
            requirement.boundary_kind,
        )
        if value
    )
    redaction = _value(requirement.redaction)
    disclosure = "full" if redaction == "none" else "redacted"
    return CaptureDemand(
        demand_id=name,
        address=f"evidence_requirements.{name}",
        output_contract=requirement.output_contract,
        field_selectors=tuple(requirement.field_selectors),
        artifact_roles=(requirement.artifact_role,) if requirement.artifact_role else (),
        media_types=tuple(requirement.media_types),
        capture_kind=_CHANNEL_CAPTURE_KIND.get(channel, ""),
        source_classes=(_value(requirement.source_class),) if requirement.source_class is not None else (),
        source_refs=tuple(requirement.source_refs),
        scopes=(requirement.scope,) if requirement.scope else (),
        scope_refs=tuple(requirement.scope_refs),
        channel_kinds=(_CHANNEL_MANIFEST_KIND[channel],) if channel else (),
        channel_refs=tuple(requirement.channel_refs),
        window_kinds=window_kinds,
        integrity_modes=(_value(requirement.integrity),),
        sensitivity=_value(requirement.sensitivity),
        disclosure=disclosure,
        retention_policy_refs=(_value(requirement.retention),),
        redaction_policy=None if redaction == "none" else redaction,
        capture_spec_ref=requirement.capture_spec_ref,
        capture_requirement_ref=requirement.capture_requirement_ref,
    )


def compile_scenario_capture_demands(scenario: ScenarioContent) -> tuple[CaptureDemand, ...]:
    """Compile only explicit SDL evidence requirements into stable demand."""

    return tuple(
        _sdl_capture_demand(name, scenario.evidence_requirements[name])
        for name in sorted(scenario.evidence_requirements)
    )


def compile_capture_spec_demands(
    capture_specs: tuple[ExperimentCaptureSpecModel, ...],
) -> tuple[CaptureDemand, ...]:
    """Compile exact experiment capture specifications into stable demand."""

    demands: list[CaptureDemand] = []
    for capture_spec in sorted(capture_specs, key=lambda item: (item.capture_spec_id, item.spec_version)):
        windows = {window.window_id: window.window_kind for window in capture_spec.capture_windows}
        for requirement_id in sorted(capture_spec.capture_requirements):
            requirement = capture_spec.capture_requirements[requirement_id]
            demands.append(
                CaptureDemand(
                    demand_id=requirement.requirement_id,
                    address=(f"capture_specs.{capture_spec.capture_spec_id}.capture_requirements.{requirement_id}"),
                    output_contract=requirement.output_contract,
                    field_selectors=tuple(requirement.field_selectors),
                    artifact_roles=tuple(requirement.required_artifact_roles),
                    media_types=tuple(requirement.expected_media_types),
                    capture_kind=requirement.capture_kind,
                    source_classes=(),
                    source_refs=(),
                    scopes=(requirement.capture_scope,),
                    scope_refs=(),
                    channel_kinds=(),
                    channel_refs=(requirement.channel_ref.ref_id,),
                    window_kinds=tuple(sorted({windows[window_ref] for window_ref in requirement.window_refs})),
                    integrity_modes=tuple(requirement.integrity_requirements),
                    sensitivity=requirement.sensitivity,
                    disclosure=(
                        "redacted"
                        if requirement.redaction_policy is not None or requirement.sensitivity == "redacted"
                        else "full"
                    ),
                    retention_policy_refs=(
                        (requirement.retention_policy,) if requirement.retention_policy is not None else ()
                    ),
                    redaction_policy=requirement.redaction_policy,
                )
            )
    return tuple(demands)


def _subset(required: tuple[str, ...], supported: frozenset[str]) -> bool:
    return not required or "*" in supported or set(required).issubset(supported)


def _offer_failures(demand: CaptureDemand, offer: ObservationCaptureOffer) -> tuple[str, ...]:
    failures = [
        *_offer_quality_failures(demand, offer),
        *_offer_content_failures(demand, offer),
        *_offer_dimension_failures(demand, offer),
        *_offer_policy_failures(demand, offer),
    ]
    return tuple(sorted(failures))


def _offer_quality_failures(demand: CaptureDemand, offer: ObservationCaptureOffer) -> list[str]:
    failures: list[str] = []
    if offer.availability != "available":
        failures.append("availability-insufficient")
    if offer.fidelity != "complete":
        failures.append("fidelity-insufficient")
    if offer.disclosure != demand.disclosure:
        failures.append("disclosure-insufficient")
    if offer.redaction_policy != demand.redaction_policy:
        failures.append("redaction-policy-mismatch")
    return failures


def _offer_content_failures(demand: CaptureDemand, offer: ObservationCaptureOffer) -> list[str]:
    failures: list[str] = []
    if demand.output_contract and offer.output_contract != demand.output_contract:
        failures.append("output-contract-mismatch")
    if (
        demand.field_selectors
        and "" not in offer.field_selectors
        and not set(demand.field_selectors).issubset(offer.field_selectors)
    ):
        failures.append("field-selector-missing")
    if demand.capture_kind and offer.capture_kind != demand.capture_kind:
        failures.append("capture-kind-mismatch")
    return failures


def _offer_dimension_failures(demand: CaptureDemand, offer: ObservationCaptureOffer) -> list[str]:
    failures: list[str] = []
    dimensions = (
        ("artifact-role-mismatch", demand.artifact_roles, offer.artifact_roles),
        ("source-class-mismatch", demand.source_classes, offer.source_classes),
        ("source-ref-mismatch", demand.source_refs, offer.source_refs),
        ("scope-mismatch", demand.scopes, offer.scopes),
        ("channel-mismatch", demand.channel_kinds, offer.channel_kinds),
        ("channel-ref-mismatch", demand.channel_refs, offer.channel_refs),
        ("window-mismatch", demand.window_kinds, offer.window_kinds),
        ("integrity-mismatch", demand.integrity_modes, offer.integrity_modes),
        ("retention-mismatch", demand.retention_policy_refs, offer.retention_policy_refs),
    )
    for failure, required, supported in dimensions:
        if not _subset(required, supported):
            failures.append(failure)
    return failures


def _offer_policy_failures(demand: CaptureDemand, offer: ObservationCaptureOffer) -> list[str]:
    failures: list[str] = []
    if demand.scope_refs and not set(demand.scope_refs).issubset(offer.scope_refs):
        failures.append("scope-ref-mismatch")
    if demand.media_types and not set(demand.media_types).intersection(offer.media_types):
        failures.append("media-type-mismatch")
    if demand.sensitivity and offer.sensitivity != "*" and demand.sensitivity != offer.sensitivity:
        failures.append("sensitivity-mismatch")
    if demand.export_policy != "not-required" and demand.export_policy != offer.export_policy:
        failures.append("export-policy-mismatch")
    return failures


def _diagnostic(demand: CaptureDemand, failure: str) -> Diagnostic:
    return Diagnostic(
        code=f"capture.{failure}",
        domain="capture",
        address=demand.address,
        message=f"Required capture {demand.demand_id!r} is not covered: {failure.replace('-', ' ')}.",
        severity=Severity.ERROR,
    )


def capture_admission_diagnostics(
    demands: tuple[CaptureDemand, ...],
    observation: ObservationCapabilities | None,
) -> list[Diagnostic]:
    """Return every unmet demand deterministically without combining offers."""

    diagnostics: list[Diagnostic] = []
    offers = () if observation is None else observation.capture_offers
    for demand in sorted(demands, key=lambda item: (item.address, item.demand_id)):
        if demand.capture_spec_ref or demand.capture_requirement_ref:
            diagnostics.append(_diagnostic(demand, "reference-unresolved"))
            continue
        if not offers:
            diagnostics.append(_diagnostic(demand, "offer-missing"))
            continue
        failures_by_offer = tuple(
            sorted(
                ((_offer_failures(demand, offer), offer.offer_id) for offer in offers),
                key=lambda item: (len(item[0]), item[0], item[1]),
            )
        )
        best_failures = failures_by_offer[0][0]
        if not best_failures:
            continue
        diagnostics.extend(_diagnostic(demand, failure) for failure in best_failures)
    return diagnostics


__all__ = [
    "CaptureDemand",
    "capture_admission_diagnostics",
    "compile_capture_spec_demands",
    "compile_scenario_capture_demands",
]
