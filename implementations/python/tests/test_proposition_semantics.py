"""Backend-neutral proposition and assertion semantics for issue #725."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from raes._errors import SDLParseError, SDLValidationError
from raes.parser import parse_sdl
from raes.propositions import (
    Assertion,
    AssertionPolarity,
    AssertionRole,
    BooleanPredicate,
    NumericPredicate,
    Proposition,
    PropositionBasis,
    StringPredicate,
    SubjectQuantifier,
    TruthCompositionMode,
)
from raes.semantics.propositions import (
    TruthValue,
    compose_truth,
    evaluate_assertion_polarity,
    negate_truth,
    quantify_subject_truth,
)
from raes_processor.compiler import compile_runtime_model


def test_proposition_is_inspectable_without_probe_execution() -> None:
    proposition = Proposition.model_validate(
        {
            "description": "The addressed service reports its governed availability state as available.",
            "subjects": ["nodes.web.services.http"],
            "basis": "observed_state",
            "predicate": {
                "kind": "string",
                "property": "service-availability",
                "semantic_ref": "urn:raes:observable:service-availability",
                "operator": "equals",
                "expected": "available",
            },
            "quantifier": "all",
            "evidence_requirements": ["service-health-evidence"],
        }
    )

    assert isinstance(proposition.predicate, StringPredicate)
    assert proposition.predicate.expected == "available"
    assert proposition.quantifier is SubjectQuantifier.ALL
    assert proposition.model_dump(mode="json") == {
        "description": "The addressed service reports its governed availability state as available.",
        "subjects": ["nodes.web.services.http"],
        "basis": "observed_state",
        "predicate": {
            "kind": "string",
            "property": "service-availability",
            "semantic_ref": "urn:raes:observable:service-availability",
            "operator": "equals",
            "expected": "available",
        },
        "quantifier": "all",
        "threshold": None,
        "evidence_requirements": ["service-health-evidence"],
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "description": "Observed property without evidence basis.",
                "subjects": ["nodes.web"],
                "basis": "observed_state",
                "predicate": {
                    "kind": "boolean",
                    "property": "reachable",
                    "semantic_ref": "urn:raes:observable:reachable",
                    "operator": "equals",
                    "expected": True,
                },
            },
            "observed-state propositions require at least one evidence requirement",
        ),
        (
            {
                "description": "An impossible finite threshold.",
                "subjects": ["nodes.web"],
                "basis": "declared_state",
                "predicate": {
                    "kind": "presence",
                    "property": "runtime",
                    "semantic_ref": "urn:raes:declared-property:runtime",
                    "operator": "exists",
                },
                "quantifier": "at_least",
                "threshold": 2,
            },
            "threshold cannot exceed the finite subject count",
        ),
    ],
)
def test_proposition_rejects_semantically_incomplete_shapes(payload: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Proposition.model_validate(payload)


def test_predicate_families_are_closed_and_type_specific() -> None:
    assert (
        BooleanPredicate.model_validate(
            {
                "kind": "boolean",
                "property": "reachable",
                "semantic_ref": "urn:raes:observable:reachable",
                "operator": "equals",
                "expected": False,
            }
        ).expected
        is False
    )
    assert (
        NumericPredicate.model_validate(
            {
                "kind": "number",
                "property": "packet-loss",
                "semantic_ref": "urn:raes:observable:packet-loss",
                "operator": "less_than_or_equal",
                "expected": 0.01,
                "unit": "ratio",
                "unit_semantic_ref": "urn:qudt:unit:UNITLESS",
            }
        ).expected
        == 0.01
    )

    with pytest.raises(ValidationError):
        BooleanPredicate.model_validate(
            {
                "kind": "boolean",
                "property": "reachable",
                "semantic_ref": "urn:raes:observable:reachable",
                "operator": "greater_than",
                "expected": 1,
            }
        )
    with pytest.raises(ValidationError):
        NumericPredicate.model_validate(
            {
                "kind": "number",
                "property": "packet-loss",
                "semantic_ref": "urn:raes:observable:packet-loss",
                "operator": "matches",
                "expected": ".*",
                "unit": "ratio",
                "unit_semantic_ref": "urn:qudt:unit:UNITLESS",
            }
        )


@pytest.mark.parametrize("expected", [float("nan"), float("inf"), float("-inf")])
def test_numeric_predicate_rejects_non_finite_operands(expected: float) -> None:
    with pytest.raises(ValidationError, match="must be finite"):
        NumericPredicate.model_validate(
            {
                "kind": "number",
                "property": "packet-loss",
                "semantic_ref": "urn:raes:observable:packet-loss",
                "operator": "less_than_or_equal",
                "expected": expected,
                "unit": "ratio",
                "unit_semantic_ref": "urn:qudt:unit:UNITLESS",
            }
        )


def test_assertion_carries_role_and_polarity_without_redefining_proposition() -> None:
    assertion = Assertion.model_validate(
        {
            "description": "The service must remain unavailable throughout the governed objective window.",
            "proposition": "service-available",
            "role": "invariant",
            "polarity": "negative",
        }
    )

    assert assertion.role is AssertionRole.INVARIANT
    assert assertion.polarity is AssertionPolarity.NEGATIVE
    assert assertion.proposition == "service-available"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (TruthValue.TRUE, TruthValue.FALSE),
        (TruthValue.FALSE, TruthValue.TRUE),
        (TruthValue.UNKNOWN, TruthValue.UNKNOWN),
        (TruthValue.UNSUPPORTED, TruthValue.UNSUPPORTED),
    ],
)
def test_negation_preserves_indeterminate_and_unsupported_outcomes(
    value: TruthValue,
    expected: TruthValue,
) -> None:
    assert negate_truth(value) is expected
    assert evaluate_assertion_polarity(value, AssertionPolarity.NEGATIVE) is expected


def test_finite_subject_quantifiers_use_the_portable_truth_tables() -> None:
    values = [TruthValue.TRUE, TruthValue.UNKNOWN, TruthValue.FALSE]

    assert quantify_subject_truth(values, quantifier=SubjectQuantifier.ALL) is TruthValue.FALSE
    assert quantify_subject_truth(values, quantifier=SubjectQuantifier.ANY) is TruthValue.TRUE
    assert quantify_subject_truth(values, quantifier=SubjectQuantifier.AT_LEAST, threshold=2) is TruthValue.UNKNOWN


@pytest.mark.parametrize(
    ("mode", "values", "threshold", "expected"),
    [
        (TruthCompositionMode.ALL_OF, [TruthValue.TRUE, TruthValue.TRUE], None, TruthValue.TRUE),
        (TruthCompositionMode.ALL_OF, [TruthValue.TRUE, TruthValue.FALSE], None, TruthValue.FALSE),
        (TruthCompositionMode.ALL_OF, [TruthValue.UNKNOWN, TruthValue.UNSUPPORTED], None, TruthValue.UNSUPPORTED),
        (TruthCompositionMode.ANY_OF, [TruthValue.FALSE, TruthValue.FALSE], None, TruthValue.FALSE),
        (TruthCompositionMode.ANY_OF, [TruthValue.UNKNOWN, TruthValue.TRUE], None, TruthValue.TRUE),
        (TruthCompositionMode.ANY_OF, [TruthValue.UNKNOWN, TruthValue.UNSUPPORTED], None, TruthValue.UNSUPPORTED),
        (
            TruthCompositionMode.AT_LEAST,
            [TruthValue.TRUE, TruthValue.FALSE, TruthValue.TRUE],
            2,
            TruthValue.TRUE,
        ),
        (
            TruthCompositionMode.AT_LEAST,
            [TruthValue.TRUE, TruthValue.FALSE, TruthValue.FALSE],
            2,
            TruthValue.FALSE,
        ),
        (
            TruthCompositionMode.AT_LEAST,
            [TruthValue.TRUE, TruthValue.UNKNOWN, TruthValue.FALSE],
            2,
            TruthValue.UNKNOWN,
        ),
        (
            TruthCompositionMode.AT_LEAST,
            [TruthValue.TRUE, TruthValue.UNSUPPORTED, TruthValue.FALSE],
            2,
            TruthValue.UNSUPPORTED,
        ),
    ],
)
def test_truth_composition_is_total_over_the_portable_outcome_domain(
    mode: TruthCompositionMode,
    values: list[TruthValue],
    threshold: int | None,
    expected: TruthValue,
) -> None:
    assert compose_truth(values, mode=mode, threshold=threshold) is expected


def test_truth_composition_rejects_empty_or_invalid_thresholds() -> None:
    with pytest.raises(ValueError, match="at least one truth value"):
        compose_truth([], mode=TruthCompositionMode.ALL_OF)
    with pytest.raises(ValueError, match="requires threshold"):
        compose_truth([TruthValue.TRUE], mode=TruthCompositionMode.AT_LEAST)
    with pytest.raises(ValueError, match="must not declare threshold"):
        compose_truth([TruthValue.TRUE], mode=TruthCompositionMode.ALL_OF, threshold=1)


def test_declared_state_can_be_decided_without_an_evidence_capture_requirement() -> None:
    proposition = Proposition(
        description="The admitted SDL declares an HTTP service on the addressed node.",
        subjects=["nodes.web"],
        basis=PropositionBasis.DECLARED_STATE,
        predicate={
            "kind": "presence",
            "property": "services.http",
            "semantic_ref": "urn:raes:declared-property:service",
            "operator": "exists",
        },
    )

    assert proposition.evidence_requirements == []


def _semantic_scenario(*, success_assertion: str = "service-ready") -> str:
    return f"""
name: proposition-semantics
nodes:
  web:
    type: compute
    resources: {{ram: 1 gib, cpu: 1}}
    conditions: {{http-health: ops}}
    roles: {{ops: operator}}
conditions:
  http-health:
    proposition: service-available
    command: /usr/local/bin/check-http
    interval: 15
entities:
  blue:
    role: blue
evidence_requirements:
  service-health-evidence:
    description: Capture the declared service state at the objective boundary.
    source_refs: [nodes.web]
    scope_refs: [nodes.web]
    boundary_kind: objective
    channel: log
    artifact_role: state_snapshot
    media_types: [application/json]
    sensitivity: plain
    redaction: none
    integrity: checksum
    retention: study_lifetime
    loss_disclosure: required
propositions:
  service-available:
    description: The addressed service reports availability as available.
    subjects: [nodes.web]
    basis: observed_state
    predicate:
      kind: string
      property: service-availability
      semantic_ref: urn:raes:observable:service-availability
      operator: equals
      expected: available
    evidence_requirements: [service-health-evidence]
assertions:
  service-ready:
    description: The service is available at objective completion.
    proposition: service-available
    role: postcondition
    polarity: positive
  service-observed:
    description: The service is available before the event fires.
    proposition: service-available
    role: precondition
    polarity: positive
events:
  notify-operator:
    assertions: [service-observed]
objectives:
  restore-service:
    owner: blue
    targets: [nodes.web]
    success:
      assertions: [{success_assertion}]
"""


def test_scenario_uses_assertions_for_backend_neutral_objective_success() -> None:
    scenario = parse_sdl(_semantic_scenario())

    assert scenario.conditions["http-health"].proposition == "service-available"
    assert scenario.objectives["restore-service"].success.assertions == ["service-ready"]
    assert scenario.assertions["service-ready"].role is AssertionRole.POSTCONDITION
    assert scenario.events["notify-operator"].assertions == ["service-observed"]


def test_scenario_rejects_dangling_objective_assertion() -> None:
    with pytest.raises(SDLValidationError, match="success assertion 'missing' not in assertions section"):
        parse_sdl(_semantic_scenario(success_assertion="missing"))


def test_objective_success_rejects_precondition_assertion() -> None:
    payload = _semantic_scenario().replace("role: postcondition", "role: precondition")
    with pytest.raises(SDLValidationError, match="must be an invariant or postcondition"):
        parse_sdl(payload)


def test_legacy_success_conditions_get_a_bounded_migration_error() -> None:
    payload = _semantic_scenario().replace("assertions: [service-ready]", "conditions: [http-health]")
    with pytest.raises(SDLParseError, match="success.conditions cannot state backend-neutral truth"):
        parse_sdl(payload)


def test_event_trigger_rejects_non_precondition_assertion() -> None:
    payload = _semantic_scenario().replace(
        "assertions: [service-observed]",
        "assertions: [service-ready]",
        1,
    )
    with pytest.raises(SDLValidationError, match="event trigger must be a precondition"):
        parse_sdl(payload)


def test_legacy_event_conditions_get_a_bounded_migration_error() -> None:
    payload = _semantic_scenario().replace(
        "assertions: [service-observed]",
        "conditions: [http-health]",
        1,
    )
    with pytest.raises(SDLParseError, match="event conditions cannot state backend-neutral truth"):
        parse_sdl(payload)


def test_compiler_preserves_proposition_assertion_and_probe_binding_boundaries() -> None:
    runtime = compile_runtime_model(parse_sdl(_semantic_scenario()))

    proposition = runtime.propositions["evaluation.proposition.service-available"]
    assertion = runtime.assertions["evaluation.assertion.service-ready"]
    binding = runtime.condition_bindings["evaluation.condition.web.http-health"]
    objective = runtime.objectives["evaluation.objective.restore-service"]

    assert proposition.subject_addresses == ("provision.node.web",)
    assert assertion.proposition_address == proposition.address
    assert binding.proposition_address == proposition.address
    assert objective.success_addresses == (assertion.address,)
    assert assertion.ordering_dependencies == (proposition.address,)
