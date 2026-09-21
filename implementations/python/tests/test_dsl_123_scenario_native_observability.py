"""DSL-123 scenario-native observability SDL semantics."""

from __future__ import annotations

import pytest
from raes._errors import SDLValidationError
from raes._runtime_service_families import RUNTIME_SERVICE_FAMILIES, collect_qualified_runtime_family_refs
from raes.observability_plane_semantics import (
    SCENARIO_NATIVE_OBSERVABILITY_FAMILIES,
    ObservabilityEvidencePlane,
    classify_runtime_family,
    collect_scenario_native_observability_refs,
)
from raes.scenario import Scenario
from raes.validator import SemanticValidator

OBSERVABILITY_REF = "nodes.siem.runtime.service_listeners.siem-http"
NON_OBSERVABILITY_REF = "nodes.siem.runtime.applications.admin-ui"


def _scenario(*, objective_target: str = OBSERVABILITY_REF, interaction_target: str = OBSERVABILITY_REF) -> Scenario:
    return Scenario(
        name="dsl-123",
        nodes={
            "siem": {
                "type": "compute",
                "resources": {"ram": "1 gib", "cpu": 1},
                "services": [{"port": 80, "protocol": "tcp", "name": "http"}],
                "runtime": {
                    "service_listeners": [
                        {
                            "service_listener_id": "siem-http",
                            "service": "http",
                            "address": "0.0.0.0",  # noqa: S104 - wildcard bind is test data.
                            "port": 80,
                            "protocol": "tcp",
                            "address_family": "ipv4",
                            "scope": "wildcard",
                        }
                    ],
                    "applications": [{"application_id": "admin-ui", "service": "http"}],
                },
            }
        },
        entities={"blue": {"role": "blue"}},
        conditions={
            "observability-ready": {
                "command": "/bin/true",
                "interval": 15,
                "proposition": "observability-inspected",
            }
        },
        evidence_requirements={
            "inspection-record": {
                "description": "Record whether the participant inspected the governed observability endpoint.",
                "source_refs": [OBSERVABILITY_REF],
                "scope_refs": ["nodes.siem"],
                "trigger_ref": "conditions.observability-ready",
                "channel": "log",
                "artifact_role": "proposition_truth_evidence",
                "media_types": ["application/json"],
                "sensitivity": "plain",
                "redaction": "none",
                "integrity": "checksum",
                "retention": "study_lifetime",
                "loss_disclosure": "required",
            }
        },
        propositions={
            "observability-inspected": {
                "description": "The participant inspected the governed observability endpoint.",
                "subjects": [OBSERVABILITY_REF],
                "basis": "observed_state",
                "predicate": {
                    "kind": "boolean",
                    "property": "participant-inspected",
                    "semantic_ref": "urn:raes:observable:participant-inspected",
                    "operator": "equals",
                    "expected": True,
                },
                "evidence_requirements": ["inspection-record"],
            }
        },
        assertions={
            "observability-inspected": {
                "description": "Inspection must be observed at the objective boundary.",
                "proposition": "observability-inspected",
                "role": "postcondition",
                "polarity": "positive",
            }
        },
        relationships={
            "dashboard-depends-on-listener": {
                "type": "depends_on",
                "source": "nodes.siem",
                "target": OBSERVABILITY_REF,
            }
        },
        action_contracts={
            "inspect-dashboard": {
                "semantic_version": "1.0.0",
                "behavioral_granularity": "atomic",
                "procedure_basis": "participant inspects an in-world monitoring endpoint",
                "realization_profile": "backend-declared",
                "fidelity_claim": "records the participant interaction target only",
                "preconditions": [
                    {
                        "precondition_id": "authority-in-scope",
                        "precondition_class": "authority",
                        "description": "the participant is allowed to inspect the monitoring endpoint",
                        "support_refs": ["agents.blue-agent", interaction_target],
                    }
                ],
                "effects": [
                    {
                        "effect_id": "observability-endpoint-inspected",
                        "effect_class": "intended_effect",
                        "description": "the participant inspects the in-world observability endpoint",
                        "target_refs": [interaction_target],
                    }
                ],
                "failure_classes": ["precondition_unsatisfied", "target_unavailable"],
                "interactions": [
                    {
                        "interaction_class": "shared_state_change",
                        "target": interaction_target,
                        "rationale": "the participant interacts with the in-world observability service",
                        "shared_state_refs": [interaction_target],
                    }
                ],
            }
        },
        agents={"blue-agent": {"affiliations": ["blue"], "actions": ["inspect-dashboard"]}},
        objectives={
            "inspect-observability": {
                "owner": "blue",
                "actions": ["inspect-dashboard"],
                "targets": [objective_target],
                "success": {"assertions": ["observability-inspected"]},
            }
        },
    )


def _validate(scenario: Scenario) -> list[str]:
    validator = SemanticValidator(scenario)
    try:
        validator.validate()
        return []
    except SDLValidationError as exc:
        return exc.errors


def test_dsl_123_exposes_scenario_native_observability_refs_without_second_resolver() -> None:
    registered = {family.collection_name for family in RUNTIME_SERVICE_FAMILIES}
    assert registered >= SCENARIO_NATIVE_OBSERVABILITY_FAMILIES
    assert classify_runtime_family("service_listeners") is ObservabilityEvidencePlane.SCENARIO_NATIVE_OBSERVABILITY

    scenario = _scenario()
    all_runtime_refs = collect_qualified_runtime_family_refs(scenario)
    observability_refs = collect_scenario_native_observability_refs(scenario)

    assert OBSERVABILITY_REF in observability_refs
    assert NON_OBSERVABILITY_REF in all_runtime_refs
    assert NON_OBSERVABILITY_REF not in observability_refs
    assert observability_refs <= all_runtime_refs


def test_dsl_123_observability_refs_are_targetable_relationship_objective_and_action_refs() -> None:
    assert _validate(_scenario()) == []


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("objective", "Objective 'inspect-observability' target 'siem-http' does not reference any defined"),
        ("interaction", "Action contract 'inspect-dashboard' interaction[0] target 'siem-http' does not reference"),
    ],
)
def test_dsl_123_observability_refs_do_not_resolve_by_bare_runtime_id(field: str, expected: str) -> None:
    if field == "objective":
        scenario = _scenario(objective_target="siem-http")
    else:
        scenario = _scenario(interaction_target="siem-http")

    errors = _validate(scenario)

    assert any(expected in error for error in errors)
