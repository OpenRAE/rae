"""Deterministic required-capture projection and backend admission."""

from __future__ import annotations

from dataclasses import dataclass

from raes.evidence_requirements import EvidenceRequirement
from raes.scenario import ScenarioContent
from raes_backend_protocols.capabilities import ObservationCapabilities, ObservationCaptureOffer
from raes_contracts.capture_dimensions import CAPTURE_DIMENSIONS, project_capture_dimensions
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
        **project_capture_dimensions(
            requirement,
            source="sdl",
            overrides={
                "capture_kind": _CHANNEL_CAPTURE_KIND.get(channel, ""),
                "channel_kinds": (_CHANNEL_MANIFEST_KIND[channel],) if channel else (),
                "window_kinds": window_kinds,
                "disclosure": disclosure,
                "redaction_policy": None if redaction == "none" else redaction,
            },
        ),
        capture_spec_ref=requirement.capture_spec_ref,
        capture_requirement_ref=requirement.capture_requirement_ref,
    )


def compile_scenario_capture_demands(scenario: ScenarioContent) -> tuple[CaptureDemand, ...]:
    """Compile mandatory SDL evidence requirements into stable capture demand.

    A scoped observation rule owns whether its selected observation is a
    mandatory capability-admission obligation.  Requirements without that
    newer policy carrier retain the historical required-capture behavior.
    """

    return tuple(
        _sdl_capture_demand(name, scenario.evidence_requirements[name])
        for name in sorted(scenario.evidence_requirements)
        if scenario.evidence_requirements[name].observation_demand is None
        or scenario.evidence_requirements[name].observation_demand.required
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
                    **project_capture_dimensions(
                        requirement,
                        source="capture",
                        overrides={
                            "channel_refs": (requirement.channel_ref.ref_id,),
                            "window_kinds": tuple(sorted({windows[ref] for ref in requirement.window_refs})),
                            "disclosure": (
                                "redacted"
                                if requirement.redaction_policy is not None or requirement.sensitivity == "redacted"
                                else "full"
                            ),
                        },
                    ),
                )
            )
    return tuple(demands)


def _offer_failures(demand: CaptureDemand, offer: ObservationCaptureOffer) -> tuple[str, ...]:
    return tuple(
        sorted(
            dimension.diagnostic
            for dimension in CAPTURE_DIMENSIONS
            if not dimension.matches(
                dimension.required_value if dimension.required_value is not None else getattr(demand, dimension.name),
                getattr(offer, dimension.name),
            )
        )
    )


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
