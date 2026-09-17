"""Author-bound conversion cannot invent sentinel identity or authority."""

import pytest
import yaml
from raes import parse_sdl
from raes.canonical import canonical_sdl_digest
from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION, source_byte_digest


def context(source, decisions=()):
    from raes.semantic_migration import SDLSemanticMigrationContext

    return SDLSemanticMigrationContext(
        source_digest=source_byte_digest(source),
        adopt_recursive_constraints=True,
        admission_contract="backend-realization-preparation-v1",
        observation_contract="observation-demand-v1",
        rationale="Author adopts the separately negotiated current admission and explicit observation policy.",
        sentinel_decisions=decisions,
    )


def test_semantic_conversion_requires_explicit_policy_adoption():
    from raes.semantic_migration import migrate_sdl_semantics

    result = migrate_sdl_semantics("name: old\n")
    assert not result.succeeded
    assert result.output is None
    assert not result.binding_documents
    assert result.report.diagnostics[0].code == "semantic-migration.context-required"


def test_conversion_preserves_omitted_closed_state_and_exact_apt_repository():
    from raes.semantic_migration import migrate_sdl_semantics
    from test_issue_847_runtime_package_repositories import _package

    source = yaml.safe_dump(
        {"name": "old", "nodes": {"host": {"type": "compute", "runtime": {"packages": [_package()]}}}}
    )
    result = migrate_sdl_semantics(source, context=context(source))
    assert result.succeeded, result.report.diagnostics
    assert result.output.semantic_revision == PROGRESSIVE_SDL_REVISION
    assert result.output.realization is None
    assert result.output.nodes["host"].os is None
    assert (
        result.output.nodes["host"].runtime.packages[0].repository
        == parse_sdl(source).nodes["host"].runtime.packages[0].repository
    )
    assert result.report.source_digest == source_byte_digest(source)
    assert result.report.target_digest == canonical_sdl_digest(result.output).value
    assert result.report.preservation.outcome.value == "not-applicable"
    assert migrate_sdl_semantics(source, context=context(source)).report == result.report


def test_sentinel_refuses_until_author_decides_knowledge_or_exact_identity():
    from raes.semantic_migration import migrate_sdl_semantics

    source = "name: old\nnodes: {host: {type: compute, runtime: {database_services: [{database_service_id: db, engine: other}]}}}\n"
    missing = migrate_sdl_semantics(source, context=context(source))
    assert not missing.succeeded
    assert missing.report.diagnostics[0].code == "semantic-migration.sentinel-decision-required"
    pointer = "/nodes/host/runtime/database_services/0/engine"
    for interpretation, identity in (("knowledge", None), ("exact-identity", "x-owner:private-db")):
        decision = {
            "pointer": pointer,
            "interpretation": interpretation,
            "identity": identity,
            "rationale": "Author reviewed source provenance.",
        }
        result = migrate_sdl_semantics(source, context=context(source, (decision,)))
        assert result.succeeded, result.report.diagnostics
        assert result.output.nodes["host"].runtime.database_services[0].engine == (identity or "other")
        assert result.report.affected_identities == (pointer,)


def test_delegation_decision_requires_an_existing_open_scope():
    from raes.semantic_migration import migrate_sdl_semantics

    source = "name: old\nnodes: {host: {type: compute, runtime: {database_services: [{database_service_id: db, engine: other}]}}}\n"
    decision = {
        "pointer": "/nodes/host/runtime/database_services/0/engine",
        "interpretation": "delegated",
        "rationale": "Author delegates this choice.",
    }
    denied = migrate_sdl_semantics(source, context=context(source, (decision,)))
    assert not denied.succeeded
    opened = source + "realization: {default: open}\n"
    accepted = migrate_sdl_semantics(opened, context=context(opened, (decision,)))
    assert accepted.succeeded, accepted.report.diagnostics
    assert "engine" not in accepted.output.nodes["host"].runtime.database_services[0].model_fields_set


@pytest.mark.parametrize("reverse_decisions", [False, True])
@pytest.mark.parametrize(
    ("protocols", "actions", "expected"),
    [
        (["other"], [(0, "http")], ["http"]),
        (["other"], [(0, None)], []),
        (["other", "tls", "unknown"], [(0, None), (2, None)], ["tls"]),
        (["other", "tls", "unknown"], [(0, None), (2, "http")], ["tls", "http"]),
    ],
)
def test_scalar_list_decisions_preserve_original_pointer_addresses(protocols, actions, expected, reverse_decisions):
    from raes.semantic_migration import migrate_sdl_semantics

    source = yaml.safe_dump(
        {
            "name": "old",
            "realization": {"default": "open"},
            "nodes": {
                "host": {
                    "type": "compute",
                    "runtime": {
                        "network_detection_engines": [
                            {"network_detection_engine_id": "ids", "app_layer_protocols": protocols}
                        ]
                    },
                }
            },
        }
    )
    decisions = [
        {
            "pointer": f"/nodes/host/runtime/network_detection_engines/0/app_layer_protocols/{index}",
            "interpretation": "exact-identity" if identity else "delegated",
            "identity": identity,
            "rationale": "Author reviewed the original protocol collection.",
        }
        for index, identity in actions
    ]
    if reverse_decisions:
        decisions.reverse()
    result = migrate_sdl_semantics(source, context=context(source, decisions))
    assert result.succeeded, result.report.diagnostics
    assert result.output.nodes["host"].runtime.network_detection_engines[0].app_layer_protocols == expected


def test_stale_source_decision_is_atomic_refusal():
    from raes.semantic_migration import migrate_sdl_semantics

    result = migrate_sdl_semantics("name: changed\n", context=context("name: original\n"))
    assert not result.succeeded
    assert result.report.target_digest is None
    assert result.report.diagnostics[0].code == "semantic-migration.source-mismatch"


def test_converting_current_output_again_is_a_semantic_noop():
    from raes import render_sdl_source
    from raes.semantic_migration import migrate_sdl_semantics

    source = "name: old\nrealization: {default: open}\n"
    first = migrate_sdl_semantics(source, context=context(source))
    assert first.succeeded
    second = migrate_sdl_semantics(render_sdl_source(first.output).content)
    assert second.succeeded, second.report.diagnostics
    assert canonical_sdl_digest(first.output) == canonical_sdl_digest(second.output)
    assert second.report.source_profile == PROGRESSIVE_SDL_REVISION


def test_generated_migration_context_schema_matches_authorization_rules():
    import pytest
    from jsonschema import Draft202012Validator
    from raes.semantic_migration import SDLSemanticMigrationContext
    from raes_contracts.contracts import schema_bundle

    schema = schema_bundle()["sdl-semantic-migration-context-v1"]
    payload = context("name: old\n").model_dump(mode="json")
    Draft202012Validator(schema).validate(payload)
    payload["adopt_recursive_constraints"] = 1
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValueError):
        SDLSemanticMigrationContext.model_validate(payload)


@pytest.mark.parametrize(
    "identity", ["OTHER", "Other", "UNKNOWN", "UnKnOwN", "UN\u212aNOWN", "${engine}", "${module.engine}"]
)
def test_exact_identity_rejects_sentinel_aliases_and_variable_references(identity):
    from jsonschema import Draft202012Validator
    from raes.semantic_migration import SDLSemanticMigrationContext
    from raes_contracts.contracts import schema_bundle

    payload = context("name: old\n").model_dump(mode="json")
    payload["sentinel_decisions"] = [
        {
            "pointer": "/nodes/host/runtime/database_services/0/engine",
            "interpretation": "exact-identity",
            "identity": identity,
            "rationale": "Author must provide a concrete identity.",
        }
    ]
    with pytest.raises(ValueError):
        SDLSemanticMigrationContext.model_validate(payload)
    assert list(Draft202012Validator(schema_bundle()["sdl-semantic-migration-context-v1"]).iter_errors(payload))


@pytest.mark.parametrize("identity", ["POSTGRESQL", "x-owner:unknown", "x-owner:other"])
def test_exact_identity_accepts_concrete_native_and_private_values(identity):
    from jsonschema import Draft202012Validator
    from raes.semantic_migration import migrate_sdl_semantics
    from raes_contracts.contracts import schema_bundle

    source = "name: old\nnodes: {host: {type: compute, runtime: {database_services: [{database_service_id: db, engine: other}]}}}\n"
    author_context = context(
        source,
        [
            {
                "pointer": "/nodes/host/runtime/database_services/0/engine",
                "interpretation": "exact-identity",
                "identity": identity,
                "rationale": "Author identifies the engine.",
            }
        ],
    )
    Draft202012Validator(schema_bundle()["sdl-semantic-migration-context-v1"]).validate(
        author_context.model_dump(mode="json")
    )
    result = migrate_sdl_semantics(source, context=author_context)
    assert result.succeeded, result.report.diagnostics
    assert result.output.nodes["host"].runtime.database_services[0].engine == identity.lower()


def test_classification_migration_chains_with_exact_binding_retargeting():
    from raes import render_sdl_source
    from raes.classification_migration import migrate_sdl_classifications
    from raes.semantic_migration import migrate_sdl_semantics
    from raes.transformations import ArtifactTransformationPolicy
    from raes_contracts.contracts import ArtifactTransformationLossKind
    from test_classification_migration import LEGACY_SOURCE, _migration_inputs

    document, snapshot = _migration_inputs()
    classified = migrate_sdl_classifications(
        LEGACY_SOURCE,
        bindings=document,
        scheme_snapshots=(snapshot,),
        policy=ArtifactTransformationPolicy(allowed_loss_kinds=(ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
    )
    assert classified.succeeded
    intermediate = render_sdl_source(classified.output).content
    converted = migrate_sdl_semantics(
        intermediate,
        context=context(intermediate),
        binding_documents=classified.binding_documents,
        scheme_snapshots=(snapshot,),
    )
    assert converted.succeeded, converted.report.diagnostics
    binding = converted.binding_documents[0].bindings["attack-execution"]
    assert binding.subject.artifact_digest == canonical_sdl_digest(converted.output).value
    assert binding.provenance == classified.binding_documents[0].bindings["attack-execution"].provenance
    refused = migrate_sdl_semantics(
        intermediate, context=context(intermediate), binding_documents=classified.binding_documents
    )
    assert not refused.succeeded
    assert not refused.binding_documents
    assert refused.output is None
