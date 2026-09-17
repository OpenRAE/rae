"""Finite authoring-path conformance for ASR-516, independent of transport."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_conformance.authoring_adapters import (
    AuthoringPathOutput,
    compare_authoring_paths,
    load_authoring_vectors,
    reference_authoring_output,
)
from raes_contracts.authoring_adapters import AuthoringAdapterComparisonModel, parse_authoring_vector
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import schema_bundle
from raes_contracts.diagnostics import DiagnosticModel, Severity
from raes_contracts.json_ingress import StrictJsonIngressError

ROOT = Path(__file__).resolve().parents[3]


def _case(case_id="strict-source"):
    vector = next(v for v in load_authoring_vectors() if v.case_id == case_id)
    return vector, reference_authoring_output(vector)


@pytest.mark.parametrize("path_id", ["cli", "mcp-agent", "graphical", "documentation"])
def test_published_vectors_accept_equivalent_authoring_paths(path_id: str) -> None:
    vectors = load_authoring_vectors()
    assert {v.case_id for v in vectors} == {
        "strict-source",
        "duplicate-key",
        "rename-node",
        "rename-collision",
        "rename-invalid-source",
        "editorial-difference",
        "declaration-difference",
    }
    for vector in vectors:
        output = reference_authoring_output(vector)
        # Comments are presentation, not artifact or semantic identity.
        other = replace(
            output,
            output_source=("# rendered by another path\n" + output.output_source)
            if output.output_source is not None
            else None,
        )
        comparison = compare_authoring_paths(vector, output, other, left_path="library", right_path=path_id)
        assert comparison.report.conformant, comparison.report.model_dump_json()
        assert comparison.report.left_matches_expected
        assert comparison.report.right_matches_expected


def test_semantic_change_is_typed_and_two_identical_wrong_paths_do_not_pass() -> None:
    vector = next(v for v in load_authoring_vectors() if v.case_id == "strict-source")
    output = reference_authoring_output(vector)
    changed = replace(output, output_source=output.output_source.replace("web:", "edge:"))
    comparison = compare_authoring_paths(vector, output, changed)
    assert comparison.report.artifact_relation == "different"
    assert comparison.report.semantic_relation == "different"
    assert not comparison.report.conformant
    assert comparison.semantic_result is not None
    assert not compare_authoring_paths(vector, changed, changed).report.conformant


def test_empty_corpus_is_not_success(tmp_path) -> None:
    with pytest.raises(ValueError, match="empty"):
        load_authoring_vectors(root=tmp_path)


def test_published_contrasts_have_independent_expected_dispositions() -> None:
    contrasts = [vector for vector in load_authoring_vectors() if getattr(vector, "contrast", None) is not None]
    assert len(contrasts) == 2
    for vector in contrasts:
        output = reference_authoring_output(vector)
        alternative = replace(output, output_source=vector.contrast.output_source)
        report = compare_authoring_paths(vector, output, alternative).report
        assert report.artifact_relation == vector.contrast.artifact_relation
        assert report.semantic_relation == vector.contrast.semantic_relation
        assert report.diagnostic_relation == "equivalent"
        assert report.provenance_relation == "not-applicable"
        assert report.left_matches_expected
        assert not report.right_matches_expected
        assert not report.conformant


def test_invalid_output_is_incomparable_without_echoing_source() -> None:
    vector = next(v for v in load_authoring_vectors() if v.case_id == "strict-source")
    output = reference_authoring_output(vector)
    invalid = replace(output, output_source="name: unsafe-value-marker\nnodes: [invalid]\n")
    report = compare_authoring_paths(vector, output, invalid).report
    assert report.semantic_relation == "incomparable"
    assert "right-invalid" in report.reason_codes
    assert "unsafe-value-marker" not in report.model_dump_json()


def test_editorial_change_is_an_artifact_difference_without_semantic_change() -> None:
    vector, output = _case()
    changed = replace(output, output_source=output.output_source + "description: changed editorial prose\n")
    result = compare_authoring_paths(vector, output, changed)
    assert result.report.artifact_relation == "different"
    assert result.report.semantic_relation == "equivalent"
    assert not result.report.conformant
    assert result.report.semantic_result_digest == canonical_json_digest(result.semantic_result.model_dump(mode="json"))


@pytest.mark.parametrize("uncertainty", ["context", "change"])
def test_semantic_uncertainty_remains_incomparable(monkeypatch, uncertainty) -> None:
    from raes_conformance import authoring_adapters
    from raes_contracts.semantic_comparison import ComparisonReason, RelationStatus

    vector, output = _case()
    baseline = compare_authoring_paths(vector, output, output).semantic_result
    if uncertainty == "context":
        incomplete = baseline.model_copy(update={"reason_codes": (ComparisonReason.IMPACT_SCOPE_PARTIAL,)})
    else:
        assert baseline.changes
        changes = (baseline.changes[0].model_copy(update={"semantic_relation": RelationStatus.UNKNOWN}),)
        incomplete = baseline.model_copy(update={"changes": changes})
    monkeypatch.setattr(authoring_adapters, "analyze_semantic_comparison", lambda *_args: incomplete)
    comparison = compare_authoring_paths(vector, output, output)
    assert comparison.report.semantic_relation == "incomparable"
    assert "semantic-context-incomplete" in comparison.report.reason_codes
    assert not comparison.report.conformant
    assert comparison.semantic_result is incomplete


def test_each_input_must_match_the_exact_bound_source() -> None:
    vector, output = _case()
    wrong = replace(output, input_source=output.input_source + "# different input\n")
    report = compare_authoring_paths(vector, output, wrong).report
    assert "right-input-mismatch" in report.reason_codes
    assert report.right is None
    assert set(report.relations) == {"incomparable"}


def test_diagnostic_projection_preserves_code_severity_address_and_multiplicity() -> None:
    vector, output = _case("duplicate-key")
    original = output.diagnostics[0]
    for field, value in (("code", "sdl.other"), ("severity", "warning"), ("pointer", "/other"), ("stage", "semantic")):
        altered = replace(output, diagnostics=(replace(original, **{field: value}),))
        report = compare_authoring_paths(vector, output, altered).report
        assert not report.conformant
        assert report.diagnostic_relation == "different"
    duplicated = replace(output, diagnostics=(original, original))
    assert compare_authoring_paths(vector, output, duplicated).report.diagnostic_relation == "different"
    prose = replace(
        output, diagnostics=(replace(original, message="Equivalent human explanation.", source="other.yaml"),)
    )
    assert compare_authoring_paths(vector, output, prose).report.conformant


def test_portable_diagnostics_are_order_independent_but_not_ignored() -> None:
    vector, output = _case()
    diagnostics = tuple(
        DiagnosticModel(
            code=f"authoring.{code}",
            domain="sdl",
            address="/nodes/web",
            message="Synthetic advisory.",
            severity=Severity.WARNING,
        )
        for code in ("one", "two")
    )
    left = replace(output, diagnostics=diagnostics)
    right = replace(output, diagnostics=tuple(reversed(diagnostics)))
    report = compare_authoring_paths(vector, left, right).report
    assert report.diagnostic_relation == "equivalent"
    assert not report.conformant  # Both differ from the empty diagnostic oracle.
    assert compare_authoring_paths(vector, output, left).report.diagnostic_relation == "different"


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_digest", "sha256:" + "a" * 64),
        ("target_digest", "sha256:" + "a" * 64),
        ("operation_profile", "remove-sdl-declaration/v1"),
        ("canonicalization_profile", "raes-sdl-semantic/v1"),
        ("source_profile", "sdl-yaml/v1"),
        ("target_profile", "sdl-yaml/v1"),
    ],
)
def test_stale_or_wrong_transformation_joins_are_incomparable(field, value) -> None:
    vector, output = _case("rename-node")
    changed = replace(output, transformation_report=output.transformation_report.model_copy(update={field: value}))
    report = compare_authoring_paths(vector, output, changed).report
    assert "right-invalid" in report.reason_codes
    assert not report.conformant


def test_declared_provenance_difference_does_not_rewrite_artifact_equivalence() -> None:
    vector, output = _case("rename-node")
    changed = replace(
        output,
        transformation_report=output.transformation_report.model_copy(
            update={"derivation_digest": "sha256:" + "a" * 64}
        ),
    )
    report = compare_authoring_paths(vector, output, changed).report
    assert report.artifact_relation == report.semantic_relation == "equivalent"
    assert report.provenance_relation == "different"
    assert not report.conformant


def test_missing_provenance_and_refusal_without_diagnostics_fail_closed() -> None:
    vector, output = _case("rename-node")
    assert (
        "right-invalid"
        in compare_authoring_paths(vector, output, replace(output, transformation_report=None)).report.reason_codes
    )
    vector, output = _case("duplicate-key")
    assert (
        "right-invalid" in compare_authoring_paths(vector, output, replace(output, diagnostics=())).report.reason_codes
    )


def test_rename_source_admission_refusal_needs_no_transformation_report() -> None:
    vector, output = _case("rename-invalid-source")
    assert output.output_source is None
    assert output.diagnostics
    assert output.transformation_report is None
    comparison = compare_authoring_paths(vector, output, output)
    assert comparison.report.conformant
    assert comparison.report.diagnostic_relation == "equivalent"
    assert comparison.report.artifact_relation == "not-applicable"
    assert comparison.report.provenance_relation == "not-applicable"
    assert comparison.report.semantic_relation == "not-applicable"
    assert comparison.semantic_result is None


def test_post_admission_rename_refusal_still_requires_provenance() -> None:
    vector, output = _case("rename-collision")
    assert output.output_source is None
    without_report = replace(output, transformation_report=None)
    report = compare_authoring_paths(vector, output, without_report).report
    assert "right-invalid" in report.reason_codes
    assert not report.conformant


def test_pre_operation_rename_refusal_cannot_emit_an_artifact() -> None:
    vector, output = _case("rename-invalid-source")
    fabricated = replace(output, output_source="name: fabricated\n")
    report = compare_authoring_paths(vector, output, fabricated).report
    assert "right-invalid" in report.reason_codes
    assert not report.conformant


def test_success_and_refusal_are_an_explicit_outcome_difference() -> None:
    vector, refused = _case("duplicate-key")
    success = AuthoringPathOutput(vector.input_source, "name: synthetic\n")
    report = compare_authoring_paths(vector, refused, success).report
    assert "outcomes-differ" in report.reason_codes
    assert report.artifact_relation == "different"
    assert report.semantic_relation == "not-applicable"
    assert not report.conformant


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update(input_digest="sha256:" + "0" * 64),
        lambda data: data["operation"].update(profile="unknown/v1"),
        lambda data: data["operation"].update(target_address="nodes.web"),
        lambda data: data.update(operation_digest="sha256:" + "0" * 64),
        lambda data: data.update(unknown=True),
    ],
)
def test_closed_vector_contract_rejects_tampering(mutate) -> None:
    vector, _ = _case()
    data = vector.model_dump(mode="json")
    mutate(data)
    source = json.dumps(data)
    with pytest.raises(ValidationError):
        parse_authoring_vector(source)


def test_strict_json_ingress_and_utf8_byte_limits() -> None:
    with pytest.raises(StrictJsonIngressError):
        parse_authoring_vector('{"case_id":"one","case_id":"two"}')
    with pytest.raises(StrictJsonIngressError):
        parse_authoring_vector('{"value":NaN}')
    with pytest.raises(StrictJsonIngressError):
        parse_authoring_vector(" " * (128 * 1024 + 1))
    vector, output = _case()
    for bad in ("#" + "a" * 65536, "#" + "é" * 32768):
        assert (
            "right-invalid"
            in compare_authoring_paths(vector, output, replace(output, output_source=bad)).report.reason_codes
        )
    excessive = replace(
        output,
        diagnostics=(
            DiagnosticModel(
                code="test.warning", domain="sdl", address="", message="Synthetic.", severity=Severity.WARNING
            ),
        )
        * 65,
    )
    assert "right-invalid" in compare_authoring_paths(vector, output, excessive).report.reason_codes


def test_vector_profile_is_pinned_and_case_paths_cannot_escape(tmp_path) -> None:
    vector, output = _case()
    forged = vector.model_copy(update={"profile_digest": "sha256:" + "0" * 64})
    with pytest.raises(ValueError, match="profile digest"):
        compare_authoring_paths(forged, output, output)
    (tmp_path / "strict-source.json").symlink_to(
        ROOT / "contracts/fixtures/authoring-adapters-v1/cases/strict-source.json"
    )
    with pytest.raises(ValueError, match="outside"):
        load_authoring_vectors(root=tmp_path)


def test_published_schemas_and_deterministic_reports() -> None:
    bundle = schema_bundle()
    for vector in load_authoring_vectors():
        Draft202012Validator(bundle["authoring-adapter-vector-v1"]).validate(vector.model_dump(mode="json"))
        output = reference_authoring_output(vector)
        first = compare_authoring_paths(vector, output, output)
        second = compare_authoring_paths(vector, output, output)
        assert first.report.model_dump_json() == second.report.model_dump_json()
        Draft202012Validator(bundle["authoring-adapter-comparison-v1"]).validate(first.report.model_dump(mode="json"))
        assert AuthoringAdapterComparisonModel.model_validate_json(first.report.model_dump_json()) == first.report


def test_json_artifact_gate_routes_vectors_and_profile() -> None:
    from tools.check_json_artifacts import collect_validation_targets

    paths = [
        "contracts/profiles/authoring-adapters/reference-v1.json",
        "contracts/fixtures/authoring-adapters-v1/cases/strict-source.json",
    ]
    for selected in (paths, None):
        routed = {target.path: target.schema_path for target in collect_validation_targets(ROOT, paths=selected)}
        assert routed[paths[0]] == "contracts/schemas/authoring-adapters/authoring-adapter-profile-v1.json"
        assert routed[paths[1]] == "contracts/schemas/authoring-adapters/authoring-adapter-vector-v1.json"


def test_contracts_publish_contextual_invariants_and_bounded_report_ingress() -> None:
    from raes_contracts.authoring_adapters import parse_authoring_comparison

    for contract in ("authoring-adapter-vector-v1", "authoring-adapter-comparison-v1"):
        assert schema_bundle()[contract]["x-raes-invariants"]
    vector, output = _case()
    report = compare_authoring_paths(vector, output, output).report
    assert parse_authoring_comparison(report.model_dump_json()) == report
    with pytest.raises(StrictJsonIngressError):
        parse_authoring_comparison('{"case_id":"one","case_id":"two"}')
    with pytest.raises(StrictJsonIngressError):
        parse_authoring_comparison(" " * 65537)


@pytest.mark.parametrize(
    "alter",
    [
        {"semantic_result_digest": None},
        {"semantic_relation": "not-applicable"},
        {"artifact_relation": "not-applicable"},
        {"diagnostic_relation": "not-applicable"},
        {"reason_codes": ["artifacts-differ", "artifacts-differ"]},
        {"left": None},
        {"right": None},
        {"left": None, "left_matches_expected": False},
        {"right": None, "right_matches_expected": False},
    ],
)
def test_report_cannot_claim_missing_or_inapplicable_success_evidence(alter) -> None:
    vector, output = _case()
    payload = compare_authoring_paths(vector, output, output).report.model_dump(mode="json")
    payload.update(alter)
    with pytest.raises(ValidationError):
        AuthoringAdapterComparisonModel.model_validate(payload)


def test_corpus_bound_and_identifier_are_enforced(tmp_path) -> None:
    vector, _ = _case()
    (tmp_path / "wrong.json").write_text(vector.model_dump_json())
    with pytest.raises(ValueError, match="filename"):
        load_authoring_vectors(root=tmp_path)
    for index in range(32):
        (tmp_path / f"extra-{index}.json").write_text("{}")
    with pytest.raises(ValueError, match="count"):
        load_authoring_vectors(root=tmp_path)


def test_unsupported_imports_and_unstructured_advisories_do_not_claim_equivalence() -> None:
    vector, output = _case()
    for source in (
        "name: unstructured\nnodes:\n  host:\n    type: compute\n",
        "name: imports\nimports:\n  - source: missing.yaml\n    namespace: example\n",
    ):
        report = compare_authoring_paths(vector, output, replace(output, output_source=source)).report
        assert "right-invalid" in report.reason_codes
        assert not report.conformant


@pytest.mark.parametrize("name", ["1front", "front-end", "front_end"])
def test_rename_request_reuses_the_owning_portable_identifier(name) -> None:
    from raes_contracts.authoring_adapters import AuthoringOperationModel

    operation = AuthoringOperationModel(
        profile="rename-sdl-declaration/v1", target_address="nodes.web", new_local_name=name
    )
    assert operation.new_local_name == name


@pytest.mark.parametrize("name", ["Front", "_front", "x" * 65, "front\n"])
def test_rename_request_rejects_nonportable_identifiers(name) -> None:
    from raes_contracts.authoring_adapters import AuthoringOperationModel

    with pytest.raises(ValidationError):
        AuthoringOperationModel(profile="rename-sdl-declaration/v1", target_address="nodes.web", new_local_name=name)
