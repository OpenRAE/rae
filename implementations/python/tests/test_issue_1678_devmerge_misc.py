"""#1678: the exception policy applied to the validation session, trial sources and typed treatments from dev.

The validation session reuses pass outputs. A reused output keeps the owner and the pointer of each finding,
so source diagnostics, migration pointers and relationship completions do not depend on reuse.
Typed treatment and authoring-source refusals raise categories (ADR-116 rules E1 and E9).
"""

from __future__ import annotations

import runpy
from dataclasses import replace
from pathlib import Path

import pytest
import raes._language_relationship_candidates as relationship_candidates
import yaml
from mixed_control_rev1_scenarios import rev1_policy_of, rev1_scenario
from paths import REPO_ROOT
from raes import (
    ExpandedScenarioBindingTargetResolver,
    SDLParseError,
    SDLSelectionError,
    SDLValidationError,
    admit_scenario_family,
    canonical_sdl_digest,
    parse_sdl,
    parse_sdl_file,
)
from raes._declaration_sources import semantic_source_diagnostics
from raes.language_service import language_completions
from raes.mixed_control_migration import _error_pointers
from raes.validator import SemanticValidator, ValidationSession
from raes_contracts.contracts import LiteralBindingValueModel, TrialCoordinateModel
from raes_contracts.contracts.experiment_treatments import ExperimentFactorLevelSelectionModel
from raes_contracts.errors import InvalidInputError
from raes_processor.trial_compiler import compile_admitted_trial_plan
from raes_processor.trial_compiler.profiles import REPLICATE_ID_WIDTH, replicate_id
from raes_processor.trial_compiler.replacement_inputs import replacement_coordinate
from raes_processor.trial_compiler.sources import validate_authoring_selections
from test_issue_1363_mixed_control_migration import _source
from test_issue_1666_factorial_compilation import _treatment_request, _with_design
from test_issue_1678_validator_findings import (
    _INVALID_FIXTURES,
    _imitating_baseline_payload,
    _owner_payload,
    _typed_endpoint_payload,
)
from test_scenario_family_admission import _SOURCE as _FAMILY_SOURCE


class _CountingSession(ValidationSession):
    """A validation session that counts the pass outputs that it reuses."""

    def __init__(self) -> None:
        super().__init__()
        self.hits = 0

    def lookup(self, scope: tuple[object, ...], values: dict[str, object]) -> object | None:
        outputs = super().lookup(scope, values)
        if outputs is not None:
            self.hits += 1
        return outputs


def _results(scenario: object, session: ValidationSession) -> tuple[object, ...]:
    """Return the findings, source diagnostics and migration pointers of one validation."""

    try:
        SemanticValidator(scenario, session=session).validate()
    except SDLValidationError as error:
        semantic_source_diagnostics(error, scenario)
        return error.findings, error.diagnostics, _error_pointers(error)
    return ()


def _scenarios(tmp_path: Path) -> list[object]:
    owners = tmp_path / "owners.yaml"
    owners.write_text(yaml.safe_dump(_owner_payload(), sort_keys=False), encoding="utf-8")
    revoked = rev1_scenario()
    rev1_policy_of(revoked)["controller_states"]["supervised"]["authority_status"] = "revoked"
    scenarios = [
        parse_sdl_file(owners, skip_semantic_validation=True),
        parse_sdl(_source(revoked), skip_semantic_validation=True),
    ]
    for path in _INVALID_FIXTURES:
        try:
            scenarios.append(parse_sdl_file(path, skip_semantic_validation=True))
        except SDLParseError:
            continue
    return scenarios


def test_reused_pass_outputs_keep_owners_pointers_diagnostics_and_migration_pointers(tmp_path: Path) -> None:
    owned = pointed = 0
    for scenario in _scenarios(tmp_path):
        reference = _results(scenario.model_copy(), ValidationSession(memoize=False))
        session = _CountingSession()
        first = _results(scenario, session)
        hits_before_reuse = session.hits
        # The copy shares every field object, so each pass reuses the stored outputs.
        reused = _results(scenario.model_copy(), session)

        assert session.hits > hits_before_reuse
        assert first == reference
        assert reused == reference
        findings = reference[0] if reference else ()
        owned += sum(finding.owner is not None for finding in findings)
        pointed += sum(finding.pointer is not None for finding in findings)
    assert owned
    assert pointed


@pytest.mark.parametrize("build", [_typed_endpoint_payload, _imitating_baseline_payload])
def test_relationship_completion_gives_the_same_candidates_without_session_reuse(
    build, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, cursor = build()
    text = yaml.safe_dump(payload, sort_keys=False)
    shared = language_completions(text, cursor_path=cursor)

    monkeypatch.setattr(relationship_candidates, "ValidationSession", lambda: ValidationSession(memoize=False))

    assert shared["items"]
    assert language_completions(text, cursor_path=cursor) == shared


def _family_treatment(outcome: str, **changes: object):
    family = admit_scenario_family(parse_sdl(_FAMILY_SOURCE))
    resolver = ExpandedScenarioBindingTargetResolver(family)
    resolution = resolver.resolve(family.name, "image-choice", "variables.image")
    fields = {
        "target": {
            "plane": "scenario",
            "scenario_family_id": family.name,
            "variation_point_id": "image-choice",
            "target_id": resolution.canonical_target_id,
        },
        "scenario_family_digest": canonical_sdl_digest(family).value,
        "owner": resolution.owner,
        "outcome": LiteralBindingValueModel(kind="literal", value=outcome),
        **changes,
    }
    treatment = ExperimentFactorLevelSelectionModel(**fields).descriptor("image", outcome, f"condition-{outcome}")
    return resolver, treatment


def test_typed_treatment_refusals_raise_the_selection_category() -> None:
    resolver, outside = _family_treatment("windows")
    with pytest.raises(SDLSelectionError, match="outside the declared point domain"):
        resolver.validate_selection(outside)

    resolver, stale = _family_treatment("bsd", scenario_family_digest="sha256:" + "0" * 64)
    with pytest.raises(SDLSelectionError, match="authoritative SDL target"):
        resolver.validate_selection(stale)


def test_compiler_reports_an_out_of_domain_typed_member_as_a_treatment_refusal() -> None:
    request = _treatment_request()
    payload = request.experiment.model_dump(mode="json")
    payload["factorial_design"]["level_effects"]["terrain-x"]["isolated"]["selections"][0]["outcome"]["member_id"] = (
        "undeclared-member"
    )

    result = compile_admitted_trial_plan(_with_design(request, payload))

    assert result.plan is None
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["trial-compiler.selection-treatment-rejected"]
    assert "undeclared-member" not in repr(result.diagnostics)


def test_authoring_source_reconstruction_refusal_is_an_input_refusal() -> None:
    request = _treatment_request()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None, result.diagnostics
    damaged = request.experiment.model_copy(update={"spec_version": ""})

    with pytest.raises(InvalidInputError, match="failed closed reconstruction") as raised:
        validate_authoring_selections(result.plan, request.family, damaged, {}, {})
    assert type(raised.value) is InvalidInputError


def test_a_replacement_slot_beyond_the_replicate_range_is_an_input_refusal() -> None:
    coordinates = [TrialCoordinateModel(condition_id="condition", replicate_id=replicate_id(1))]

    with pytest.raises(InvalidInputError, match="replicate range"):
        replacement_coordinate(coordinates, 0, 10**REPLICATE_ID_WIDTH, 10**REPLICATE_ID_WIDTH)


def test_public_example_refuses_an_uncompilable_request_with_a_category() -> None:
    example = runpy.run_path(str(REPO_ROOT / "implementations/python/examples/factorial_treatments.py"))
    request = _treatment_request()
    request = replace(request, limits=request.limits.model_copy(update={"max_bindings_per_entry": 2}))

    with pytest.raises(InvalidInputError, match="typed treatment compilation failed: trial-compiler\\."):
        example["compile_example"](request)


# Node-default comparison refuses a malformed node payload with a category (ADR-116 rules E9 and H5).


@pytest.mark.parametrize(
    "payload",
    [{}, {"spec": []}, {"spec": {"node": "not-a-node"}}, {"spec": {"node": {"type": 7}}}],
    ids=["no-spec", "spec-not-mapping", "node-not-mapping", "node-refused-by-contract"],
)
def test_node_defaults_refuse_a_malformed_payload_as_invalid_input(payload):
    from types import SimpleNamespace

    from raes_contracts.errors import InvalidInputError
    from raes_processor.semantics.realization_node_defaults import defaulted_node_payload, with_node_defaults

    resource = SimpleNamespace(address="nodes.web", payload=payload)
    with pytest.raises(InvalidInputError):
        with_node_defaults(resource)
    assert defaulted_node_payload(resource, {}) is None


def test_node_defaults_do_not_report_a_defect_as_a_refusal(monkeypatch):
    from types import SimpleNamespace

    from raes_processor.semantics import realization_node_defaults

    def defect(*_args: object, **_kwargs: object) -> object:
        raise KeyError("node-defaults-defect-1678")

    monkeypatch.setattr(realization_node_defaults, "typed_runtime_observation_shape", defect)
    resource = SimpleNamespace(address="nodes.web", payload={"spec": {"node": {"type": "compute"}}})
    with pytest.raises(KeyError):
        realization_node_defaults.defaulted_node_payload(resource, {})
