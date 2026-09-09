"""External classifications never become native SDL execution facts (#989)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from raes import SDLParseError, parse_sdl
from raes.entities import Entity
from raes.features import Feature
from raes.nodes import Node
from raes.participant_behavior import ParticipantActionContract
from raes.participant_behavior_specification import ParticipantBehaviorSpecification
from raes.runtime_application import RuntimeApplicationRoute
from raes.scenario import Scenario
from raes_processor.models import RuntimeModel


@pytest.mark.parametrize(
    "source",
    [
        "name: legacy\nvulnerabilities: {}\n",
        "name: legacy\nnodes: {web: {type: compute, vulnerabilities: []}}\n",
        "name: legacy\nfeatures: {service: {type: service, vulnerabilities: []}}\n",
        "name: legacy\nentities: {team: {vulnerabilities: []}}\n",
        "name: legacy\nentities: {team: {categories: []}}\n",
        "name: legacy\nentities: {team: {entities: {person: {categories: []}}}}\n",
    ],
)
@pytest.mark.parametrize("migration_policy", ["reject", "accept"])
def test_legacy_classifications_require_explicit_artifact_migration(source, migration_policy):
    with pytest.raises(SDLParseError, match="classification migration") as caught:
        parse_sdl(source, migration_policy=migration_policy, skip_semantic_validation=True)
    assert caught.value.diagnostics
    assert {item.code for item in caught.value.diagnostics} == {"sdl.classification-migration-required"}


def test_configuration_without_weakness_labels_is_admitted():
    scenario = parse_sdl("name: native\nnodes: {web: {type: compute}}\n")
    assert scenario.semantic_validated
    assert scenario.nodes["web"].type.value == "compute"


@pytest.mark.parametrize(
    "model,fields",
    [
        (Scenario, {"vulnerabilities"}),
        (Node, {"vulnerabilities"}),
        (Feature, {"vulnerabilities"}),
        (Entity, {"vulnerabilities", "categories"}),
        (RuntimeApplicationRoute, {"vulnerability_refs"}),
        (ParticipantActionContract, {"external_mappings"}),
        (
            ParticipantBehaviorSpecification,
            {"offensive_behavior_refs", "ai_offensive_behavior_refs", "defensive_behavior_refs"},
        ),
    ],
)
def test_canonical_models_and_generated_schema_have_no_domain_classification_fields(model, fields):
    assert not (fields & model.model_fields.keys())
    schema = model.model_json_schema()
    definition = schema.get("$defs", {}).get(model.__name__, schema)
    assert not (fields & definition["properties"].keys())


def test_runtime_model_cannot_carry_intrinsic_vulnerability_templates():
    assert "vulnerability_templates" not in RuntimeModel.__dataclass_fields__


LEGACY_SOURCE = """name: legacy
nodes:
  web:
    type: compute
    vulnerabilities: [injection]
vulnerabilities:
  injection:
    name: Injection
    description: Authored classification of the web service
    technical: true
    class: CWE-89
"""


def _migration_inputs(source=LEGACY_SOURCE):
    from raes.classification_migration import legacy_classification_source_digest
    from raes_contracts.contracts import ExternalConceptBindingDocumentModel
    from raes_contracts.external_concept_bindings import ExternalConceptSchemeSnapshotModel

    root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (
            root / "contracts/fixtures/concept-authority/external-concept-bindings-v1/valid/attack-enterprise.json"
        ).read_text()
    )
    binding = payload["bindings"]["attack-execution"]
    binding["subject"]["artifact_digest"] = legacy_classification_source_digest(source).value
    binding["scheme"] = {
        "scheme_id": "example-weakness-scheme",
        "authority": "fixture-authority",
        "revision": "1",
        "source_locator": "https://example.org/catalog/1",
        "source_digest": "sha256:" + "a" * 64,
        "concept_id": "CWE-89",
    }
    binding["provenance"]["source_refs"] = [
        {
            "ref_kind": "authoring-input",
            "ref_id": "legacy-source",
            "ref_digest": binding["subject"]["artifact_digest"],
            "ref_path": "/nodes/web/vulnerabilities/0",
        }
    ]
    snapshot = ExternalConceptSchemeSnapshotModel.model_validate(
        {
            **{key: value for key, value in binding["scheme"].items() if key != "concept_id"},
            "concepts": [{"concept_id": "CWE-89"}],
        }
    )
    return ExternalConceptBindingDocumentModel.model_validate(payload), snapshot


def test_legacy_association_migrates_atomically_to_generic_binding_and_report():
    from raes.canonical import canonical_sdl_digest
    from raes.classification_migration import migrate_sdl_classifications
    from raes.external_concept_subjects import external_concept_subjects
    from raes.transformations import ArtifactTransformationPolicy
    from raes_contracts.contracts import ArtifactTransformationLossKind
    from raes_contracts.external_concept_bindings import admit_external_concept_bindings

    document, snapshot = _migration_inputs()
    policy = ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,))
    result = migrate_sdl_classifications(LEGACY_SOURCE, bindings=document, scheme_snapshots=(snapshot,), policy=policy)
    repeated = migrate_sdl_classifications(
        LEGACY_SOURCE, bindings=document, scheme_snapshots=(snapshot,), policy=policy
    )
    assert result.succeeded
    assert result.report == repeated.report
    assert result.binding_documents == repeated.binding_documents
    assert result.output.model_dump(mode="json", exclude_unset=True) == {
        "name": "legacy",
        "nodes": {"web": {"type": "compute"}},
    }
    binding = result.binding_documents[0].bindings["attack-execution"]
    assert binding.subject.artifact_digest == canonical_sdl_digest(result.output).value
    assert binding.perspective == document.bindings["attack-execution"].perspective
    assert binding.assertion == document.bindings["attack-execution"].assertion
    assert binding.approximation == document.bindings["attack-execution"].approximation
    assert binding.provenance.source_refs[0].ref_digest == result.report.source_digest
    assert result.report.losses[0].kind == ArtifactTransformationLossKind.DECLARATION_REMOVED
    assert admit_external_concept_bindings(
        result.binding_documents[0], subjects=external_concept_subjects(result.output), scheme_snapshots=(snapshot,)
    ).admitted


def test_missing_assertion_context_is_an_actionable_atomic_refusal():
    from raes.classification_migration import migrate_sdl_classifications

    result = migrate_sdl_classifications(LEGACY_SOURCE)
    assert not result.succeeded
    assert result.output is None and result.binding_documents == ()
    assert result.report.diagnostics[0].code == "classification-migration.context-required"
    assert "CWE-89" not in result.report.diagnostics[0].message


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("unavailable", "binding-admission-failed"),
        ("stale-snapshot", "binding-admission-failed"),
        ("unknown-concept", "binding-admission-failed"),
        ("duplicate-snapshot", "binding-admission-failed"),
        ("stale-subject", "context-invalid"),
        ("wrong-subject", "context-invalid"),
        ("missing-pointer", "context-invalid"),
        ("unauthorized-loss", "loss-not-authorized"),
    ],
)
def test_migration_refuses_incomplete_or_conflicting_evidence(mutation, expected):
    from raes.classification_migration import migrate_sdl_classifications
    from raes.transformations import ArtifactTransformationPolicy
    from raes_contracts.contracts import ArtifactTransformationLossKind, ExternalConceptBindingDocumentModel

    document, snapshot = _migration_inputs()
    payload = document.model_dump(mode="json")
    binding = payload["bindings"]["attack-execution"]
    snapshots = (snapshot,)
    policy = ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,))
    if mutation == "unavailable":
        snapshots = ()
    elif mutation == "stale-snapshot":
        snapshots = (snapshot.model_copy(update={"revision": "2"}),)
    elif mutation == "unknown-concept":
        term = snapshot.concepts[0].model_copy(update={"concept_id": "another-concept"})
        snapshots = (snapshot.model_copy(update={"concepts": [term]}),)
    elif mutation == "duplicate-snapshot":
        snapshots = (snapshot, snapshot)
    elif mutation == "stale-subject":
        binding["subject"]["artifact_digest"] = "sha256:" + "f" * 64
    elif mutation == "wrong-subject":
        binding["subject"]["canonical_ref"] = "nodes.other"
    elif mutation == "missing-pointer":
        binding["provenance"]["source_refs"][0]["ref_path"] = "/nodes/other/vulnerabilities/0"
    elif mutation == "unauthorized-loss":
        policy = ArtifactTransformationPolicy()
    mutated = ExternalConceptBindingDocumentModel.model_validate(payload)
    result = migrate_sdl_classifications(LEGACY_SOURCE, bindings=mutated, scheme_snapshots=snapshots, policy=policy)
    assert not result.succeeded
    assert result.output is None and result.binding_documents == ()
    assert result.report.diagnostics[0].code == f"classification-migration.{expected}"
    assert document == _migration_inputs()[0]


def test_generic_references_to_removed_vulnerability_declarations_fail_closed():
    from raes.classification_migration import migrate_sdl_classifications
    from raes.transformations import ArtifactTransformationPolicy
    from raes_contracts.contracts import ArtifactTransformationLossKind

    source = LEGACY_SOURCE + "infrastructure: {web: {count: 1, links: [injection]}}\n"
    document, snapshot = _migration_inputs(source)
    result = migrate_sdl_classifications(
        source,
        bindings=document,
        scheme_snapshots=(snapshot,),
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
    )
    assert not result.succeeded
    assert result.report.diagnostics[0].code == "classification-migration.target-invalid"


def test_native_configuration_is_unchanged_by_participant_eligibility():
    from raes.classification_migration import migrate_sdl_classifications
    from raes.transformations import ArtifactTransformationPolicy
    from raes_contracts.contracts import ArtifactTransformationLossKind, ExternalConceptBindingDocumentModel

    document, snapshot = _migration_inputs()
    payload = document.model_dump(mode="json")
    payload["bindings"]["attack-execution"]["perspective"]["participant_availability"] = {
        "kind": "eligibility-only",
        "participant_refs": ["operator"],
        "basis_refs": [{"ref_kind": "profile", "ref_id": "fixture-disclosure"}],
    }
    result = migrate_sdl_classifications(
        LEGACY_SOURCE,
        bindings=ExternalConceptBindingDocumentModel.model_validate(payload),
        scheme_snapshots=(snapshot,),
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
    )
    assert result.succeeded
    assert result.output.model_dump(mode="json", exclude_unset=True) == {
        "name": "legacy",
        "nodes": {"web": {"type": "compute"}},
    }
    assert not result.output.agents
    assert not result.output.content


def test_canonical_source_migration_is_idempotent():
    from raes.classification_migration import migrate_sdl_classifications
    from raes.formatting import render_sdl_source

    source = "name: native\nnodes: {web: {type: compute}}\n"
    first = migrate_sdl_classifications(source)
    second = migrate_sdl_classifications(render_sdl_source(first.output).content)
    assert first.succeeded and second.succeeded
    assert first.output == second.output
    assert first.report.source_digest == first.report.target_digest == second.report.target_digest


@pytest.mark.parametrize(
    "allowed,succeeded",
    [
        ((), False),
        (("declaration-removed",), False),
        (("declaration-removed", "semantic-omission"), True),
    ],
)
def test_unreferenced_classification_requires_separate_omission_authorization(allowed, succeeded):
    from raes.classification_migration import migrate_sdl_classifications
    from raes.transformations import ArtifactTransformationPolicy
    from raes_contracts.contracts import ArtifactTransformationLossKind

    source = LEGACY_SOURCE.replace("vulnerabilities: [injection]", "vulnerabilities: []")
    result = migrate_sdl_classifications(
        source,
        policy=ArtifactTransformationPolicy(
            allowed_loss_kinds=tuple(ArtifactTransformationLossKind(kind) for kind in allowed)
        ),
    )
    assert result.succeeded is succeeded
    assert result.binding_documents == ()
    if succeeded:
        assert {loss.kind for loss in result.report.losses} == set(allowed)
        assert {loss.affected_identity for loss in result.report.losses} == {"vulnerabilities.injection"}
    else:
        assert result.output is None
        assert result.report.diagnostics[0].code == "classification-migration.loss-not-authorized"


def test_migration_refuses_to_normalize_native_configuration_incidentally():
    from raes.classification_migration import migrate_sdl_classifications
    from raes.transformations import ArtifactTransformationPolicy
    from raes_contracts.contracts import ArtifactTransformationLossKind

    source = LEGACY_SOURCE.replace("type: compute", "type: compute\n    resources: {ram: 1 GiB, cpu: 1}")
    document, snapshot = _migration_inputs(source)
    result = migrate_sdl_classifications(
        source,
        bindings=document,
        scheme_snapshots=(snapshot,),
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
    )
    assert result.output is None and result.binding_documents == ()
    assert result.report.diagnostics[0].code == "classification-migration.native-projection-changed"


@pytest.mark.parametrize("field", ["offensive_behavior_refs", "ai_offensive_behavior_refs", "defensive_behavior_refs"])
def test_catalogs_no_longer_govern_removed_sdl_scopes(field):
    from raes_contracts.controlled_vocabularies import validate_controlled_vocabulary_scope_values

    with pytest.raises(ValueError, match="not governed"):
        validate_controlled_vocabulary_scope_values(f"behavior_specifications.{field}", [])


def test_atlas_uses_the_same_neutral_snapshot_adapter_contract():
    from raes_contracts.external_concept_bindings import adapt_atlas_tactics_snapshot
    from raes_contracts.vocabulary_sources import load_atlas_tactics_source

    source = load_atlas_tactics_source()
    snapshot = adapt_atlas_tactics_snapshot(source)
    assert snapshot.authority == source.source_authority
    assert snapshot.revision == source.source_version
    assert [term.concept_id for term in snapshot.concepts] == [term.tactic_id for term in source.tactics]


def test_route_classification_subject_is_exact_and_never_widened_to_its_node():
    from raes.external_concept_subjects import external_concept_subjects

    scenario = parse_sdl("""name: routes
nodes:
  web:
    type: compute
    runtime:
      applications:
        - application_id: portal
          routes:
            - route_id: upload
              path: /upload
""")
    routes = [
        subject
        for subject in external_concept_subjects(scenario)
        if subject.subject_kind == "runtime-application-route"
    ]
    assert len(routes) == 1
    assert routes[0].canonical_ref == "nodes.web.runtime.applications.portal.routes.upload"


@pytest.mark.parametrize(
    "source",
    [
        "name: invalid\nname: duplicate\n",
        "name: invalid\nvulnerabilities: {v: {class: CWE-89, technical: 'true'}}\n",
        "name: invalid\nnodes: {web: {type: compute, vulnerabilities: ['${label}']}}\n",
        "name: invalid\nnodes: {web: {type: compute, vulnerabilities: [missing]}}\n",
        "name: invalid\ninstantiation_provenance: {}\n",
    ],
)
def test_malformed_legacy_sources_return_only_bounded_refusal(source):
    from raes.classification_migration import migrate_sdl_classifications

    result = migrate_sdl_classifications(source)
    assert result.output is None and result.binding_documents == ()
    assert result.report.diagnostics[0].code == "classification-migration.source-invalid"
    assert result.report.canonicalization_profile == "raw-utf8/v1"


def test_source_limits_are_enforced_before_migration():
    from raes._source_profile import SDLParserLimits
    from raes.classification_migration import migrate_sdl_classifications

    result = migrate_sdl_classifications(LEGACY_SOURCE, limits=SDLParserLimits(max_input_bytes=10))
    assert result.output is None and result.binding_documents == ()
    assert result.report.diagnostics[0].code == "classification-migration.source-invalid"


def test_route_coordinate_delimiters_cannot_create_ambiguous_subjects():
    from raes.classification_migration import migrate_sdl_classifications

    source = """name: collision
nodes:
  web:
    type: compute
    runtime:
      applications:
        - application_id: portal
          routes: [{route_id: a.routes.b, path: /one}]
        - application_id: portal.routes.a
          routes: [{route_id: b, path: /two}]
"""
    result = migrate_sdl_classifications(source)
    assert result.output is None and result.binding_documents == ()
    assert result.report.diagnostics[0].code == "classification-migration.source-invalid"


def test_curated_example_sidecars_resolve_against_current_native_scenario():
    from raes import parse_sdl_file
    from raes.external_concept_subjects import external_concept_subjects
    from raes_contracts.contracts import ExternalConceptBindingDocumentModel
    from raes_contracts.external_concept_bindings import (
        ExternalConceptSchemeSnapshotModel,
        admit_external_concept_bindings,
    )

    root = Path(__file__).resolve().parents[3]
    examples = root / "docs/migration/classification-examples"
    document = ExternalConceptBindingDocumentModel.model_validate_json(
        (examples / "techvault.bindings.json").read_text()
    )
    snapshot = ExternalConceptSchemeSnapshotModel.model_validate_json((examples / "techvault.scheme.json").read_text())
    scenario = parse_sdl_file(root / "examples/scenarios/techvault.sdl.yaml")
    assert admit_external_concept_bindings(
        document, subjects=external_concept_subjects(scenario), scheme_snapshots=(snapshot,)
    ).admitted
    assert len(document.bindings) == 4
    assert {b.subject.subject_kind for b in document.bindings.values()} == {"node", "runtime-application-route"}
    assert all(
        b.confidence.posture == "unknown" and b.review.status == "unreviewed" for b in document.bindings.values()
    )


def test_removal_timeline_keeps_explicit_legacy_reader_and_canonical_exclusion():
    import yaml

    root = Path(__file__).resolve().parents[3]
    payload = yaml.safe_load((root / "specs/evolution/deprecation-records.yaml").read_text())
    records = payload["records"]
    record = next(item for item in records if item["id"] == "sdl-domain-classification-fields")
    assert record["status"] == "removed"
    assert "migrate_sdl_classifications" in str(record)


NATIVE_MIGRATION_SOURCE = """name: native
nodes:
  web:
    type: compute
    runtime:
      applications:
        - application_id: portal
          routes: [{route_id: upload, path: /upload, methods: [GET]}]
features: {service: {type: service}}
entities: {team: {role: red, entities: {member: {role: red}}}}
agents: {operator: {entity: team}}
behavior_specifications: {behavior: {semantic_version: 1.0.0, participant_refs: [operator], action_contract_refs: [inspect]}}
action_contracts:
  inspect:
    semantic_version: 1.0.0
    behavioral_granularity: atomic
    procedure_basis: author procedure
    realization_profile: backend-declared
    fidelity_claim: intent only
    preconditions:
      - precondition_id: exists
        precondition_class: target
        description: target exists
        support_refs: [nodes.web]
    effects:
      - effect_id: none
        effect_class: no_effect
        description: no native changes
    failure_classes: [unknown]
"""


@pytest.mark.parametrize(
    "path,field,subject_ref",
    [
        (("nodes", "web"), "vulnerabilities", "nodes.web"),
        (("features", "service"), "vulnerabilities", "features.service"),
        (("entities", "team"), "vulnerabilities", "entities.team"),
        (("entities", "team", "entities", "member"), "vulnerabilities", "entities.team.member"),
        (("entities", "team", "entities", "member"), "categories", "entities.team.member"),
        (("behavior_specifications", "behavior"), "offensive_behavior_refs", "behavior_specifications.behavior"),
        (("behavior_specifications", "behavior"), "ai_offensive_behavior_refs", "behavior_specifications.behavior"),
        (("behavior_specifications", "behavior"), "defensive_behavior_refs", "behavior_specifications.behavior"),
        (("action_contracts", "inspect"), "external_mappings", "action_contracts.inspect"),
        (
            ("nodes", "web", "runtime", "applications", 0, "routes", 0),
            "vulnerability_refs",
            "nodes.web.runtime.applications.portal.routes.upload",
        ),
    ],
)
def test_every_supported_surface_externalizes_without_changing_native_runtime(path, field, subject_ref):
    import yaml
    from raes.classification_migration import migrate_sdl_classifications
    from raes.external_concept_subjects import external_concept_subjects
    from raes.transformations import ArtifactTransformationPolicy
    from raes_contracts.contracts import ArtifactTransformationLossKind, ExternalConceptBindingDocumentModel
    from raes_processor.compiler import compile_runtime_model

    native = parse_sdl(NATIVE_MIGRATION_SOURCE)
    payload = native.model_dump(mode="json", by_alias=True, exclude_unset=True)
    cursor = payload
    for part in path:
        cursor = cursor[part]
    if field in {"vulnerabilities", "vulnerability_refs"}:
        payload["vulnerabilities"] = {
            "injection": {"name": "Injection", "description": "Authored weakness label", "class": "CWE-89"}
        }
        cursor[field] = ["injection"]
    elif field == "external_mappings":
        cursor[field] = [
            {
                "system": "custom-scheme",
                "identifier": "old-label",
                "loss_label": "lossy",
                "rationale": "Historical authored rationale",
            }
        ]
    else:
        cursor[field] = ["old-label"]
    source = yaml.safe_dump(payload, sort_keys=False)
    document, snapshot = _migration_inputs(source)
    context = document.model_dump(mode="json")
    assertion = context["bindings"]["attack-execution"]
    source_digest = assertion["subject"]["artifact_digest"]
    assertion["subject"] = next(
        s for s in external_concept_subjects(native) if s.canonical_ref == subject_ref
    ).model_dump(mode="json")
    assertion["subject"]["artifact_digest"] = source_digest
    assertion["provenance"]["source_refs"][0]["ref_path"] = "/" + "/".join(map(str, (*path, field, 0)))
    context = ExternalConceptBindingDocumentModel.model_validate(context)
    result = migrate_sdl_classifications(
        source,
        bindings=context,
        scheme_snapshots=(snapshot,),
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
    )
    assert result.succeeded, result.report.diagnostics
    assert result.output == native
    assert compile_runtime_model(result.output) == compile_runtime_model(native)
    converted = result.binding_documents[0].bindings["attack-execution"]
    assert converted.subject.canonical_ref == subject_ref
    assert converted.assertion == context.bindings["attack-execution"].assertion
    assert converted.provenance.source_refs[0].ref_path.endswith(f"/{field}/0")


def test_existing_sidecars_are_retargeted_without_rewriting_their_provenance():
    from raes.classification_migration import migrate_sdl_classifications
    from raes.transformations import ArtifactTransformationPolicy
    from raes_contracts.contracts import ArtifactTransformationLossKind, ExternalConceptBindingDocumentModel

    context, snapshot = _migration_inputs()
    existing = context.model_dump(mode="json")
    existing["binding_set_id"] = "existing-interpretation"
    binding = existing["bindings"]["attack-execution"]
    binding["perspective"]["perspective"] = "independent-existing-interpretation"
    binding["provenance"]["source_refs"][0]["ref_path"] = "/nodes/web"
    existing = ExternalConceptBindingDocumentModel.model_validate(existing)
    result = migrate_sdl_classifications(
        LEGACY_SOURCE,
        bindings=context,
        scheme_snapshots=(snapshot,),
        existing_binding_documents=(existing,),
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
    )
    assert result.succeeded and len(result.binding_documents) == 2
    output = result.binding_documents[1].bindings["attack-execution"]
    assert output.subject.artifact_digest == result.report.target_digest
    assert output.provenance == existing.bindings["attack-execution"].provenance


def test_historical_vm_snapshot_default_cleanup_never_drops_assertions():
    from copy import deepcopy

    from pydantic import ValidationError
    from raes.canonical import InstantiatedScenarioSnapshot, migrate_legacy_instantiated_snapshot_payload

    root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (root / "docs/research/formal-semantic-validation/corpus/exploit-path-valid-v2.json").read_text()
    )["snapshot"]
    original = deepcopy(payload)
    migrated, changed = migrate_legacy_instantiated_snapshot_payload(payload)
    assert changed and payload == original
    assert "vulnerabilities" not in migrated["scenario"]
    assert InstantiatedScenarioSnapshot.model_validate(migrated)
    payload["scenario"]["nodes"]["target"]["vulnerabilities"] = ["historical-claim"]
    migrated, changed = migrate_legacy_instantiated_snapshot_payload(payload)
    assert changed and migrated["scenario"]["nodes"]["target"]["vulnerabilities"] == ["historical-claim"]
    with pytest.raises(ValidationError, match="classification migration"):
        InstantiatedScenarioSnapshot.model_validate(migrated)


@pytest.mark.parametrize(
    "nodes", ["{}", "{switch: {type: switch}}", "{host: {type: compute, resources: {ram: 1 GiB, cpu: 1}}}"]
)
def test_empty_snapshot_classification_defaults_migrate_without_legacy_vm_nodes(nodes):
    from copy import deepcopy

    from raes import instantiate_scenario
    from raes.canonical import (
        InstantiatedScenarioSnapshot,
        migrate_legacy_instantiated_snapshot_join,
        migrate_legacy_instantiated_snapshot_payload,
    )
    from raes_contracts.canonical import canonical_json_digest

    scenario = instantiate_scenario(parse_sdl("name: empty-defaults\nnodes: " + nodes + "\n"))
    clean = InstantiatedScenarioSnapshot(profile="raes-sdl-instantiated-snapshot/v1", scenario=scenario).model_dump(
        mode="json"
    )
    payload = deepcopy(clean)
    payload["scenario"]["vulnerabilities"] = {}
    for node in payload["scenario"]["nodes"].values():
        node["vulnerabilities"] = []
    original = deepcopy(payload)
    migrated, changed = migrate_legacy_instantiated_snapshot_payload(payload)
    assert changed and migrated == clean and payload == original
    admitted = InstantiatedScenarioSnapshot.model_validate(payload)
    assert admitted.model_dump(mode="json") == clean
    joined, digest, changed = migrate_legacy_instantiated_snapshot_join(payload, canonical_json_digest(payload))
    assert changed and joined == clean and digest == canonical_json_digest(clean)
    with pytest.raises(ValueError, match="must bind"):
        migrate_legacy_instantiated_snapshot_join(payload, "sha256:" + "0" * 64)
    assert migrate_legacy_instantiated_snapshot_payload(clean) == (clean, False)


def test_nonempty_compute_snapshot_classification_is_not_erased():
    from raes import instantiate_scenario
    from raes.canonical import InstantiatedScenarioSnapshot

    scenario = instantiate_scenario(
        parse_sdl("name: classified\nnodes: {host: {type: compute, resources: {ram: 1 GiB, cpu: 1}}}\n")
    )
    payload = InstantiatedScenarioSnapshot(profile="raes-sdl-instantiated-snapshot/v1", scenario=scenario).model_dump(
        mode="json"
    )
    payload["scenario"]["vulnerabilities"] = {}
    payload["scenario"]["nodes"]["host"]["vulnerabilities"] = ["authored-claim"]
    with pytest.raises(ValueError, match="classification migration"):
        InstantiatedScenarioSnapshot.model_validate(payload)


def test_rendered_classification_uses_ordinary_content_and_disclosure_contract():
    from raes_contracts.canonical import canonical_json_digest
    from raes_processor.compiler import compile_runtime_model

    root = Path(__file__).resolve().parents[3]
    binding_payload = json.loads((root / "docs/migration/classification-examples/techvault.bindings.json").read_text())
    digest = canonical_json_digest(binding_payload)
    source = (
        root / "contracts/fixtures/sdl/participant-inject-delivery-v1/valid/participant-directed.yaml"
    ).read_text()
    rendered = (
        f"Historical author classification CWE-434; binding legacy-association-1 in {digest}; confidence unknown."
    )
    source = source.replace("text: governed participant briefing", f"text: {rendered}")
    scenario = parse_sdl(source)
    assert scenario.content["briefing"].text == rendered
    assert scenario.content["briefing"].sensitive is True
    disclosure = scenario.behavior_specifications["red-briefing"].participant_inject_deliveries["briefing"]
    assert disclosure.source_item_ref == "content.briefing"
    assert disclosure.observation_boundary_ref == "red-view"
    assert disclosure.evidence_requirement_refs == ["briefing-delivery-evidence"]
    compiled = compile_runtime_model(scenario)
    delivery = compiled.participant_inject_deliveries[
        "participant.behavior-specification.red-briefing.inject-delivery.briefing"
    ]
    assert delivery.participant_address == "participant.behavior.red-agent"
    assert scenario.agents["red-agent"].initial_knowledge is None
