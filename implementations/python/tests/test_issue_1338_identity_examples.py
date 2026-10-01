"""Published scenarios retain declared intent through the identity migration."""

from pathlib import Path

import pytest
from raes import parse_sdl_file
from raes_processor.compiler import compile_scenario_runtime_model

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "name", ["hospital-ransomware-surgery-day", "port-authority-surge-response", "satcom-release-poisoning"]
)
def test_published_objective_actions_have_portable_abstract_contracts(name):
    scenario = parse_sdl_file(ROOT / "examples/scenarios" / f"{name}.sdl.yaml")
    compiled = compile_scenario_runtime_model(scenario)
    assert len(compiled.objectives) == len(scenario.objectives)
    for objective in scenario.objectives.values():
        assert set(objective.actions) <= set(scenario.action_contracts)
        if objective.assigned_participant:
            assert set(objective.actions) <= set(scenario.agents[objective.assigned_participant].actions)
    for contract in scenario.action_contracts.values():
        assert contract.realization_profile == "abstract"
        assert "no backend procedure" in contract.fidelity_claim
