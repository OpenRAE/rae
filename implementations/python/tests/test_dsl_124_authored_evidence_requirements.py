"""DSL-124 authored evidence requirement SDL semantics."""

from __future__ import annotations

import pytest
from raes._errors import SDLParseError, SDLValidationError
from raes.observability_plane_semantics import (
    ObservabilityEvidencePlane,
    classify_sdl_section_plane,
    collect_scenario_native_observability_refs,
)
from raes.parser import parse_sdl

OBSERVABILITY_REF = "nodes.siem.runtime.service_listeners.siem-http"


def _scenario_yaml(*, source_ref: str = OBSERVABILITY_REF, trigger: str | None = "conditions.capture-open") -> str:
    trigger_line = f"        trigger_ref: {trigger}\n" if trigger is not None else ""
    return f"""
    name: dsl-124
    nodes:
      siem:
        type: compute
        resources:
          ram: 1 gib
          cpu: 1
        services:
          - name: http
            port: 80
            protocol: tcp
        runtime:
          service_listeners:
            - service_listener_id: siem-http
              service: http
              address: 0.0.0.0
              port: 80
              protocol: tcp
              address_family: ipv4
              scope: wildcard
    conditions:
      capture-open:
        command: /bin/true
        interval: 15
    entities:
      blue:
        role: blue
    evidence_requirements:
      network-trace:
        description: Capture the SIEM listener output without creating a participant objective.
        source_refs:
          - {source_ref}
        scope_refs:
          - nodes.siem
{trigger_line}        channel: packet_capture
        artifact_role: network_trace
        media_types:
          - application/vnd.tcpdump.pcap
        sensitivity: plain
        redaction: none
        integrity: checksum
        retention: study_lifetime
        loss_disclosure: required
    """


def test_dsl_124_accepts_authored_evidence_requirement_independent_of_objectives() -> None:
    scenario = parse_sdl(_scenario_yaml())

    requirement = scenario.evidence_requirements["network-trace"]

    assert scenario.objectives == {}
    assert requirement.source_refs == [OBSERVABILITY_REF]
    assert requirement.scope_refs == ["nodes.siem"]
    assert requirement.trigger_ref == "conditions.capture-open"
    assert classify_sdl_section_plane("evidence_requirements") is (
        ObservabilityEvidencePlane.AUTHORED_EVIDENCE_REQUIREMENT
    )
    assert OBSERVABILITY_REF in collect_scenario_native_observability_refs(scenario)


def test_dsl_124_evidence_requirements_are_not_objective_targets() -> None:
    payload = (
        _scenario_yaml()
        + """
    objectives:
      capture-the-trace:
        owner: blue
        targets:
          - evidence_requirements.network-trace
        success:
          assertions:
            - trace-captured
    propositions:
      trace-captured:
        description: The governed network trace was captured.
        subjects:
          - nodes.siem
        basis: observed_state
        predicate:
          kind: boolean
          property: network-trace-captured
          semantic_ref: urn:raes:observable:network-trace-captured
          operator: equals
          expected: true
        evidence_requirements:
          - network-trace
    assertions:
      trace-captured:
        description: Trace capture must be observed at the objective boundary.
        proposition: trace-captured
        role: postcondition
        polarity: positive
    """
    )

    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(payload)

    assert any(
        "Objective 'capture-the-trace' target 'evidence_requirements.network-trace' does not reference any defined"
        in error
        for error in excinfo.value.errors
    )


def test_dsl_124_rejects_capture_requirement_without_window_trigger_or_boundary() -> None:
    with pytest.raises(SDLParseError, match="window, trigger_ref, boundary_ref, or boundary_kind"):
        parse_sdl(_scenario_yaml(trigger=None))


@pytest.mark.parametrize(
    ("source_ref", "expected"),
    [
        ("nodes.missing", "source_ref 'nodes.missing' does not reference any defined targetable element"),
        ("siem-http", "source_ref 'siem-http' does not reference any defined targetable element"),
    ],
)
def test_dsl_124_source_refs_fail_closed(source_ref: str, expected: str) -> None:
    with pytest.raises(SDLValidationError) as excinfo:
        parse_sdl(_scenario_yaml(source_ref=source_ref))

    assert any(expected in error for error in excinfo.value.errors)
