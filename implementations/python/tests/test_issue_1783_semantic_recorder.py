"""The focused semantic oracle retains rule, source, and identity evidence."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    return importlib.import_module("tools.parity_authoring_vectors")


def vector(name: str) -> dict:
    from tools.parity_authoring_vectors import read_semantic_vectors

    return next(row for row in read_semantic_vectors() if row["name"] == name)


@pytest.mark.parametrize(
    "name",
    [
        "minimal",
        "advisory",
        "node-bindings",
        "descriptor-wrong-use",
        "execution-scope-missing",
        "collision-node-service",
        "workflow-predicate-impossible",
        "canonical-materialized",
        "materialized-portable-defaults-3853",
        "descriptor-portable-scalar-4097",
        "explicitness-enum-and-literal",
        "explicitness-atomic-child-variable",
        "explicitness-dns-exact-extension",
        "service-profile-constructor-default",
        "canonical-http-wire-methods",
        "condition-null-optional-integers",
    ],
)
def test_frozen_semantic_evidence_matches_reference(recorder, name: str) -> None:
    row = vector(name)
    assert json.loads(json.dumps(recorder.semantic([row]))) == [row]


def test_materialized_oracle_constructs_without_semantic_admission(recorder) -> None:
    from raes._errors import SDLValidationError
    from raes._source_profile import SDLParserLimits
    from raes.parser import parse_sdl
    from raes.validator import SemanticValidator

    row = vector("workflow-missing-start")
    document = recorder.semantic_input(row, SDLParserLimits())
    assert not document.semantic_validated
    validator = SemanticValidator(document)
    with pytest.raises(SDLValidationError):
        validator.validate()
    # The normal parser intentionally refuses this description even when its
    # caller requests construction only. The oracle does not alter that API.
    with pytest.raises(SDLValidationError):
        parse_sdl(row["source"], skip_semantic_validation=True)


def test_semantic_oracle_does_not_hide_operational_errors(recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_canonical(_document):
        raise RuntimeError("reference failure")

    monkeypatch.setattr(recorder, "canonical_sdl_bytes", broken_canonical)
    row = vector("minimal")
    with pytest.raises(RuntimeError, match="reference failure"):
        recorder.semantic([row])


def test_materialized_portable_limit_precedes_semantic_rules(recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_semantics(_self):
        raise RuntimeError("semantic rules must not run after portable refusal")

    monkeypatch.setattr(recorder.SemanticValidator, "validate", unexpected_semantics)
    result = recorder.semantic([vector("materialized-portable-defaults-3853")])[0]
    assert not result["accepted"]
    assert result["admission_error"] == "materialized SDL exceeds portable bounds"
    assert result["findings"] == result["advisories"] == []


def test_semantic_evidence_requires_unique_case_names(recorder) -> None:
    row = vector("minimal")
    with pytest.raises(ValueError, match="case names must be unique"):
        recorder.semantic([row] * 2)


@pytest.mark.parametrize(
    "name",
    ["finite-import-domains", "nested-finite-import-domains", "ordered-import-findings", "public-runtime-derivation"],
)
def test_frozen_import_identity_and_original_locations(recorder, name: str) -> None:
    path = ROOT / "implementations/go/internal/sdl/authoring/testdata/semantic-imports.json"
    row = next(row for row in json.loads(path.read_text()) if row["name"] == name)
    assert json.loads(json.dumps(recorder.semantic_imports([row]))) == [row]


def test_classified_runtime_domains_are_absent_from_import_identity() -> None:
    path = ROOT / "implementations/go/internal/sdl/authoring/testdata/semantic-imports.json"
    rows = json.loads(path.read_text())
    row = next(row for row in rows if row["name"] == "finite-import-domains")
    identity = json.loads(row["canonical"])
    assert all("secret" not in name for name in identity["module_variable_specs"])
    os_only = next(row for row in rows if row["name"] == "os-only-import-domain")
    assert json.loads(os_only["canonical"])["module_node_variable_refs"] == {
        "demo.web": {"os": "demo.__private.platform", "count": None}
    }


@pytest.mark.parametrize("name", ["minimal", "node-bindings", "canonical-materialized", "explicitness-variables"])
def test_corpus_oracle_preserves_owner_evidence_and_isolates_paths(recorder, monkeypatch, name: str) -> None:
    row = vector(name)
    arguments = {"sdl_content": row["source"], "semantic_validation": False}
    monkeypatch.setattr(recorder, "read_blob", lambda *_: json.dumps(arguments).encode())
    result = json.loads(
        json.dumps(recorder.corpus_semantic({"name": name, "files": {"arguments.json": "sha256:" + "a" * 64}}, ROOT))
    )
    assert result["constructed"]
    for key in ("accepted", "findings", "advisories", "locations", "canonical", "digest", "explicitness"):
        if key in row:
            assert result[key] == row[key]
    assert result["record_explicitness"]


def test_corpus_oracle_keeps_construction_refusal_separate(recorder, monkeypatch) -> None:
    monkeypatch.setattr(recorder, "read_blob", lambda *_: b'{"sdl_content":"[broken"}')
    result = recorder.corpus_semantic({"name": "broken", "files": {"arguments.json": "sha256:" + "a" * 64}}, ROOT)
    assert result["constructed"] is False
    assert result["construction_error"] == "SDLParseError"
    assert "accepted" not in result


@pytest.mark.parametrize("source", [None, [], {}, 42, True])
@pytest.mark.parametrize("migration", [False, ["invalid"]])
def test_corpus_oracle_retains_non_text_transport_refusals(recorder, monkeypatch, source, migration) -> None:
    arguments = {"sdl_content": source, "accept_migration_syntax": migration}
    monkeypatch.setattr(recorder, "read_blob", lambda *_: json.dumps(arguments).encode())

    def unexpected_semantic(_rows):
        pytest.fail("non-text transport input must not reach the SDL parser")

    monkeypatch.setattr(recorder, "semantic", unexpected_semantic)
    result = recorder.corpus_semantic({"name": "non-text", "files": {"arguments.json": "sha256:" + "a" * 64}}, ROOT)
    assert result == {
        "name": "non-text",
        "source": source,
        "constructed": False,
        "input_error": "non-text-source",
        "accept_migration": migration,
    }


def test_corpus_oracle_preserves_operational_failures(recorder, monkeypatch) -> None:
    monkeypatch.setattr(recorder, "read_blob", lambda *_: b'{"sdl_content":"name: example"}')

    def broken_semantic(_rows):
        raise RuntimeError("reference failure")

    monkeypatch.setattr(recorder, "semantic", broken_semantic)
    with pytest.raises(RuntimeError, match="reference failure"):
        recorder.corpus_semantic({"name": "broken", "files": {"arguments.json": "sha256:" + "a" * 64}}, ROOT)
