"""Explicit revision selection precedes SDL interpretation and defaults."""

import hashlib

import pytest
from raes import SDLParseError


def digest(content):
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()


def test_unidentified_source_requires_revision_context():
    from raes.semantic_revisions import read_versioned_sdl

    with pytest.raises(SDLParseError, match="revision"):
        read_versioned_sdl("name: historical\n")


def test_legacy_revision_is_rejected_by_current_reader():
    from raes.semantic_revisions import LEGACY_SDL_REVISION, read_versioned_sdl

    source = "name: legacy\n"
    source_digest = digest(source)
    with pytest.raises(SDLParseError, match="revision"):
        read_versioned_sdl(source, semantic_revision=LEGACY_SDL_REVISION, source_digest=source_digest)


def test_explicit_current_context_requires_exact_source_binding():
    from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION, read_versioned_sdl

    source = "name: current\n"
    for source_digest in (None, "sha256:" + "0" * 64):
        with pytest.raises(SDLParseError, match="digest"):
            read_versioned_sdl(source, semantic_revision=PROGRESSIVE_SDL_REVISION, source_digest=source_digest)


def test_current_revision_is_carried_without_filling_abstract_infrastructure():
    from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION, read_versioned_sdl

    source = (
        f"semantic_revision: {PROGRESSIVE_SDL_REVISION}\n"
        "name: abstract\nrealization: {default: open}\nnodes: {host: {type: compute}}\n"
    )
    result = read_versioned_sdl(source)
    assert result.scenario.semantic_revision == PROGRESSIVE_SDL_REVISION
    assert result.scenario.nodes["host"].os is None
    assert result.scenario.nodes["host"].runtime is None
    assert "os" not in result.payload["nodes"]["host"]


@pytest.mark.parametrize("revision", ["future/v99", "", "sdl-yaml/v1"])
def test_unknown_revision_never_falls_back_to_current(revision):
    from raes.semantic_revisions import read_versioned_sdl

    source = "name: sample\n"
    source_digest = digest(source)
    with pytest.raises(SDLParseError, match="revision"):
        read_versioned_sdl(source, semantic_revision=revision, source_digest=source_digest)


@pytest.mark.parametrize("child_revision", [None, "raes-legacy-semantics/384e8b19", "future/v99"])
def test_tagged_import_graph_rejects_unidentified_or_mixed_revision(tmp_path, child_revision):
    from raes import parse_sdl_file
    from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION

    child = "name: child\nmodule: {id: example/child, version: 1.0.0}\n"
    if child_revision is not None:
        child += f"semantic_revision: {child_revision}\n"
    (tmp_path / "child.yaml").write_text(child)
    root = tmp_path / "root.yaml"
    root.write_text(
        f"semantic_revision: {PROGRESSIVE_SDL_REVISION}\nname: root\n"
        "imports: [{path: child.yaml, namespace: child}]\n"
    )
    with pytest.raises(SDLParseError, match="revision"):
        parse_sdl_file(root)


def test_revision_survives_composition_instantiation_and_canonical_snapshot(tmp_path):
    import json

    from raes import instantiate_scenario, parse_sdl_file
    from raes.canonical import InstantiatedScenarioSnapshot, canonical_instantiated_sdl_bytes
    from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION

    tag = f"semantic_revision: {PROGRESSIVE_SDL_REVISION}\n"
    (tmp_path / "child.yaml").write_text(
        tag + "name: child\nmodule: {id: example/child, version: 1.0.0, exports: {nodes: [host]}}\n"
        "realization: {default: open}\nnodes: {host: {type: compute, os: 'x-owner:abstract'}}\n"
    )
    root = tmp_path / "root.yaml"
    root.write_text(tag + "name: root\nimports: [{path: child.yaml, namespace: child}]\n")
    expanded = parse_sdl_file(root)
    assert expanded.semantic_revision == PROGRESSIVE_SDL_REVISION
    instantiated = instantiate_scenario(expanded)
    assert instantiated.semantic_revision == PROGRESSIVE_SDL_REVISION
    encoded = canonical_instantiated_sdl_bytes(instantiated)
    assert json.loads(encoded)["scenario"]["semantic_revision"] == PROGRESSIVE_SDL_REVISION
    restored = InstantiatedScenarioSnapshot.model_validate_json(encoded)
    assert canonical_instantiated_sdl_bytes(restored.scenario) == encoded


def test_untagged_import_root_cannot_erase_child_revision(tmp_path):
    from raes import parse_sdl_file
    from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION

    (tmp_path / "child.yaml").write_text(
        f"semantic_revision: {PROGRESSIVE_SDL_REVISION}\nname: child\nmodule: {{id: example/child, version: 1.0.0}}\n"
    )
    root = tmp_path / "root.yaml"
    root.write_text("name: root\nimports: [{path: child.yaml, namespace: child}]\n")
    with pytest.raises(SDLParseError, match="revision"):
        parse_sdl_file(root)


def test_invalid_revision_shape_is_not_an_editor_declaration():
    from raes.language_service import language_references

    result = language_references("name: invalid\nsemantic_revision: {host: {}}\n", "host")
    assert result["definitions"] == []


@pytest.mark.parametrize("tagged", [False, True])
def test_current_identity_cannot_reuse_pre_cutover_authoring_or_snapshot_profiles(tagged):
    import json

    import rfc8785
    from pydantic import ValidationError
    from raes import canonical_sdl_bytes, canonical_sdl_digest, instantiate_scenario, parse_sdl
    from raes.canonical import InstantiatedScenarioSnapshot, canonical_instantiated_sdl_bytes
    from raes.semantic_revisions import PROGRESSIVE_SDL_REVISION

    source = "name: identity\n"
    if tagged:
        source += f"semantic_revision: {PROGRESSIVE_SDL_REVISION}\n"
    scenario = parse_sdl(source)
    current = json.loads(canonical_sdl_bytes(scenario))
    assert current["profile"] == "raes-sdl-semantic/v2"
    old = dict(current, profile="raes-sdl-semantic/v1")
    assert canonical_sdl_digest(scenario).value != "sha256:" + hashlib.sha256(rfc8785.dumps(old)).hexdigest()
    instantiated = instantiate_scenario(scenario)
    assert instantiated.instantiation_provenance.authored_digest.profile == "raes-sdl-semantic/v2"
    snapshot = json.loads(canonical_instantiated_sdl_bytes(instantiated))
    assert snapshot["profile"] == "raes-sdl-instantiated-snapshot/v2"
    snapshot["profile"] = "raes-sdl-instantiated-snapshot/v1"
    with pytest.raises(ValidationError):
        InstantiatedScenarioSnapshot.model_validate(snapshot)


def _raise_defect(*_args, **_kwargs):
    raise ValueError("SECRET-DEFECT-DETAIL")


@pytest.mark.parametrize(
    ("module_name", "function_name", "patched_name", "refusal_code"),
    [
        (
            "raes.semantic_migration",
            "migrate_sdl_semantics",
            "load_sdl_yaml",
            "semantic-migration.source-or-target-invalid",
        ),
        (
            "raes.mixed_control_migration",
            "migrate_mixed_control_to_finite_script",
            "parse_sdl",
            "mixed-control-migration.source-or-target-invalid",
        ),
        (
            "raes.participant_migration",
            "migrate_participant_identity",
            "load_sdl_yaml",
            "participant-migration.source-or-target-invalid",
        ),
        (
            "raes.classification_migration",
            "migrate_sdl_classifications",
            "read_legacy_classification_source",
            "classification-migration.source-invalid",
        ),
    ],
)
def test_sdl_migrations_refuse_invalid_sources_but_do_not_hide_defects(
    monkeypatch, module_name, function_name, patched_name, refusal_code
):
    """An invalid source is a refusal; a built-in exception from a defect propagates (ADR-116 rule H5)."""
    import importlib

    module = importlib.import_module(module_name)
    migrate = getattr(module, function_name)

    refused = migrate("name: [\n")
    assert refused.output is None
    assert refusal_code in {diagnostic.code for diagnostic in refused.report.diagnostics}

    monkeypatch.setattr(module, patched_name, _raise_defect)
    with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
        migrate("name: source\n")


@pytest.mark.parametrize("operation", ["remove", "rename"])
def test_sdl_transformations_do_not_report_defects_as_refusals(monkeypatch, operation):
    from raes import parse_sdl
    from raes.transformations import (
        ArtifactTransformationPolicy,
        RemoveSDLDeclarationRequest,
        RenameSDLDeclarationRequest,
        remove_sdl_declaration,
        rename_sdl_declaration,
    )
    from raes_contracts.contracts import ArtifactTransformationLossKind

    scenario = parse_sdl("name: transform\nnodes:\n  web: {type: switch}\n  extra: {type: switch}\n")
    if operation == "remove":
        monkeypatch.setattr("raes._transformation_remove.SemanticValidator", _raise_defect)
        with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
            remove_sdl_declaration(
                scenario,
                RemoveSDLDeclarationRequest(target_address="nodes.extra"),
                policy=ArtifactTransformationPolicy((ArtifactTransformationLossKind.DECLARATION_REMOVED,)),
            )
    else:
        monkeypatch.setattr("raes._transformation_rename.SemanticValidator", _raise_defect)
        with pytest.raises(ValueError, match="SECRET-DEFECT-DETAIL"):
            rename_sdl_declaration(
                scenario,
                RenameSDLDeclarationRequest(target_address="nodes.web", new_local_name="frontend"),
            )
