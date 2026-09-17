"""Tests for the SDL scenario loading boundary."""

import pytest
from paths import EXAMPLES_DIR

VALID_SDL = """
name: test-scenario
description: Minimal SDL scenario
"""
REFERENCE_SCENARIO = EXAMPLES_DIR / "enterprise-participant-evidence-loop.sdl.yaml"
COMPLEX_EXAMPLES = [
    EXAMPLES_DIR / "hospital-ransomware-surgery-day.sdl.yaml",
    EXAMPLES_DIR / "satcom-release-poisoning.sdl.yaml",
    EXAMPLES_DIR / "port-authority-surge-response.sdl.yaml",
]


class TestLoadScenario:
    """Tests for loading SDL scenarios from YAML files."""

    def test_load_valid_sdl(self, tmp_path):
        from raes.scenarios import load_scenario

        path = tmp_path / "scenario.yaml"
        path.write_text(VALID_SDL, encoding="utf-8")

        scenario = load_scenario(path)
        assert scenario.name == "test-scenario"
        assert scenario.description == "Minimal SDL scenario"

    def test_load_nonexistent_file_raises(self, tmp_path):
        from raes.scenarios import load_scenario

        with pytest.raises(FileNotFoundError):
            load_scenario(tmp_path / "missing.yaml")

    def test_load_empty_file_raises_validation_error(self, tmp_path):
        from raes.scenarios import ScenarioValidationError, load_scenario

        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")

        with pytest.raises(ScenarioValidationError, match="empty"):
            load_scenario(path)

    def test_load_invalid_yaml_raises_validation_error(self, tmp_path):
        from raes.scenarios import ScenarioValidationError, load_scenario

        path = tmp_path / "broken.yaml"
        path.write_text("{{not: valid: yaml: [}", encoding="utf-8")

        with pytest.raises(ScenarioValidationError, match="Invalid YAML"):
            load_scenario(path)

    def test_load_legacy_yaml_is_rejected(self, tmp_path):
        from raes.scenarios import ScenarioValidationError, load_scenario

        path = tmp_path / "legacy.yaml"
        path.write_text(
            """
metadata:
  id: old-scenario
  name: Old Scenario
mode: red
            """.strip(),
            encoding="utf-8",
        )

        # Match against the legacy-format fingerprint (the `metadata` /
        # `mode` extra-field rejection that distinguishes the old SDL shape
        # from a generic invalid scenario) so the test fails if the legacy-
        # detection path is removed but the YAML keeps being rejected for
        # an unrelated reason.
        with pytest.raises(ScenarioValidationError, match=r"(?s)(metadata|mode).*Extra inputs"):
            load_scenario(path)

    def test_validation_error_includes_path(self, tmp_path):
        from raes.scenarios import ScenarioValidationError, load_scenario

        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")

        with pytest.raises(ScenarioValidationError) as exc_info:
            load_scenario(path)

        assert exc_info.value.path == path
        assert str(path) in str(exc_info.value)


class TestFindScenarios:
    """Tests for SDL scenario discovery."""

    def test_finds_yaml_files(self, tmp_path):
        from raes.scenarios import find_scenarios

        (tmp_path / "a.yaml").write_text(VALID_SDL, encoding="utf-8")
        (tmp_path / "b.yaml").write_text(VALID_SDL, encoding="utf-8")

        paths = find_scenarios(tmp_path)
        assert [path.name for path in paths] == ["a.yaml", "b.yaml"]

    def test_ignores_non_yaml_files(self, tmp_path):
        from raes.scenarios import find_scenarios

        (tmp_path / "a.yml").write_text(VALID_SDL, encoding="utf-8")
        (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")

        assert find_scenarios(tmp_path) == []

    def test_returns_empty_for_missing_directory(self, tmp_path):
        from raes.scenarios import find_scenarios

        assert find_scenarios(tmp_path / "missing") == []


@pytest.mark.parametrize("path", COMPLEX_EXAMPLES, ids=lambda path: path.name)
def test_complex_examples_have_experiment_semantics(path):
    """Curated complex examples should exercise the full experiment surface."""
    from raes.scenarios import load_scenario

    scenario = load_scenario(path)

    assert scenario.objectives
    assert scenario.agents
    assert scenario.relationships
    assert scenario.content
    assert scenario.stories
    # Post ADR-079: objective success references backend-neutral assertions.
    assert scenario.propositions
    assert scenario.assertions
    assert any(objective.success.assertions for objective in scenario.objectives.values())


def test_complex_examples_cover_new_sdl_surfaces():
    """Complex examples should exercise workflows, enum vars, and direct refs."""
    from raes.scenarios import load_scenario

    satcom = load_scenario(EXAMPLES_DIR / "satcom-release-poisoning.sdl.yaml")
    assert satcom.workflows
    assert any(
        step.type.value == "parallel" for workflow in satcom.workflows.values() for step in workflow.steps.values()
    )
    assert any(acct.password_strength == "${release_engineer_password_strength}" for acct in satcom.accounts.values())

    hospital = load_scenario(EXAMPLES_DIR / "hospital-ransomware-surgery-day.sdl.yaml")
    assert hospital.nodes["ad01"].runtime.identity_authorities
    assert any(
        target.startswith("nodes.") for objective in hospital.objectives.values() for target in objective.targets
    )
    assert any(
        target.startswith("infrastructure.")
        for objective in hospital.objectives.values()
        for target in objective.targets
    )

    port = load_scenario(EXAMPLES_DIR / "port-authority-surge-response.sdl.yaml")
    assert port.workflows
    assert any(
        step.type.value == "parallel" for workflow in port.workflows.values() for step in workflow.steps.values()
    )
    assert any(target.startswith("nodes.") for objective in port.objectives.values() for target in objective.targets)
    assert any(
        target.startswith("infrastructure.") for objective in port.objectives.values() for target in objective.targets
    )


def test_reference_scenario_compiles_participant_loop():
    """Issue #598: the reference scenario proves the participant handoff surface."""
    from raes.scenarios import load_scenario
    from raes_processor.compiler import compile_runtime_model

    scenario = load_scenario(REFERENCE_SCENARIO)
    model = compile_runtime_model(scenario)

    assert {
        "red-workbench",
        "customer-portal",
        "customer-db",
        "wazuh-manager",
        "wazuh-indexer",
        "participant-policy-gate",
    } <= set(scenario.nodes)
    assert set(scenario.infrastructure["red-workbench"].links) == {"redteam-net", "dmz-net"}
    assert set(scenario.infrastructure["customer-portal"].links) == {"dmz-net", "internal-net"}
    assert scenario.infrastructure["customer-db"].links == ["internal-net"]
    assert set(scenario.infrastructure["wazuh-manager"].links) == {"security-net", "internal-net"}
    assert scenario.infrastructure["wazuh-indexer"].links == ["security-net"]
    assert scenario.infrastructure["participant-policy-gate"].links == ["security-net"]

    assert {
        "participant-observation",
        "wazuh-evidence",
        "policy-decision-log",
        "boundary-check-evidence",
    } <= set(scenario.content)
    assert scenario.agents["participant-agent"].actions == ["probe-customer-portal-login"]
    assert scenario.agents["participant-agent"].allowed_subnets == ["dmz-net"]
    assert set(scenario.agents["participant-agent"].operating_scope) == {
        "nodes.customer-portal.services.http",
        "content.task-brief",
    }

    contract = scenario.action_contracts["probe-customer-portal-login"]
    assert {effect.effect_id for effect in contract.effects} >= {
        "wazuh-evidence-retained",
        "policy-decision-retained",
        "boundary-checks-retained",
        "internal-db-not-disclosed",
        "wazuh-internals-not-disclosed",
    }

    boundary = scenario.observation_boundaries["participant-view"]
    assert "nodes.customer-db.services.postgres" in boundary.hidden_refs
    assert "nodes.wazuh-manager" in boundary.hidden_refs
    assert "nodes.wazuh-indexer" in boundary.hidden_refs
    assert "nodes.participant-policy-gate" in boundary.hidden_refs
    assert {
        "content.participant-observation",
        "content.wazuh-evidence",
        "content.policy-decision-log",
        "content.boundary-check-evidence",
    } <= set(boundary.evidence_refs)

    assert model.participant_behaviors
    assert model.action_contracts
    assert model.observation_boundaries
    assert "participant.behavior.participant-agent" in model.participant_behaviors
    assert "participant.action-contract.probe-customer-portal-login" in model.action_contracts
    assert "participant.observation-boundary.participant-view" in model.observation_boundaries


class TestScenarioExceptions:
    """Tests for shared scenario exception types."""

    def test_scenario_not_found_error(self):
        from raes.scenarios import ScenarioError, ScenarioNotFoundError

        error = ScenarioNotFoundError("example")
        assert error.identifier == "example"
        assert isinstance(error, ScenarioError)

    def test_scenario_validation_error_without_path(self):
        from raes.scenarios import ScenarioError, ScenarioValidationError

        error = ScenarioValidationError("bad field")
        assert error.path is None
        assert error.details == "bad field"
        assert isinstance(error, ScenarioError)
