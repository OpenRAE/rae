"""Typed domain-profile contracts and offline admission (issue #1202)."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_conformance.conformance import _fixture_case_diagnostics
from raes_contracts.contracts import schema_bundle
from raes_contracts.domain_profiles import (
    SAFE_DOMAIN_PROFILE_SCHEMA_KEYWORDS,
    AdmittedDomainProfileDefinitionModel,
    DomainProfileAdmissionOutcome,
    DomainProfileAdmissionPolicyModel,
    DomainProfileBindingBasis,
    DomainProfileBindingModel,
    DomainProfileBindingOwnerModel,
    DomainProfileBindingProvenanceModel,
    DomainProfileBindingUse,
    DomainProfileDefinitionModel,
    DomainProfileDefinitionProvenanceModel,
    DomainProfileLimitsModel,
    DomainProfileNamespaceAdmissionModel,
    DomainProfileOperation,
    DomainProfileResolutionContextModel,
    DomainProfileResolutionOutcome,
    DomainProfileSchemaModel,
    DomainProfileSemanticContractModel,
    DomainProfileSupportDeclarationModel,
    admit_domain_profile_bindings,
    draft_domain_profile_definition,
    parse_domain_profile_binding,
    resolve_domain_profile_definition,
    seal_domain_profile_definition,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
_PUBLISHED_DOMAIN_PROFILE_FIXTURES = (
    ("domain-profile-admission-policy-v1", "valid/reference.json", True),
    ("domain-profile-admission-policy-v1", "invalid/unknown-operation.json", False),
    ("domain-profile-binding-v1", "valid/reference.json", True),
    ("domain-profile-binding-v1", "invalid/observed-without-evidence.json", False),
    ("domain-profile-binding-v1", "invalid/unknown-use.json", False),
    ("domain-profile-definition-v1", "valid/reference.json", True),
    ("domain-profile-definition-v1", "invalid/missing-coordinate.json", False),
    ("domain-profile-resolution-context-v1", "valid/reference.json", True),
    ("domain-profile-resolution-context-v1", "invalid/unbounded-limits.json", False),
    ("domain-profile-support-declaration-v1", "valid/reference.json", True),
    ("domain-profile-support-declaration-v1", "invalid/structural-without-dialects.json", False),
    ("domain-profile-support-declaration-v1", "invalid/unknown-operation.json", False),
)


def _schema(*, title: str, extra_property: str | None = None) -> DomainProfileSchemaModel:
    properties: dict[str, object] = {"name": {"type": "string"}}
    if extra_property is not None:
        properties[extra_property] = {"type": "integer"}
    return DomainProfileSchemaModel(
        dialect="https://json-schema.org/draft/2020-12/schema",
        schema_id=f"urn:example:schema:{title}",
        revision="1.0.0",
        schema_document={
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"urn:example:schema:{title}",
            "type": "object",
            "properties": properties,
            "required": ["name"],
            "additionalProperties": False,
        },
    )


def _definition(
    *,
    namespace: str,
    authority: str,
    profile_id: str,
    revision: str = "1.0.0",
    extra_property: str | None = None,
) -> DomainProfileDefinitionModel:
    return seal_domain_profile_definition(
        draft_domain_profile_definition(
            namespace=namespace,
            authority=authority,
            profile_id=profile_id,
            revision=revision,
            schema=_schema(title=profile_id, extra_property=extra_property),
            semantic_contract=DomainProfileSemanticContractModel(
                authority=authority,
                contract_id=f"{profile_id}-semantics",
                revision="1.0.0",
                digest="sha256:" + "1" * 64,
            ),
            allowed_contexts=("artifact-acquisition",),
        )
    )


def _definition_with_schema_document(
    document: dict[str, object],
    *,
    required_vocabularies: tuple[str, ...] = (),
) -> DomainProfileDefinitionModel:
    return seal_domain_profile_definition(
        draft_domain_profile_definition(
            namespace="com.example.private",
            authority="urn:example:profile-authority",
            profile_id="repository",
            revision="1.0.0",
            schema=DomainProfileSchemaModel(
                dialect="https://json-schema.org/draft/2020-12/schema",
                schema_id="urn:example:schema:repository",
                revision="1.0.0",
                required_vocabularies=required_vocabularies,
                schema_document=document,
            ),
            semantic_contract=DomainProfileSemanticContractModel(
                authority="urn:example:profile-authority",
                contract_id="repository-semantics",
                revision="1.0.0",
                digest="sha256:" + "3" * 64,
            ),
            allowed_contexts=("artifact-acquisition",),
        )
    )


def _admitted(definition: DomainProfileDefinitionModel) -> AdmittedDomainProfileDefinitionModel:
    return AdmittedDomainProfileDefinitionModel(
        definition=definition,
        provenance=DomainProfileDefinitionProvenanceModel(
            source_locator="urn:example:admitted-profile",
            source_digest=definition.coordinate.definition_digest,
            trust_decision_id="trust-private-profile-1",
        ),
    )


def _context(
    *definitions: DomainProfileDefinitionModel,
    namespace_admissions: tuple[DomainProfileNamespaceAdmissionModel, ...] | None = None,
    support_declarations: tuple[DomainProfileSupportDeclarationModel, ...] = (),
) -> DomainProfileResolutionContextModel:
    first = definitions[0]
    return DomainProfileResolutionContextModel(
        namespace_admissions=namespace_admissions
        or (
            DomainProfileNamespaceAdmissionModel(
                namespace=first.coordinate.namespace,
                authority=first.coordinate.authority,
                trust_decision_id="trust-namespace-1",
            ),
        ),
        definitions=tuple(_admitted(definition) for definition in definitions),
        support_declarations=support_declarations,
    )


def _support(
    definition: DomainProfileDefinitionModel,
    *operations: DomainProfileOperation,
    vocabularies: tuple[str, ...] = (),
) -> DomainProfileSupportDeclarationModel:
    return DomainProfileSupportDeclarationModel(
        coordinate=definition.coordinate,
        semantic_contract=definition.semantic_contract,
        operations=tuple(sorted(operations, key=str)),
        supported_schema_dialects=("https://json-schema.org/draft/2020-12/schema",),
        supported_vocabularies=tuple(sorted(vocabularies)),
        supported_schema_keywords=SAFE_DOMAIN_PROFILE_SCHEMA_KEYWORDS,
    )


def _binding(
    definition: DomainProfileDefinitionModel,
    *,
    value: object,
    use: DomainProfileBindingUse = DomainProfileBindingUse.CONSTRAINT,
    children: tuple[DomainProfileBindingModel, ...] = (),
    basis: DomainProfileBindingBasis | None = None,
) -> DomainProfileBindingModel:
    return DomainProfileBindingModel(
        binding_id="repository-binding",
        coordinate=definition.coordinate,
        owner=DomainProfileBindingOwnerModel(
            owning_contract_id="artifact-requirement/v1",
            canonical_address="#/source/artifact_requirement",
            concept_family="tools-and-artifacts",
            lifecycle_phase="authoring",
            context="artifact-acquisition",
            use=use,
        ),
        value=value,
        provenance=DomainProfileBindingProvenanceModel(
            basis=basis
            or (
                DomainProfileBindingBasis.BACKEND_SELECTED
                if use is DomainProfileBindingUse.TYPED_REPORT
                else DomainProfileBindingBasis.AUTHOR_SUPPLIED
            ),
            source_ref="urn:example:binding-source",
        ),
        children=children,
    )


def test_standard_and_private_definitions_share_one_exact_sealed_contract() -> None:
    standard = _definition(
        namespace="org.openrae.standard",
        authority="https://openrae.org/profiles",
        profile_id="repository",
    )
    private = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )

    assert type(standard) is type(private) is DomainProfileDefinitionModel
    assert standard.coordinate.definition_digest.startswith("sha256:")
    assert private.coordinate.definition_digest.startswith("sha256:")
    assert standard.coordinate.namespace != private.coordinate.namespace
    assert standard.profile_schema.schema_digest.startswith("sha256:")
    assert private.profile_schema.schema_digest.startswith("sha256:")


def test_portable_contract_family_is_published_through_the_canonical_schema_bundle() -> None:
    bundle = schema_bundle()
    expected = {
        "domain-profile-admission-policy-v1",
        "domain-profile-binding-v1",
        "domain-profile-definition-v1",
        "domain-profile-resolution-context-v1",
        "domain-profile-support-declaration-v1",
    }

    assert expected <= bundle.keys()
    assert bundle["domain-profile-definition-v1"]["properties"]["schema_version"]["const"] == (
        "domain-profile-definition/v1"
    )


@pytest.mark.parametrize(
    ("contract_id", "fixture", "valid"),
    _PUBLISHED_DOMAIN_PROFILE_FIXTURES,
)
def test_published_domain_profile_fixtures_use_the_canonical_conformance_path(
    contract_id: str,
    fixture: str,
    valid: bool,
) -> None:
    path = REPO_ROOT / "contracts/fixtures/profiles" / contract_id / fixture
    diagnostics = _fixture_case_diagnostics(contract_id, json.loads(path.read_text(encoding="utf-8")))

    assert (not diagnostics) is valid


@pytest.mark.parametrize(
    ("contract_id", "fixture", "valid"),
    _PUBLISHED_DOMAIN_PROFILE_FIXTURES,
)
def test_published_domain_profile_schemas_enforce_fixture_contracts(
    contract_id: str,
    fixture: str,
    valid: bool,
) -> None:
    fixture_path = REPO_ROOT / "contracts/fixtures/profiles" / contract_id / fixture
    schema_path = REPO_ROOT / "contracts/schemas/profiles" / f"{contract_id}.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    assert Draft202012Validator(schema).is_valid(payload) is valid


def test_exact_definition_resolves_only_from_the_supplied_offline_context() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )

    result = resolve_domain_profile_definition(definition.coordinate, _context(definition))

    assert result.outcome is DomainProfileResolutionOutcome.RESOLVED
    assert result.definition == definition
    assert result.provenance == _admitted(definition).provenance
    assert result.diagnostics == ()


def test_missing_definition_and_incompatible_revision_are_distinct() -> None:
    available = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
        revision="2.0.0",
    )
    requested_elsewhere = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="generator",
    )
    missing = resolve_domain_profile_definition(requested_elsewhere.coordinate, _context(available))
    incompatible = resolve_domain_profile_definition(
        requested_elsewhere.coordinate.model_copy(update={"profile_id": "repository", "revision": "1.0.0"}),
        _context(available),
    )

    assert missing.outcome is DomainProfileResolutionOutcome.DEFINITION_UNAVAILABLE
    assert incompatible.outcome is DomainProfileResolutionOutcome.INCOMPATIBLE_REVISION
    assert not missing.resolved
    assert not incompatible.resolved


def test_exact_digest_mismatch_is_not_revision_fallback() -> None:
    available = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    requested = available.coordinate.model_copy(update={"definition_digest": "sha256:" + "f" * 64})

    result = resolve_domain_profile_definition(requested, _context(available))

    assert result.outcome is DomainProfileResolutionOutcome.DIGEST_MISMATCH
    assert not result.resolved


def test_binding_admission_preserves_distinct_resolution_failures() -> None:
    available = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    unavailable_context = DomainProfileResolutionContextModel(
        namespace_admissions=(
            DomainProfileNamespaceAdmissionModel(
                namespace=available.coordinate.namespace,
                authority=available.coordinate.authority,
                trust_decision_id="trust-namespace-1",
            ),
        ),
        definitions=(),
    )
    digest_mismatch = available.coordinate.model_copy(update={"definition_digest": "sha256:" + "f" * 64})

    unavailable = admit_domain_profile_bindings(
        (_binding(available, value={"name": "unavailable"}),),
        unavailable_context,
        policy=DomainProfileAdmissionPolicyModel(),
    )
    conflicting = admit_domain_profile_bindings(
        (_binding(available, value={"name": "conflicting"}).model_copy(update={"coordinate": digest_mismatch}),),
        _context(available),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert unavailable.results[0].resolution_outcome is DomainProfileResolutionOutcome.DEFINITION_UNAVAILABLE
    assert conflicting.results[0].resolution_outcome is DomainProfileResolutionOutcome.DIGEST_MISMATCH
    assert unavailable.results[0].diagnostics[0].code == "domain-profile.definition-unavailable"
    assert conflicting.results[0].diagnostics[0].code == "domain-profile.digest-mismatch"


def test_same_logical_coordinate_with_different_digests_is_a_fatal_collision() -> None:
    first = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    conflicting = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
        extra_property="priority",
    )

    result = resolve_domain_profile_definition(first.coordinate, _context(first, conflicting))

    assert result.outcome is DomainProfileResolutionOutcome.COORDINATE_COLLISION
    assert not result.resolved
    assert result.definition is None


def test_namespace_ownership_collision_is_not_first_match_resolution() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    admissions = (
        DomainProfileNamespaceAdmissionModel(
            namespace="com.example.private",
            authority="urn:example:profile-authority",
            trust_decision_id="trust-a",
        ),
        DomainProfileNamespaceAdmissionModel(
            namespace="com.example.private",
            authority="urn:other:profile-authority",
            trust_decision_id="trust-b",
        ),
    )

    result = resolve_domain_profile_definition(
        definition.coordinate,
        _context(definition, namespace_admissions=admissions),
    )

    assert result.outcome is DomainProfileResolutionOutcome.NAMESPACE_COLLISION
    assert not result.resolved
    assert len(result.diagnostics) == 1
    assert "com.example.private" not in result.diagnostics[0].message


def test_nested_private_binding_is_structurally_validated_with_exact_support() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    child = _binding(
        definition,
        value={"name": "nested-mirror"},
        use=DomainProfileBindingUse.ANNOTATION,
    ).model_copy(update={"binding_id": "nested-binding"})
    binding = _binding(definition, value={"name": "private-mirror"}, children=(child,))
    support = _support(
        definition,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.SEMANTIC_VALIDATION,
    )

    report = admit_domain_profile_bindings(
        (binding,),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert report.admitted
    assert [result.binding_id for result in report.results] == ["repository-binding", "nested-binding"]
    assert {result.outcome for result in report.results} == {DomainProfileAdmissionOutcome.VALIDATED}
    assert all(result.structurally_valid for result in report.results)
    assert all(not result.opaque for result in report.results)


def test_structurally_invalid_profile_value_fails_without_echoing_payload() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    binding = _binding(definition, value={"name": 42, "secret": "DO-NOT-ECHO"})
    support = _support(
        definition,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.SEMANTIC_VALIDATION,
    )

    report = admit_domain_profile_bindings(
        (binding,),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert not report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.VALUE_INVALID
    assert "DO-NOT-ECHO" not in str(report.results[0].diagnostics)


def test_unsupported_required_operation_and_vocabulary_refuse_admission() -> None:
    vocabulary = "https://example.test/vocab/required"
    definition = seal_domain_profile_definition(
        draft_domain_profile_definition(
            namespace="com.example.private",
            authority="urn:example:profile-authority",
            profile_id="repository",
            revision="1.0.0",
            schema=DomainProfileSchemaModel(
                dialect="https://json-schema.org/draft/2020-12/schema",
                schema_id="urn:example:schema:repository",
                revision="1.0.0",
                required_vocabularies=(vocabulary,),
                schema_document={
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$id": "urn:example:schema:repository",
                    "$vocabulary": {vocabulary: True},
                    "type": "object",
                },
            ),
            semantic_contract=DomainProfileSemanticContractModel(
                authority="urn:example:profile-authority",
                contract_id="repository-semantics",
                revision="1.0.0",
                digest="sha256:" + "2" * 64,
            ),
            allowed_contexts=("artifact-acquisition",),
        )
    )
    binding = _binding(definition, value={})
    vocabulary_report = admit_domain_profile_bindings(
        (binding,),
        _context(
            definition,
            support_declarations=(
                _support(
                    definition,
                    DomainProfileOperation.STRUCTURAL_VALIDATION,
                    DomainProfileOperation.SEMANTIC_VALIDATION,
                ),
            ),
        ),
        policy=DomainProfileAdmissionPolicyModel(),
    )
    operation_report = admit_domain_profile_bindings(
        (_binding(definition, value={}, use=DomainProfileBindingUse.TYPED_REPORT),),
        _context(
            definition,
            support_declarations=(
                _support(
                    definition,
                    DomainProfileOperation.STRUCTURAL_VALIDATION,
                    vocabularies=(vocabulary,),
                ),
            ),
        ),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert vocabulary_report.results[0].outcome is DomainProfileAdmissionOutcome.UNSUPPORTED_VOCABULARY
    assert operation_report.results[0].outcome is DomainProfileAdmissionOutcome.UNSUPPORTED_OPERATION
    assert not vocabulary_report.admitted
    assert not operation_report.admitted


@pytest.mark.parametrize(
    "operation",
    [
        DomainProfileOperation.SEMANTIC_VALIDATION,
        DomainProfileOperation.COMPARISON,
        DomainProfileOperation.EXECUTION,
    ],
)
def test_required_semantic_comparison_and_execution_operations_fail_honestly(
    operation: DomainProfileOperation,
) -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    structural_only = _support(definition, DomainProfileOperation.STRUCTURAL_VALIDATION)

    report = admit_domain_profile_bindings(
        (_binding(definition, value={"name": "required"}, use=DomainProfileBindingUse.ANNOTATION),),
        _context(definition, support_declarations=(structural_only,)),
        policy=DomainProfileAdmissionPolicyModel(required_operations=(operation,)),
    )

    assert not report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.UNSUPPORTED_OPERATION


def test_binding_context_must_be_allowed_by_the_exact_definition() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    binding = _binding(definition, value={"name": "private"})
    disallowed_owner = binding.owner.model_copy(update={"context": "runtime-observation"})
    support = _support(
        definition,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.SEMANTIC_VALIDATION,
    )

    report = admit_domain_profile_bindings(
        (binding.model_copy(update={"owner": disallowed_owner}),),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert not report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.CONTEXT_REFUSED


def test_absent_definition_is_opaque_only_for_explicit_non_binding_host_policy() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    annotation = _binding(
        definition,
        value={"name": "unknown-private"},
        use=DomainProfileBindingUse.OPAQUE_EXCHANGE,
    )
    context = DomainProfileResolutionContextModel(
        namespace_admissions=(
            DomainProfileNamespaceAdmissionModel(
                namespace=definition.coordinate.namespace,
                authority=definition.coordinate.authority,
                trust_decision_id="trust-namespace-1",
            ),
        ),
        definitions=(),
    )

    preserved = admit_domain_profile_bindings(
        (annotation,),
        context,
        policy=DomainProfileAdmissionPolicyModel(allow_opaque_exchange=True),
    )
    refused = admit_domain_profile_bindings(
        (_binding(definition, value={"name": "required"}),),
        context,
        policy=DomainProfileAdmissionPolicyModel(allow_opaque_exchange=True),
    )

    assert preserved.admitted
    assert preserved.results[0].outcome is DomainProfileAdmissionOutcome.OPAQUE_PRESERVED
    assert preserved.results[0].opaque
    assert not preserved.results[0].structurally_valid
    assert not preserved.results[0].semantics_supported
    assert not refused.admitted
    assert refused.results[0].outcome is DomainProfileAdmissionOutcome.RESOLUTION_REFUSED


def test_resolved_opaque_exchange_is_not_reported_valid_without_structural_validation() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    support = _support(definition, DomainProfileOperation.STRUCTURAL_VALIDATION)
    invalid = _binding(
        definition,
        value={"name": 42},
        use=DomainProfileBindingUse.OPAQUE_EXCHANGE,
    )

    report = admit_domain_profile_bindings(
        (invalid,),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(allow_opaque_exchange=True),
    )

    assert not report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.VALUE_INVALID
    assert not report.results[0].structurally_valid


def test_resolved_opaque_exchange_does_not_claim_unsupported_semantics() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    support = _support(definition, DomainProfileOperation.STRUCTURAL_VALIDATION)
    binding = _binding(
        definition,
        value={"name": "bounded-opaque-value"},
        use=DomainProfileBindingUse.OPAQUE_EXCHANGE,
    )

    report = admit_domain_profile_bindings(
        (binding,),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(allow_opaque_exchange=True),
    )

    assert report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.VALIDATED
    assert report.results[0].structurally_valid
    assert not report.results[0].semantics_supported


def test_diagnostic_truncation_cannot_hide_a_required_binding_refusal() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    context = DomainProfileResolutionContextModel(
        namespace_admissions=(
            DomainProfileNamespaceAdmissionModel(
                namespace=definition.coordinate.namespace,
                authority=definition.coordinate.authority,
                trust_decision_id="trust-namespace-1",
            ),
        ),
        definitions=(),
        limits=DomainProfileLimitsModel(max_diagnostics=1),
    )
    opaque = _binding(
        definition,
        value={"name": "opaque"},
        use=DomainProfileBindingUse.OPAQUE_EXCHANGE,
    )
    required = _binding(definition, value={"name": "required"}).model_copy(update={"binding_id": "required-binding"})

    report = admit_domain_profile_bindings(
        (opaque, required),
        context,
        policy=DomainProfileAdmissionPolicyModel(allow_opaque_exchange=True),
    )

    assert report.diagnostics_truncated
    assert len(report.results) == 1
    assert not report.admitted


def test_duplicate_json_members_and_executable_handler_fields_are_rejected() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    payload = _binding(definition, value={"name": "one"}).model_dump(mode="json")
    encoded = json.dumps(payload).replace(
        '"value": {"name": "one"}',
        '"value": {"name": "one", "name": "two"}',
    )

    with pytest.raises(ValueError, match="duplicate JSON member"):
        parse_domain_profile_binding(encoded)
    support_payload = {
        **_support(definition, DomainProfileOperation.EXECUTION).model_dump(mode="json"),
        "handler": "os.system",
    }
    with pytest.raises(ValidationError):
        DomainProfileSupportDeclarationModel.model_validate(support_payload)


def test_irrelevant_backend_internal_choice_requires_no_profile_contract() -> None:
    report = admit_domain_profile_bindings(
        (),
        DomainProfileResolutionContextModel(namespace_admissions=(), definitions=()),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert report.admitted
    assert report.results == ()


def test_local_acyclic_schema_reference_validates_without_ambient_io(monkeypatch: pytest.MonkeyPatch) -> None:
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:example:schema:repository",
        "$defs": {"name": {"type": "string", "minLength": 1}},
        "type": "object",
        "properties": {"name": {"$ref": "#/$defs/name"}},
        "required": ["name"],
        "additionalProperties": False,
    }
    definition = _definition_with_schema_document(document)
    support = _support(
        definition,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.SEMANTIC_VALIDATION,
    )

    def unexpected_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("profile admission attempted ambient I/O")

    monkeypatch.setattr(urllib.request, "urlopen", unexpected_io)
    monkeypatch.setattr(subprocess, "run", unexpected_io)
    report = admit_domain_profile_bindings(
        (_binding(definition, value={"name": "offline-private"}),),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.VALIDATED


@pytest.mark.parametrize(
    ("schema_extension", "expected"),
    [
        (
            {"$ref": "https://example.test/remote-schema.json"},
            DomainProfileAdmissionOutcome.SCHEMA_INVALID,
        ),
        (
            {"properties": {"name": {"type": "string", "pattern": "(a+)+$"}}},
            DomainProfileAdmissionOutcome.UNSUPPORTED_KEYWORD,
        ),
        (
            {"properties": {"name": {"type": "string", "x-python-handler": "os.system"}}},
            DomainProfileAdmissionOutcome.UNSUPPORTED_KEYWORD,
        ),
    ],
)
def test_remote_references_regex_and_executable_keywords_are_inertly_refused(
    schema_extension: dict[str, object],
    expected: DomainProfileAdmissionOutcome,
) -> None:
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:example:schema:repository",
        "type": "object",
        **schema_extension,
    }
    definition = _definition_with_schema_document(document)
    support = _support(
        definition,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.SEMANTIC_VALIDATION,
    )

    report = admit_domain_profile_bindings(
        (_binding(definition, value={"name": "safe"}),),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert not report.admitted
    assert report.results[0].outcome is expected


@pytest.mark.parametrize(
    "schema_extension",
    [
        {"type": "array", "uniqueItems": True},
        {"enum": [{"name": "one"}, {"name": "two"}]},
        {"const": {"name": "one"}},
    ],
)
def test_unmetered_deep_equality_keywords_are_outside_the_safe_subset(
    schema_extension: dict[str, object],
) -> None:
    definition = _definition_with_schema_document(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:example:schema:repository",
            **schema_extension,
        }
    )
    support = _support(
        definition,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.SEMANTIC_VALIDATION,
    )

    report = admit_domain_profile_bindings(
        (_binding(definition, value={"name": "one"}),),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert not report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.UNSUPPORTED_KEYWORD


def test_recursive_local_schema_and_exhausted_budgets_fail_closed() -> None:
    recursive = _definition_with_schema_document(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:example:schema:repository",
            "$defs": {
                "node": {
                    "type": "object",
                    "properties": {"next": {"$ref": "#/$defs/node"}},
                }
            },
            "$ref": "#/$defs/node",
        }
    )
    recursive_support = _support(
        recursive,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.SEMANTIC_VALIDATION,
    )
    recursive_report = admit_domain_profile_bindings(
        (_binding(recursive, value={}),),
        _context(recursive, support_declarations=(recursive_support,)),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    bounded = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    bounded_support = _support(
        bounded,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.SEMANTIC_VALIDATION,
    )
    bounded_context = _context(bounded, support_declarations=(bounded_support,)).model_copy(
        update={"limits": DomainProfileLimitsModel(max_nodes=3)}
    )
    bounded_report = admit_domain_profile_bindings(
        (_binding(bounded, value={"name": "too-many-nodes"}),),
        bounded_context,
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert recursive_report.results[0].outcome is DomainProfileAdmissionOutcome.SCHEMA_INVALID
    assert bounded_report.results[0].outcome is DomainProfileAdmissionOutcome.LIMIT_EXCEEDED


def test_json_schema_checker_and_value_evaluator_consume_the_declared_budget() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    support = _support(
        definition,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.SEMANTIC_VALIDATION,
    )
    context = _context(definition, support_declarations=(support,)).model_copy(
        update={"limits": DomainProfileLimitsModel(max_evaluations=6)}
    )

    report = admit_domain_profile_bindings(
        (_binding(definition, value={"name": "bounded"}),),
        context,
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert not report.admitted
    assert report.results[0].outcome is DomainProfileAdmissionOutcome.LIMIT_EXCEEDED


def test_definition_and_binding_provenance_remain_distinct_from_observation() -> None:
    definition = _definition(
        namespace="com.example.private",
        authority="urn:example:profile-authority",
        profile_id="repository",
    )
    support = _support(
        definition,
        DomainProfileOperation.STRUCTURAL_VALIDATION,
        DomainProfileOperation.TYPED_REPORT,
    )
    report = admit_domain_profile_bindings(
        (_binding(definition, value={"name": "selected"}, use=DomainProfileBindingUse.TYPED_REPORT),),
        _context(definition, support_declarations=(support,)),
        policy=DomainProfileAdmissionPolicyModel(),
    )

    assert report.admitted
    assert report.results[0].definition_provenance == _admitted(definition).provenance
    assert report.results[0].binding_basis is DomainProfileBindingBasis.BACKEND_SELECTED
    with pytest.raises(ValidationError, match="observed domain profile bindings require evidence refs"):
        DomainProfileBindingProvenanceModel(
            basis=DomainProfileBindingBasis.OBSERVED,
            source_ref="urn:example:observation",
        )


def test_definition_provenance_rejects_credential_bearing_locators() -> None:
    with pytest.raises(ValidationError, match="credential userinfo"):
        DomainProfileDefinitionProvenanceModel(
            source_locator="https://user:secret@example.test/profile.json",
            source_digest="sha256:" + "4" * 64,
            trust_decision_id="trust-profile-1",
        )
