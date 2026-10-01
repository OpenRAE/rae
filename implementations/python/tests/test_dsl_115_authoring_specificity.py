"""DSL-115 author-selectable specificity over owned concern surfaces."""

from __future__ import annotations

import textwrap

from raes import parse_sdl
from raes.explicitness import ExplicitnessClass, classify_authoring_specificity
from raes_contracts.contracts import ExperimentReferenceModel


def _scenario_with_specificity_levels():
    return parse_sdl(
        textwrap.dedent("""
        name: dsl-115-specificity
        version: ${scenario_version}
        variables:
          scenario_version:
            type: string
            default: 1.0.0
            allowed_values: [1.0.0, 1.1.0]
          participant_label:
            type: string
            default: red operator
            allowed_values: [red operator, autonomous red team]
        entities:
          red:
            role: red
        agents:
          red-agent:
            affiliations: [red]
            description: ${participant_label}
        propositions:
          objective-complete:
            description: The red participant has completed the governed assessment activity.
            subjects: [entities.red]
            basis: declared_state
            predicate:
              kind: boolean
              property: assessment-complete
              semantic_ref: urn:raes:declared-property:assessment-complete
              operator: equals
              expected: true
        assertions:
          objective-complete:
            description: Assessment completion is required at the objective boundary.
            proposition: objective-complete
            role: postcondition
            polarity: positive
        objectives:
          assess:
            assigned_participant: red-agent
            success:
              assertions: [objective-complete]
        """)
    )


def test_specificity_does_not_treat_missing_fields_as_open_by_default():
    result = classify_authoring_specificity(_scenario_with_specificity_levels())

    assert "agents.red-agent.initial_knowledge" not in result.records
    assert "objectives.assess.window" not in result.records


def test_specificity_classifies_scenario_participant_and_evaluation_concerns():
    result = classify_authoring_specificity(
        _scenario_with_specificity_levels(),
        admitted_open_paths=(
            "version",
            "objectives.assess.success.assertions[0]",
            "agents.red-agent.initial_knowledge",
            "objectives.assess.window",
        ),
    )

    assert result.records["version"].classification is ExplicitnessClass.CONSTRAINED
    assert result.records["agents.red-agent.description"].classification is ExplicitnessClass.CONSTRAINED
    assert result.records["objectives.assess.success.assertions[0]"].classification is ExplicitnessClass.EXACT
    assert result.records["agents.red-agent.initial_knowledge"].classification is ExplicitnessClass.OPEN
    assert result.records["objectives.assess.window"].classification is ExplicitnessClass.OPEN


def test_specificity_rejects_admitted_open_paths_outside_model_surface():
    result = classify_authoring_specificity(
        _scenario_with_specificity_levels(),
        admitted_open_paths=(
            "agents.red-agent.initialKnowlege",
            "agents.ghost.initial_knowledge",
            "objectives.assess.window",
        ),
    )

    assert "agents.red-agent.initialKnowlege" not in result.records
    assert "agents.ghost.initial_knowledge" not in result.records
    assert result.records["objectives.assess.window"].classification is ExplicitnessClass.OPEN
    assert result.errors == (
        "Cannot classify open specificity for 'agents.red-agent.initialKnowlege': "
        "path does not resolve to a model surface",
        "Cannot classify open specificity for 'agents.ghost.initial_knowledge': "
        "path does not resolve to a model surface",
    )


def test_specificity_classifies_experiment_contract_concerns_without_new_sdl_syntax():
    reference = ExperimentReferenceModel(ref_kind="scenario", ref_id="benchmark-a")

    result = classify_authoring_specificity(reference, admitted_open_paths=("ref_version",))

    assert result.records["ref_kind"].classification is ExplicitnessClass.EXACT
    assert result.records["ref_id"].classification is ExplicitnessClass.EXACT
    assert result.records["ref_version"].classification is ExplicitnessClass.OPEN
    assert "ref_digest" not in result.records
