"""Pure artifact-transformation contract and operation tests for AUT-810."""

from __future__ import annotations

import json
import logging
import textwrap
from copy import deepcopy
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError
from raes import (
    ArtifactTransformationPolicy,
    RemoveSDLDeclarationRequest,
    RenameSDLDeclarationRequest,
    canonical_sdl_bytes,
    canonicalize_portable_contract,
    compare_canonical_artifacts,
    parse_sdl,
    parse_sdl_file,
    remove_sdl_declaration,
    rename_sdl_declaration,
)
from raes_conformance.artifact_transformations import run_artifact_transformation_fixture_suite
from raes_conformance.conformance.validators import validate_contract_payload
from raes_contracts.contracts import (
    ArtifactTransformationCheckModel,
    ArtifactTransformationKind,
    ArtifactTransformationLossKind,
    ArtifactTransformationPreservationModel,
    ArtifactTransformationReportModel,
    ArtifactTransformationStatus,
    ContractModel,
    ExternalConceptBindingDocumentModel,
    PreservationOutcome,
    TransformationCheckOutcome,
    schema_bundle,
)

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64
REPO_ROOT = Path(__file__).resolve().parents[3]


def _successful_report() -> ArtifactTransformationReportModel:
    return ArtifactTransformationReportModel(
        operation_profile="canonicalize-portable-contract/v1",
        status=ArtifactTransformationStatus.SUCCESS,
        artifact_kind=ArtifactTransformationKind.PORTABLE_CONTRACT,
        source_profile="external-concept-bindings/v1",
        target_profile="external-concept-bindings/v1",
        canonicalization_profile="rfc8785-jcs-sha256/v1",
        source_digest=_DIGEST_A,
        target_digest=_DIGEST_A,
        policy_digest=_DIGEST_B,
        derivation_digest=_DIGEST_C,
        preconditions=(
            ArtifactTransformationCheckModel(
                check_id="source-admitted",
                outcome=TransformationCheckOutcome.PASSED,
            ),
        ),
        postconditions=(
            ArtifactTransformationCheckModel(
                check_id="canonical-identity",
                outcome=TransformationCheckOutcome.PASSED,
            ),
        ),
        preservation=ArtifactTransformationPreservationModel(
            profile="canonical-artifact-identity",
            outcome=PreservationOutcome.VERIFIED,
            evidence_digests=(_DIGEST_A,),
        ),
    )


def test_transformation_report_is_closed_frozen_and_deterministic() -> None:
    report = _successful_report()

    assert report.schema_version == "artifact-transformation-report/v1"
    assert report.model_dump_json() == _successful_report().model_dump_json()
    assert "artifact-transformation-report-v1" in schema_bundle()

    invalid_payload = report.model_dump(mode="json") | {"unknown": "forbidden"}
    with pytest.raises(ValidationError):
        ArtifactTransformationReportModel.model_validate(invalid_payload)
    with pytest.raises(ValidationError):
        report.status = ArtifactTransformationStatus.REFUSED  # type: ignore[misc]


def test_success_requires_a_target_and_verified_evidence() -> None:
    payload = _successful_report().model_dump(mode="json")
    payload["target_digest"] = None

    with pytest.raises(ValidationError, match="successful transformation"):
        ArtifactTransformationReportModel.model_validate(payload)

    payload = _successful_report().model_dump(mode="json")
    payload["preservation"]["evidence_digests"] = []
    with pytest.raises(ValidationError, match="verified preservation"):
        ArtifactTransformationReportModel.model_validate(payload)


def _referenced_scenario():
    return parse_sdl(
        textwrap.dedent(
            """
            name: rename-reference-case
            nodes:
              web: {type: compute, resources: {ram: 1 GiB, cpu: 1}}
            content:
              payload: {type: file, target: web, path: /opt/payload}
            relationships:
              loop: {type: connects_to, source: web, target: web}
            """
        )
    )


def test_rename_is_atomic_deterministic_and_rewrites_resolved_references() -> None:
    scenario = _referenced_scenario()
    source_bytes = canonical_sdl_bytes(scenario)
    request = RenameSDLDeclarationRequest(
        target_address="nodes.web",
        new_local_name="frontend",
    )

    first = rename_sdl_declaration(scenario, request)
    second = rename_sdl_declaration(scenario, request)

    assert first.output is not None
    assert first.report.status == ArtifactTransformationStatus.SUCCESS
    assert first.report == second.report
    assert canonical_sdl_bytes(first.output) == canonical_sdl_bytes(second.output)
    assert canonical_sdl_bytes(scenario) == source_bytes
    assert set(first.output.nodes) == {"frontend"}
    assert first.output.content["payload"].target == "frontend"
    assert first.output.relationships["loop"].source == "frontend"
    assert first.output.relationships["loop"].target == "frontend"
    assert [(item.before, item.after) for item in first.report.identity_map] == [("nodes.web", "nodes.frontend")]
    assert first.report.preservation.profile == "sdl-declaration-identity-transport/v1"
    assert first.report.preservation.outcome == PreservationOutcome.VERIFIED


def test_rename_refuses_aliases_and_collisions_without_partial_output() -> None:
    scenario = parse_sdl(
        """\
name: refusal-case
nodes:
  web: {type: switch}
  frontend: {type: switch}
"""
    )
    source_bytes = canonical_sdl_bytes(scenario)

    alias_result = rename_sdl_declaration(
        scenario,
        RenameSDLDeclarationRequest(target_address="web", new_local_name="renamed"),
    )
    collision_result = rename_sdl_declaration(
        scenario,
        RenameSDLDeclarationRequest(target_address="nodes.web", new_local_name="frontend"),
    )

    assert alias_result.output is None
    assert collision_result.output is None
    assert alias_result.report.status == ArtifactTransformationStatus.REFUSED
    assert collision_result.report.status == ArtifactTransformationStatus.REFUSED
    assert alias_result.report.target_digest is None
    assert collision_result.report.target_digest is None
    assert canonical_sdl_bytes(scenario) == source_bytes


def test_rename_refuses_node_identifiers_over_the_sdl_limit() -> None:
    scenario = _referenced_scenario()

    result = rename_sdl_declaration(
        scenario,
        RenameSDLDeclarationRequest(
            target_address="nodes.web",
            new_local_name="n" * 36,
        ),
    )

    assert result.output is None
    assert result.report.status == ArtifactTransformationStatus.REFUSED
    assert {diagnostic.code for diagnostic in result.report.diagnostics} == {
        "artifact-transformation.target-unsupported"
    }


def test_rename_updates_module_exports_and_composed_reference_semantics() -> None:
    fixture_root = REPO_ROOT / "contracts" / "fixtures" / "sdl" / "variation-points-v1" / "composition"
    module = parse_sdl((fixture_root / "module.yaml").read_text(encoding="utf-8"))

    module_result = rename_sdl_declaration(
        module,
        RenameSDLDeclarationRequest(target_address="nodes.primary", new_local_name="frontend"),
    )

    assert module_result.output is not None
    assert module_result.output.module is not None
    assert module_result.output.module.exports["nodes"] == ["frontend", "secondary"]
    assert module_result.output.content["payload"].target == "frontend"

    composed = parse_sdl_file(fixture_root / "root.yaml")
    composed_result = rename_sdl_declaration(
        composed,
        RenameSDLDeclarationRequest(
            target_address="nodes.shared.primary",
            new_local_name="frontend",
        ),
    )

    assert composed_result.output is not None
    assert composed_result.output.expansion_provenance == composed.expansion_provenance
    assert "shared.frontend" in composed_result.output.nodes
    assert composed_result.output.content["shared.payload"].target == "shared.frontend"


def _concept_binding_inputs():
    fixture_root = REPO_ROOT / "contracts" / "fixtures" / "concept-authority" / "external-concept-bindings-v1"
    scenario = parse_sdl((fixture_root / "context" / "subject.sdl.yaml").read_text(encoding="utf-8"))
    payload = json.loads((fixture_root / "valid" / "attack-enterprise.json").read_text(encoding="utf-8"))
    node_binding = payload["bindings"]["attack-execution"]
    scenario_binding = deepcopy(node_binding)
    scenario_binding["binding_id"] = "attack-scenario-context"
    scenario_binding["subject"]["subject_kind"] = "scenario"
    scenario_binding["subject"]["canonical_ref"] = "scenario.external-binding-subject"
    payload["bindings"]["attack-scenario-context"] = scenario_binding
    return scenario, ExternalConceptBindingDocumentModel.model_validate(payload)


def test_rename_retargets_every_supplied_concept_subject_digest() -> None:
    scenario, document = _concept_binding_inputs()

    result = rename_sdl_declaration(
        scenario,
        RenameSDLDeclarationRequest(target_address="nodes.web", new_local_name="frontend"),
        binding_documents=(document,),
    )

    assert result.output is not None
    assert len(result.binding_documents) == 1
    transformed = result.binding_documents[0]
    assert transformed.bindings["attack-execution"].subject.canonical_ref == "nodes.frontend"
    assert transformed.bindings["attack-scenario-context"].subject.canonical_ref == (
        "scenario.external-binding-subject"
    )
    assert {binding.subject.artifact_digest for binding in transformed.bindings.values()} == {
        result.report.target_digest
    }
    assert document.bindings["attack-execution"].subject.canonical_ref == "nodes.web"


def test_rename_refuses_a_stale_supplied_concept_subject() -> None:
    scenario, document = _concept_binding_inputs()
    binding = document.bindings["attack-execution"]
    stale = document.model_copy(
        update={
            "bindings": document.bindings
            | {
                "attack-execution": binding.model_copy(
                    update={"subject": binding.subject.model_copy(update={"artifact_digest": _DIGEST_A})}
                )
            }
        }
    )

    result = rename_sdl_declaration(
        scenario,
        RenameSDLDeclarationRequest(target_address="nodes.web", new_local_name="frontend"),
        binding_documents=(stale,),
    )

    assert result.output is None
    assert result.report.status == ArtifactTransformationStatus.REFUSED
    assert {diagnostic.code for diagnostic in result.report.diagnostics} == {
        "artifact-transformation.linked-artifact-stale"
    }


def _removal_scenario():
    return parse_sdl(
        """\
name: explicit-loss-case
nodes:
  retained: {type: switch}
  obsolete: {type: switch}
"""
    )


def test_removal_requires_exact_typed_loss_authorization() -> None:
    scenario = _removal_scenario()
    source_bytes = canonical_sdl_bytes(scenario)
    request = RemoveSDLDeclarationRequest(target_address="nodes.obsolete")

    refused = remove_sdl_declaration(scenario, request)
    allowed = remove_sdl_declaration(
        scenario,
        request,
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
    )

    assert refused.output is None
    assert refused.report.status == ArtifactTransformationStatus.REFUSED
    assert refused.report.losses[0].kind == ArtifactTransformationLossKind.DECLARATION_REMOVED
    assert allowed.output is not None
    assert set(allowed.output.nodes) == {"retained"}
    assert allowed.report.status == ArtifactTransformationStatus.SUCCESS
    assert allowed.report.preservation.outcome == PreservationOutcome.NOT_APPLICABLE
    assert allowed.report.losses[0].diagnostic.severity.value == "warning"
    assert canonical_sdl_bytes(scenario) == source_bytes

    with pytest.raises(TypeError, match="ArtifactTransformationLossKind"):
        ArtifactTransformationPolicy(("declaration-removed",))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="sorted and unique"):
        ArtifactTransformationPolicy(
            (
                ArtifactTransformationLossKind.DECLARATION_REMOVED,
                ArtifactTransformationLossKind.DECLARATION_REMOVED,
            )
        )


def test_removal_refuses_non_exact_target_addresses() -> None:
    result = remove_sdl_declaration(
        _removal_scenario(),
        RemoveSDLDeclarationRequest(target_address="obsolete"),
    )

    assert result.output is None
    assert result.report.status == ArtifactTransformationStatus.REFUSED
    assert {diagnostic.code for diagnostic in result.report.diagnostics} == {"artifact-transformation.target-not-exact"}


def test_removal_refuses_supplied_concept_bindings() -> None:
    scenario, document = _concept_binding_inputs()

    result = remove_sdl_declaration(
        scenario,
        RemoveSDLDeclarationRequest(target_address="nodes.web"),
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
        binding_documents=(document,),
    )

    assert result.output is None
    assert result.report.status == ArtifactTransformationStatus.REFUSED
    assert {diagnostic.code for diagnostic in result.report.diagnostics} == {
        "artifact-transformation.linked-artifact-unsupported"
    }


def test_authorized_removal_still_refuses_dangling_references() -> None:
    scenario = _referenced_scenario()

    result = remove_sdl_declaration(
        scenario,
        RemoveSDLDeclarationRequest(target_address="nodes.web"),
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
    )

    assert result.output is None
    assert result.report.status == ArtifactTransformationStatus.REFUSED
    assert result.report.target_digest is None
    assert {diagnostic.code for diagnostic in result.report.diagnostics} == {"artifact-transformation.target-invalid"}


def test_portable_contract_canonicalization_is_isolated_and_idempotent() -> None:
    _, document = _concept_binding_inputs()

    first = canonicalize_portable_contract(document)
    second = canonicalize_portable_contract(first.output)

    assert first.output == document
    assert first.output is not document
    assert first.report.status == ArtifactTransformationStatus.SUCCESS
    assert first.report.artifact_kind == ArtifactTransformationKind.PORTABLE_CONTRACT
    assert first.report.source_digest == first.report.target_digest
    assert first.report.preservation.profile == "canonical-artifact-identity"
    assert first.report == second.report
    assert compare_canonical_artifacts(document, first.output).equivalent


def test_portable_contract_transformation_rejects_unprofiled_models() -> None:
    class UnprofiledContract(ContractModel):
        value: int

    source = UnprofiledContract(value=1)
    comparison_peer = UnprofiledContract(value=1)

    with pytest.raises(TypeError, match="explicit governed"):
        canonicalize_portable_contract(source)
    with pytest.raises(TypeError, match="explicit governed"):
        compare_canonical_artifacts(source, comparison_peer)


def test_canonical_comparison_distinguishes_meaning_and_artifact_kind() -> None:
    scenario = _referenced_scenario()
    renamed = rename_sdl_declaration(
        scenario,
        RenameSDLDeclarationRequest(target_address="nodes.web", new_local_name="frontend"),
    )
    assert renamed.output is not None

    comparison = compare_canonical_artifacts(scenario, renamed.output)

    assert not comparison.equivalent
    assert comparison.artifact_kind == ArtifactTransformationKind.SDL_AUTHORING
    assert comparison.relation_profile == "canonical-artifact-identity"
    portable_contract = _concept_binding_inputs()[1]
    with pytest.raises(TypeError, match="same supported artifact kind"):
        compare_canonical_artifacts(scenario, portable_contract)


@settings(max_examples=24, deadline=None)
@given(
    new_name=st.from_regex(r"[a-z][a-z0-9_-]{0,14}", fullmatch=True).filter(lambda value: value not in {"web", "peer"}),
    reverse_order=st.booleans(),
)
def test_rename_property_is_repeatable_across_mapping_order(
    new_name: str,
    reverse_order: bool,
) -> None:
    node_lines = (
        "  peer: {type: switch}\n  web: {type: compute, resources: {ram: 1 GiB, cpu: 1}}"
        if reverse_order
        else "  web: {type: compute, resources: {ram: 1 GiB, cpu: 1}}\n  peer: {type: switch}"
    )
    scenario = parse_sdl(
        "name: property-case\nnodes:\n"
        f"{node_lines}\n"
        "content:\n  payload: {type: file, target: web, path: /opt/payload}\n"
    )
    request = RenameSDLDeclarationRequest(
        target_address="nodes.web",
        new_local_name=new_name,
    )

    first = rename_sdl_declaration(scenario, request)
    second = rename_sdl_declaration(scenario, request)

    assert first.output is not None
    assert second.output is not None
    assert canonical_sdl_bytes(first.output) == canonical_sdl_bytes(second.output)
    assert first.report == second.report
    assert first.output.content["payload"].target == new_name


def test_artifact_transformation_conformance_corpus() -> None:
    report = run_artifact_transformation_fixture_suite()

    assert report.profile == "artifact-transformations/v1"
    assert report.passed
    assert [case.case_id for case in report.cases] == sorted(case.case_id for case in report.cases)
    assert {case.case_id for case in report.cases} == {
        "canonicalize-portable-contract",
        "refuse-collision",
        "remove-with-explicit-loss",
        "rename-composed-reference",
        "rename-references",
    }


def test_conformance_case_outside_the_corpus_fails_without_a_log_record(tmp_path: Path, caplog) -> None:
    cases = tmp_path / "artifact-transformations-v1" / "cases"
    cases.mkdir(parents=True)
    case = {
        "case_id": "escape",
        "operation": "remove-sdl-declaration/v1",
        "source_contract": "sdl-authoring-input/v1",
        "source_path": "../outside.sdl.yaml",
        "request": {"target_address": "nodes.peer"},
        "policy": {},
        "expected": {"status": "success"},
    }
    (cases / "escape.json").write_text(json.dumps(case), encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        report = run_artifact_transformation_fixture_suite(root=tmp_path)

    assert not report.passed
    assert [item.diagnostic for item in report.cases] == ["rejected by InvalidInputError"]
    assert not [record for record in caplog.records if record.name.startswith("raes_conformance")]


def test_conformance_case_defect_fails_the_case_and_is_logged(monkeypatch, caplog) -> None:
    from raes_conformance import artifact_transformations

    def _defect(case, *, fixtures):
        raise RuntimeError("transformation defect SECRET-1678")

    monkeypatch.setattr(artifact_transformations, "_execute_case", _defect)
    with caplog.at_level(logging.ERROR, logger="raes_conformance"):
        report = run_artifact_transformation_fixture_suite()

    assert not report.passed
    assert {item.diagnostic for item in report.cases} == {"rejected by RuntimeError"}
    records = [record for record in caplog.records if record.name == "raes_conformance.artifact_transformations"]
    assert len(records) == len(report.cases)
    assert all("SECRET-1678" not in (record.getMessage() + (record.exc_text or "")) for record in records)


def test_transformation_report_positive_and_negative_fixtures() -> None:
    fixture_root = (
        REPO_ROOT / "contracts" / "fixtures" / "artifact-transformations" / "artifact-transformation-report-v1"
    )
    valid = json.loads((fixture_root / "valid" / "canonical-identity.json").read_text())
    invalid = json.loads((fixture_root / "invalid" / "success-without-target.json").read_text())

    assert not validate_contract_payload("artifact-transformation-report-v1", valid)
    assert validate_contract_payload("artifact-transformation-report-v1", invalid)
