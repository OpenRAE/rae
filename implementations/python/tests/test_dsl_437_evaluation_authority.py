"""DSL-437 declared evaluation-authority reference semantics."""

from __future__ import annotations

import pytest
import yaml
from raes._errors import SDLValidationError
from raes.parser import parse_sdl
from raes_processor.compiler import compile_runtime_model
from test_dsl_437_benign_participant_execution import _scenario_yaml


def _declared_authority_yaml(authority: dict[str, object]) -> str:
    payload = yaml.safe_load(_scenario_yaml())
    payload["objectives"] = {
        "benign-probe": {
            "assigned_participant": "participant-agent",
            "actions": ["probe-customer-portal-login"],
            "targets": ["nodes.customer-portal.services.http"],
            "success": {"assertions": ["participant-observation-recorded"]},
        }
    }
    payload["behavior_specifications"]["participant-behavior"]["autonomous_execution"]["evaluation_authority"] = {
        "mode": "declared",
        **authority,
    }
    return yaml.safe_dump(payload, sort_keys=False)


@pytest.mark.parametrize("objective_ref", ["benign-probe", "objectives.benign-probe"])
def test_declared_objective_refs_compile_to_canonical_evaluator_addresses(
    objective_ref: str,
) -> None:
    scenario = parse_sdl(
        _declared_authority_yaml(
            {"objective_refs": [objective_ref]},
        )
    )

    runtime_model = compile_runtime_model(scenario)
    policy = runtime_model.behavior_specifications[
        "participant.behavior-specification.participant-behavior"
    ].autonomous_execution

    assert policy is not None
    assert policy.objective_refs == ("evaluation.objective.benign-probe",)
    assert "evaluation.objective.benign-probe" in policy.refresh_dependencies


def test_declared_objective_ref_must_resolve() -> None:
    scenario_yaml = _declared_authority_yaml({"objective_refs": ["does-not-exist"]})

    with pytest.raises(
        SDLValidationError,
        match="evaluation-authority objective_ref 'does-not-exist' is not declared in objectives",
    ):
        parse_sdl(scenario_yaml)


@pytest.mark.parametrize(
    ("field_name", "ref"),
    [
        ("proof_producer_refs", "proof-producer.unknown"),
        ("score_authority_refs", "score-authority.unknown"),
        ("receipt_authority_refs", "receipt-authority.unknown"),
    ],
)
def test_declared_authority_namespaces_without_sdl_registries_fail_closed(
    field_name: str,
    ref: str,
) -> None:
    scenario_yaml = _declared_authority_yaml({field_name: [ref]})

    with pytest.raises(
        SDLValidationError,
        match=rf"evaluation-authority {field_name} ref '{ref}' cannot resolve",
    ):
        parse_sdl(scenario_yaml)
