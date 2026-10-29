"""Authored SDL failures reach the narrowed SDL refusal handlers as SDL errors (ADR-116, issue #1678).

Each case is authored input that the parser, a migration, a legacy digest or the
editor context must refuse. The failure is translated where the input is read, so
the narrowed handlers return their refusals and do not stop with a built-in error.
"""

from __future__ import annotations

import sys

import pytest
import yaml
from raes import SDLParseError, load_sdl_fragment, parse_sdl
from test_issue_1210_semantic_migration import context

_LIMIT = sys.get_int_max_str_digits()
_needs_digit_limit = pytest.mark.skipif(_LIMIT == 0, reason="the interpreter has no integer digit limit")
# int() refuses a decimal literal beyond the digit limit.
_DECIMAL = "7" * (_LIMIT + 1)
# A hexadecimal literal converts, but its value has more decimal digits than str() permits.
_HEX = hex(10**_LIMIT)
_SECRET = "SECRET-AUTHORED-VALUE"
_FEATURE_LIST = f"name: legacy\nnodes:\n  web: {{type: compute, features: [[{_SECRET}]]}}\n"
_ROLE_LIST = f"name: legacy\nnodes:\n  web: {{type: compute, roles: [{_SECRET}]}}\n"
_STEP_TYPE = f"name: legacy\nworkflows:\n  flow:\n    start: first\n    steps:\n      first: {{type: [{_SECRET}]}}\n"
# A double-quoted YAML escape can produce an unpaired surrogate, which has no UTF-8 form.
_SURROGATE_VALUE = 'name: "legacy\\ud800"\n'
_SURROGATE_KEY = 'name: legacy\nnodes:\n  "web\\udc80": {type: compute}\n'
# The recursive YAML composer exceeds the interpreter recursion limit long before this depth.
_DEEP_FLOW = "name: legacy\nnodes: " + "[" * 5000 + "]" * 5000 + "\n"
_DEEP_BLOCK = "name: legacy\nnodes:\n  " + "- " * 3000 + "web\n"
# float() turns these amounts into infinity or refuses them with OverflowError.
_HUGE_RAM = "name: legacy\nnodes:\n  web: {type: compute, resources: {ram: '" + "9" * 400 + " GiB', cpu: 1}}\n"
_HUGE_SPEED = "name: legacy\nscripts:\n  run: {start_time: 0, end_time: 10, speed: " + "9" * 400 + ", events: {e: 1}}\n"
_VALID = "name: legacy\nnodes:\n  web: {type: compute}\n"


def _integer_source(literal: str) -> str:
    return f"name: legacy\nvariables:\n  count: {{type: integer, default: {literal}}}\n"


def _semantic(source: str):
    from raes.semantic_migration import migrate_sdl_semantics

    return migrate_sdl_semantics(source, context=context(source))


def _participant(source: str):
    from raes.participant_migration import migrate_participant_identity

    return migrate_participant_identity(source)


def _mixed_control(source: str):
    from raes.mixed_control_migration import migrate_mixed_control_to_finite_script

    return migrate_mixed_control_to_finite_script(source)


def _classification(source: str):
    from raes.classification_migration import migrate_sdl_classifications

    return migrate_sdl_classifications(source)


def _refusal_codes(result) -> set[str]:
    assert result.output is None
    return {item.code for item in result.report.diagnostics}


_SOURCE_REFUSALS = [
    pytest.param(_semantic, "semantic-migration.source-or-target-invalid", id="semantic"),
    pytest.param(_participant, "participant-migration.source-or-target-invalid", id="participant"),
    pytest.param(_mixed_control, "mixed-control-migration.source-or-target-invalid", id="mixed-control"),
    pytest.param(_classification, "classification-migration.source-invalid", id="classification"),
]
_TARGET_REFUSALS = [
    *_SOURCE_REFUSALS[:3],
    pytest.param(_classification, "classification-migration.target-invalid", id="classification"),
]


@_needs_digit_limit
@pytest.mark.parametrize("literal", [_DECIMAL, _HEX], ids=["decimal", "hexadecimal"])
def test_loader_refuses_an_integer_without_a_decimal_form_and_omits_its_digits(literal):
    with pytest.raises(SDLParseError) as refused:
        load_sdl_fragment(_integer_source(literal))

    [diagnostic] = refused.value.diagnostics
    assert diagnostic.code == "sdl.parse"
    assert diagnostic.primary_range.start.line == 3
    digits = literal.removeprefix("0x")[:40]
    assert digits not in str(refused.value)
    assert digits not in diagnostic.message


@_needs_digit_limit
def test_loader_admits_integers_with_a_decimal_form_at_the_digit_limit():
    largest = 10**_LIMIT - 1

    loaded = load_sdl_fragment(f"a: {'9' * _LIMIT}\nb: {hex(largest)}\nc: -{'9' * _LIMIT}\n")

    assert loaded == {"a": largest, "b": largest, "c": -largest}


@_needs_digit_limit
@pytest.mark.parametrize("literal", [_DECIMAL, _HEX], ids=["decimal", "hexadecimal"])
@pytest.mark.parametrize(("migrate", "code"), _SOURCE_REFUSALS)
def test_migrations_refuse_an_integer_without_a_decimal_form(migrate, code, literal):
    assert code in _refusal_codes(migrate(_integer_source(literal)))


@_needs_digit_limit
def test_current_revision_input_refuses_an_integer_without_a_decimal_form():
    from raes.semantic_migration import migrate_sdl_semantics
    from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION

    source = _integer_source(_HEX).replace(
        "name: legacy\n", f"name: legacy\nsemantic_revision: {PROGRESSIVE_SDL_REVISION}\n"
    )

    assert "semantic-migration.source-or-target-invalid" in _refusal_codes(migrate_sdl_semantics(source))


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(_integer_source(_DECIMAL), marks=_needs_digit_limit, id="decimal"),
        pytest.param(_integer_source(_HEX), marks=_needs_digit_limit, id="hexadecimal"),
        pytest.param(_FEATURE_LIST, id="nested-feature-name"),
        pytest.param(_SURROGATE_VALUE, id="surrogate-escape"),
    ],
)
def test_legacy_classification_digest_refuses_source_that_does_not_load(source):
    from raes._legacy_classification_source import legacy_classification_source_digest

    with pytest.raises(SDLParseError) as refused:
        legacy_classification_source_digest(source)
    assert _SECRET not in str(refused.value)


@_needs_digit_limit
def test_editor_context_ignores_a_local_import_that_does_not_load(tmp_path):
    from raes.language_service import language_completions
    from test_issue_1339_editor_imports import _MODULE, _root

    module = yaml.safe_dump(_MODULE) + f"variables:\n  count: {{type: integer, default: {_DECIMAL}}}\n"
    (tmp_path / "module.yaml").write_text(module, encoding="utf-8")
    root = yaml.safe_dump(_root("first"), sort_keys=False)

    result = language_completions(root, cursor_path="/relationships", path=tmp_path / "root.yaml")

    assert result["status"] == "ok"


def test_module_export_name_that_is_not_an_identifier_is_an_sdl_refusal(tmp_path):
    from raes import parse_sdl_file
    from raes._language_context import reference_context
    from test_issue_1339_editor_imports import _MODULE, _root

    module = {**_MODULE, "module": {**_MODULE["module"], "exports": {"nodes": [f"${{{_SECRET}}}"]}}}
    (tmp_path / "module.yaml").write_text(yaml.safe_dump(module), encoding="utf-8")
    root = yaml.safe_dump(_root("first"), sort_keys=False)
    (tmp_path / "root.yaml").write_text(root, encoding="utf-8")

    with pytest.raises(SDLParseError) as refused:
        parse_sdl_file(tmp_path / "root.yaml")
    assert _SECRET not in str(refused.value)
    assert isinstance(refused.value.__cause__, ValueError)
    assert reference_context(root, tmp_path / "root.yaml") is not None


@pytest.mark.parametrize(
    ("import_path", "cause"),
    [("first\\x00.yaml", None), ("modules", IsADirectoryError)],
    ids=["nul-character", "directory"],
)
def test_local_import_path_that_does_not_name_a_readable_file_is_an_sdl_refusal(tmp_path, import_path, cause):
    from raes import parse_sdl_file
    from raes._language_context import reference_context

    (tmp_path / "modules").mkdir()
    root = f'name: root\nimports: [{{path: "{import_path}", namespace: first}}]\n'
    (tmp_path / "root.yaml").write_text(root, encoding="utf-8")

    with pytest.raises(SDLParseError) as refused:
        parse_sdl_file(tmp_path / "root.yaml")
    assert cause is None or isinstance(refused.value.__cause__, cause)
    assert reference_context(root, tmp_path / "root.yaml") is not None


def test_editor_context_ignores_an_import_list_that_is_not_a_sequence(tmp_path):
    from raes._language_context import reference_context

    root = "name: root\nimports: 7\n"
    (tmp_path / "root.yaml").write_text(root, encoding="utf-8")

    assert reference_context(root, tmp_path / "root.yaml") is not None


@pytest.mark.parametrize(("migrate", "code"), _SOURCE_REFUSALS)
def test_migrations_refuse_a_node_list_shorthand_with_a_nested_name(migrate, code):
    assert code in _refusal_codes(migrate(_FEATURE_LIST))


@pytest.mark.parametrize("source", [_STEP_TYPE, _ROLE_LIST], ids=["step-type", "role-list"])
@pytest.mark.parametrize(("migrate", "code"), _TARGET_REFUSALS)
def test_migrations_refuse_malformed_model_values(migrate, code, source):
    assert code in _refusal_codes(migrate(source))


@pytest.mark.parametrize(
    "source",
    [_FEATURE_LIST, _ROLE_LIST, _STEP_TYPE, _HUGE_RAM, _HUGE_SPEED],
    ids=["feature", "role", "step-type", "huge-ram", "huge-speed"],
)
def test_parser_reports_malformed_authored_shapes_as_parse_errors(source):
    with pytest.raises(SDLParseError) as refused:
        parse_sdl(source)

    assert _SECRET not in str(refused.value)
    assert all(_SECRET not in diagnostic.message for diagnostic in refused.value.diagnostics)


@pytest.mark.parametrize(("source", "line"), [(_SURROGATE_VALUE, 1), (_SURROGATE_KEY, 3)], ids=["value", "key"])
def test_loader_refuses_a_scalar_escape_without_a_utf8_form(source, line):
    with pytest.raises(SDLParseError) as refused:
        parse_sdl(source)

    [diagnostic] = refused.value.diagnostics
    assert diagnostic.code == "sdl.utf8"
    assert diagnostic.primary_range.start.line == line
    assert isinstance(refused.value.__cause__, UnicodeEncodeError)


@pytest.mark.parametrize(("migrate", "code"), _SOURCE_REFUSALS)
def test_migrations_refuse_a_scalar_escape_without_a_utf8_form(migrate, code):
    assert code in _refusal_codes(migrate(_SURROGATE_VALUE))


@pytest.mark.parametrize("source", [_DEEP_FLOW, _DEEP_BLOCK], ids=["flow", "block"])
def test_loader_refuses_nesting_beyond_the_depth_limit_before_composing(source):
    with pytest.raises(SDLParseError) as refused:
        parse_sdl(source)

    [diagnostic] = refused.value.diagnostics
    assert (diagnostic.code, diagnostic.message) == ("sdl.source_limit", "SDL node depth exceeds 128.")
    assert diagnostic.primary_range.start.line == (2 if source is _DEEP_FLOW else 3)


def test_depth_limit_keeps_its_boundary_and_its_position():
    load_sdl_fragment("a: " + "[" * 127 + "]" * 127 + "\n")

    with pytest.raises(SDLParseError) as refused:
        load_sdl_fragment("a: " + "[" * 128 + "]" * 128 + "\n")

    [diagnostic] = refused.value.diagnostics
    assert diagnostic.message == "SDL node depth exceeds 128."
    assert (diagnostic.primary_range.start.line, diagnostic.primary_range.start.column) == (1, 131)


@pytest.mark.parametrize(("migrate", "code"), _SOURCE_REFUSALS)
def test_migrations_refuse_nesting_beyond_the_depth_limit(migrate, code):
    assert code in _refusal_codes(migrate(_DEEP_FLOW))


# The target admits 2**53, but RFC 8785 refuses it, so the target has no canonical digest.
_NON_CANONICAL_TARGET = _integer_source(str(2**53))


@pytest.mark.parametrize(("migrate", "code"), _SOURCE_REFUSALS)
def test_migrations_refuse_a_target_without_a_canonical_digest(migrate, code):
    result = migrate(_NON_CANONICAL_TARGET)

    assert code in _refusal_codes(result)
    assert result.report.target_digest is None


def test_current_revision_input_refuses_a_target_without_a_canonical_digest():
    from raes.semantic_migration import migrate_sdl_semantics
    from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION

    source = _NON_CANONICAL_TARGET.replace(
        "name: legacy\n", f"name: legacy\nsemantic_revision: {PROGRESSIVE_SDL_REVISION}\n"
    )
    result = migrate_sdl_semantics(source)

    assert "semantic-migration.source-or-target-invalid" in _refusal_codes(result)
    assert result.report.target_digest is None


@pytest.mark.parametrize(("migrate", "code"), _SOURCE_REFUSALS)
def test_migrations_refuse_content_with_an_unpaired_surrogate(migrate, code):
    from raes.semantic_revisions import source_byte_digest

    content = "name: legacy\ud800\n"

    result = migrate(content)

    assert code in _refusal_codes(result)
    assert result.report.source_digest == source_byte_digest(content)


def test_source_byte_digest_keeps_utf8_bytes_and_binds_text_without_a_utf8_form():
    import hashlib

    from raes.semantic_revisions import source_byte_digest

    assert source_byte_digest("name: é\n") == "sha256:" + hashlib.sha256("name: é\n".encode()).hexdigest()
    surrogate = "name: \ud800\n"
    expected = "sha256:" + hashlib.sha256(surrogate.encode("utf-8", errors="surrogatepass")).hexdigest()
    assert source_byte_digest(surrogate) == expected


def _realization_source(token: str) -> str:
    return (
        "name: legacy\nnodes:\n  web: {type: compute, services: [{name: http, port: 80}]}\n"
        f"realization:\n  scopes: [{{field_pointer: '/nodes/web/services/{token}', posture: open}}]\n"
    )


def test_realization_pointer_with_a_unicode_digit_is_a_validation_finding():
    from raes import SDLValidationError

    # str.isdigit() accepts a superscript two, but int() refuses it.
    with pytest.raises(SDLValidationError, match="does not resolve to a typed SDL surface"):
        parse_sdl(_realization_source("²"))


@pytest.mark.parametrize(("migrate", "code"), _TARGET_REFUSALS)
def test_migrations_refuse_a_realization_pointer_with_a_unicode_digit(migrate, code):
    assert code in _refusal_codes(migrate(_realization_source("²")))


def test_realization_pointer_walker_reads_only_ascii_list_positions():
    from raes.realization_designation import resolve_json_pointer_surface

    scenario = parse_sdl(_realization_source("0"))

    assert resolve_json_pointer_surface(scenario, "/nodes/web/services/0")[0]
    assert resolve_json_pointer_surface(scenario, "/nodes/web/services/00") == (False, None)
    assert resolve_json_pointer_surface(scenario, "/nodes/web/services/1") == (False, None)
    assert resolve_json_pointer_surface(scenario, "/nodes/web/services/²") == (False, None)
    assert resolve_json_pointer_surface(scenario, "/nodes/web/services/" + "1" * (_LIMIT + 1)) == (False, None)


def test_one_public_array_index_rule_serves_every_pointer_walker():
    from raes_contracts.json_pointer import array_index, is_array_index_token
    from raes_contracts.realization_structure import _common

    assert [is_array_index_token(token) for token in ("0", "01", "²", "", "-1")] == [True, False, False, False, False]
    assert [array_index(token, 2) for token in ("0", "01", "2", "²", "9" * (_LIMIT + 1))] == [0, None, None, None, None]
    assert not hasattr(_common, "array_index")
    assert not hasattr(_common, "is_array_index_token")


@_needs_digit_limit
def test_ram_size_refusals_do_not_repeat_the_authored_value():
    from raes.runtime_values import parse_ram

    for value in ("²", _SECRET, "9" * (_LIMIT + 1)):
        with pytest.raises(ValueError) as refused:
            parse_ram(value)
        assert value[:20] not in str(refused.value)
    # int() accepts every Unicode decimal digit, so such sizes keep their meaning.
    assert parse_ram("٣") == 3
    with pytest.raises(SDLParseError) as parsed:
        parse_sdl("name: legacy\nnodes:\n  web: {type: compute, resources: {ram: '²', cpu: 1}}\n")
    assert "²" not in str(parsed.value)


def _oversized_asset_source() -> str:
    from test_dsl_118_control_context import asset_payload

    asset = asset_payload()
    # RFC 8785 refuses an integer outside the I-JSON range, so the descriptor has no canonical digest.
    asset["content"]["size_bytes"] = 2**53 + 1
    return yaml.safe_dump({"name": "legacy", "control_context_assets": {"shared": asset}})


def test_control_context_asset_without_a_canonical_digest_is_a_validation_finding():
    from raes import SDLValidationError

    with pytest.raises(SDLValidationError, match="control-context.descriptor-not-canonical"):
        parse_sdl(_oversized_asset_source())


@pytest.mark.parametrize(("migrate", "code"), _SOURCE_REFUSALS)
def test_migrations_refuse_a_control_context_asset_without_a_canonical_digest(migrate, code):
    assert code in _refusal_codes(migrate(_oversized_asset_source()))


def test_selection_of_a_control_context_asset_without_a_canonical_digest_keeps_its_value_private():
    from raes import SDLValidationError
    from test_dsl_118_control_context import asset_payload, selection

    asset = asset_payload()
    briefing = selection(asset)
    asset["content"]["size_bytes"] = 2**53 + 1
    agents = {"red": {"role": "red", "control_context": {"briefing": briefing}}}
    source = yaml.safe_dump({"name": "legacy", "control_context_assets": {"shared": asset}, "agents": agents})

    with pytest.raises(SDLValidationError) as refused:
        parse_sdl(source)
    assert "control-context.descriptor-not-canonical" in refused.value.errors
    assert str(2**53 + 1) not in str(refused.value)


def _snapshot_payload(accounts: object) -> dict:
    from copy import deepcopy

    from raes import instantiate_scenario
    from raes.canonical import InstantiatedScenarioSnapshot

    scenario = instantiate_scenario(parse_sdl("name: snapshot\nnodes: {}\n"))
    snapshot = InstantiatedScenarioSnapshot(profile="raes-sdl-instantiated-snapshot/v2", scenario=scenario)
    payload = deepcopy(snapshot.model_dump(mode="json"))
    payload["scenario"]["accounts"] = accounts
    return payload


def test_snapshot_migration_refuses_nesting_beyond_its_depth_limit():
    from pydantic import ValidationError
    from raes.canonical import InstantiatedScenarioSnapshot, migrate_legacy_instantiated_snapshot_payload
    from raes_contracts.satisfiability import SatisfiableWitnessModel

    nested: object = {}
    for _ in range(3000):
        nested = {"a": nested}
    payload = _snapshot_payload(nested)
    witness = {
        "profile": "raes-satisfiability-witness/v1",
        "snapshot": payload,
        "snapshot_digest": "sha256:" + "0" * 64,
    }

    with pytest.raises(ValueError, match="depth limit"):
        migrate_legacy_instantiated_snapshot_payload(payload)
    with pytest.raises(ValidationError):
        SatisfiableWitnessModel.model_validate(witness)
    with pytest.raises(ValidationError):
        InstantiatedScenarioSnapshot.model_validate(payload)


def test_snapshot_migration_returns_a_valid_snapshot_unchanged():
    from raes.canonical import migrate_legacy_instantiated_snapshot_payload

    payload = _snapshot_payload({})

    migrated, changed = migrate_legacy_instantiated_snapshot_payload(payload)

    assert migrated is payload
    assert not changed


def _defect(*_args: object, **_kwargs: object) -> None:
    raise ValueError("SECRET-DEFECT-DETAIL")


def _selection_inputs():
    from types import SimpleNamespace

    return SimpleNamespace(family=None), SimpleNamespace(selections=()), SimpleNamespace(replicate_id="r1")


def test_trial_selection_refusals_stay_compilation_failures(monkeypatch):
    from raes.selected_scenario import SDLSelectionError
    from raes_processor.trial_compiler import realization_admission
    from raes_processor.trial_compiler.models import CompilationFailure

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise SDLSelectionError("selection refused")

    monkeypatch.setattr(realization_admission, "select_scenario_family", refuse)
    request, row, coordinate = _selection_inputs()

    with pytest.raises(CompilationFailure) as selected:
        realization_admission.validate_selected_scenario(request, row, coordinate)
    with pytest.raises(CompilationFailure) as source:
        realization_admission._source_scenario(request, row)
    assert (selected.value.code, source.value.code) == (
        "selected-scenario-rejected",
        "composition-source-selection-invalid",
    )


def test_trial_selection_handlers_do_not_report_a_defect_as_a_refusal(monkeypatch):
    from raes_processor.trial_compiler import realization_admission

    monkeypatch.setattr(realization_admission, "select_scenario_family", _defect)
    request, row, coordinate = _selection_inputs()

    with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
        realization_admission.validate_selected_scenario(request, row, coordinate)
    with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
        realization_admission._source_scenario(request, row)


def test_selection_refusals_are_sdl_selection_errors_and_defects_propagate(monkeypatch):
    from raes import selected_scenario
    from raes.selected_scenario import SDLSelectionError
    from test_issue_1625_structural_variation import _family, _outcome, _payload

    family = _family(_payload())
    with pytest.raises(SDLSelectionError, match="complete scenario-family selection required"):
        selected_scenario.select_scenario_family(family, {})
    with pytest.raises(SDLSelectionError):
        selected_scenario.select_scenario_family(family, {"host-state": _outcome("missing-member")})

    monkeypatch.setattr(selected_scenario, "_validate_cross_point_relations", _defect)
    with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
        selected_scenario.select_scenario_family(family, {"host-state": _outcome("baseline")})


def test_selection_intent_refusals_are_sdl_selection_errors():
    from raes import SDLSelectionError, validate_experiment_selection_against_family
    from raes_contracts.contracts import ExperimentSpecModel
    from raes_contracts.errors import InvalidInputError
    from test_experiment_selection import _base_payload, _expanded_family, _fixed_policy, _spec_with_binding_family

    payload = _base_payload()
    payload["run_plan"]["selection_policies"] = {"fixed-path": _fixed_policy()}
    spec = ExperimentSpecModel.model_validate(payload)
    spec.intended_scenario_ref.ref_id = "other-family"

    with pytest.raises(SDLSelectionError, match="family identity must match") as refused:
        validate_experiment_selection_against_family(spec, family=_expanded_family())
    assert isinstance(refused.value, InvalidInputError)
    assert not isinstance(refused.value, ValueError)
    with pytest.raises(SDLSelectionError, match="binding target family identity"):
        validate_experiment_selection_against_family(_spec_with_binding_family("other"), family=_expanded_family())


def test_compiler_reports_selection_intent_refusals_and_propagates_defects(monkeypatch):
    import raes_processor.trial_compiler.compiler as compiler_module
    from raes import SDLSelectionError
    from raes_processor.trial_compiler import compile_admitted_trial_plan
    from test_sce_002_trial_compiler import _request

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise SDLSelectionError("selection refused")

    monkeypatch.setattr(compiler_module, "validate_experiment_selection_against_family", refuse)
    result = compile_admitted_trial_plan(_request())
    assert [item.code for item in result.diagnostics] == ["trial-compiler.selection-intent-rejected"]

    monkeypatch.setattr(compiler_module, "validate_experiment_selection_against_family", _defect)
    with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
        compile_admitted_trial_plan(_request())


def test_binding_target_refusals_are_binding_target_errors():
    from raes import ExpandedScenarioBindingTargetResolver
    from raes_contracts.contracts import ExperimentBindingDescriptorSetModel
    from raes_contracts.errors import InvalidInputError
    from raes_contracts.experiment_bindings import ExperimentBindingTargetError, validate_experiment_binding_targets
    from test_experiment_bindings import _scenario_binding_payload, _ScenarioOwnerMismatchResolver
    from test_sce_002_selected_scenario import _family

    descriptors = ExperimentBindingDescriptorSetModel.model_validate(_scenario_binding_payload())
    with pytest.raises(ExperimentBindingTargetError, match="owner does not match") as refused:
        validate_experiment_binding_targets(
            descriptors,
            scenario_resolver=_ScenarioOwnerMismatchResolver(),
            participant_manifests={},
            apparatus_manifests={},
        )
    assert isinstance(refused.value, InvalidInputError)
    assert not isinstance(refused.value, ValueError)

    resolver = ExpandedScenarioBindingTargetResolver(_family())
    with pytest.raises(ExperimentBindingTargetError, match="family does not match"):
        resolver.resolve("other-family", "payload-path", "variables.payload_path")
    with pytest.raises(ExperimentBindingTargetError, match="is not declared"):
        resolver.resolve("compiler-family", "missing-point", "variables.payload_path")
    with pytest.raises(ExperimentBindingTargetError, match="not the canonical SDL target"):
        resolver.resolve("compiler-family", "payload-path", "variables.other")


def test_binding_admission_handler_keeps_refusals_and_propagates_defects(monkeypatch):
    from types import SimpleNamespace

    from raes_contracts.experiment_bindings import ExperimentBindingTargetError
    from raes_processor.trial_compiler import bindings as bindings_module
    from raes_processor.trial_compiler.models import CompilationFailure

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise ExperimentBindingTargetError("binding refused")

    monkeypatch.setattr(bindings_module, "ExpandedScenarioBindingTargetResolver", lambda _family: None)
    monkeypatch.setattr(bindings_module, "validate_experiment_binding_targets", refuse)
    request = SimpleNamespace(family=None, experiment=SimpleNamespace(binding_descriptors=SimpleNamespace()))

    with pytest.raises(CompilationFailure) as failure:
        bindings_module._admitted_descriptors(request, {}, {})
    assert failure.value.code == "binding-target-rejected"

    monkeypatch.setattr(bindings_module, "validate_experiment_binding_targets", _defect)
    with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
        bindings_module._admitted_descriptors(request, {}, {})


@pytest.mark.parametrize(
    ("module", "attribute", "migrate"),
    [
        pytest.param("raes.semantic_migration", "apply_sentinel_decisions", _semantic, id="semantic"),
        pytest.param("raes.participant_migration", "_adopt", _participant, id="participant"),
        pytest.param("raes.mixed_control_migration", "_convert", _mixed_control, id="mixed-control"),
        pytest.param("raes.classification_migration", "parse_sdl", _classification, id="classification"),
    ],
)
def test_migration_refusals_do_not_report_a_defect_as_a_refusal(monkeypatch, module, attribute, migrate):
    monkeypatch.setattr(f"{module}.{attribute}", _defect)

    with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
        migrate(_VALID)


def test_editor_context_does_not_report_a_composition_defect_as_a_missing_import(monkeypatch, tmp_path):
    from raes._language_context import document_context

    monkeypatch.setattr("raes.composition.expand_sdl_modules", _defect)

    with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
        document_context({"name": "root", "imports": [{"path": "module.yaml"}]}, tmp_path / "root.yaml")
